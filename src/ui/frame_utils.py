import cv2
from PySide6.QtGui import QImage, QPixmap


def frame_to_pixmap(frame_bgr, espejo=False):
    """Convierte un frame BGR (como lo entrega OpenCV) en un QPixmap listo
    para mostrarse en un QLabel. Con espejo=True se voltea horizontalmente
    SOLO lo que se muestra (vista previa tipo espejo); el frame original, que
    se guarda y se usa para reconocer, no se modifica."""
    if espejo:
        frame_bgr = cv2.flip(frame_bgr, 1)
    frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    alto, ancho, canales = frame_rgb.shape
    bytes_por_linea = canales * ancho
    imagen = QImage(frame_rgb.data, ancho, alto, bytes_por_linea, QImage.Format.Format_RGB888)
    # .copy() para desligar el QImage del buffer de numpy, que OpenCV puede
    # reutilizar/sobrescribir en la próxima lectura.
    return QPixmap.fromImage(imagen.copy())


def frame_to_jpeg_bytes(frame_bgr):
    """Codifica un frame BGR como JPEG y devuelve los bytes resultantes,
    listos para guardarse en la base de datos (columna bytea)."""
    ok, buffer = cv2.imencode(".jpg", frame_bgr)
    if not ok:
        return None
    return buffer.tobytes()
