"""Empleados: servicio (repositorios falsos), pantalla y recuadros de fotos."""
import os
from contextlib import contextmanager

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from services import auth_service as auth  # noqa: E402
from services.auth_service import ADMINISTRADOR, RECEPCIONISTA, AccesoDenegado, ReglaDeCuentas, Sesion  # noqa: E402
from services.empleado_service import EmpleadoService, ErroresFormulario  # noqa: E402
from ui import tema  # noqa: E402

ADMIN = Sesion(1, None, "admin", "Administrador", frozenset({ADMINISTRADOR}))
FOTOS = {"frente": b"f", "perfil_izquierdo": b"i", "perfil_derecho": b"d"}
DATOS = {"dni": "30.111.222", "nombre": "Rocío", "apellido": "Paz", "usuario": "rocio",
         "contrasenia": "inicial-123", "rol": "recepcionista"}


@pytest.fixture(autouse=True)
def bcrypt_rapido(monkeypatch):
    monkeypatch.setattr(auth, "COSTO_BCRYPT", 4)


@pytest.fixture(scope="module")
def app():
    aplicacion = QApplication.instance() or QApplication([])
    tema.aplicar_tema(aplicacion)
    return aplicacion


@contextmanager
def _sin_base():
    yield None


class Base:
    """Personas y usuarios en memoria."""

    def __init__(self):
        self.personas, self.fotos, self.usuarios, self.roles = {}, {}, {}, {}

    # personas
    def obtener_por_dni(self, dni, conn=None):
        for pid, p in self.personas.items():
            if p["dni"] == dni:
                return (pid, dni, p["nombre"], p["apellido"])
        return None

    def contar_fotos(self, persona_id, conn=None):
        return len(self.fotos.get(persona_id, {}))

    def crear(self, datos, conn=None):
        pid = len(self.personas) + 1
        self.personas[pid] = {"dni": datos["dni"], "nombre": datos["nombre"], "apellido": datos["apellido"]}
        return pid

    def guardar_fotos(self, persona_id, fotos, conn=None):
        self.fotos.setdefault(persona_id, {}).update(fotos)

    # usuarios
    def obtener_por_persona(self, persona_id, conn=None):
        return next(((u, d["nombre"], d["activo"]) for u, d in self.usuarios.items()
                     if d["persona_id"] == persona_id), None)

    def existe_nombre_usuario(self, nombre, conn=None):
        return any(d["nombre"].lower() == nombre.lower() for d in self.usuarios.values())

    def crear_usuario(self, persona_id, nombre, contrasenia_hash, debe_cambiar, conn=None):
        uid = len(self.usuarios) + 10
        self.usuarios[uid] = {"persona_id": persona_id, "nombre": nombre, "hash": contrasenia_hash,
                              "debe_cambiar": debe_cambiar, "activo": True}
        self.roles[uid] = set()
        return uid

    def asignar_rol(self, usuario_id, rol, asignado_por=None, conn=None):
        self.roles[usuario_id].add(rol)

    def obtener_roles(self, usuario_id, conn=None):
        return sorted(self.roles.get(usuario_id, ()))

    def actualizar_estado(self, usuario_id, activo, conn=None):
        self.usuarios[usuario_id]["activo"] = activo
        return True

    def listar_personal(self, conn=None):
        return [(u, self.personas[d["persona_id"]]["nombre"], self.personas[d["persona_id"]]["apellido"],
                 self.personas[d["persona_id"]]["dni"], d["nombre"], d["activo"], sorted(self.roles[u]), None)
                for u, d in self.usuarios.items()]


class Usuarios:
    """Adapta Base a la interfaz de UserRepository."""

    def __init__(self, base):
        self.b = base

    def __getattr__(self, nombre):
        return getattr(self.b, nombre)

    def crear(self, *args, **kwargs):
        return self.b.crear_usuario(*args, **kwargs)


def _servicio(base=None, detectable=lambda datos: datos != b"sin"):
    base = base or Base()
    return EmpleadoService(base, Usuarios(base), transaccion=_sin_base, detectable=detectable), base


# --- Servicio ---

def test_alta_de_recepcionista_con_persona_nueva():
    servicio, base = _servicio()
    uid = servicio.registrar(ADMIN, DATOS, FOTOS)
    assert base.personas[1] == {"dni": "30111222", "nombre": "Rocío", "apellido": "Paz"}
    assert base.fotos[1] == FOTOS
    usuario = base.usuarios[uid]
    assert usuario["debe_cambiar"] and usuario["hash"].startswith("$2") and "inicial-123" not in usuario["hash"]
    assert base.roles[uid] == {"recepcionista"}


def test_socio_que_pasa_a_ser_entrenador_reutiliza_la_persona():
    servicio, base = _servicio()
    pid = base.crear({"dni": "30111222", "nombre": "Ana", "apellido": "Pérez"})
    base.guardar_fotos(pid, FOTOS)
    existente = servicio.buscar_por_dni(ADMIN, "30111222")
    assert existente == {"persona_id": pid, "nombre": "Ana", "apellido": "Pérez", "fotos": 3,
                         "tiene_cuenta": False}
    uid = servicio.registrar(ADMIN, {**DATOS, "nombre": "", "apellido": "", "rol": "entrenador"}, {})
    assert len(base.personas) == 1 and base.fotos[pid] == FOTOS     # sin duplicar persona ni fotos
    assert base.usuarios[uid]["persona_id"] == pid and base.roles[uid] == {"entrenador"}


@pytest.mark.parametrize("cambios, fotos, campo", [
    ({"dni": "123"}, FOTOS, "dni"),
    ({"nombre": " "}, FOTOS, "nombre"),
    ({"apellido": ""}, FOTOS, "apellido"),
    ({"usuario": ""}, FOTOS, "usuario"),
    ({"usuario": "con espacio"}, FOTOS, "usuario"),
    ({"contrasenia": "corta"}, FOTOS, "contrasenia"),
    ({"rol": None}, FOTOS, "rol"),
    ({"rol": "administrador"}, FOTOS, "rol"),               # no se crean administradores
    ({}, {"frente": b"f"}, "fotos"),
    ({}, {**FOTOS, "frente": b"sin"}, "fotos"),
])
def test_validacion_por_campo(cambios, fotos, campo):
    servicio, base = _servicio()
    with pytest.raises(ErroresFormulario) as error:
        servicio.registrar(ADMIN, {**DATOS, **cambios}, fotos)
    assert campo in error.value.errores
    assert base.usuarios == {} and base.personas == {}


def test_usuario_repetido_y_persona_con_cuenta():
    servicio, base = _servicio()
    servicio.registrar(ADMIN, DATOS, FOTOS)
    with pytest.raises(ErroresFormulario) as error:
        servicio.registrar(ADMIN, {**DATOS, "dni": "20333444", "usuario": "ROCIO"}, FOTOS)
    assert error.value.errores == {"usuario": "Ese nombre de usuario ya existe."}
    with pytest.raises(ErroresFormulario) as error:
        servicio.registrar(ADMIN, {**DATOS, "usuario": "otra"}, {})
    assert error.value.errores["dni"] == "Esa persona ya tiene una cuenta de usuario."


def test_activar_y_desactivar_solo_al_personal():
    servicio, base = _servicio()
    uid = servicio.registrar(ADMIN, DATOS, FOTOS)
    assert servicio.cambiar_estado(ADMIN, uid, False) and not base.usuarios[uid]["activo"]
    servicio.cambiar_estado(ADMIN, uid, True)
    base.roles[99] = {"administrador"}
    with pytest.raises(ReglaDeCuentas):
        servicio.cambiar_estado(ADMIN, 99, False)


def test_solo_el_administrador():
    servicio, _ = _servicio()
    recepcion = Sesion(2, 5, "r", "R", frozenset({RECEPCIONISTA}))
    for llamada in (lambda: servicio.registrar(recepcion, DATOS, FOTOS),
                    lambda: servicio.listar(recepcion),
                    lambda: servicio.buscar_por_dni(recepcion, "30111222")):
        with pytest.raises(AccesoDenegado):
            llamada()


# --- Recuadros de fotos ---

def test_recuadros_de_fotos(app):
    from ui import captura_fotos as cf
    from ui.fotos_referencia import FotosReferencia
    archivos, avisos = [b"sin", b"f"], []
    fotos = FotosReferencia(tomar=lambda angulo, parent: {"perfil_izquierdo": b"i",
                                                          "perfil_derecho": b"sin"}[angulo],
                            elegir=lambda parent: archivos.pop(0),
                            detectable=lambda datos: datos != b"sin",
                            avisar=lambda parent: avisos.append("frente"),
                            preguntar=lambda parent, nombre: cf.USAR_IGUAL)
    fotos.slots["frente"].cargar_foto()                  # sin rostro: se rechaza y avisa
    assert fotos.fotos() == {} and avisos == ["frente"]
    fotos.slots["frente"].cargar_foto()
    fotos.slots["perfil_izquierdo"].tomar_foto()
    fotos.slots["perfil_derecho"].tomar_foto()           # vía tomar_foto ya revisada: se acepta
    assert fotos.completas() and fotos.frente_detectable()
    assert fotos.slots["perfil_derecho"].estado.text() == "Sin rostro detectable: no se usa para reconocer"
    fotos.slots["frente"].limpiar()
    assert not fotos.completas()


# --- Pantalla ---

class FotosFalsas:
    """Reemplaza al widget de fotos dentro de la pantalla."""

    def __init__(self):
        from PySide6.QtWidgets import QLabel
        self.widget = QLabel("fotos")
        self.datos = dict(FOTOS)

    def __getattr__(self, nombre):
        return getattr(self.widget, nombre)


def _pagina(servicio, confirmar=lambda *a: True):
    from ui.empleados_page import EmpleadosPage
    from ui.fotos_referencia import FotosReferencia
    fotos = FotosReferencia(tomar=lambda a, p: FOTOS[a], detectable=lambda d: d != b"sin")
    pagina = EmpleadosPage(ADMIN, servicio, fotos=fotos, confirmar_accion=confirmar)
    pagina.resize(1100, 800)
    pagina.show()
    return pagina


def test_pantalla_muestra_errores_junto_al_campo(app):
    servicio, _ = _servicio()
    p = _pagina(servicio)
    p.dni.setText("12")
    p.registrar()
    assert p.campos["dni"].mensaje.text() == "El DNI debe tener 7 u 8 dígitos."
    assert p.campos["nombre"].tiene_error() and p.campos["usuario"].tiene_error()
    assert p.campos["fotos"].mensaje.text().startswith("Faltan fotos")
    assert p.campos["contrasenia"].tiene_error() and not p.campos["rol"].tiene_error()


def test_entrenador_elegido_por_defecto(app):
    servicio, _ = _servicio()
    p = _pagina(servicio)
    assert p.rol.currentData() == "entrenador" and p.rol.currentText() == "Entrenador"
    p.rol.setCurrentIndex(p.rol.findData("recepcionista"))
    p.limpiar()
    assert p.rol.currentData() == "entrenador"


def test_pantalla_alta_y_lista(app):
    servicio, base = _servicio()
    p = _pagina(servicio)
    p.dni.setText("30111222")
    p.nombre.setText("Rocío")
    p.apellido.setText("Paz")
    for slot in p.fotos.slots.values():
        slot.tomar_foto()
    p.usuario.setText("rocio")
    p.contrasenia.setText("inicial-123")
    p.rol.setCurrentIndex(p.rol.findData("recepcionista"))
    p.registrar()
    assert p.resultado.text().startswith("Se registró a Rocío Paz como recepcionista")
    assert p.dni.text() == "" and not p.fotos.fotos()
    assert p.tabla.rowCount() == 1 and p.tabla.item(0, 2).text() == "Recepcionista"
    boton = p.tabla.cellWidget(0, 4).findChild(type(p.registrar_boton))
    assert boton.text() == "Desactivar"
    boton.click()
    assert not next(iter(base.usuarios.values()))["activo"]
    assert p.tabla.cellWidget(0, 4).findChild(type(p.registrar_boton)).text() == "Reactivar"


def test_pantalla_reutiliza_persona_por_dni(app):
    servicio, base = _servicio()
    pid = base.crear({"dni": "30111222", "nombre": "Ana", "apellido": "Pérez"})
    base.guardar_fotos(pid, FOTOS)
    p = _pagina(servicio)
    p.dni.setText("30.111.222")
    p.buscar_dni()
    assert (p.nombre.text(), p.nombre.isReadOnly()) == ("Ana", True)
    assert "se reutilizan sus datos" in p.aviso_persona.text()


def test_desactivar_requiere_confirmacion(app):
    servicio, base = _servicio()
    uid = servicio.registrar(ADMIN, DATOS, FOTOS)
    p = _pagina(servicio, confirmar=lambda *a: False)
    p.cargar_lista()
    p.tabla.cellWidget(0, 4).findChild(type(p.registrar_boton)).click()
    assert base.usuarios[uid]["activo"]                     # no confirmó: no cambia
