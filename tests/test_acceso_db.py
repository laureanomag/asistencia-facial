"""Flujo de ingreso completo contra el esquema real (AccesoService + repositorios).
Ver tests/apoyo_db.py: se ejecutan solo con ZEBRAGYM_TEST_DSN y nunca dejan datos."""
from datetime import timedelta
from decimal import Decimal

import pytest

from apoyo_db import membresia, persona, requiere_base, socio, usuario, valor
from services import reglas_ingreso as r
from services.acceso_service import AVISO, ENTRENAR, FICHAR, PROPUESTA, RECHAZADO, AccesoService

pytestmark = requiere_base


@pytest.fixture
def abierto_todo_el_dia(db):
    """Las pruebas no dependen de la hora en que se ejecutan."""
    for dia in range(1, 8):
        db.execute("INSERT INTO horario_atencion (dia_semana, hora_apertura, hora_cierre) "
                   "VALUES (%s, '00:00', '23:59')", (dia,))
    return db


def _accesos(db):
    return [tuple(f) for f in db.execute(
        "SELECT resultado, motivo_rechazo FROM acceso ORDER BY id")]


def test_pase_por_dia_de_punta_a_punta(abierto_todo_el_dia):
    db = abierto_todo_el_dia
    pid = persona(db)
    s = socio(db, pid)
    membresia(db, s, plan="Pase por día", precio=Decimal("3000"))
    servicio = AccesoService()

    ev = servicio.evaluar(pid, Decimal("0.21"))
    assert ev.estado == PROPUESTA and ev.socio_id == s
    assert _accesos(db) == []                                 # la propuesta no escribe

    assert servicio.confirmar(ev, ENTRENAR).registrado
    assert _accesos(db) == [("permitido", None)]
    assert valor(db, "SELECT distancia_facial FROM acceso") == Decimal("0.2100")

    # Doble OK sobre la misma propuesta: se vuelve a evaluar y ya no corresponde.
    segundo = servicio.confirmar(ev, ENTRENAR)
    assert (segundo.registrado, segundo.motivo) == (False, r.LIMITE_DIARIO)

    otra = servicio.evaluar(pid)
    assert (otra.estado, otra.motivo) == (RECHAZADO, r.LIMITE_DIARIO)
    assert _accesos(db) == [("permitido", None), ("rechazado", r.LIMITE_DIARIO),
                            ("rechazado", r.LIMITE_DIARIO)]


def test_socio_sin_membresia_y_no_socio(abierto_todo_el_dia):
    db = abierto_todo_el_dia
    con_datos = persona(db)
    socio(db, con_datos)
    sin_ficha = persona(db, "20333444", "Luis", "Gómez")
    servicio = AccesoService()
    assert servicio.evaluar(con_datos).motivo == r.SIN_MEMBRESIA
    assert servicio.evaluar(sin_ficha).motivo == r.NO_ES_SOCIO
    assert valor(db, "SELECT COUNT(*) FROM acceso WHERE socio_id IS NULL") == 1


def test_entrenador_que_tambien_es_socio(abierto_todo_el_dia):
    db = abierto_todo_el_dia
    pid = persona(db)
    s = socio(db, pid)
    membresia(db, s)
    uid = usuario(db, pid, "ana")
    servicio = AccesoService()

    ev = servicio.evaluar(pid)
    assert ev.modo == "ambos" and [o.clave for o in ev.opciones] == [FICHAR, ENTRENAR]
    resultado = servicio.confirmar(ev, FICHAR)
    assert resultado.registrado and resultado.mensaje.startswith("Llegada marcada a las ")
    # Sin turno cargado: queda como fuera de turno (sin jornada).
    assert valor(db, "SELECT COUNT(*) FROM fichaje WHERE usuario_id = %s AND salida IS NULL "
                     "AND jornada_id IS NULL", (uid,)) == 1
    assert _accesos(db) == []                                 # fichar no es un ingreso de socio

    # Recién fichó: puede entrar a entrenar; Trabajar queda deshabilitado con el motivo.
    ev = servicio.evaluar(pid)
    assert [(o.clave, o.habilitada) for o in ev.opciones] == [(FICHAR, False), (ENTRENAR, True)]
    assert ev.sugerida == ENTRENAR


def test_empleado_con_entrada_recien_registrada(abierto_todo_el_dia):
    db = abierto_todo_el_dia
    pid = persona(db)
    usuario(db, pid, "rocio", ("recepcionista",))
    servicio = AccesoService()
    assert servicio.confirmar(servicio.evaluar(pid), FICHAR).registrado
    ev = servicio.evaluar(pid)
    assert ev.estado == AVISO and ev.mensaje.startswith("Ya marcaste tu llegada a las ")


def test_no_reconocido(db):
    AccesoService().registrar_no_reconocido(Decimal("0.6120"))
    assert _accesos(db) == [("rechazado", r.NO_RECONOCIDO)]


# --- Plan "3 veces por semana": 3 días por semana, 1 ingreso por día, sin cupo total ---

def _tres_por_semana(db, socio_id, desde=-10):
    db.execute("UPDATE plan SET entrenamientos_mensuales = NULL, max_dias_semanales = 3, "
               "max_ingresos_diarios = 1 WHERE nombre = '3 veces por semana'")
    return membresia(db, socio_id, plan="3 veces por semana", desde=desde)


def _ingreso(db, socio_id, membresia_id, fecha):
    db.execute("INSERT INTO acceso (socio_id, membresia_id, resultado, fecha_hora) "
               "VALUES (%s, %s, 'permitido', (%s::date + TIME '10:00') AT TIME ZONE 'America/Argentina/Buenos_Aires')",
               (socio_id, membresia_id, fecha))


def _semana(db):
    """(hoy, días de esta semana distintos de hoy, lunes de esta semana)."""
    hoy = valor(db, "SELECT (NOW() AT TIME ZONE 'America/Argentina/Buenos_Aires')::date")
    lunes = hoy - timedelta(days=hoy.weekday())
    return hoy, [lunes + timedelta(days=i) for i in range(7) if lunes + timedelta(days=i) != hoy], lunes


def test_tres_dias_en_la_semana_y_el_cuarto_es_limite_semanal(abierto_todo_el_dia):
    db = abierto_todo_el_dia
    pid = persona(db)
    s = socio(db, pid)
    mid = _tres_por_semana(db, s)
    _hoy, otros, _lunes = _semana(db)
    for fecha in otros[:3]:
        _ingreso(db, s, mid, fecha)
    ev = AccesoService().evaluar(pid)
    assert (ev.estado, ev.motivo) == (RECHAZADO, r.LIMITE_SEMANAL)


def test_un_ingreso_por_dia(abierto_todo_el_dia):
    db = abierto_todo_el_dia
    pid = persona(db)
    s = socio(db, pid)
    _tres_por_semana(db, s)
    servicio = AccesoService()
    assert servicio.confirmar(servicio.evaluar(pid), ENTRENAR).registrado
    ev = servicio.evaluar(pid)
    assert (ev.estado, ev.motivo) == (RECHAZADO, r.LIMITE_DIARIO)
    assert ev.mensaje == "Su plan permite 1 ingreso por día y hoy ya lo usó."


def test_la_semana_nueva_empieza_de_cero_y_no_compensa(abierto_todo_el_dia):
    db = abierto_todo_el_dia
    pid = persona(db)
    s = socio(db, pid)
    mid = _tres_por_semana(db, s, desde=-20)
    _hoy, otros, lunes = _semana(db)
    for dias in (7, 6, 5):                                   # 3 días la semana pasada
        _ingreso(db, s, mid, lunes - timedelta(days=dias))
    assert AccesoService().evaluar(pid).estado == PROPUESTA    # esta semana vuelve a entrar
    # Una semana en que no vino no le suma días a la siguiente.
    for fecha in otros[:3]:
        _ingreso(db, s, mid, fecha)
    assert AccesoService().evaluar(pid).motivo == r.LIMITE_SEMANAL


def test_sin_cupo_total_no_se_agota_en_el_mes(abierto_todo_el_dia):
    db = abierto_todo_el_dia
    pid = persona(db)
    s = socio(db, pid)
    mid = _tres_por_semana(db, s, desde=-28)
    _hoy, _otros, lunes = _semana(db)
    for semana in range(1, 5):                               # 3 días por semana, 4 semanas: 12 ingresos
        for dia in range(3):
            _ingreso(db, s, mid, lunes - timedelta(weeks=semana) + timedelta(days=dia))
    estado = valor(db, "SELECT estado_membresia FROM v_socio_estado WHERE socio_id = %s", (s,))
    assert estado == "vigente"
    assert AccesoService().evaluar(pid).estado == PROPUESTA
