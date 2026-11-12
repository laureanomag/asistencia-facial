"""Flujo de ingreso completo contra el esquema real (AccesoService + repositorios).
Ver tests/apoyo_db.py: se ejecutan solo con ZEBRAGYM_TEST_DSN y nunca dejan datos."""
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
    assert [o.clave for o in ev.opciones] == [ENTRENAR, FICHAR]
    resultado = servicio.confirmar(ev, FICHAR)
    assert resultado.registrado and "fuera de turno" in resultado.mensaje
    assert valor(db, "SELECT COUNT(*) FROM fichaje WHERE usuario_id = %s AND salida IS NULL", (uid,)) == 1
    assert _accesos(db) == []                                 # fichar no es un ingreso de socio

    # Recién fichó: puede entrar a entrenar, pero no se le propone la salida.
    ev = servicio.evaluar(pid)
    assert [o.clave for o in ev.opciones] == [ENTRENAR]


def test_empleado_con_entrada_recien_registrada(abierto_todo_el_dia):
    db = abierto_todo_el_dia
    pid = persona(db)
    usuario(db, pid, "rocio", ("recepcionista",))
    servicio = AccesoService()
    assert servicio.confirmar(servicio.evaluar(pid), FICHAR).registrado
    ev = servicio.evaluar(pid)
    assert ev.estado == AVISO and ev.mensaje.startswith("Ya registraste tu entrada a las ")


def test_no_reconocido(db):
    AccesoService().registrar_no_reconocido(Decimal("0.6120"))
    assert _accesos(db) == [("rechazado", r.NO_RECONOCIDO)]
