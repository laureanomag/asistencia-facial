from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QWidget, QFileDialog, QDialog
)

from ui.photo_capture_window import PhotoCaptureWindow


class ImageSlotWidget(QWidget):
    """
    Sección para un ángulo de foto (Frontal, Izquierdo o Derecho).

    Contiene: botón "Cargar Foto" (selecciona un archivo del disco), botón
    "Tomar Foto" (abre la webcam para capturar una foto en el momento), un
    panel que muestra la imagen o "Sin imagen todavía", y un botón rojo de
    basura para borrar la imagen cargada.
    """

    PLACEHOLDER_TEXT = "Sin imagen todavía"

    def __init__(self, titulo):
        super().__init__()
        self._image_bytes = None

        titulo_label = QLabel(titulo)
        titulo_label.setStyleSheet("font-weight: bold;")

        self.cargar_button = QPushButton("Cargar Foto")
        self.tomar_button = QPushButton("Tomar Foto")

        self.cargar_button.clicked.connect(self.cargar_foto)
        self.tomar_button.clicked.connect(self.tomar_foto)

        botones_layout = QHBoxLayout()
        botones_layout.addWidget(self.cargar_button)
        botones_layout.addWidget(self.tomar_button)

        self.panel = QLabel(self.PLACEHOLDER_TEXT)
        self.panel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.panel.setFixedSize(160, 160)
        self.panel.setStyleSheet("border: 1px solid #888; color: #aaa;")

        self.eliminar_button = QPushButton("🗑")
        self.eliminar_button.setFixedSize(28, 28)
        self.eliminar_button.setStyleSheet(
            "background-color: #c0392b; color: white; border-radius: 4px;"
        )
        self.eliminar_button.clicked.connect(self.eliminar_foto)
        self.eliminar_button.setVisible(False)

        panel_layout = QHBoxLayout()
        panel_layout.addWidget(self.panel)
        panel_layout.addWidget(self.eliminar_button)
        panel_layout.addStretch()

        layout = QVBoxLayout()
        layout.addWidget(titulo_label)
        layout.addLayout(botones_layout)
        layout.addLayout(panel_layout)
        self.setLayout(layout)

    def cargar_foto(self):
        ruta, _ = QFileDialog.getOpenFileName(
            self,
            "Seleccionar imagen",
            "",
            "Imágenes (*.png *.jpg *.jpeg)",
        )
        if not ruta:
            return

        with open(ruta, "rb") as archivo:
            self._image_bytes = archivo.read()

        self._mostrar_pixmap(QPixmap(ruta))

    def tomar_foto(self):
        dialogo = PhotoCaptureWindow(self)
        if dialogo.exec() == QDialog.DialogCode.Accepted:
            imagen_bytes = dialogo.get_image_bytes()
            pixmap = dialogo.get_pixmap()
            if imagen_bytes is not None and pixmap is not None:
                self._image_bytes = imagen_bytes
                self._mostrar_pixmap(pixmap)

    def _mostrar_pixmap(self, pixmap):
        escalado = pixmap.scaled(
            self.panel.width(),
            self.panel.height(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.panel.setPixmap(escalado)
        self.panel.setText("")
        self.eliminar_button.setVisible(True)

    def eliminar_foto(self):
        self._image_bytes = None
        self.panel.clear()
        self.panel.setText(self.PLACEHOLDER_TEXT)
        self.eliminar_button.setVisible(False)

    def has_image(self):
        return self._image_bytes is not None

    def get_image_bytes(self):
        return self._image_bytes
