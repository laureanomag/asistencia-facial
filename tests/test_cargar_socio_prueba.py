"""Script scripts/cargar_socio_prueba.py contra el esquema real (sin cámara).
Ver tests/apoyo_db.py: se ejecutan solo con ZEBRAGYM_TEST_DSN y nunca dejan datos."""
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest

from apoyo_db import persona, requiere_base, usuario, valor

pytestmark = requiere_base
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import cargar_socio_prueba as script  # noqa: E402

FOTOS = {"frente": b"\x01", "perfil_izquierdo": b"\x02", "perfil_derecho": b"\x03"}
DATOS = {"dni": "99.000.001", "nombre": "Socio", "apellido": "de Prueba"}


def _transaccion(db):
    @contextmanager
    def misma():
        yield db
    return misma


@pytest.fixture
def profe(db):
    """Cuenta de entrenador: es quien registra socios en el mostrador."""
    return usuario(db, persona(db, dni="30111222", nombre="Profe", apellido="Zebra"), "profe")


def test_registra_a_nombre_del_entrenador(db, profe):
    r = script.cargar(DATOS, FOTOS, "388", transaccion=_transaccion(db))
    assert r["registrado_por"] == "profe"
    assert valor(db, "SELECT registrado_por_usuario_id FROM socio s JOIN persona p ON p.id = s.persona_id "
                     "WHERE p.dni = '99000001'") == profe


def test_sin_entrenador_activo_avisa(db):
    with pytest.raises(SystemExit, match="No hay ninguna cuenta de entrenador activa"):
        script.cargar(DATOS, FOTOS, "388", transaccion=_transaccion(db))


def test_usuario_que_no_es_entrenador_activo(db, profe):
    with pytest.raises(SystemExit, match="'admin'"):
        script.cargar(DATOS, FOTOS, "388", transaccion=_transaccion(db), usuario="admin")


def test_crea_socio_con_fotos_y_pase_por_dia(db, profe):
    r = script.cargar(DATOS, FOTOS, "388", transaccion=_transaccion(db))
    assert (r["socio"], r["fotos"], r["dni"]) == ("creado", 3, "99000001")
    assert r["membresia"].startswith("nueva: Pase por día")
    estado = valor(db, "SELECT estado_membresia FROM v_socio_estado WHERE socio_id = %s", (r["socio_id"],))
    assert estado == "vigente"


def test_volver_a_ejecutarlo_no_duplica(db, profe):
    primero = script.cargar(DATOS, FOTOS, "388", transaccion=_transaccion(db))
    segundo = script.cargar(DATOS, {"frente": b"\x09"}, "388", transaccion=_transaccion(db))
    assert segundo["socio"] == "existente" and segundo["socio_id"] == primero["socio_id"]
    assert segundo["membresia"].startswith("vigente")          # no agrega otra membresía
    assert valor(db, "SELECT COUNT(*) FROM persona WHERE dni = '99000001'") == 1
    assert valor(db, "SELECT COUNT(*) FROM membresia") == 1
    assert bytes(valor(db, "SELECT imagen FROM foto_persona WHERE angulo = 'frente'")) == b"\x09"


def test_con_el_pase_usado_hoy_agrega_otro(db, profe):
    r = script.cargar(DATOS, FOTOS, "388", transaccion=_transaccion(db))
    m = valor(db, "SELECT id FROM membresia WHERE socio_id = %s", (r["socio_id"],))
    db.execute("INSERT INTO acceso (socio_id, membresia_id, resultado) VALUES (%s, %s, 'permitido')",
               (r["socio_id"], m))
    otra = script.cargar(DATOS, None, "388", transaccion=_transaccion(db))
    assert otra["membresia"].startswith("nueva:")
