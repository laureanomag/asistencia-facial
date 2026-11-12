from datetime import date, datetime, time, timedelta
from decimal import Decimal

import pytest

from services import reglas_ingreso as r
from services.reglas_ingreso import Franja, Jornada, evaluar_fichaje, evaluar_socio

LUNES_A_VIERNES = [Franja(time(7, 0), time(23, 0))]
SABADO = [Franja(time(10, 0), time(14, 0))]
DOMINGO = []
JUEVES = datetime(2026, 11, 12, 18, 30)          # jueves 12/11/2026, 18:30
ACTIVO = {"activo": True}


def estado(**cambios):
    """Fila de v_socio_estado de un socio al día con 'Pase libre'."""
    base = {
        "membresia_id": 7, "plan": "Pase libre", "estado_membresia": "vigente",
        "fecha_inicio": date(2026, 11, 1), "fecha_vencimiento": date(2026, 12, 1),
        "dias_para_vencer": 19, "accesos_incluidos": None, "accesos_restantes": None,
        "accesos_hoy": 0, "max_ingresos_diarios": None, "dias_entrenados_semana": 0,
        "max_dias_semanales": None, "saldo": Decimal("0"),
    }
    base.update(cambios)
    return base


def evaluar(estado_socio=None, socio=ACTIVO, franjas=LUNES_A_VIERNES, ahora=JUEVES):
    return evaluar_socio(socio, estado() if estado_socio is None else estado_socio, franjas, ahora)


# --- Horario de atención ---

@pytest.mark.parametrize("hora, abierto", [
    (time(6, 59), False), (time(7, 0), True), (time(22, 59), True), (time(23, 0), False),
])
def test_bordes_lunes_a_viernes(hora, abierto):
    assert (r.franja_actual(LUNES_A_VIERNES, hora) is not None) == abierto


@pytest.mark.parametrize("hora, abierto", [
    (time(9, 59), False), (time(10, 0), True), (time(13, 59), True), (time(14, 0), False),
])
def test_bordes_sabado(hora, abierto):
    assert (r.franja_actual(SABADO, hora) is not None) == abierto


def test_varias_franjas_en_un_dia():
    partido = [Franja(time(16, 0), time(22, 0)), Franja(time(7, 0), time(12, 0))]
    assert r.franja_actual(partido, time(13, 0)) is None
    assert r.franja_actual(partido, time(16, 0)) == partido[0]
    assert r.texto_horario(partido) == "07:00 a 12:00 y 16:00 a 22:00"


def test_gimnasio_cerrado_informa_el_horario_de_hoy():
    d = evaluar(ahora=JUEVES.replace(hour=6, minute=30))
    assert (d.permitido, d.motivo) == (False, r.GIMNASIO_CERRADO)
    assert d.mensaje == "El gimnasio está cerrado. Horario de hoy: 07:00 a 23:00 hs."


def test_domingo_cerrado():
    d = evaluar(franjas=DOMINGO, ahora=datetime(2026, 11, 15, 11, 0))
    assert d.motivo == r.GIMNASIO_CERRADO and d.mensaje == "Hoy el gimnasio está cerrado."


# --- Identidad y orden de los motivos ---

def test_no_es_socio():
    d = evaluar(socio=None)
    assert (d.permitido, d.motivo) == (False, r.NO_ES_SOCIO)


def test_socio_dado_de_baja_antes_que_el_horario():
    # La vista no incluye socios dados de baja: el estado llega en None.
    d = evaluar_socio({"activo": False}, None, DOMINGO, JUEVES)
    assert d.motivo == r.SOCIO_INACTIVO


def test_horario_antes_que_la_membresia():
    d = evaluar(estado(estado_membresia="vencida"), franjas=DOMINGO)
    assert d.motivo == r.GIMNASIO_CERRADO


# --- Membresía ---

def test_socio_con_datos_pero_sin_membresia():
    d = evaluar(estado(estado_membresia="sin_membresia", membresia_id=None))
    assert (d.motivo, d.membresia_id) == (r.SIN_MEMBRESIA, None)
    assert "contratar un plan" in d.mensaje


def test_socio_sin_fila_en_la_vista_se_trata_como_sin_membresia():
    assert evaluar_socio(ACTIVO, None, LUNES_A_VIERNES, JUEVES).motivo == r.SIN_MEMBRESIA


def test_membresia_vencida_informa_la_fecha():
    d = evaluar(estado(estado_membresia="vencida", fecha_vencimiento=date(2026, 11, 12)))
    assert (d.motivo, d.membresia_id) == (r.MEMBRESIA_VENCIDA, 7)
    assert "venció el 12/11/2026" in d.mensaje


def test_membresia_que_todavia_no_empieza():
    d = evaluar(estado(estado_membresia="no_vigente", fecha_inicio=date(2026, 11, 13)))
    assert d.motivo == r.MEMBRESIA_NO_VIGENTE and "empieza el 13/11/2026" in d.mensaje


def test_cupo_agotado():
    d = evaluar(estado(estado_membresia="agotada", accesos_incluidos=8, accesos_restantes=0))
    assert d.motivo == r.CUPO_AGOTADO and "8 accesos" in d.mensaje


# --- Límites ---

def test_pase_por_dia_un_solo_ingreso():
    pase = estado(plan="Pase por día", max_ingresos_diarios=1)
    assert evaluar(pase).permitido
    d = evaluar({**pase, "accesos_hoy": 1})
    assert d.motivo == r.LIMITE_DIARIO and "1 ingreso por día" in d.mensaje


def test_tres_veces_por_semana():
    plan = estado(plan="3 veces por semana", max_dias_semanales=3)
    assert evaluar({**plan, "dias_entrenados_semana": 2}).permitido
    d = evaluar({**plan, "dias_entrenados_semana": 3})
    assert d.motivo == r.LIMITE_SEMANAL
    assert d.mensaje == ("Ya entrenó 3 días esta semana: es el límite del plan "
                         "3 veces por semana. Puede volver el lunes.")


def test_cada_motivo_del_esquema_tiene_etiqueta():
    # Los mismos 10 códigos que admite el CHECK de acceso.motivo_rechazo.
    motivos = {r.NO_RECONOCIDO, r.NO_ES_SOCIO, r.SOCIO_INACTIVO, r.SIN_MEMBRESIA,
               r.MEMBRESIA_VENCIDA, r.MEMBRESIA_NO_VIGENTE, r.CUPO_AGOTADO,
               r.LIMITE_DIARIO, r.LIMITE_SEMANAL, r.GIMNASIO_CERRADO}
    assert set(r.ETIQUETAS_MOTIVO) == motivos and len(motivos) == 10


def test_segundo_ingreso_del_mismo_dia_no_suma_otro_dia():
    plan = estado(plan="3 veces por semana", max_dias_semanales=3,
                  dias_entrenados_semana=3, accesos_hoy=1)
    assert evaluar(plan).permitido


def test_limite_diario_antes_que_el_semanal():
    plan = estado(max_ingresos_diarios=1, max_dias_semanales=3,
                  dias_entrenados_semana=3, accesos_hoy=1)
    assert evaluar(plan).motivo == r.LIMITE_DIARIO


def test_pase_libre_sin_limites():
    d = evaluar(estado(accesos_hoy=5, dias_entrenados_semana=7))
    assert d.permitido and d.motivo is None


# --- Permitido y advertencias ---

def test_permitido_al_dia():
    d = evaluar()
    assert (d.permitido, d.membresia_id, d.advertencias) == (True, 7, ())
    assert d.mensaje == "Bienvenido/a a ZebraGym. Plan Pase libre, vence el 01/12/2026."


def test_pago_parcial_permite_y_advierte_la_deuda():
    d = evaluar(estado(saldo=Decimal("12500.50")))
    assert d.permitido and d.advertencias == ("Debe $12.500,50",)


@pytest.mark.parametrize("dias, aviso", [(5, "Vence en 5 días"), (1, "Vence mañana"), (6, None)])
def test_aviso_de_vencimiento(dias, aviso):
    d = evaluar(estado(dias_para_vencer=dias))
    assert d.advertencias == ((aviso,) if aviso else ())


def test_aviso_de_accesos_restantes():
    assert evaluar(estado(accesos_incluidos=8, accesos_restantes=3)).advertencias == \
        ("Le quedan 2 accesos después de este",)
    assert evaluar(estado(accesos_incluidos=8, accesos_restantes=1)).advertencias == \
        ("Es su último acceso del plan",)


def test_pesos():
    assert r.pesos(0) == "$0,00"
    assert r.pesos(Decimal("1234567.8")) == "$1.234.567,80"


# --- Fichaje ---

TURNO_MANANA = Jornada(1, time(7, 0), time(15, 0), "jornada")


def test_entrada_dentro_del_turno():
    p = evaluar_fichaje(None, [TURNO_MANANA], JUEVES.replace(hour=7, minute=0))
    assert (p.permitido, p.operacion, p.jornada_id, p.advertencias) == (True, r.ENTRADA, 1, ())


@pytest.mark.parametrize("hora", [time(6, 50), time(15, 0), time(20, 0)])
def test_entrada_fuera_de_turno(hora):
    p = evaluar_fichaje(None, [TURNO_MANANA], datetime.combine(JUEVES.date(), hora))
    assert (p.operacion, p.jornada_id) == (r.ENTRADA, None)
    assert p.advertencias == ("Fichaje fuera de turno",)


def test_entrada_sin_jornada_y_con_licencia():
    assert evaluar_fichaje(None, [], JUEVES).advertencias == ("Fichaje fuera de turno",)
    licencia = Jornada(2, time(7, 0), time(15, 0), "licencia_vacaciones")
    p = evaluar_fichaje(None, [licencia], JUEVES.replace(hour=8))
    assert p.jornada_id is None
    assert p.advertencias == ("Fichaje fuera de turno", "Hoy figura con licencia o vacaciones.")


def test_fichaje_no_depende_del_horario_de_atencion():
    # Domingo a las 6:30 (gimnasio cerrado): el empleado puede fichar igual.
    assert evaluar_fichaje(None, [], datetime(2026, 11, 15, 6, 30)).permitido


def test_salida_con_entrada_abierta():
    entrada = JUEVES.replace(hour=7, minute=5)
    p = evaluar_fichaje((40, entrada), [TURNO_MANANA], JUEVES.replace(hour=15, minute=2))
    assert (p.permitido, p.operacion, p.fichaje_id) == (True, r.SALIDA, 40)
    assert p.mensaje == "Registrar SALIDA (entrada a las 07:05)."


def test_salida_todavia_no_habilitada():
    entrada = JUEVES.replace(hour=7, minute=5)
    p = evaluar_fichaje((40, entrada), [], entrada + timedelta(minutes=9, seconds=59))
    assert (p.permitido, p.operacion) == (False, None)
    assert p.mensaje == "Ya registraste tu entrada a las 07:05."
    assert evaluar_fichaje((40, entrada), [], entrada + r.ESPERA_MINIMA_SALIDA).operacion == r.SALIDA


def test_entrada_abierta_de_otro_dia():
    entrada = datetime(2026, 11, 11, 7, 0)
    p = evaluar_fichaje((40, entrada), [], JUEVES.replace(hour=7, minute=1))
    assert p.operacion == r.SALIDA
    assert p.advertencias == ("Tiene una entrada abierta del 11/11/2026 a las 07:00.",)
