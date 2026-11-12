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
    ({ENTRENADOR}, ["Control de acceso", "Socios", "Estado del socio", "Fichajes"]),
    ({ADMINISTRADOR}, ["Control de acceso", "Socios", "Cobros y renovaciones", "Estado del socio",
                       "Fichajes", "Jornadas", "Informes", "Configuración"]),
])
def test_menu_segun_permisos(app, roles, esperado):
    from ui.main_window import MainWindow
    ventana = MainWindow(_sesion(*roles), _HorarioFalso())
    assert _menu(ventana) == esperado


def test_encabezado_con_reloj_y_estado(app):
    from ui.main_window import MainWindow
    ventana = MainWindow(_sesion(RECEPCIONISTA), _HorarioFalso())
    assert ventana.encabezado.titulo.text() == "Control de acceso"
    assert ventana.encabezado.subtitulo.text() == "Jueves 12/11 · 18:42 · Mirá a la cámara para ingresar"
    assert ventana.indicador.texto() == "Abierto · cierra a las 23:00"
    assert ventana.indicador.property("tono") == "verde"
    ventana.seleccionar(3)
    assert ventana.encabezado.titulo.text() == "Estado del socio"
    assert ventana.botones.button(3).isChecked() and not ventana.botones.button(0).isChecked()


def test_sin_base_de_datos_la_ventana_igual_abre(app):
    from ui.main_window import MainWindow
    ventana = MainWindow(_sesion(ADMINISTRADOR), _HorarioFalso(falla=True))
    assert ventana.indicador.texto() == "Sin conexión con la base de datos"
    assert ventana.indicador.property("tono") == "rojo"


def test_pie_del_login_sale_del_horario(app):
    from ui.login_window import LoginWindow, pie_login
    assert pie_login(_HorarioFalso()) == "San Pedrito, Jujuy · Lun a Vie 7:30–23 · Sáb 10–14"
    assert pie_login(_HorarioFalso(falla=True)) == "San Pedrito, Jujuy"
    login = LoginWindow(auth_service=object(), horario_service=_HorarioFalso())
    assert login.pie.text() == "San Pedrito, Jujuy · Lun a Vie 7:30–23 · Sáb 10–14"


@pytest.mark.parametrize("nombre, esperado", [
    ("Juan Pérez", "JP"), ("Lucas Díaz", "LD"), ("admin", "AD"), ("", "?"),
])
def test_iniciales(nombre, esperado):
    assert iniciales(nombre) == esperado


def test_textos_sin_vocabulario_de_alumnos(app):
    from ui import main_window
    textos = " ".join(f"{s.menu} {s.titulo} {s.subtitulo}" for s in main_window.SECCIONES).lower()
    for palabra in ("alumno", "cátedra", "catedra", "profesor"):
        assert palabra not in textos
