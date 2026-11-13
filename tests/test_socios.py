"""Socios: validación por campo, pantalla (servicio falso) y lista contra la base."""
import os
from datetime import date

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

from apoyo_db import membresia, persona, requiere_base, socio  # noqa: E402
from services.auth_service import ENTRENADOR, Sesion  # noqa: E402
from services.persona_service import DatosInvalidos, PersonaService  # noqa: E402
from ui import tema  # noqa: E402

PROFE = Sesion(2, 2, "profe", "Sofía Romero", frozenset({ENTRENADOR}))
FOTOS = {"frente": b"f", "perfil_izquierdo": b"i", "perfil_derecho": b"d"}
DATOS = {"dni": "30.111.222", "nombre": "Juan", "apellido": "Pérez", "celular": "",
         "contacto_emergencia_nombre": "", "contacto_emergencia_telefono": "388 412-3456"}


@pytest.fixture(scope="module")
def app():
    aplicacion = QApplication.instance() or QApplication([])
    tema.aplicar_tema(aplicacion)
    return aplicacion


# --- Validación ---

def test_validacion_por_campo():
    validar = PersonaService.validar_socio
    assert validar(DATOS, FOTOS) == {}
    errores = validar({"dni": "12", "nombre": " ", "apellido": "", "celular": "abc",
                       "contacto_emergencia_telefono": ""}, {"frente": b"f"})
    assert set(errores) == {"dni", "nombre", "apellido", "celular", "contacto_emergencia_telefono", "fotos"}
    assert errores["fotos"] == "Cargá las 3 fotos (frente y los dos perfiles)."


def test_persona_existente_reutiliza_datos_y_fotos():
    validar = PersonaService.validar_socio
    entrenador = {"nombre": "Sofía", "apellido": "Romero", "fotos": 3, "es_socio": False}
    assert validar(dict(DATOS, nombre="", apellido=""), {}, entrenador) == {}
    assert validar(DATOS, {}, dict(entrenador, fotos=0))["fotos"] == "La persona no tiene fotos: cargá las 3."
    assert validar(DATOS, {}, dict(entrenador, es_socio=True, socio_activo=True))["dni"] == "Esa persona ya es socio."


# --- Pantalla ---

class FotosFalsas(QWidget):
    def __init__(self, fotos=None):
        super().__init__()
        self._fotos = dict(fotos or {})

    def fotos(self):
        return dict(self._fotos)

    def frente_detectable(self):
        return True

    def limpiar(self):
        self._fotos = {}


class ServicioFalso:
    validar_socio = staticmethod(PersonaService.validar_socio)

    def __init__(self, existente=None, falla=False):
        self.existente, self.falla = existente, falla
        self.registrados, self.busquedas = [], []
        self.filas = [(1, 1, "30111222", "Juan", "Pérez", None, True, "Pase libre", "vigente", "al_dia",
                       date(2026, 12, 5), 0),
                      (2, 2, "20333444", "Luis", "Gómez", None, False, None, None, None, None, None)]

    def buscar_persona(self, sesion, dni):
        if dni == "1":
            raise DatosInvalidos("El DNI debe tener 7 u 8 dígitos.")
        return self.existente

    def registrar_socio(self, sesion, datos, fotos, telefono, nombre_contacto=None):
        if self.falla:
            raise ConnectionError("sin conexión")
        self.registrados.append((datos["dni"], telefono, nombre_contacto, sorted(fotos)))

    def listar_socios(self, sesion, texto=None):
        self.busquedas.append(texto)
        if texto:
            return [f for f in self.filas if texto.lower() in f"{f[3]} {f[4]} {f[2]}".lower()]
        return self.filas


def _pagina(app, servicio=None, fotos=None):
    from ui.socios_page import SociosPage
    pagina = SociosPage(PROFE, servicio or ServicioFalso(), FotosFalsas(fotos))
    pagina.resize(1200, 800)
    pagina.show()
    app.processEvents()
    return pagina


def _completar(pagina, datos=DATOS):
    pagina.dni.setText(datos["dni"])
    pagina.nombre.setText(datos["nombre"])
    pagina.apellido.setText(datos["apellido"])
    pagina.emergencia_telefono.setText(datos["contacto_emergencia_telefono"])


def test_registrar_socio(app):
    pagina = _pagina(app, fotos=FOTOS)
    _completar(pagina)
    pagina.registrar()
    assert pagina.servicio.registrados == [("30.111.222", "388 412-3456", None,
                                            ["frente", "perfil_derecho", "perfil_izquierdo"])]
    assert "Cobros y renovaciones" in pagina.resultado.text() and pagina.dni.text() == ""


def test_errores_al_lado_de_cada_campo(app):
    pagina = _pagina(app)
    pagina.registrar()
    assert pagina.campos["dni"].tiene_error() and pagina.campos["nombre"].tiene_error()
    assert pagina.campos["contacto_emergencia_telefono"].mensaje.text() == "Escribí un teléfono de emergencia."
    assert pagina.campos["fotos"].tiene_error() and pagina.servicio.registrados == []


def test_dni_de_una_persona_existente(app):
    servicio = ServicioFalso(existente={"persona_id": 9, "nombre": "Sofía", "apellido": "Romero",
                                        "fotos": 3, "es_socio": False, "socio_activo": False})
    pagina = _pagina(app, servicio)
    pagina.dni.setText("27555888")
    pagina.buscar_dni()
    assert pagina.nombre.text() == "Sofía" and pagina.nombre.isReadOnly()
    assert pagina.aviso_persona.isVisible()
    pagina.emergencia_telefono.setText("3884000000")
    pagina.registrar()                                     # sin fotos nuevas: usa las que ya tiene
    assert servicio.registrados and servicio.registrados[0][3] == []


def test_dni_que_ya_es_socio(app):
    servicio = ServicioFalso(existente={"persona_id": 9, "nombre": "Juan", "apellido": "Pérez",
                                        "fotos": 3, "es_socio": True, "socio_activo": True})
    pagina = _pagina(app, servicio)
    pagina.dni.setText("30111222")
    pagina.buscar_dni()
    assert pagina.campos["dni"].mensaje.text() == "Esa persona ya es socio."


def test_error_de_base_al_registrar(app):
    pagina = _pagina(app, ServicioFalso(falla=True), FOTOS)
    _completar(pagina)
    pagina.registrar()
    assert pagina.resultado.text().startswith("No se pudo registrar el socio.")


def test_lista_y_busqueda(app):
    from ui.tablas import textos
    pagina = _pagina(app)
    assert [f[:2] for f in textos(pagina.tabla)] == [["Juan Pérez", "30.111.222"], ["Luis Gómez", "20.333.444"]]
    estado = pagina.tabla.cellWidget(1, 2).findChildren(type(pagina.lista_vacia))
    assert any(e.text() == "Dado de baja" for e in estado)
    pagina.busqueda.setText("gómez")
    pagina.cargar_lista()
    assert [f[0] for f in textos(pagina.tabla)] == ["Luis Gómez"]
    pagina.busqueda.setText("nadie")
    pagina.cargar_lista()
    assert pagina.lista_vacia.text() == "No hay socios que coincidan con la búsqueda."


# --- Base de datos ---

@requiere_base
def test_listar_socios_con_su_estado(db):
    juan = socio(db, persona(db))
    membresia(db, juan)
    socio(db, persona(db, "20333444", "Luis", "Gómez"))
    db.execute("UPDATE socio SET activo = FALSE, fecha_baja = CURRENT_DATE WHERE id <> %s", (juan,))
    servicio = PersonaService()
    filas = servicio.listar_socios(PROFE)
    assert [(f[3], f[6], f[8]) for f in filas] == [("Ana", True, "vigente"), ("Luis", False, None)]
    assert [f[3] for f in servicio.listar_socios(PROFE, "333")] == ["Luis"]
    assert [f[3] for f in servicio.listar_socios(PROFE, "ana pé")] == ["Ana"]
