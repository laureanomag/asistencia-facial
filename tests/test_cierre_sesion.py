"""Cerrar sesión y cambiar de usuario sin cerrar el programa (Qt offscreen,
sin cámara, sin proceso de reconocimiento real y sin base de datos)."""
import os
import subprocess
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

from services.auth_service import ADMINISTRADOR, ENTRENADOR, Sesion  # noqa: E402
from ui import tema  # noqa: E402
from test_control_acceso_ui import (  # noqa: E402
    PROPUESTA_ANA, Accesos, Camara, Detector, Fichajes, Horario, Reloj, Worker,
)
from test_ui_tema import _HorarioFalso, _menu  # noqa: E402

DUENIA = Sesion(1, None, "admin", "Administrador", frozenset({ADMINISTRADOR}))
PROFE = Sesion(2, 2, "profe", "Sofía Romero", frozenset({ENTRENADOR}))


@pytest.fixture(scope="module")
def app():
    aplicacion = QApplication.instance() or QApplication([])
    tema.aplicar_tema(aplicacion)
    return aplicacion


class PaginaFalsa(QWidget):
    def __init__(self):
        super().__init__()
        self.liberaciones = 0

    def liberar(self):
        self.liberaciones += 1


def _ventana(sesion, confirma=True, paginas=None):
    from ui.main_window import MainWindow
    preguntas = []

    def confirmar(_ventana, nombre):
        preguntas.append(nombre)
        return confirma
    ventana = MainWindow(sesion, _HorarioFalso(), paginas=paginas, fabricas={}, confirmar=confirmar)
    ventana.preguntas = preguntas
    return ventana


# --- Menú de la cuenta ---

def test_tarjeta_de_usuario_abre_el_menu_de_la_cuenta(app):
    ventana = _ventana(PROFE)
    ventana.show()
    app.processEvents()
    textos = [a.text() for a in ventana.menu_cuenta.actions() if not a.isSeparator()]
    assert textos == ["Cambiar contraseña", "Cerrar sesión"]
    assert ventana.tarjeta_usuario.nombre.text() == "Sofía Romero"
    assert ventana.tarjeta_usuario.rol.text() == "Entrenador"
    ventana.tarjeta_usuario.clicked.emit()
    app.processEvents()
    assert ventana.menu_cuenta.isVisible()
    ventana.menu_cuenta.close()
    ventana.close()


def test_cerrar_sesion_pide_confirmacion_y_si_se_cancela_no_hace_nada(app):
    pagina = PaginaFalsa()
    ventana = _ventana(PROFE, confirma=False, paginas={"socios": pagina})
    cerradas = []
    ventana.sesion_cerrada.connect(lambda: cerradas.append(True))
    assert ventana.cerrar_sesion() is False
    assert ventana.preguntas == ["Sofía Romero"]
    assert cerradas == [] and pagina.liberaciones == 0


def test_cerrar_sesion_libera_las_pantallas_una_sola_vez(app):
    pagina = PaginaFalsa()
    ventana = _ventana(PROFE, paginas={"socios": pagina})
    cerradas = []
    ventana.sesion_cerrada.connect(lambda: cerradas.append(True))
    assert ventana.cerrar_sesion() is True
    assert cerradas == [True] and pagina.liberaciones == 1
    ventana.close()                       # el cierre posterior no vuelve a liberar
    assert pagina.liberaciones == 1


def test_una_pantalla_que_falla_al_liberar_no_impide_salir(app):
    class Rota(PaginaFalsa):
        def liberar(self):
            raise RuntimeError("cámara trabada")
    otra = PaginaFalsa()
    ventana = _ventana(PROFE, paginas={"acceso": Rota(), "socios": otra})
    assert ventana.cerrar_sesion() is True
    assert otra.liberaciones == 1


# --- Control de acceso al cerrar sesión ---

def _control(app, abrir_modal=None):
    from ui.control_acceso_page import ControlAccesoPage
    p = ControlAccesoPage(worker=Worker(), camara=Camara(), detector=Detector(), accesos=Accesos(),
                          fichajes=Fichajes(),
                          abrir_modal=abrir_modal, reloj=Reloj(), horario=Horario())
    p.resize(1000, 700)
    p.show()
    app.processEvents()
    return p


def test_liberar_detiene_camara_y_reconocimiento(app):
    p = _control(app, abrir_modal=lambda ev, s: None)
    assert p.camara.abierta and p.timer.isActive()
    p.liberar()
    assert not p.camara.abierta and not p.timer.isActive() and p.worker.detenido
    p.liberar()                           # dos veces no falla


def test_modal_abierto_se_cancela_sin_registrar_nada(app):
    # La sesión se cierra mientras el modal está abierto: aunque el modal
    # devolviera una opción, no se envía "confirmar".
    pagina = {}

    def modal_que_se_interrumpe(_evaluacion, _cierre_s):
        pagina["p"].liberar()
        return "entrenar"
    p = _control(app, abrir_modal=modal_que_se_interrumpe)
    pagina["p"] = p
    p.on_respuesta(PROPUESTA_ANA)
    assert "confirmar" not in p.worker.comandos()
    assert p.worker.detenido and not p.camara.abierta


def test_modal_real_se_cierra_al_liberar(app):
    p = _control(app)                     # usa el modal de confirmación real
    QTimer.singleShot(50, p.liberar)      # se cierra la sesión con el modal en pantalla
    p.on_respuesta(PROPUESTA_ANA)         # vuelve cuando el modal se cierra
    assert p._modal is None
    assert "confirmar" not in p.worker.comandos() and p.worker.detenido


def test_respuestas_tardias_se_ignoran(app):
    p = _control(app, abrir_modal=lambda ev, s: None)
    p.liberar()
    consultas = p.accesos.consultas
    p.on_respuesta({"estado": "CONFIRMADO", "mensaje": "ok", "nombre": "Juan Pérez"})
    assert p.accesos.consultas == consultas and not p.camara_panel.aviso.isVisible()


def test_el_proceso_de_reconocimiento_no_queda_colgado():
    from services.face_worker_client import FaceWorkerClient

    class Senales:
        class terminado:
            emitidos = []

            @classmethod
            def emit(cls, datos):
                cls.emitidos.append(datos)
    cliente = FaceWorkerClient(Senales)
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    cliente._adoptar(proc)
    cliente.detener()
    assert proc.poll() is not None        # terminó: no quedó el proceso en segundo plano
    assert Senales.terminado.emitidos == []   # cerrar a propósito no es un error
    cliente.detener()                     # dos veces no falla


# --- Volver al login y entrar con otra cuenta ---

class AuthFalso:
    def __init__(self, sesiones):
        self.sesiones = sesiones

    def autenticar(self, identificador, _contrasenia):
        return self.sesiones[identificador]


def test_login_emite_la_sesion(app):
    from ui.login_window import LoginWindow
    login = LoginWindow(auth_service=AuthFalso({"profe": PROFE}), horario_service=_HorarioFalso())
    recibidas = []
    login.ingreso.connect(recibidas.append)
    login.identifier_input.setText("profe")
    login.password_input.setText("clave-segura")
    login.iniciar_sesion()
    assert recibidas == [PROFE] and login.password_input.text() == ""


def test_cerrar_sesion_vuelve_al_login_y_otra_cuenta_arma_su_menu(app):
    from ui.aplicacion import Aplicacion
    from ui.main_window import MainWindow
    paginas = []

    def crear_principal(sesion, auth, horario):
        pagina = PaginaFalsa()
        paginas.append(pagina)
        return MainWindow(sesion, horario, fabricas={"estado": lambda _v: pagina},
                          auth_service=auth, confirmar=lambda *_: True)
    aplicacion = Aplicacion(AuthFalso({"admin": DUENIA, "profe": PROFE}), _HorarioFalso(),
                            crear_principal=crear_principal)
    aplicacion.iniciar()
    app.processEvents()
    assert aplicacion.login.isVisible()

    aplicacion.login.ingreso.emit(DUENIA)
    app.processEvents()
    primera = aplicacion.principal
    assert aplicacion.login is None and primera.isVisible()
    assert _menu(primera)[0] == "Panel" and "Control de acceso" not in _menu(primera)

    assert primera.cerrar_sesion()
    app.processEvents()
    assert aplicacion.principal is None and not primera.isVisible()
    assert aplicacion.login.isVisible()            # el programa sigue abierto
    assert paginas[0].liberaciones == 1

    aplicacion.login.ingreso.emit(PROFE)
    app.processEvents()
    segunda = aplicacion.principal
    assert segunda is not primera and paginas[1] is not paginas[0]
    assert _menu(segunda) == ["Control de acceso", "Socios", "Cobros y renovaciones",
                              "Estado del socio", "Fichajes"]
    assert segunda.tarjeta_usuario.nombre.text() == "Sofía Romero"
    assert segunda.sesion is PROFE
    segunda.close()
