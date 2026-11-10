from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QLabel, QSizePolicy


class VideoPanel(QLabel):
    """
    Panel donde se muestra el video de la webcam.

    - Toma la proporción (ancho/alto) real de los frames de la cámara, de
      modo que el cuadro y la imagen tengan el mismo ángulo y no se recorte
      ni se estire nada.
    - Su tamaño preferido NO depende del último frame mostrado. Un QLabel
      común usa el tamaño del pixmap como sizeHint, y al ir mostrando frames
      escalados al tamaño actual se agranda solo en cada ciclo (efecto de
      "zoom" progresivo).
    """

    def __init__(self, ancho_min=480, relacion=(16, 9)):
        super().__init__()
        self._ancho_min = ancho_min
        self._relacion = relacion[0] / relacion[1]
        self._pixmap_actual = None

        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("border: 1px solid #888; background-color: #222; color: #ccc;")

        politica = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        politica.setHeightForWidth(True)
        self.setSizePolicy(politica)

    # --- Tamaño: siempre derivado de la proporción de la cámara ---

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, ancho):
        return int(ancho / self._relacion)

    def sizeHint(self):
        ancho = self._ancho_min + 160
        return QSize(ancho, self.heightForWidth(ancho))

    def minimumSizeHint(self):
        return QSize(self._ancho_min, self.heightForWidth(self._ancho_min))

    def set_aspect_ratio(self, ancho, alto):
        """Ajusta el panel a la proporción real de la cámara."""
        if ancho <= 0 or alto <= 0:
            return

        nueva = ancho / alto
        if abs(nueva - self._relacion) < 0.001:
            return

        self._relacion = nueva
        self.updateGeometry()
        self._renderizar()

    # --- Contenido ---

    def mostrar_frame(self, pixmap):
        self._pixmap_actual = pixmap
        self._renderizar()

    def limpiar(self):
        self._pixmap_actual = None
        self.clear()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._renderizar()

    def _renderizar(self):
        if self._pixmap_actual is None:
            return

        escalado = self._pixmap_actual.scaled(
            self.contentsRect().size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )
        self.setPixmap(escalado)
