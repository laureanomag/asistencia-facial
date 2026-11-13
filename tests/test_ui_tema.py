"""Pruebas de la interfaz (sin pantalla: Qt en modo offscreen)."""
import os
from datetime import datetime, time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from services.auth_service import ADMINISTRADOR, ENTRENADOR, RECEPCIONISTA, Sesion  # noqa: E402
from services.reglas_ingreso import Franja  # noqa: E402
from ui import tema  # noqa: E402
from ui.componentes import iniciales  # noqa: E402


@pytest.fixture(scope="module")
def app():
    aplicacion = QApplication.instance() or QApplication([])
    tema.aplicar_tema(aplicacion)
    return aplicacion


class _HorarioFalso:
    def __init__(self, falla=False):
        self.falla = falla

    def franjas_semana(self):
        if self.falla:
            raise ConnectionError("sin base")
        semana = {d: [Franja(time(7, 30), time(23, 0))] for d in range(1, 6)}
        semana[6] = [Franja(time(10, 0), time(14, 0))]
        return semana

    def estado_actual(self):
        if self.falla:
            raise ConnectionError("sin base")
        return True, "Abierto · cierra a las 23:00", datetime(2026, 11, 12, 18, 42)


def _sesion(*roles, nombre="Ana Pérez"):
    return Sesion(1, 10, "ana", nombre, frozenset(roles))


def _menu(ventana):
    return [ventana.botones.button(i).texto() for i in range(len(ventana.secciones))]


def test_tipografias_y_logo_disponibles(app):
    assert {"Montserrat", "Inter"} <= tema.cargar_tipografias()
    assert tema.LOGO.exists()
    assert app.font().family() == "Inter"


def test_hoja_de_estilos_usa_la_paleta(app):
    qss = tema.hoja_de_estilos()
    for color in (tema.FONDO, tema.PANEL, tema.BORDE, tema.DORADO, tema.VERDE, tema.ROJO, tema.AMBAR):
        assert color in qss


@pytest.mark.parametrize("roles, esperado", [
    ({RECEPCIONISTA}, ["Control de acceso", "Socios", "Cobros y renovaciones", "Estado del socio",
                       "Fichajes"]),
    ({ENTRENADOR}, ["Control de acceso", "Socios", "Cobros y renovaciones", "Estado del socio",
                    "Fichajes"]),
    ({ADMINISTRADOR}, ["Panel", "Informes", "Estado del socio", "Empleados", "Jornadas", "Fichajes",
                       "Configuración"]),
    ({ADMINISTRADOR, ENTRENADOR}, ["Panel", "Informes", "Estado del socio", "Empleados", "Jornadas",
                                   "Fichajes", "Configuración", "Control de acceso", "Socios",
                                   "Cobros y renovaciones"]),
])
def test_menu_segun_permisos(app, roles, esperado):
    from ui.main_window import MainWindow
    ventana = MainWindow(_sesion(*roles), _HorarioFalso(), fabricas={})
    assert _menu(ventana) == esperado


def test_encabezado_con_reloj_y_estado(app):
    from ui.main_window import MainWindow
    ventana = MainWindow(_sesion(RECEPCIONISTA), _HorarioFalso(), fabricas={})
    assert ventana.encabezado.titulo.text() == "Control de acceso"
    assert ventana.encabezado.subtitulo.text() == "Jueves 12/11 · 18:42 · Mirá a la cámara para ingresar"
    assert ventana.indicador.texto() == "Abierto · cierra a las 23:00"
    assert ventana.indicador.property("tono") == "verde"
    ventana.seleccionar(3)
    assert ventana.encabezado.titulo.text() == "Estado del socio"
    assert ventana.botones.button(3).isChecked() and not ventana.botones.button(0).isChecked()


def test_sin_base_de_datos_la_ventana_igual_abre(app):
    from ui.main_window import MainWindow
    ventana = MainWindow(_sesion(ADMINISTRADOR), _HorarioFalso(falla=True), fabricas={})
    assert ventana.indicador.texto() == "Sin conexión con la base de datos"
    assert ventana.indicador.property("tono") == "rojo"


def test_pie_del_login_sale_del_horario(app):
    from ui.login_window import LoginWindow, pie_login
    direccion = "Av. Corrientes 2833 · San Pedrito, San Salvador de Jujuy"
    assert pie_login(_HorarioFalso()) == f"{direccion}\nLun a Vie 7:30–23 · Sáb 10–14"
    assert pie_login(_HorarioFalso(falla=True)) == direccion
    login = LoginWindow(auth_service=object(), horario_service=_HorarioFalso())
    assert login.pie.text() == f"{direccion}\nLun a Vie 7:30–23 · Sáb 10–14"


@pytest.mark.parametrize("nombre, esperado", [
    ("Juan Pérez", "JP"), ("Lucas Díaz", "LD"), ("admin", "AD"), ("", "?"),
])
def test_iniciales(nombre, esperado):
    assert iniciales(nombre) == esperado


def test_textos_sin_vocabulario_de_alumnos(app):
    from ui import main_window
    textos = " ".join(f"{s.menu} {s.titulo} {s.subtitulo}" for s in main_window.SECCIONES.values()).lower()
    for palabra in ("alumno", "cátedra", "catedra", "profesor"):
        assert palabra not in textos


def test_administrador_empieza_en_el_panel_sin_camara(app):
    from PySide6.QtWidgets import QLabel
    from ui.main_window import MainWindow
    creadas = []
    fabricas = {"acceso": lambda v: creadas.append("camara") or QLabel("cámara"),
                "panel": lambda v: QLabel("panel")}
    ventana = MainWindow(_sesion(ADMINISTRADOR), _HorarioFalso(), fabricas=fabricas)
    assert ventana.encabezado.titulo.text() == "Panel"
    assert "acceso" not in ventana.paginas and creadas == []      # la cámara no se inicia


def test_pantalla_que_falla_no_cierra_la_app(app):
    from ui.main_window import MainWindow, PaginaConError

    def falla(ventana):
        raise ConnectionError("sin base de datos")
    ventana = MainWindow(_sesion(ADMINISTRADOR), _HorarioFalso(), fabricas={"panel": falla})
    assert isinstance(ventana.paginas["panel"], PaginaConError)


def test_modulo_todavia_inexistente_queda_pendiente(app):
    from ui.main_window import MainWindow, PaginaPendiente, _por_modulo
    ventana = MainWindow(_sesion(ADMINISTRADOR), _HorarioFalso(),
                         fabricas={"panel": _por_modulo("ui.no_existe", "Nada")})
    assert "panel" not in ventana.paginas
    assert isinstance(ventana.stack.widget(0), PaginaPendiente)


def test_mensajes_de_error_en_espanol():
    import psycopg
    from main import mensaje_de_error
    assert mensaje_de_error(psycopg.OperationalError, "timeout").startswith(
        "No se pudo comunicar con la base de datos")
    assert mensaje_de_error(ValueError, "x").startswith("Ocurrió un error inesperado. La aplicación sigue")
