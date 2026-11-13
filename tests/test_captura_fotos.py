"""Toma guiada de las 3 fotos (sin cámara: ventanas y detector simulados)."""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import cv2  # noqa: E402
import numpy as np  # noqa: E402
import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

from services.face_service import tiene_rostro_detectable  # noqa: E402
from ui import captura_fotos as cf  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def app():
    return QApplication.instance() or QApplication([])


class Ventanas:
    """Cada ventana "captura" el siguiente valor de la lista (None = Cancelar)."""

    def __init__(self, capturas):
        self.capturas = list(capturas)
        self.titulos, self.indicaciones = [], []

    def __call__(self, parent, titulo, indicacion):
        self.titulos.append(titulo)
        self.indicaciones.append(indicacion)
        valor = self.capturas.pop(0)
        ventanas = self

        class Ventana:
            def exec(self):
                return QDialog.DialogCode.Rejected if valor is None else QDialog.DialogCode.Accepted

            def get_image_bytes(self):
                return valor
        return Ventana()


def _con_rostro(datos):
    return not datos.startswith(b"sin")


def _flujo(capturas, respuestas=()):
    ventanas = Ventanas(capturas)
    respuestas = list(respuestas)
    avisos, preguntas = [], []

    def preguntar(parent, nombre):
        preguntas.append(nombre)
        return respuestas.pop(0)

    fotos = cf.capturar_guiado(crear_ventana=ventanas, detectable=_con_rostro,
                               avisar=lambda parent: avisos.append("frente"), preguntar=preguntar)
    return fotos, ventanas, avisos, preguntas


def test_tres_fotos_con_rostro():
    fotos, ventanas, avisos, preguntas = _flujo([b"f", b"i", b"d"])
    assert fotos == {"frente": b"f", "perfil_izquierdo": b"i", "perfil_derecho": b"d"}
    assert ventanas.titulos == ["Foto 1 de 3 · Frente", "Foto 2 de 3 · Perfil izquierdo",
                                "Foto 3 de 3 · Perfil derecho"]
    assert ventanas.indicaciones[1] == ("Girá la cabeza levemente hacia tu izquierda (unos 15°), "
                                        "que se vean los dos ojos.")
    assert ventanas.indicaciones[2] == ("Girá la cabeza levemente hacia tu derecha (unos 15°), "
                                        "que se vean los dos ojos.")
    assert (avisos, preguntas) == ([], [])


def test_frente_sin_rostro_hay_que_repetirla():
    fotos, ventanas, avisos, _ = _flujo([b"sin-1", b"sin-2", b"f", b"i", b"d"])
    assert fotos["frente"] == b"f" and avisos == ["frente", "frente"]
    assert ventanas.titulos[:3] == ["Foto 1 de 3 · Frente"] * 3


def test_perfil_sin_rostro_repetir_o_usar_igual():
    fotos, ventanas, _, preguntas = _flujo(
        [b"f", b"sin-i", b"i", b"sin-d"], respuestas=[cf.REPETIR, cf.USAR_IGUAL])
    assert fotos == {"frente": b"f", "perfil_izquierdo": b"i", "perfil_derecho": b"sin-d"}
    assert preguntas == ["Perfil izquierdo", "Perfil derecho"]


def test_cancelar_no_devuelve_fotos():
    fotos, _, _, _ = _flujo([b"f", None])
    assert fotos is None


def test_revision_con_el_detector_real():
    """Una imagen sin cara o ilegible no pasa la revisión (mismo detector que
    las referencias)."""
    vacia = cv2.imencode(".jpg", np.zeros((480, 640, 3), np.uint8))[1].tobytes()
    assert not tiene_rostro_detectable(vacia)
    assert not tiene_rostro_detectable(b"no es una imagen")
    assert not tiene_rostro_detectable(None)
    assert cf.revisar_foto("frente", vacia) == cf.FRENTE_SIN_ROSTRO
    assert cf.revisar_foto("perfil_derecho", vacia) == cf.SIN_ROSTRO


def test_mensajes_con_tildes():
    assert "Girá" in cf.INDICACION_PERFIL and "°" in cf.INDICACION_PERFIL
    assert cf.MENSAJE_PERFIL.format(nombre="perfil derecho").startswith("La foto de perfil derecho")


def test_script_revisa_las_fotos_de_archivo(tmp_path, capsys):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import cargar_socio_prueba as script
    rutas = []
    for nombre, contenido in (("f.jpg", b"f"), ("i.jpg", b"sin-i"), ("d.jpg", b"d")):
        ruta = tmp_path / nombre
        ruta.write_bytes(contenido)
        rutas.append(str(ruta))
    fotos = script.leer_fotos(rutas, detectable=_con_rostro)
    assert list(fotos) == ["frente", "perfil_izquierdo", "perfil_derecho"]
    assert "perfil izquierdo" in capsys.readouterr().out
    (tmp_path / "f.jpg").write_bytes(b"sin-f")
    with pytest.raises(SystemExit, match="foto de frente"):
        script.leer_fotos(rutas, detectable=_con_rostro)


def test_guardar_requiere_clic_y_cancelar_es_por_defecto():
    from PySide6.QtCore import Qt
    from ui.captura_fotos import ConfirmarFotos
    dialogo = ConfirmarFotos({"frente": b"f", "perfil_izquierdo": b"i", "perfil_derecho": b"d"},
                             detectable=_con_rostro)
    assert dialogo.cancelar.isDefault() and not dialogo.guardar.autoDefault()
    assert dialogo.guardar.focusPolicy() == Qt.FocusPolicy.NoFocus
    dialogo.guardar.click()
    assert dialogo.result() == QDialog.DialogCode.Accepted


def test_ventana_de_captura_no_se_dispara_con_el_teclado(monkeypatch):
    from PySide6.QtCore import Qt
    import ui.photo_capture_window as pcw

    class SinCamara:
        def open(self): return True
        def close(self): pass
        def read_frame(self): return None

    monkeypatch.setattr(pcw, "CameraController", SinCamara)
    ventana = pcw.PhotoCaptureWindow(None, titulo="Foto 1 de 3 · Frente")
    assert not ventana.capturar_button.autoDefault() and not ventana.capturar_button.isDefault()
    assert ventana.capturar_button.focusPolicy() == Qt.FocusPolicy.NoFocus
    ventana.done(0)


# --- Ventana de captura: cámara, cierre y vista previa ---

class Reloj:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def _ventana(camara, reloj=None):
    import ui.photo_capture_window as pcw
    return pcw.PhotoCaptureWindow(None, titulo="Foto 2 de 3 · Perfil izquierdo",
                                  indicacion="Girá la cabeza", camara=camara, reloj=reloj or Reloj())


def _frame():
    import numpy as np
    frame = np.zeros((90, 160, 3), np.uint8)
    frame[:, :80] = (0, 0, 255)                   # mitad izquierda roja (BGR)
    return frame


@pytest.fixture
def webcam_falsa(monkeypatch):
    """cv2.VideoCapture falsa: cuenta aperturas y liberaciones de la webcam real compartida."""
    import hardware.camera_controller as cc

    class Captura:
        abiertas = 0

        def __init__(self, _indice):
            Captura.abiertas += 1
            self.liberada = False

        def isOpened(self):
            return True

        def set(self, *_):
            return True

        def read(self):
            return True, _frame()

        def release(self):
            Captura.abiertas -= 1

    monkeypatch.setattr(cc.cv2, "VideoCapture", Captura)
    monkeypatch.setattr(cc, "_DISPOSITIVOS", {})
    return Captura


def test_abrir_y_cerrar_la_captura_tres_veces(app, webcam_falsa):
    from hardware.camera_controller import CameraController
    for vuelta in range(3):
        reloj = Reloj()
        ventana = _ventana(CameraController(), reloj)
        ventana.show()
        assert webcam_falsa.abiertas == 1
        ventana._actualizar_frame()
        reloj.t = 0.6
        ventana._actualizar_frame()
        assert ventana.isVisible() and ventana.capturar_button.isEnabled()
        if vuelta == 1:
            ventana.cancelar_button.click()
            assert ventana.result() == QDialog.DialogCode.Rejected and ventana.motivo_cierre == "cancelar"
        else:
            ventana.capturar_button.click()
            assert ventana.result() == QDialog.DialogCode.Accepted and ventana.get_image_bytes()
        assert not ventana.isVisible()
        assert webcam_falsa.abiertas == 0             # la webcam queda libre después de cada vuelta


def test_la_captura_comparte_la_camara_con_control_de_acceso(app, webcam_falsa):
    from hardware.camera_controller import CameraController
    acceso = CameraController()
    assert acceso.open()
    ventana = _ventana(CameraController())
    ventana.done(0)
    assert webcam_falsa.abiertas == 1 and acceso.read_frame() is not None    # sigue andando
    acceso.close()
    assert webcam_falsa.abiertas == 0


def test_no_se_cierra_sola_ni_con_el_teclado(app):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    class Camara:
        def open(self): return True
        def close(self): pass
        def read_frame(self): return _frame()
    reloj = Reloj()
    ventana = _ventana(Camara(), reloj)
    ventana.show()
    for tecla in (Qt.Key.Key_Escape, Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
        QTest.keyClick(ventana, tecla)
    assert ventana.isVisible() and ventana.result() == 0
    ventana._actualizar_frame()
    ventana.capturar_button.click()                   # doble clic apurado: todavía no captura
    assert ventana.isVisible() and ventana.get_image_bytes() is None
    reloj.t = 0.6
    ventana._actualizar_frame()
    ventana.capturar_button.click()
    assert not ventana.isVisible() and ventana.get_image_bytes()


def test_sin_camara_avisa_y_reintenta(app):
    class Camara:
        def __init__(self):
            self.intentos = 0
        def open(self):
            self.intentos += 1
            return self.intentos >= 2
        def close(self): pass
        def read_frame(self): return _frame()
    camara = Camara()
    ventana = _ventana(camara)
    ventana.show()
    assert ventana.isVisible() and not ventana.capturar_button.isEnabled()
    assert ventana.video_panel.text().startswith("No se pudo abrir la cámara.")
    assert ventana.reintento.isActive()
    ventana._abrir_camara()                           # el reintento la abre
    assert not ventana.reintento.isActive() and ventana.timer.isActive()
    ventana.cancelar_button.click()


def test_vista_previa_sin_espejo(app):
    class Camara:
        def open(self): return True
        def close(self): pass
        def read_frame(self): return _frame()
    reloj = Reloj()
    ventana = _ventana(Camara(), reloj)
    ventana._actualizar_frame()
    reloj.t = 0.6
    ventana._actualizar_frame()
    ventana.capturar_button.click()
    imagen = ventana.get_pixmap().toImage()
    assert imagen.pixelColor(5, 45).red() > 200 and imagen.pixelColor(150, 45).red() < 50   # rojo a la izquierda
