"""Ingreso por reconocimiento facial en ZebraGym.

Flujo (consigna 41, contexto B, puntos 4 y 6):
  1. evaluar(persona_id): con la persona ya identificada por el rostro,
     consulta sus roles, la membresía (v_socio_estado), los límites y el
     horario. Si puede entrar como socio ("Entrenar") o fichar como empleado
     ("Fichar"), devuelve una PROPUESTA para el modal y NO escribe nada.
     Si no puede, registra el rechazo en acceso con su motivo.
  2. confirmar(evaluacion, opcion): botón OK del modal. En una transacción
     bloquea al socio (o la entrada abierta del empleado), vuelve a evaluar
     las reglas y recién entonces registra el acceso o el fichaje.
  3. Cancelar no llama a este servicio: no se escribe nada.

Además: GestorPropuestas (una propuesta por vez, con token que solo se puede
usar una vez), Antirrebote (10 s por persona tras cualquier decisión) y
ContadorNoReconocidos (no_reconocido se registra recién al tercer intento
seguido sin reconocer)."""
import secrets
import time
from dataclasses import asdict, dataclass, field

import psycopg

from config.database import usar_conexion
from services import reglas_ingreso as reglas
from services.reglas_ingreso import Franja, Jornada, fecha_texto, hora_texto, pesos

ENTRENAR = "entrenar"
FICHAR = "fichar"

PROPUESTA = "PROPUESTA"     # hay al menos una opción: se abre el modal
RECHAZADO = "RECHAZADO"     # quedó registrado en acceso con su motivo
AVISO = "AVISO"             # nada para hacer (p. ej., entrada recién fichada); no se registra

ANTIRREBOTE_S = 10.0
INTENTOS_NO_RECONOCIDO = 3
VIGENCIA_PROPUESTA_S = 65.0          # el modal se cancela solo a los 60 s
ROLES_QUE_FICHAN = {"entrenador", "recepcionista"}

# Qué modal se abre según quién es la persona reconocida
MODO_SOCIO = "socio"          # solo valida su identidad para entrar
MODO_EMPLEADO = "empleado"    # asistencia laboral
MODO_AMBOS = "ambos"          # socio y empleado: elige Trabajar o Entrenar

SITUACION_MEMBRESIA = {"vigente": "Vigente", "por_vencer": "Vigente", "vencida": "Vencida",
                       "sin_membresia": "Sin membresía", "no_vigente": "Todavía no vigente",
                       "agotada": "Cupo agotado"}


def dni_texto(dni):
    """'30111222' -> '30.111.222'."""
    try:
        return f"{int(dni):,}".replace(",", ".")
    except (TypeError, ValueError):
        return dni or ""


@dataclass(frozen=True)
class Opcion:
    clave: str               # ENTRENAR o FICHAR
    boton: str               # texto corto del botón: Entrar, Llegué, Me voy, Trabajar, Entrenar
    habilitada: bool = True
    motivo: object = None    # por qué está deshabilitada


@dataclass
class Evaluacion:
    estado: str
    mensaje: str
    persona_id: object = None
    nombre: str = ""
    dni: str = ""
    rol_texto: str = ""
    motivo: object = None
    modo: object = None           # MODO_SOCIO, MODO_EMPLEADO o MODO_AMBOS (solo en PROPUESTA)
    opciones: tuple = ()
    sugerida: object = None       # clave de la opción más probable (botón dorado)
    advertencias: tuple = ()
    tarjetas: tuple = ()          # ((titulo, valor, tono), ...) para el modal
    lineas: tuple = ()            # ((texto, tono), ...) una por condición (MODO_AMBOS)
    socio_id: object = None
    membresia_id: object = None
    usuario_id: object = None
    distancia: object = None

    def a_dict(self):
        datos = asdict(self)
        datos["opciones"] = [asdict(o) for o in self.opciones]
        datos["advertencias"] = list(self.advertencias)
        datos["tarjetas"] = [list(t) for t in self.tarjetas]
        datos["lineas"] = [list(t) for t in self.lineas]
        if datos["distancia"] is not None:
            datos["distancia"] = float(datos["distancia"])
        return datos


@dataclass(frozen=True)
class Confirmacion:
    registrado: bool
    mensaje: str
    tono: str                     # verde, rojo o ambar
    motivo: object = None
    momento: object = None


def texto_semana(dias, maximo):
    """'2 de 3 días' si el plan tiene límite semanal; si no, '2 días' (o '1 día')."""
    if maximo:
        return f"{dias} de {maximo} días"
    return "1 día" if dias == 1 else f"{dias} días"


def tarjetas_socio(estado):
    """Plan / Esta semana / Vence / Estado contable."""
    restantes = estado["dias_para_vencer"]
    cuando = "mañana" if restantes == 1 else f"en {restantes} días"
    vence = f"{estado['fecha_vencimiento'].strftime('%d/%m')} · {cuando}"
    saldo = estado.get("saldo") or 0
    if saldo > 0:
        contable = (f"Debe {pesos(saldo)}", "rojo")
    elif estado.get("estado_contable") == "por_vencer":
        contable = ("Por vencer", "ambar")
    else:
        contable = ("Al día", "verde")
    semana = texto_semana(estado["dias_entrenados_semana"], estado["max_dias_semanales"])
    return (("Plan", estado["plan"], None), ("Esta semana", semana, None), ("Vence", vence, None),
            ("Estado contable", contable[0], contable[1]))


def tono_laboral(estado):
    if estado == "En horario":
        return "verde"
    if estado.startswith("Llegaste") or estado == "Fuera de turno":
        return "ambar"
    return None


def tarjetas_empleado(rol, fichaje, ahora):
    """Rol / Turno de hoy / Hora / Estado (asistencia laboral)."""
    return (("Rol", rol, None), ("Turno de hoy", fichaje.turno or "Sin turno hoy", None),
            ("Hora", hora_texto(ahora), None),
            ("Estado", fichaje.estado, tono_laboral(fichaje.estado)))


def linea_empleado(fichaje):
    """'Empleado · Turno 14:00–22:00 · En horario' o 'Empleado · Sin turno hoy'."""
    partes = ["Empleado", f"Turno {fichaje.turno}" if fichaje.turno else "Sin turno hoy"]
    if fichaje.turno or fichaje.estado != "Fuera de turno":
        partes.append(fichaje.estado)
    return " · ".join(partes), tono_laboral(fichaje.estado) or "neutro"


def linea_socio(estado):
    """'Socio · Pase libre · Vigente (vence 05/12)', 'Socio · Vencida', 'Socio · Sin membresía'."""
    situacion = (estado or {}).get("estado_membresia") or "sin_membresia"
    texto = SITUACION_MEMBRESIA.get(situacion, "Sin membresía")
    if texto == "Vigente":
        texto = f"Vigente (vence {estado['fecha_vencimiento'].strftime('%d/%m')})"
    partes = ["Socio"]
    if situacion != "sin_membresia" and estado.get("plan"):
        partes.append(estado["plan"])
    partes.append(texto)
    return " · ".join(partes), "verde" if texto.startswith("Vigente") else "rojo"


def _rol_empleado(roles):
    return "Entrenador" if "entrenador" in roles else "Recepcionista"


def _sin_repetir_tarjetas(advertencias):
    """El vencimiento y la deuda ya están en las tarjetas del modal."""
    return tuple(a for a in advertencias if not a.startswith(("Debe", "Vence")))


def _rol_texto(es_socio, es_empleado, roles):
    partes = []
    if es_socio:
        partes.append("Socio")
    if es_empleado:
        partes.append(_rol_empleado(roles))
    return " y ".join(partes) if len(partes) < 2 else f"{partes[0]} y {partes[1].lower()}"


class AccesoService:
    def __init__(self, personas=None, socios=None, accesos=None, horario=None, fichajes=None,
                 transaccion=usar_conexion, reloj=None):
        from repositories.acceso_repository import AccesoRepository
        from repositories.fichaje_repository import FichajeRepository
        from repositories.horario_repository import HorarioRepository
        from repositories.person_repository import PersonRepository
        from repositories.socio_repository import SocioRepository
        self._personas = personas or PersonRepository()
        self._socios = socios or SocioRepository()
        self._accesos = accesos or AccesoRepository()
        self._horario = horario or HorarioRepository()
        self._fichajes = fichajes or FichajeRepository()
        self._transaccion = transaccion
        self._reloj = reloj           # para pruebas: f(conn) -> datetime

    def _ahora(self, conn):
        return self._reloj(conn) if self._reloj else self._horario.ahora(conn=conn)

    def _franjas_hoy(self, ahora, conn):
        return [Franja(a, c) for a, c in self._horario.franjas_del_dia(ahora.isoweekday(), conn=conn)]

    def _jornadas_hoy(self, usuario_id, ahora, conn):
        return [Jornada(*fila) for fila in self._fichajes.jornadas_del_dia(usuario_id, ahora.date(),
                                                                          conn=conn)]

    # --- Evaluación (sin escrituras salvo el rechazo) ---

    def evaluar(self, persona_id, distancia=None):
        with self._transaccion() as conn:
            ahora = self._ahora(conn)
            persona = self._personas.obtener_por_id(persona_id, conn=conn)
            if persona is None:
                # El rostro corresponde a una referencia que ya no existe.
                self._accesos.registrar_rechazo(reglas.NO_RECONOCIDO, distancia_facial=distancia,
                                                conn=conn)
                return Evaluacion(RECHAZADO, "Rostro no registrado en ZebraGym.",
                                  motivo=reglas.NO_RECONOCIDO, distancia=distancia)

            _pid, dni, nombre, apellido = persona[:4]
            roles = self._personas.obtener_roles(persona_id, conn=conn)
            base = dict(persona_id=persona_id, nombre=f"{nombre} {apellido}", dni=dni_texto(dni),
                        distancia=distancia, socio_id=roles["socio_id"])

            decision, estado = self._evaluar_socio(roles, ahora, conn)
            fichaje, usuario_id = self._evaluar_fichaje(roles, ahora, conn)
            base["usuario_id"] = usuario_id
            base["rol_texto"] = _rol_texto(decision is not None, fichaje is not None,
                                           set(roles["roles"]))

            propuesta = self._propuesta(decision, estado, fichaje, set(roles["roles"]), ahora, base)
            if propuesta is not None:
                return propuesta

            if decision is not None:
                self._accesos.registrar_rechazo(decision.motivo, roles["socio_id"],
                                                decision.membresia_id, distancia, conn=conn)
                return Evaluacion(RECHAZADO, decision.mensaje, motivo=decision.motivo,
                                  membresia_id=decision.membresia_id, **base)
            if fichaje is not None:
                return Evaluacion(AVISO, fichaje.mensaje, **base)
            self._accesos.registrar_rechazo(reglas.NO_ES_SOCIO, distancia_facial=distancia, conn=conn)
            return Evaluacion(RECHAZADO, "No figura como socio de ZebraGym.",
                              motivo=reglas.NO_ES_SOCIO, **base)

    @staticmethod
    def _propuesta(decision, estado, fichaje, roles, ahora, base):
        """La PROPUESTA para el modal según quién es la persona, o None si no
        tiene ninguna opción habilitada (entonces se rechaza o se avisa)."""
        puede_entrenar = decision is not None and decision.permitido
        puede_fichar = fichaje is not None and fichaje.permitido
        socio_activo = decision is not None and decision.motivo != reglas.SOCIO_INACTIVO
        membresia_id = decision.membresia_id if decision else None
        # Licencia o permiso aprobado: no se ofrece marcar la llegada (solo Entrenar, si es socio).
        con_ausencia = fichaje is not None and fichaje.ausencia is not None

        if socio_activo and fichaje is not None and not con_ausencia and (puede_entrenar or puede_fichar):
            trabajar = Opcion(FICHAR, "Me voy" if fichaje.operacion == reglas.SALIDA else "Trabajar",
                              puede_fichar, None if puede_fichar else fichaje.mensaje)
            entrenar = Opcion(ENTRENAR, "Entrenar", puede_entrenar,
                              None if puede_entrenar else decision.mensaje)
            # Dorado: Trabajar si está en su turno, a menos de 30 min o con la llegada marcada.
            sugerida = FICHAR if puede_fichar and (fichaje.en_turno or not puede_entrenar) else ENTRENAR
            avisos = (_sin_repetir_tarjetas(decision.advertencias) if puede_entrenar else ()) + \
                (fichaje.advertencias if puede_fichar else ())
            return Evaluacion(PROPUESTA, "¿Qué vas a hacer?", modo=MODO_AMBOS,
                              opciones=(trabajar, entrenar), sugerida=sugerida, advertencias=avisos,
                              lineas=(linea_empleado(fichaje), linea_socio(estado)),
                              membresia_id=membresia_id, **base)
        if puede_entrenar and (fichaje is None or con_ausencia):
            avisos = _sin_repetir_tarjetas(decision.advertencias) + ((fichaje.mensaje,) if con_ausencia else ())
            return Evaluacion(PROPUESTA, "¿Confirmás tu entrada al gimnasio?", modo=MODO_SOCIO,
                              opciones=(Opcion(ENTRENAR, "Entrar"),), sugerida=ENTRENAR,
                              advertencias=avisos,
                              tarjetas=tarjetas_socio(estado), membresia_id=membresia_id, **base)
        if puede_fichar:
            boton = "Me voy" if fichaje.operacion == reglas.SALIDA else "Llegué"
            return Evaluacion(PROPUESTA, "Asistencia laboral", modo=MODO_EMPLEADO,
                              opciones=(Opcion(FICHAR, boton),), sugerida=FICHAR,
                              advertencias=fichaje.advertencias,
                              tarjetas=tarjetas_empleado(_rol_empleado(roles), fichaje, ahora),
                              **base)
        return None

    def _evaluar_socio(self, roles, ahora, conn):
        """(DecisionSocio, fila de v_socio_estado) o (None, None) si no es socio."""
        if roles["socio_id"] is None:
            return None, None
        estado = self._socios.obtener_estado(roles["socio_id"], conn=conn)
        decision = reglas.evaluar_socio({"activo": roles["socio_activo"]}, estado,
                                        self._franjas_hoy(ahora, conn), ahora)
        return decision, estado

    def _evaluar_fichaje(self, roles, ahora, conn):
        """(PropuestaFichaje, usuario_id) o (None, None) si no es un empleado que ficha."""
        usuario_id = roles["usuario_id"]
        if usuario_id is None or not roles["usuario_activo"] or not (set(roles["roles"]) & ROLES_QUE_FICHAN):
            return None, None
        abierto = self._fichajes.fichaje_abierto(usuario_id, conn=conn)
        propuesta = reglas.evaluar_fichaje(abierto, self._jornadas_hoy(usuario_id, ahora, conn), ahora)
        return propuesta, usuario_id

    def registrar_no_reconocido(self, distancia=None):
        with self._transaccion() as conn:
            self._accesos.registrar_rechazo(reglas.NO_RECONOCIDO, distancia_facial=distancia, conn=conn)

    # --- Confirmación (botón OK del modal) ---

    def confirmar(self, evaluacion, clave):
        if evaluacion.estado != PROPUESTA or clave not in {o.clave for o in evaluacion.opciones if o.habilitada}:
            raise ValueError(f"La opción {clave!r} no estaba propuesta.")
        try:
            with self._transaccion() as conn:
                ahora = self._ahora(conn)
                if clave == ENTRENAR:
                    return self._confirmar_ingreso(evaluacion, ahora, conn)
                return self._confirmar_fichaje(evaluacion, ahora, conn)
        except psycopg.errors.UniqueViolation:
            # Otra confirmación registró la entrada al mismo tiempo.
            return Confirmacion(False, "La llegada ya estaba marcada.", "ambar")

    def _confirmar_ingreso(self, ev, ahora, conn):
        fila = self._socios.obtener_por_id(ev.socio_id, bloquear=True, conn=conn)
        socio = {"activo": fila[5]} if fila else None
        estado = self._socios.obtener_estado(ev.socio_id, conn=conn)
        decision = reglas.evaluar_socio(socio, estado, self._franjas_hoy(ahora, conn), ahora)
        if not decision.permitido:
            self._accesos.registrar_rechazo(decision.motivo, ev.socio_id, decision.membresia_id,
                                            ev.distancia, conn=conn)
            return Confirmacion(False, decision.mensaje, "rojo", decision.motivo)
        _id, momento = self._accesos.registrar_permitido(ev.socio_id, decision.membresia_id,
                                                         ev.distancia, conn=conn)
        return Confirmacion(True, f"¡Listo, {ev.nombre.split()[0]}! Buen entrenamiento.", "verde",
                            momento=momento)

    def _confirmar_fichaje(self, ev, ahora, conn):
        abierto = self._fichajes.fichaje_abierto(ev.usuario_id, bloquear=True, conn=conn)
        propuesta = reglas.evaluar_fichaje(abierto, self._jornadas_hoy(ev.usuario_id, ahora, conn), ahora)
        if not propuesta.permitido:
            return Confirmacion(False, propuesta.mensaje, "ambar")
        if propuesta.operacion == reglas.ENTRADA:
            _id, momento = self._fichajes.registrar_entrada(ev.usuario_id, propuesta.jornada_id, conn=conn)
            # Sin jornada_id queda como "Fuera de turno" (se ve en Fichajes del personal).
            return Confirmacion(True, f"Llegada marcada a las {hora_texto(momento)}.", "verde",
                                momento=momento)
        momento = self._fichajes.registrar_salida(propuesta.fichaje_id, conn=conn)
        if momento is None:
            return Confirmacion(False, "La salida ya estaba marcada.", "ambar")
        return Confirmacion(True, f"Salida marcada a las {hora_texto(momento)}.", "verde",
                            momento=momento)


class GestorPropuestas:
    """Una sola propuesta pendiente por vez (la del modal abierto). El token
    se usa una sola vez: un doble OK no registra dos veces."""

    def __init__(self, vigencia_s=VIGENCIA_PROPUESTA_S, reloj=time.monotonic):
        self._vigencia = vigencia_s
        self._reloj = reloj
        self._token = None
        self._evaluacion = None
        self._creada = 0.0

    def crear(self, evaluacion):
        self._token = secrets.token_hex(8)
        self._evaluacion = evaluacion
        self._creada = self._reloj()
        return self._token

    def tomar(self, token):
        """La evaluación del token (y la consume), o None si no coincide o venció."""
        if token is None or token != self._token:
            return None
        vigente = self._reloj() - self._creada <= self._vigencia
        evaluacion = self._evaluacion
        self.descartar(token)
        return evaluacion if vigente else None

    def descartar(self, token):
        if token is not None and token == self._token:
            self._token, self._evaluacion = None, None
            return True
        return False

    def pendiente(self):
        return self._token is not None and self._reloj() - self._creada <= self._vigencia


@dataclass
class Antirrebote:
    """Después de cualquier decisión (OK, Cancelar o rechazo) se ignora a esa
    misma persona durante unos segundos."""
    segundos: float = ANTIRREBOTE_S
    reloj: object = time.monotonic
    _hasta: dict = field(default_factory=dict)

    def registrar(self, clave):
        self._hasta[clave] = self.reloj() + self.segundos

    def bloqueado(self, clave):
        return self.restante(clave) > 0

    def restante(self, clave):
        """Segundos que faltan para volver a atender a esa persona (0 si ya puede)."""
        hasta = self._hasta.get(clave)
        if hasta is None:
            return 0.0
        falta = hasta - self.reloj()
        if falta <= 0:
            del self._hasta[clave]
            return 0.0
        return falta


@dataclass
class ContadorNoReconocidos:
    """no_reconocido se registra recién al alcanzar N intentos seguidos sin
    reconocer; reconocer a alguien reinicia la cuenta."""
    intentos: int = INTENTOS_NO_RECONOCIDO
    _seguidos: int = 0

    def fallo(self):
        """Cuenta un intento sin reconocer. Devuelve True cuando hay que registrarlo."""
        self._seguidos += 1
        if self._seguidos >= self.intentos:
            self._seguidos = 0
            return True
        return False

    def reiniciar(self):
        self._seguidos = 0
