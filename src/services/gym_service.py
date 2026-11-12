import calendar
from datetime import date, datetime, time, timedelta

from repositories.gym_repository import GymRepository
from repositories.person_repository import PersonRepository


def calcular_fecha_vencimiento_un_mes(fecha_inicio: date) -> date:
    """Calcula la fecha de vencimiento exactamente a un mes calendario.
    Ejemplo: 20 de octubre vence el 20 de noviembre.
    Maneja con precisión los días 29, 30 y 31 en meses más cortos (ej. 31 de enero -> 28 o 29 de febrero).
    """
    anio = fecha_inicio.year
    mes = fecha_inicio.month + 1
    if mes > 12:
        mes = 1
        anio += 1

    dia = fecha_inicio.day
    dias_en_mes = calendar.monthrange(anio, mes)[1]
    dia_ajustado = min(dia, dias_en_mes)
    return date(anio, mes, dia_ajustado)


class GymService:
    """Lógica central de negocio para Zebra Gym Jujuy:
    - Control de horarios, feriados nacionales y provinciales.
    - Validación y control de acceso de socios (planes, cupos mensuales, regla diaria, vigencia).
    - Registro de entrada/salida y turnos rotativos de profesores con adaptabilidad a cambios.
    - Confirmación y descarte en base de datos.
    - Auditoría de rechazos.
    """

    def __init__(self, gym_repo=None, person_repo=None):
        self._gym_repo = gym_repo or GymRepository()
        self._person_repo = person_repo or PersonRepository()

    # --- Verificación de Estado del Gimnasio (Horarios y Feriados) ---
    def verificar_gimnasio_abierto(self, ahora=None):
        """Comprueba si el gimnasio está habilitado para recibir personas en el momento actual.
        Devuelve (abierto: bool, motivo: str).
        """
        momento = ahora or datetime.now()
        hoy = momento.date()
        hora_actual = momento.time()

        # 1. Verificar Feriados
        feriado = self._gym_repo.obtener_feriado(hoy)
        if feriado:
            _id, _fecha, descripcion, es_nacional, abre_gimnasio = feriado
            if not abre_gimnasio:
                tipo = "nacional" if es_nacional else "especial"
                return False, f"Gimnasio cerrado por feriado {tipo}: {descripcion}"

        # 2. Verificar Horario de Atención del día de la semana
        dia_semana = hoy.weekday()  # 0=Lunes ... 5=Sábado, 6=Domingo
        horario = self._gym_repo.obtener_horario_dia(dia_semana)
        if not horario:
            return True, "Horario habilitado"  # Si no hay configuración, por defecto permite

        _id, _dia, nombre_dia, abierto, apertura, cierre = horario
        if not abierto:
            return False, f"Gimnasio cerrado los días {nombre_dia}"

        if apertura and cierre:
            if not (apertura <= hora_actual <= cierre):
                h_ap = apertura.strftime("%H:%M")
                h_ci = cierre.strftime("%H:%M")
                return False, f"Fuera del horario de atención ({nombre_dia}: {h_ap} a {h_ci} hs)"

        return True, "Horario habilitado"

    # --- Evaluación de Acceso al Reconocer una Persona ---
    def evaluar_acceso(self, persona_id, ahora=None):
        """Evalúa a la persona identificada y devuelve un diccionario con el resultado.
        NO realiza escrituras en la base de datos hasta que se confirme en el modal.
        """
        momento = ahora or datetime.now()
        persona = self._person_repo.obtener_por_id(persona_id)
        if not persona:
            self._gym_repo.registrar_rechazo(persona_id, "desconocido", "Persona no encontrada en el sistema", ahora=momento)
            return {
                "permitido": False,
                "motivo": "Persona no registrada en el sistema",
                "tipo_persona": "desconocido",
            }

        _id, tipo, nombre, apellido, dni, correo, telefono, f_nac, f_alta, activo = persona
        nombre_completo = f"{apellido}, {nombre}"

        if not activo:
            motivo = "Persona registrada pero dada de baja / inactiva"
            self._gym_repo.registrar_rechazo(persona_id, tipo, motivo, ahora=momento)
            return {
                "permitido": False,
                "motivo": motivo,
                "tipo_persona": tipo,
                "nombre": nombre_completo,
                "dni": dni,
            }

        # Comprobar horario del gimnasio
        abierto, motivo_cierre = self.verificar_gimnasio_abierto(momento)
        if not abierto:
            self._gym_repo.registrar_rechazo(persona_id, tipo, motivo_cierre, ahora=momento)
            return {
                "permitido": False,
                "motivo": motivo_cierre,
                "tipo_persona": tipo,
                "nombre": nombre_completo,
                "dni": dni,
            }

        if tipo == "socio":
            return self._evaluar_socio(persona_id, nombre_completo, dni, momento)
        elif tipo == "profesor":
            return self._evaluar_profesor(persona_id, nombre_completo, dni, momento)

        return {
            "permitido": False,
            "motivo": f"Tipo de persona no reconocido: {tipo}",
            "tipo_persona": tipo,
        }

    # --- Lógica específica para Socios ---
    def _evaluar_socio(self, socio_id, nombre_completo, dni, momento):
        hoy = momento.date()
        membresia = self._gym_repo.obtener_membresia_activa(socio_id, hoy)

        if not membresia:
            motivo = "El socio no posee una membresía activa o se encuentra vencida"
            self._gym_repo.registrar_rechazo(socio_id, "socio", motivo, ahora=momento)
            return {
                "permitido": False,
                "motivo": motivo,
                "tipo_persona": "socio",
                "nombre": nombre_completo,
                "dni": dni,
            }

        (
            m_id, _s_id, plan_id, f_pago, f_inicio, f_vencimiento,
            cupos_totales, monto, estado,
            plan_codigo, plan_nombre, cupo_mensual, max_dia
        ) = membresia

        # 1. Regla de fecha de vigencia
        if hoy > f_vencimiento:
            motivo = f"Membresía vencida el {f_vencimiento.strftime('%d/%m/%Y')}"
            self._gym_repo.actualizar_estado_membresia(m_id, "vencida")
            self._gym_repo.registrar_rechazo(socio_id, "socio", motivo, ahora=momento)
            return {
                "permitido": False,
                "motivo": motivo,
                "tipo_persona": "socio",
                "nombre": nombre_completo,
                "dni": dni,
                "plan_nombre": plan_nombre,
            }

        if hoy < f_inicio:
            motivo = f"Membresía aún no vigente (inicia el {f_inicio.strftime('%d/%m/%Y')})"
            self._gym_repo.registrar_rechazo(socio_id, "socio", motivo, ahora=momento)
            return {
                "permitido": False,
                "motivo": motivo,
                "tipo_persona": "socio",
                "nombre": nombre_completo,
                "dni": dni,
                "plan_nombre": plan_nombre,
            }

        # 2. Regla de cupo mensual de entrenamientos (2x sem: 8, 3x sem: 12, 5x sem: 20)
        ingresos_usados = self._gym_repo.contar_ingresos_membresia(m_id)
        if cupo_mensual is not None and ingresos_usados >= cupo_mensual:
            motivo = f"Cupo agotado ({ingresos_usados}/{cupo_mensual} entrenamientos utilizados)"
            self._gym_repo.actualizar_estado_membresia(m_id, "agotada")
            self._gym_repo.registrar_rechazo(socio_id, "socio", motivo, ahora=momento)
            return {
                "permitido": False,
                "motivo": motivo,
                "tipo_persona": "socio",
                "nombre": nombre_completo,
                "dni": dni,
                "plan_nombre": plan_nombre,
            }

        # 3. Regla de ingreso diario (ej. 'todos_los_dias' o 'pase_diario')
        ingresos_hoy = self._gym_repo.contar_ingresos_hoy(socio_id, hoy)
        if max_dia is not None and ingresos_hoy >= max_dia:
            motivo = f"El plan '{plan_nombre}' admite {max_dia} ingreso diario y ya ingresó hoy"
            self._gym_repo.registrar_rechazo(socio_id, "socio", motivo, ahora=momento)
            return {
                "permitido": False,
                "motivo": motivo,
                "tipo_persona": "socio",
                "nombre": nombre_completo,
                "dni": dni,
                "plan_nombre": plan_nombre,
            }

        # Métricas informativas para el modal y la confirmación
        cupos_restantes = (cupo_mensual - ingresos_usados) if cupo_mensual is not None else None
        dias_restantes_vigencia = max(0, (f_vencimiento - hoy).days)
        entrenamientos_semana = self._gym_repo.contar_ingresos_semana_actual(socio_id, hoy)

        return {
            "permitido": True,
            "tipo_persona": "socio",
            "persona_id": socio_id,
            "nombre": nombre_completo,
            "dni": dni,
            "membresia_id": m_id,
            "plan_nombre": plan_nombre,
            "plan_codigo": plan_codigo,
            "fecha_pago": f_pago,
            "fecha_vencimiento": f_vencimiento,
            "dias_restantes_vigencia": dias_restantes_vigencia,
            "cupos_totales": cupo_mensual,
            "cupos_usados": ingresos_usados,
            "cupos_restantes": cupos_restantes,
            "entrenamientos_semana": entrenamientos_semana,
            "operacion": "REGISTRAR_INGRESO",
            "mensaje": f"Socio habilitado: {plan_nombre}. {dias_restantes_vigencia} días restantes de vigencia.",
        }

    # --- Lógica específica para Profesores ---
    def _evaluar_profesor(self, profesor_id, nombre_completo, dni, momento):
        hoy = momento.date()
        hora = momento.time()

        # Buscar turno programado (incluye turnos rotativos de sábados)
        turno = self._gym_repo.obtener_turno_profesor_hoy(profesor_id, hoy)
        turno_id = None
        info_turno = "Sin turno específico asignado (Horario flexible)"
        es_cambio_turno = False

        if turno:
            turno_id, _pid, _dia, f_esp, h_ini, h_fin, es_rot, obs = turno
            tipo_t = "Rotativo (Sábado)" if es_rot or f_esp else "Habitual"
            info_turno = f"Turno {tipo_t}: {h_ini.strftime('%H:%M')} a {h_fin.strftime('%H:%M')} hs"
            if not (h_ini <= hora <= h_fin):
                es_cambio_turno = True
                info_turno += " (Fuera del horario de turno programado)"
        else:
            es_cambio_turno = True

        # Verificar asistencia de hoy
        asistencia = self._gym_repo.obtener_asistencia_profesor_hoy(profesor_id, hoy)
        if not asistencia:
            return {
                "permitido": True,
                "tipo_persona": "profesor",
                "persona_id": profesor_id,
                "nombre": nombre_completo,
                "dni": dni,
                "turno_id": turno_id,
                "info_turno": info_turno,
                "es_cambio_turno": es_cambio_turno,
                "operacion": "REGISTRAR_ENTRADA",
                "mensaje": f"Profesor identificado. Proponer registro de ENTRADA. {info_turno}",
            }

        _asist_id, _pid, _tid, entrada, salida, _cambio, _obs = asistencia
        if salida is None:
            # Ya registró entrada, corresponde registrar salida
            return {
                "permitido": True,
                "tipo_persona": "profesor",
                "persona_id": profesor_id,
                "nombre": nombre_completo,
                "dni": dni,
                "asistencia_id": _asist_id,
                "turno_id": turno_id,
                "info_turno": info_turno,
                "entrada": entrada,
                "operacion": "REGISTRAR_SALIDA",
                "mensaje": f"Profesor identificado. Proponer registro de SALIDA (Entrada: {entrada.strftime('%H:%M')}).",
            }

        # Entrada y salida ya registradas hoy
        return {
            "permitido": False,
            "motivo": f"Jornada ya completada hoy (Entrada: {entrada.strftime('%H:%M')} - Salida: {salida.strftime('%H:%M')})",
            "tipo_persona": "profesor",
            "nombre": nombre_completo,
            "dni": dni,
        }

    # --- Persistencia tras Confirmación (Acción OK del Modal) ---
    def confirmar_ingreso_socio(self, socio_id, membresia_id, ahora=None):
        """Registra el ingreso del socio tras confirmación con botón OK."""
        momento = ahora or datetime.now()
        ingreso_id = self._gym_repo.registrar_ingreso(socio_id, membresia_id, momento)
        return ingreso_id

    def confirmar_asistencia_profesor(self, profesor_id, operacion, asistencia_id=None, turno_id=None,
                                      es_cambio_turno=False, observaciones=None, ahora=None):
        """Registra la entrada o salida del profesor tras confirmación con botón OK."""
        momento = ahora or datetime.now()
        if operacion == "REGISTRAR_ENTRADA":
            return self._gym_repo.registrar_entrada_profesor(
                profesor_id, turno_id, momento, es_cambio_turno, observaciones
            )
        elif operacion == "REGISTRAR_SALIDA":
            if asistencia_id:
                return self._gym_repo.registrar_salida_profesor(asistencia_id, momento)
            else:
                # Buscar la última asistencia sin salida
                asist = self._gym_repo.obtener_asistencia_profesor_hoy(profesor_id, momento.date())
                if asist and asist[4] is None:
                    return self._gym_repo.registrar_salida_profesor(asist[0], momento)
        return False
