import json
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta
from decimal import Decimal

import pytest

from services import reglas_ingreso as r
from services.acceso_service import (
    AVISO, ENTRENAR, FICHAR, PROPUESTA, RECHAZADO, AccesoService, Antirrebote,
    MODO_AMBOS, MODO_EMPLEADO, MODO_SOCIO, ContadorNoReconocidos, GestorPropuestas, dni_texto,
    tarjetas_socio,
)

JUEVES = datetime(2026, 11, 12, 18, 42)


@contextmanager
def _sin_base():
    yield None


def estado(**cambios):
    base = {
        "membresia_id": 7, "plan": "3 veces por semana", "estado_membresia": "vigente",
        "fecha_inicio": date(2026, 11, 5), "fecha_vencimiento": date(2026, 12, 5),
        "dias_para_vencer": 23, "accesos_incluidos": None, "accesos_restantes": None,
        "accesos_hoy": 0, "max_ingresos_diarios": None, "dias_entrenados_semana": 2,
        "max_dias_semanales": 3, "saldo": Decimal("0"), "estado_contable": "al_dia",
    }
    base.update(cambios)
    return base


class Mundo:
    """Repositorios falsos con una persona configurable."""

    def __init__(self, socio=True, socio_activo=True, empleado=False, estado_socio=None,
                 abierto=None, jornadas=(), franjas=((time(7, 30), time(23, 0)),), existe=True):
        self.existe = existe
        self.roles = {
            "socio_id": 50 if socio else None, "socio_activo": socio_activo if socio else None,
            "usuario_id": 80 if empleado else None, "usuario_activo": True if empleado else None,
            "roles": ["entrenador"] if empleado else [],
        }
        self.estado = estado() if estado_socio is None else estado_socio
        self.abierto = abierto
        self.jornadas = list(jornadas)
        self.franjas = list(franjas)
        self.rechazos, self.permitidos, self.entradas, self.salidas = [], [], [], []

    # personas
    def obtener_por_id(self, persona_id, conn=None, bloquear=False):
        if bloquear:                                   # SocioRepository.obtener_por_id
            return (50, 1, None, "388", None, self.roles["socio_activo"], None, None)
        return (persona_id, "30111222", "Juan", "Pérez", None, None, None, None) if self.existe else None

    def obtener_roles(self, persona_id, conn=None):
        return dict(self.roles)

    # socios
    def obtener_estado(self, socio_id, conn=None):
        return self.estado if self.roles["socio_activo"] else None

    # horario
    def franjas_del_dia(self, dia, conn=None):
        return self.franjas

    # fichajes
    def fichaje_abierto(self, usuario_id, bloquear=False, conn=None):
        return self.abierto

    def jornadas_del_dia(self, usuario_id, fecha, conn=None):
        return self.jornadas

    def registrar_entrada(self, usuario_id, jornada_id=None, conn=None):
        self.entradas.append((usuario_id, jornada_id))
        return 900, JUEVES

    def registrar_salida(self, fichaje_id, conn=None):
        self.salidas.append(fichaje_id)
        return JUEVES

    # accesos
    def registrar_rechazo(self, motivo, socio_id=None, membresia_id=None, distancia_facial=None, conn=None):
        self.rechazos.append((motivo, socio_id, membresia_id))
        return 1, JUEVES

    def registrar_permitido(self, socio_id, membresia_id, distancia_facial=None, conn=None):
        self.permitidos.append((socio_id, membresia_id, distancia_facial))
        return 2, JUEVES


def servicio(mundo, ahora=JUEVES):
    return AccesoService(mundo, _SociosDe(mundo), mundo, mundo, mundo,
                         transaccion=_sin_base, reloj=lambda conn: ahora)


class _SociosDe:
    """SocioRepository falso: obtener_por_id con bloqueo devuelve la fila del socio."""

    def __init__(self, mundo):
        self.mundo = mundo

    def obtener_por_id(self, socio_id, bloquear=False, conn=None):
        return self.mundo.obtener_por_id(socio_id, bloquear=True)

    def obtener_estado(self, socio_id, conn=None):
        return self.mundo.obtener_estado(socio_id)


# --- Evaluación ---

def test_socio_habilitado_propone_ingreso_sin_escribir():
    m = Mundo()
    ev = servicio(m).evaluar(1, Decimal("0.18"))
    assert ev.estado == PROPUESTA and ev.modo == MODO_SOCIO
    assert [(o.clave, o.boton) for o in ev.opciones] == [(ENTRENAR, "Entrar")]
    assert ev.mensaje == "¿Confirmás tu entrada al gimnasio?" and ev.sugerida == ENTRENAR
    assert (ev.nombre, ev.dni, ev.rol_texto) == ("Juan Pérez", "30.111.222", "Socio")
    assert ev.tarjetas == (("Plan", "3 veces por semana", None), ("Vence", "05/12 · en 23 días", None),
                           ("Estado contable", "Al día", "verde"))
    assert (m.rechazos, m.permitidos) == ([], [])


def test_rechazo_queda_registrado_con_su_motivo():
    m = Mundo(estado_socio=estado(dias_entrenados_semana=3))
    ev = servicio(m).evaluar(1)
    assert (ev.estado, ev.motivo) == (RECHAZADO, r.LIMITE_SEMANAL)
    assert "Puede volver el lunes" in ev.mensaje
    assert m.rechazos == [(r.LIMITE_SEMANAL, 50, 7)]


def test_gimnasio_cerrado():
    m = Mundo()
    ev = servicio(m, ahora=JUEVES.replace(hour=23, minute=5)).evaluar(1)
    assert (ev.estado, ev.motivo) == (RECHAZADO, r.GIMNASIO_CERRADO)
    assert m.rechazos == [(r.GIMNASIO_CERRADO, 50, None)]


def test_socio_con_datos_pero_sin_membresia():
    m = Mundo(estado_socio=estado(estado_membresia="sin_membresia", membresia_id=None))
    ev = servicio(m).evaluar(1)
    assert (ev.estado, ev.motivo) == (RECHAZADO, r.SIN_MEMBRESIA)


def test_persona_que_no_es_socio_ni_empleado():
    m = Mundo(socio=False)
    ev = servicio(m).evaluar(1)
    assert (ev.estado, ev.motivo) == (RECHAZADO, r.NO_ES_SOCIO)
    assert m.rechazos == [(r.NO_ES_SOCIO, None, None)]


def test_referencia_de_una_persona_que_ya_no_existe():
    m = Mundo(existe=False)
    assert servicio(m).evaluar(1).motivo == r.NO_RECONOCIDO
    assert m.rechazos == [(r.NO_RECONOCIDO, None, None)]


def test_pago_parcial_permite_y_advierte():
    m = Mundo(estado_socio=estado(saldo=Decimal("8000"), estado_contable="debe"))
    ev = servicio(m).evaluar(1)
    assert ev.estado == PROPUESTA and ev.advertencias == ()      # la deuda ya está en la tarjeta
    assert ev.tarjetas[2] == ("Estado contable", "Debe $8.000,00", "rojo")


TURNO_TARDE = (1, time(14, 0), time(22, 0), "jornada")


def test_socio_y_entrenador_en_su_turno_sugiere_trabajar():
    m = Mundo(empleado=True, jornadas=[TURNO_TARDE])
    ev = servicio(m).evaluar(1)
    assert (ev.modo, ev.mensaje, ev.rol_texto) == (MODO_AMBOS, "¿Qué vas a hacer?", "Socio y entrenador")
    assert [(o.clave, o.boton, o.habilitada) for o in ev.opciones] == [
        (FICHAR, "Trabajar", True), (ENTRENAR, "Entrenar", True)]
    assert ev.sugerida == FICHAR
    assert ev.lineas == (("Empleado · Turno 14:00–22:00 · Llegaste 282 min tarde", "ambar"),
                         ("Socio · 3 veces por semana · Vigente (vence 05/12)", "verde"))


def test_socio_y_entrenador_media_hora_antes_del_turno_sugiere_trabajar():
    m = Mundo(empleado=True, jornadas=[TURNO_TARDE])
    ev = servicio(m, ahora=JUEVES.replace(hour=13, minute=35)).evaluar(1)
    assert ev.sugerida == FICHAR
    assert ev.lineas[0] == ("Empleado · Turno 14:00–22:00 · En horario", "verde")


def test_socio_y_entrenador_fuera_de_turno_sugiere_entrenar():
    m = Mundo(empleado=True, jornadas=[(1, time(7, 0), time(15, 0), "jornada")])
    ev = servicio(m).evaluar(1)
    assert ev.sugerida == ENTRENAR
    assert ev.lineas[0] == ("Empleado · Turno 07:00–15:00 · Fuera de turno", "ambar")
    ev = servicio(Mundo(empleado=True)).evaluar(1)
    assert (ev.sugerida, ev.lineas[0]) == (ENTRENAR, ("Empleado · Sin turno hoy", "ambar"))


def test_con_la_llegada_marcada_sugiere_trabajar_para_salir():
    m = Mundo(empleado=True, abierto=(40, JUEVES - timedelta(hours=4, minutes=40)))
    ev = servicio(m).evaluar(1)
    assert [o.boton for o in ev.opciones] == ["Me voy", "Entrenar"] and ev.sugerida == FICHAR
    assert ev.lineas[0] == ("Empleado · Sin turno hoy · Trabajaste 4 h 40 min", "neutro")


@pytest.mark.parametrize("situacion, texto", [
    ("vencida", "Socio · 3 veces por semana · Vencida"),
    ("sin_membresia", "Socio · Sin membresía"),
])
def test_socio_sin_membresia_vigente_que_es_entrenador(situacion, texto):
    m = Mundo(empleado=True, estado_socio=estado(estado_membresia=situacion))
    ev = servicio(m).evaluar(1)
    entrenar = ev.opciones[1]
    assert (entrenar.clave, entrenar.habilitada) == (ENTRENAR, False) and entrenar.motivo
    assert ev.sugerida == FICHAR and ev.lineas[1] == (texto, "rojo")
    assert m.rechazos == []                      # vino a trabajar: no es un rechazo
    with pytest.raises(ValueError):              # una opción deshabilitada no se confirma
        servicio(m).confirmar(ev, ENTRENAR)


def test_entrada_reciente_deja_trabajar_deshabilitado_y_sugiere_entrenar():
    m = Mundo(empleado=True, abierto=(40, JUEVES - timedelta(minutes=3)))
    ev = servicio(m).evaluar(1)
    trabajar = ev.opciones[0]
    assert (trabajar.habilitada, trabajar.motivo) == (False, "Ya marcaste tu llegada a las 18:39.")
    assert ev.sugerida == ENTRENAR


def test_empleado_solo_ve_su_asistencia_laboral():
    m = Mundo(socio=False, empleado=True, jornadas=[TURNO_TARDE])
    ev = servicio(m, ahora=JUEVES.replace(hour=14, minute=0)).evaluar(1)
    assert (ev.modo, ev.mensaje) == (MODO_EMPLEADO, "Asistencia laboral")
    assert [(o.clave, o.boton) for o in ev.opciones] == [(FICHAR, "Llegué")]
    assert ev.tarjetas == (("Rol", "Entrenador", None), ("Turno de hoy", "14:00–22:00", None),
                           ("Hora", "14:00", None), ("Estado", "En horario", "verde"))


def test_empleado_al_irse_ve_lo_trabajado():
    m = Mundo(socio=False, empleado=True, jornadas=[TURNO_TARDE],
              abierto=(40, JUEVES.replace(hour=14, minute=2)))
    ev = servicio(m, ahora=JUEVES.replace(hour=22, minute=7)).evaluar(1)
    assert [o.boton for o in ev.opciones] == ["Me voy"]
    assert ev.tarjetas[3] == ("Estado", "Trabajaste 8 h 05 min", None)


def test_empleado_ficha_con_el_gimnasio_cerrado_y_sin_turno():
    m = Mundo(socio=False, empleado=True)
    ev = servicio(m, ahora=JUEVES.replace(hour=6, minute=50)).evaluar(1)
    assert ev.estado == PROPUESTA and [o.clave for o in ev.opciones] == [FICHAR]
    assert ev.tarjetas[1:] == (("Turno de hoy", "Sin turno hoy", None), ("Hora", "06:50", None),
                               ("Estado", "Fuera de turno", "ambar"))


def test_socio_dado_de_baja_que_es_entrenador_solo_ficha():
    m = Mundo(empleado=True, socio_activo=False)
    ev = servicio(m).evaluar(1)
    assert ev.modo == MODO_EMPLEADO and m.rechazos == []


def test_empleado_con_entrada_reciente_solo_recibe_un_aviso():
    m = Mundo(socio=False, empleado=True, abierto=(40, JUEVES - timedelta(minutes=3)))
    ev = servicio(m).evaluar(1)
    assert (ev.estado, ev.mensaje) == (AVISO, "Ya marcaste tu llegada a las 18:39.")
    assert m.rechazos == []


def test_evaluacion_se_serializa_para_el_proceso_de_reconocimiento():
    datos = servicio(Mundo(empleado=True)).evaluar(1, Decimal("0.18")).a_dict()
    texto = json.dumps(datos, default=str)
    assert '"clave": "entrenar"' in texto and datos["distancia"] == pytest.approx(0.18)


# --- Confirmación ---

def test_confirmar_ingreso():
    m = Mundo()
    s = servicio(m)
    resultado = s.confirmar(s.evaluar(1, Decimal("0.18")), ENTRENAR)
    assert resultado.registrado and resultado.tono == "verde"
    assert resultado.mensaje == "¡Listo, Juan! Buen entrenamiento."
    assert m.permitidos == [(50, 7, Decimal("0.18"))]


def test_confirmar_vuelve_a_evaluar_las_reglas():
    m = Mundo(estado_socio=estado(dias_entrenados_semana=2))
    s = servicio(m)
    ev = s.evaluar(1)
    m.estado = estado(dias_entrenados_semana=3)     # entre la propuesta y el OK
    resultado = s.confirmar(ev, ENTRENAR)
    assert not resultado.registrado and resultado.motivo == r.LIMITE_SEMANAL
    assert m.permitidos == [] and m.rechazos == [(r.LIMITE_SEMANAL, 50, 7)]


def test_no_se_confirma_una_opcion_no_propuesta():
    s = servicio(Mundo())
    with pytest.raises(ValueError):
        s.confirmar(s.evaluar(1), FICHAR)


def test_confirmar_fichaje_entrada_y_salida():
    turno = (1, time(7, 30), time(23, 0), "jornada")
    m = Mundo(socio=False, empleado=True, jornadas=[turno])
    s = servicio(m)
    assert s.confirmar(s.evaluar(1), FICHAR).mensaje == "Llegada marcada a las 18:42."
    assert m.entradas == [(80, 1)]

    m.jornadas = []                               # fuera de turno: se marca igual, sin jornada
    assert s.confirmar(s.evaluar(1), FICHAR).mensaje == "Llegada marcada a las 18:42."
    assert m.entradas[-1] == (80, None)

    m.abierto = (40, JUEVES - timedelta(hours=8))
    ev = s.evaluar(1)
    assert ev.opciones[0].boton == "Me voy"
    assert s.confirmar(ev, FICHAR).mensaje == "Salida marcada a las 18:42."
    assert m.salidas == [40]


# --- Propuesta, antirrebote y no reconocidos ---

class Reloj:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def test_token_de_un_solo_uso():
    reloj = Reloj()
    g = GestorPropuestas(reloj=reloj)
    token = g.crear("evaluacion")
    assert g.pendiente()
    assert g.tomar("otro") is None and g.tomar(token) == "evaluacion"
    assert g.tomar(token) is None and not g.pendiente()       # doble OK


def test_propuesta_vencida_o_reemplazada():
    reloj = Reloj()
    g = GestorPropuestas(vigencia_s=35, reloj=reloj)
    viejo = g.crear("a")
    nuevo = g.crear("b")
    assert g.tomar(viejo) is None and g.tomar(nuevo) == "b"
    token = g.crear("c")
    reloj.t += 36
    assert not g.pendiente() and g.tomar(token) is None
    token = g.crear("d")
    assert g.descartar(token) and g.tomar(token) is None       # Cancelar


def test_antirrebote_de_diez_segundos():
    reloj = Reloj()
    a = Antirrebote(reloj=reloj)
    a.registrar(1)
    reloj.t += 9.9
    assert a.bloqueado(1) and not a.bloqueado(2)
    reloj.t += 0.1
    assert not a.bloqueado(1)


def test_no_reconocido_al_tercer_intento_seguido():
    c = ContadorNoReconocidos()
    assert [c.fallo(), c.fallo(), c.fallo(), c.fallo()] == [False, False, True, False]
    c.reiniciar()
    assert [c.fallo(), c.fallo()] == [False, False]


def test_formatos():
    assert dni_texto("30111222") == "30.111.222" and dni_texto("1234567") == "1.234.567"
    assert tarjetas_socio(estado(max_dias_semanales=None, dias_entrenados_semana=1,
                                 dias_para_vencer=1, estado_contable="por_vencer"))[1:] == (
        ("Vence", "05/12 · mañana", None),
        ("Estado contable", "Por vencer", "ambar"))
