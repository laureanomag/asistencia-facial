"""Reglas de ingreso de ZebraGym como funciones puras.

No acceden a la base ni leen el reloj: reciben los datos ya consultados
(socio, fila de v_socio_estado, franjas de horario_atencion, jornadas y
fichaje abierto) y el momento actual en hora de Argentina. Así cada regla
se prueba caso por caso y la misma evaluación se repite al confirmar (OK).

Orden de evaluación del socio (el primer motivo que aplica es el que se informa):
  1. no_es_socio        la persona reconocida no tiene ficha de socio
  2. socio_inactivo     el socio está dado de baja
  3. gimnasio_cerrado   fuera de las franjas de horario_atencion de hoy
  4. sin_membresia / membresia_vencida / membresia_no_vigente / cupo_agotado
                        según v_socio_estado.estado_membresia
  5. limite_diario      accesos_hoy >= max_ingresos_diarios
  6. limite_semanal     ya entrenó max_dias_semanales días distintos esta semana
                        y hoy todavía no ingresó (un segundo ingreso el mismo día
                        no suma otro día)
El fichaje de empleados no depende del horario de atención.
"""
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from decimal import Decimal

NO_RECONOCIDO = "no_reconocido"
NO_ES_SOCIO = "no_es_socio"
SOCIO_INACTIVO = "socio_inactivo"
SIN_MEMBRESIA = "sin_membresia"
MEMBRESIA_VENCIDA = "membresia_vencida"
MEMBRESIA_NO_VIGENTE = "membresia_no_vigente"
CUPO_AGOTADO = "cupo_agotado"
LIMITE_DIARIO = "limite_diario"
LIMITE_SEMANAL = "limite_semanal"
GIMNASIO_CERRADO = "gimnasio_cerrado"

# Etiqueta corta de cada motivo para la interfaz (chips e historial de ingresos).
ETIQUETAS_MOTIVO = {
    NO_RECONOCIDO: "No reconocido",
    NO_ES_SOCIO: "No es socio",
    SOCIO_INACTIVO: "Socio dado de baja",
    SIN_MEMBRESIA: "Sin membresía",
    MEMBRESIA_VENCIDA: "Membresía vencida",
    MEMBRESIA_NO_VIGENTE: "Todavía no vigente",
    CUPO_AGOTADO: "Cupo agotado",
    LIMITE_DIARIO: "Ya ingresó hoy",
    LIMITE_SEMANAL: "Límite semanal",
    GIMNASIO_CERRADO: "Gimnasio cerrado",
}

ENTRADA = "ENTRADA"
SALIDA = "SALIDA"

# Tiempo mínimo entre la entrada y la salida de un fichaje, para que el
# reconocimiento siguiente no proponga cerrar una entrada recién registrada.
ESPERA_MINIMA_SALIDA = timedelta(minutes=10)

# Licencia o permiso de día completo: la jornada ocupa todo el día.
DIA_COMPLETO = (time(0, 0), time(23, 59))

# Llegar hasta 30 min antes del inicio del turno cuenta como "En horario".
ANTICIPO_TURNO = timedelta(minutes=30)

DIAS_AVISO_VENCIMIENTO = 5
ESTADOS_JORNADA = {"licencia_vacaciones": "licencia o vacaciones", "permiso": "permiso"}


@dataclass(frozen=True)
class Franja:
    apertura: object   # datetime.time
    cierre: object     # datetime.time; la franja incluye la apertura y excluye el cierre


@dataclass(frozen=True)
class DecisionSocio:
    permitido: bool
    motivo: object          # código de motivo_rechazo, o None si está permitido
    mensaje: str
    membresia_id: object = None
    advertencias: tuple = ()


@dataclass(frozen=True)
class Jornada:
    id: int
    horario_entrada: object
    horario_salida: object
    estado: str


@dataclass(frozen=True)
class PropuestaFichaje:
    permitido: bool
    operacion: object       # ENTRADA, SALIDA o None si todavía no puede fichar
    mensaje: str
    jornada_id: object = None
    fichaje_id: object = None
    advertencias: tuple = ()
    turno: object = None    # "14:00–22:00" (turnos de hoy) o None = sin turno hoy
    estado: str = ""        # "En horario", "Llegaste N min tarde", "Fuera de turno", "Trabajaste ..."
    en_turno: bool = False  # en su turno, a menos de ANTICIPO_TURNO del inicio o con la llegada marcada
    ausencia: object = None  # "Licencia" o "Permiso" si hoy no corresponde marcar llegada


# --- Formatos ---

def fecha_texto(valor):
    return valor.strftime("%d/%m/%Y")


def hora_texto(valor):
    return valor.strftime("%H:%M")


def pesos(monto):
    """12500.5 -> '$12.500,50' (formato argentino)."""
    texto = f"{Decimal(monto):,.2f}"
    return "$" + texto.replace(",", "X").replace(".", ",").replace("X", ".")


# --- Horario de atención ---

def franja_actual(franjas, hora):
    """La franja de hoy que contiene la hora, o None si el gimnasio está cerrado."""
    for franja in franjas:
        if franja.apertura <= hora < franja.cierre:
            return franja
    return None


def texto_horario(franjas):
    if not franjas:
        return "cerrado"
    partes = [f"{hora_texto(f.apertura)} a {hora_texto(f.cierre)}"
              for f in sorted(franjas, key=lambda f: f.apertura)]
    return " y ".join(partes)


def mensaje_cerrado(franjas):
    if not franjas:
        return "Hoy el gimnasio está cerrado."
    return f"El gimnasio está cerrado. Horario de hoy: {texto_horario(franjas)} hs."


# --- Socios ---

def _rechazo(motivo, mensaje, membresia_id=None):
    return DecisionSocio(False, motivo, mensaje, membresia_id)


def evaluar_socio(socio, estado, franjas_hoy, ahora):
    """socio: None (la persona no es socio) o dict con 'activo'.
    estado: dict con las columnas de v_socio_estado (None si el socio no
    figura en la vista, por ejemplo por estar dado de baja).
    franjas_hoy: franjas de horario_atencion del día de `ahora`.
    ahora: datetime en hora de Argentina."""
    if socio is None:
        return _rechazo(NO_ES_SOCIO, "No figura como socio de ZebraGym.")
    if not socio["activo"]:
        return _rechazo(SOCIO_INACTIVO, "El socio está dado de baja. Consultá en el mostrador.")
    if franja_actual(franjas_hoy, ahora.time()) is None:
        return _rechazo(GIMNASIO_CERRADO, mensaje_cerrado(franjas_hoy))

    if estado is None or estado["estado_membresia"] == "sin_membresia":
        return _rechazo(SIN_MEMBRESIA,
                        "No tiene una membresía. Pasá por el mostrador para contratar un plan.")
    membresia_id = estado["membresia_id"]
    situacion = estado["estado_membresia"]
    if situacion == "vencida":
        return _rechazo(MEMBRESIA_VENCIDA,
                        f"Su membresía venció el {fecha_texto(estado['fecha_vencimiento'])}. "
                        "Renovala en el mostrador.", membresia_id)
    if situacion == "no_vigente":
        return _rechazo(MEMBRESIA_NO_VIGENTE,
                        f"Su membresía empieza el {fecha_texto(estado['fecha_inicio'])}.",
                        membresia_id)
    if situacion == "agotada":
        return _rechazo(CUPO_AGOTADO,
                        f"Ya usó los {estado['accesos_incluidos']} accesos de su plan.", membresia_id)

    accesos_hoy = estado["accesos_hoy"]
    max_diarios = estado["max_ingresos_diarios"]
    if max_diarios is not None and accesos_hoy >= max_diarios:
        ingresos = "1 ingreso" if max_diarios == 1 else f"{max_diarios} ingresos"
        return _rechazo(LIMITE_DIARIO,
                        f"Su plan permite {ingresos} por día y hoy ya lo usó.", membresia_id)

    max_semanales = estado["max_dias_semanales"]
    dias_semana = estado["dias_entrenados_semana"]
    if max_semanales is not None and accesos_hoy == 0 and dias_semana >= max_semanales:
        return _rechazo(LIMITE_SEMANAL,
                        f"Ya entrenó {dias_semana} días esta semana: es el límite del plan "
                        f"{estado['plan']}. Puede volver el lunes.", membresia_id)

    return DecisionSocio(True, None, _mensaje_bienvenida(estado), membresia_id,
                         _advertencias_socio(estado))


def _mensaje_bienvenida(estado):
    return (f"Bienvenido/a a ZebraGym. Plan {estado['plan']}, "
            f"vence el {fecha_texto(estado['fecha_vencimiento'])}.")


def _advertencias_socio(estado):
    avisos = []
    saldo = estado.get("saldo")
    if saldo is not None and saldo > 0:
        avisos.append(f"Debe {pesos(saldo)}")
    dias = estado.get("dias_para_vencer")
    if dias is not None and dias <= DIAS_AVISO_VENCIMIENTO:
        avisos.append("Vence mañana" if dias == 1 else f"Vence en {dias} días")
    restantes = estado.get("accesos_restantes")
    if restantes is not None:
        luego = restantes - 1
        avisos.append("Es su último acceso del plan" if luego == 0
                      else f"Le quedan {luego} accesos después de este")
    return tuple(avisos)


# --- Fichaje de empleados ---

def texto_turnos(jornadas_hoy):
    """'14:00–22:00' (o varios unidos con ' y '), o None si hoy no tiene turno."""
    turnos = [f"{hora_texto(j.horario_entrada)}–{hora_texto(j.horario_salida)}"
              for j in jornadas_hoy if j.estado == "jornada"]
    return " y ".join(turnos) or None


def texto_trabajado(desde, hasta):
    """'Trabajaste 3 h 05 min'."""
    minutos = max(0, int((hasta - desde).total_seconds() // 60))
    return f"Trabajaste {minutos // 60} h {minutos % 60:02d} min"


def es_dia_completo(entrada, salida):
    return entrada == DIA_COMPLETO[0] and salida >= DIA_COMPLETO[1]


def bloqueo_llegada(jornadas_hoy, ahora):
    """(ausencia, mensaje) si hoy no corresponde marcar la llegada, o None.
    Licencia: todo el día. Permiso: mientras cubra la hora actual."""
    if any(j.estado == "licencia_vacaciones" for j in jornadas_hoy):
        return "Licencia", "Hoy tenés licencia: no corresponde marcar llegada."
    hora = ahora.time()
    for j in jornadas_hoy:
        if j.estado != "permiso":
            continue
        if es_dia_completo(j.horario_entrada, j.horario_salida):
            return "Permiso", "Hoy tenés permiso: no corresponde marcar llegada."
        if j.horario_entrada <= hora < j.horario_salida:
            return "Permiso", (f"Tenés permiso de {hora_texto(j.horario_entrada)} a "
                               f"{hora_texto(j.horario_salida)}: no corresponde marcar llegada.")
    return None


def inicio_efectivo(entrada, permisos):
    """Hora desde la que se cuenta la tardanza: si un permiso cubre el inicio del
    turno, el turno empieza cuando termina el permiso. permisos: [(desde, hasta)]."""
    corrido = True
    while corrido:
        corrido = False
        for desde, hasta in permisos:
            if desde <= entrada < hasta:
                entrada, corrido = hasta, True
    return entrada


def _en_la_jornada(jornada, ahora):
    inicio = datetime.combine(ahora.date(), jornada.horario_entrada, tzinfo=ahora.tzinfo)
    fin = datetime.combine(ahora.date(), jornada.horario_salida, tzinfo=ahora.tzinfo)
    return jornada.estado == "jornada" and inicio - ANTICIPO_TURNO <= ahora < fin, inicio


def evaluar_fichaje(fichaje_abierto, jornadas_hoy, ahora):
    """fichaje_abierto: None o (fichaje_id, entrada) con entrada en hora de Argentina.
    jornadas_hoy: jornadas del empleado para la fecha de `ahora`.
    Si hay una entrada abierta se propone la SALIDA; si no, la ENTRADA,
    vinculada a la jornada cuyo turno contiene la hora actual (o empieza en
    menos de 30 min). Sin jornada o fuera de turno se ficha igual, con
    jornada_id None: queda como "Fuera de turno"."""
    turno = texto_turnos(jornadas_hoy)
    if fichaje_abierto is not None:
        fichaje_id, entrada = fichaje_abierto
        trabajado = texto_trabajado(entrada, ahora)
        if entrada.date() < ahora.date():
            return PropuestaFichaje(
                True, SALIDA, "Marcar la salida.", fichaje_id=fichaje_id, turno=turno,
                estado=trabajado, en_turno=True,
                advertencias=(f"Tiene una entrada abierta del {fecha_texto(entrada)} "
                              f"a las {hora_texto(entrada)}.",))
        if ahora < entrada + ESPERA_MINIMA_SALIDA:
            return PropuestaFichaje(
                False, None, f"Ya marcaste tu llegada a las {hora_texto(entrada)}.",
                fichaje_id=fichaje_id, turno=turno,
                estado=f"Llegada a las {hora_texto(entrada)}", en_turno=True)
        return PropuestaFichaje(True, SALIDA, f"Marcar la salida (llegada a las {hora_texto(entrada)}).",
                                fichaje_id=fichaje_id, turno=turno, estado=trabajado, en_turno=True)

    bloqueo = bloqueo_llegada(jornadas_hoy, ahora)
    if bloqueo is not None:
        ausencia, mensaje = bloqueo
        return PropuestaFichaje(False, None, mensaje, turno=turno, estado=ausencia, ausencia=ausencia)

    permisos = [(j.horario_entrada, j.horario_salida) for j in jornadas_hoy if j.estado == "permiso"]
    for jornada in jornadas_hoy:
        dentro, inicio = _en_la_jornada(jornada, ahora)
        if dentro:
            desde = inicio_efectivo(jornada.horario_entrada, permisos)
            inicio = datetime.combine(ahora.date(), desde, tzinfo=ahora.tzinfo)
            tarde = int((ahora - inicio).total_seconds() // 60)
            estado = f"Llegaste {tarde} min tarde" if tarde > 0 else "En horario"
            return PropuestaFichaje(
                True, ENTRADA,
                f"Marcar la llegada (turno de {hora_texto(jornada.horario_entrada)} "
                f"a {hora_texto(jornada.horario_salida)}).",
                jornada_id=jornada.id, turno=turno, estado=estado, en_turno=True)

    avisos = []
    for jornada in jornadas_hoy:
        if jornada.estado in ESTADOS_JORNADA:
            avisos.append(f"Hoy figura con {ESTADOS_JORNADA[jornada.estado]}.")
            break
    return PropuestaFichaje(True, ENTRADA, "Marcar la llegada.", advertencias=tuple(avisos),
                            turno=turno, estado="Fuera de turno")
