"""Empleados contra el esquema real (ver tests/apoyo_db.py)."""
import pytest

from apoyo_db import membresia, persona, requiere_base, socio, usuario, valor
from services import auth_service as auth
from services.auth_service import ADMINISTRADOR, AuthService, Sesion
from services import reglas_ingreso as reglas
from services.acceso_service import ENTRENAR, FICHAR, PROPUESTA, RECHAZADO, AccesoService
from services.empleado_service import EmpleadoService, ErroresFormulario

pytestmark = requiere_base
FOTOS = {"frente": b"\x01", "perfil_izquierdo": b"\x02", "perfil_derecho": b"\x03"}


@pytest.fixture(autouse=True)
def bcrypt_rapido(monkeypatch):
    monkeypatch.setattr(auth, "COSTO_BCRYPT", 4)


def _admin(db):
    return Sesion(valor(db, "SELECT id FROM usuario WHERE nombre_usuario = 'admin'"), None, "admin", "admin",
                  frozenset({ADMINISTRADOR}))


def test_alta_login_y_desactivacion(db):
    servicio = EmpleadoService(detectable=lambda datos: True)
    admin = _admin(db)
    uid = servicio.registrar(admin, {"dni": "30111222", "nombre": "Rocío", "apellido": "Paz",
                                     "usuario": "rocio", "contrasenia": "inicial-123",
                                     "rol": "recepcionista"}, FOTOS)
    fila = servicio.listar(admin)[0]
    assert (fila[0], fila[1], fila[4], fila[5], fila[6]) == (uid, "Rocío", "rocio", True, ["recepcionista"])
    assert valor(db, "SELECT COUNT(*) FROM foto_persona") == 3

    sesion = AuthService().autenticar("rocio", "inicial-123")
    assert sesion.debe_cambiar_contrasenia and sesion.roles == {"recepcionista"}
    assert sesion.puede("acceso.operar_camara") and not sesion.puede("usuario.administrar")

    servicio.cambiar_estado(admin, uid, False)
    with pytest.raises(auth.ErrorAutenticacion):
        AuthService().autenticar("rocio", "inicial-123")


def test_socio_que_pasa_a_ser_entrenador(db):
    pid = persona(db)
    socio(db, pid)
    db.execute("INSERT INTO foto_persona (persona_id, angulo, imagen) VALUES "
               "(%s, 'frente', '\\x01'), (%s, 'perfil_izquierdo', '\\x02'), (%s, 'perfil_derecho', '\\x03')",
               (pid, pid, pid))
    servicio = EmpleadoService(detectable=lambda datos: True)
    servicio.registrar(_admin(db), {"dni": "30111222", "usuario": "ana", "contrasenia": "inicial-123",
                                    "rol": "entrenador"}, {})
    assert valor(db, "SELECT COUNT(*) FROM persona") == 1
    assert valor(db, "SELECT COUNT(*) FROM foto_persona") == 3
    assert valor(db, "SELECT persona_id FROM usuario WHERE nombre_usuario = 'ana'") == pid


def test_nombre_de_usuario_repetido(db):
    servicio = EmpleadoService(detectable=lambda datos: True)
    with pytest.raises(ErroresFormulario) as error:
        servicio.registrar(_admin(db), {"dni": "30111222", "nombre": "A", "apellido": "B", "usuario": "Admin",
                                        "contrasenia": "inicial-123", "rol": "entrenador"}, FOTOS)
    assert error.value.errores == {"usuario": "Ese nombre de usuario ya existe."}
    assert valor(db, "SELECT COUNT(*) FROM persona") == 0


# --- Baja y reactivación de empleados ---

@pytest.fixture
def abierto_todo_el_dia(db):
    """La cámara no depende de la hora en que se ejecutan las pruebas."""
    for dia in range(1, 8):
        db.execute("INSERT INTO horario_atencion (dia_semana, hora_apertura, hora_cierre) "
                   "VALUES (%s, '00:00', '23:59')", (dia,))
    return db


def _fichajes(db, uid):
    return valor(db, "SELECT COUNT(*) FROM fichaje WHERE usuario_id = %s", (uid,))


def test_empleado_dado_de_baja_no_inicia_sesion_ni_ficha(abierto_todo_el_dia):
    db = abierto_todo_el_dia
    pid = persona(db)
    uid = usuario(db, pid, "profe")
    EmpleadoService().cambiar_estado(_admin(db), uid, False)

    with pytest.raises(auth.ErrorAutenticacion):
        AuthService().autenticar("profe", "clave-segura")
    ev = AccesoService().evaluar(pid)
    assert (ev.estado, ev.motivo) == (RECHAZADO, reglas.NO_ES_SOCIO)   # no se le ofrece fichar
    assert _fichajes(db, uid) == 0


def test_entrenador_socio_dado_de_baja_sigue_entrenando(abierto_todo_el_dia):
    db = abierto_todo_el_dia
    pid = persona(db)
    membresia(db, socio(db, pid))
    uid = usuario(db, pid, "profe")
    EmpleadoService().cambiar_estado(_admin(db), uid, False)

    acceso = AccesoService()
    ev = acceso.evaluar(pid)
    assert ev.estado == PROPUESTA and ev.modo == "socio"
    assert [(o.clave, o.boton) for o in ev.opciones] == [(ENTRENAR, "Entrar")]
    assert acceso.confirmar(ev, ENTRENAR).registrado
    assert _fichajes(db, uid) == 0
    with pytest.raises(ValueError):                                    # tampoco por la puerta de atrás
        acceso.confirmar(ev, FICHAR)


def test_reactivar_devuelve_el_acceso(abierto_todo_el_dia):
    db = abierto_todo_el_dia
    pid = persona(db)
    membresia(db, socio(db, pid))
    uid = usuario(db, pid, "profe")
    servicio, admin = EmpleadoService(), _admin(db)
    servicio.cambiar_estado(admin, uid, False)
    servicio.cambiar_estado(admin, uid, True)

    sesion = AuthService().autenticar("profe", "clave-segura")
    assert sesion.usuario_id == uid and sesion.puede(auth.ACCESO_OPERAR_CAMARA)
    acceso = AccesoService()
    ev = acceso.evaluar(pid)
    assert ev.modo == "ambos" and [o.clave for o in ev.opciones if o.habilitada] == [FICHAR, ENTRENAR]
    assert acceso.confirmar(ev, FICHAR).registrado
    assert _fichajes(db, uid) == 1
