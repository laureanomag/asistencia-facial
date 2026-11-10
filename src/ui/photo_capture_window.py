from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QDialog, QPushButton, QVBoxLayout, QHBoxLayout, QMessageBox
)

from hardware.camera_controller import CameraController
from ui.frame_utils import frame_to_pixmap, frame_to_jpeg_bytes
from ui.video_panel import VideoPanel


class PhotoCaptureWindow(QDialog):
    """
    Ventana que se abre al hacer clic en "Tomar Foto": muestra la webcam en
    vivo y permite capturar una fotografía, que luego se devuelve al
    ImageSlotWidget que la invocó.

    Flujo: abrir ventana -> webcam en vivo -> capturar fotografía -> cerrar
    ventana -> la foto queda disponible para mostrarse en el formulario.

    Comparte la webcam con el resto de la aplicación: si la cámara de
    Asistencia está abierta, sigue abierta al cerrar esta ventana.
    """

    INTERVALO_MS = 30

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Tomar Foto")

        self.camera_controller = CameraController()
        self._ultimo_frame = None
        self._imagen_capturada_bytes = None
        self._pixmap_capturado = None

        self.video_panel = VideoPanel()
        self.video_panel.setText("Iniciando cámara...")

        self.capturar_button = QPushButton("Capturar Foto")
        self.cancelar_button = QPushButton("Cancelar")
        self.capturar_button.clicked.connect(self._capturar)
        self.cancelar_button.clicked.connect(self.reject)

        botones_layout = QHBoxLayout()
        botones_layout.addWidget(self.capturar_button)
        botones_layout.addWidget(self.cancelar_button)

        layout = QVBoxLayout()
        layout.addWidget(self.video_panel)
        layout.addLayout(botones_layout)
        self.setLayout(layout)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._actualizar_frame)

        if self.camera_controller.open():
            self.timer.start(self.INTERVALO_MS)
        else:
            QMessageBox.critical(
                self, "Cámara no disponible",
                "No se pudo acceder a la cámara del sistema.",
            )
            self.capturar_button.setEnabled(False)

    def _actualizar_frame(self):
        frame = self.camera_controller.read_frame()
        if frame is None:
            return

        self._ultimo_frame = frame
        alto, ancho = frame.shape[:2]
        self.video_panel.set_aspect_ratio(ancho, alto)
        self.video_panel.mostrar_frame(frame_to_pixmap(frame, espejo=True))

    def _capturar(self):
        if self._ultimo_frame is None:
            return

        self._imagen_capturada_bytes = frame_to_jpeg_bytes(self._ultimo_frame)
        # La miniatura se ve como la vista previa (espejo); los bytes guardados
        # en la base de datos siguen siendo la imagen original sin voltear.
        self._pixmap_capturado = frame_to_pixmap(self._ultimo_frame, espejo=True)
        self.accept()

    def get_image_bytes(self):
        return self._imagen_capturada_bytes

    def get_pixmap(self):
        return self._pixmap_capturado

    def done(self, result):
        """Se ejecuta siempre al cerrar el diálogo (Capturar, Cancelar o la
        X de la ventana): suelta la parte de la cámara que usaba esta
        ventana, para no dejar la webcam ocupada en ningún caso."""
        self.timer.stop()
        self.camera_controller.close()
        super().done(result)
