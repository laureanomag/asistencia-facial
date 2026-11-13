import time

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QPushButton, QVBoxLayout

from hardware.camera_controller import CameraController
from ui.componentes import con_rol, etiqueta
from ui.frame_utils import frame_to_jpeg_bytes, frame_to_pixmap
from ui.video_panel import VideoPanel

MENSAJE_SIN_CAMARA = ("No se pudo abrir la cámara. Revisá que esté conectada y que no la esté usando "
                      "otro programa. Se vuelve a intentar sola cada 2 segundos.")


class PhotoCaptureWindow(QDialog):
    """
    Ventana de "Tomar foto": muestra la webcam en vivo y captura una foto que
    se devuelve a quien la abrió (Socios, Empleados o el script de prueba).

    - La vista previa NO está en espejo: lo que se ve es igual a la foto que
      se guarda.
    - Solo se cierra con "Capturar foto" o "Cancelar" (o la X, que equivale a
      Cancelar). Esc y Enter no la cierran.
    - "Capturar foto" se habilita medio segundo después de que se ve la
      imagen: un doble clic sobre "Tomar foto" no captura sin querer.
    - Si la cámara no se puede abrir, lo avisa en la ventana y reintenta.
    - Comparte la webcam con el resto de la aplicación (CameraController) y la
      suelta siempre al cerrarse.
    """

    INTERVALO_MS = 30
    REINTENTO_MS = 2000
    ESPERA_CAPTURA_S = 0.5

    def __init__(self, parent=None, titulo="Tomar foto", indicacion=None, camara=None, reloj=time.monotonic):
        super().__init__(parent)
        self.setWindowTitle(titulo)
        self.setMinimumWidth(720)

        self.camera_controller = camara if camara is not None else CameraController()
        self._reloj = reloj
        self._ultimo_frame = None
        self._visible_desde = None
        self._imagen_capturada_bytes = None
        self._pixmap_capturado = None
        self.motivo_cierre = None

        self.video_panel = VideoPanel()
        self.video_panel.setStyleSheet(
            "background: #0B0B0B; border: 1px solid #2A2A2A; border-radius: 12px; color: #A8A8A8;")
        self.video_panel.setText("Iniciando cámara...")
        self.video_panel.setWordWrap(True)

        self.capturar_button = con_rol(QPushButton("Capturar foto"), "primario")
        self.cancelar_button = QPushButton("Cancelar")
        self.capturar_button.setMinimumHeight(48)
        self.cancelar_button.setMinimumHeight(48)
        self.capturar_button.clicked.connect(self._capturar)
        self.cancelar_button.clicked.connect(self._cancelar)
        # Capturar solo con un clic: ni Enter ni Espacio (por ejemplo, teclas
        # escritas en otra ventana) pueden disparar una captura.
        for boton in (self.capturar_button, self.cancelar_button):
            boton.setAutoDefault(False)
            boton.setDefault(False)
        self.capturar_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.capturar_button.setEnabled(False)

        botones_layout = QHBoxLayout()
        botones_layout.setSpacing(12)
        botones_layout.addWidget(self.cancelar_button, 1)
        botones_layout.addWidget(self.capturar_button, 2)

        layout = QVBoxLayout()
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(12)
        layout.addWidget(etiqueta(titulo, "titulo-panel"))
        if indicacion:
            self.indicacion = etiqueta(indicacion, "subtitulo")
            self.indicacion.setWordWrap(True)
            layout.addWidget(self.indicacion)
        layout.addWidget(self.video_panel)
        layout.addLayout(botones_layout)
        self.setLayout(layout)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._actualizar_frame)
        self.reintento = QTimer(self)
        self.reintento.timeout.connect(self._abrir_camara)
        self._abrir_camara()

    def _abrir_camara(self):
        if self.camera_controller.open():
            self.reintento.stop()
            self.video_panel.setText("Iniciando cámara...")
            self.timer.start(self.INTERVALO_MS)
            return True
        print("[Captura] no se pudo abrir la cámara; se reintenta", flush=True)
        self.video_panel.setText(MENSAJE_SIN_CAMARA)
        self.capturar_button.setEnabled(False)
        if not self.reintento.isActive():
            self.reintento.start(self.REINTENTO_MS)
        return False

    def _actualizar_frame(self):
        frame = self.camera_controller.read_frame()
        if frame is None:
            return
        self._ultimo_frame = frame
        alto, ancho = frame.shape[:2]
        self.video_panel.set_aspect_ratio(ancho, alto)
        self.video_panel.mostrar_frame(frame_to_pixmap(frame))        # sin espejo: igual a la foto
        if self._visible_desde is None:
            self._visible_desde = self._reloj()
        if not self.capturar_button.isEnabled() and self._reloj() - self._visible_desde >= self.ESPERA_CAPTURA_S:
            self.capturar_button.setEnabled(True)

    def _capturar(self):
        if self._ultimo_frame is None or not self.capturar_button.isEnabled():
            return
        self._imagen_capturada_bytes = frame_to_jpeg_bytes(self._ultimo_frame)
        self._pixmap_capturado = frame_to_pixmap(self._ultimo_frame)
        self.motivo_cierre = "capturar"
        self.accept()

    def _cancelar(self):
        self.motivo_cierre = "cancelar"
        self.reject()

    def keyPressEvent(self, evento):
        # Esc y Enter no cierran la ventana: solo los botones.
        if evento.key() in (Qt.Key.Key_Escape, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            evento.accept()
            return
        super().keyPressEvent(evento)

    def closeEvent(self, evento):
        # La X de la ventana equivale a Cancelar.
        if self.motivo_cierre is None:
            self.motivo_cierre = "cancelar"
        super().closeEvent(evento)

    def get_image_bytes(self):
        return self._imagen_capturada_bytes

    def get_pixmap(self):
        return self._pixmap_capturado

    def done(self, result):
        """Se ejecuta siempre al cerrar: suelta la parte de la cámara que usaba
        esta ventana, para no dejar la webcam ocupada en ningún caso."""
        self.timer.stop()
        self.reintento.stop()
        self.camera_controller.close()
        print(f"[Captura] ventana cerrada: {self.motivo_cierre or 'sin motivo'}", flush=True)
        super().done(result)
