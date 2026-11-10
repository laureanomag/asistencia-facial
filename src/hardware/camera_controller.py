import time

import cv2


class _DispositivoCamara:
    """
    Webcam física compartida. Mantiene UNA sola cv2.VideoCapture por índice
    de cámara y cuenta cuántos componentes la están usando: la cámara se
    abre cuando el primero la pide y se libera recién cuando el último la
    suelta. Así, por ejemplo, "Tomar Foto" puede usar la webcam mientras la
    de Asistencia sigue abierta, sin que una pise a la otra.
    """

    # Se pide una resolución 16:9 porque muchas webcams, al abrirse por
    # defecto en 640x480 (4:3), recortan el sensor y muestran un ángulo más
    # cerrado (efecto "zoom"). Si la cámara no la soporta, usa la suya.
    RESOLUCION_PREFERIDA = (1280, 720)
    INTERVALO_MIN_LECTURA = 0.012  # segundos

    def __init__(self, indice):
        self.indice = indice
        self._captura = None
        self._usuarios = 0
        self._ultimo_frame = None
        self._ultima_lectura = 0.0

    def acquire(self):
        if self._captura is None:
            captura = cv2.VideoCapture(self.indice)
            if not captura.isOpened():
                captura.release()
                return False

            ancho, alto = self.RESOLUCION_PREFERIDA
            captura.set(cv2.CAP_PROP_FRAME_WIDTH, ancho)
            captura.set(cv2.CAP_PROP_FRAME_HEIGHT, alto)

            self._captura = captura
            self._ultimo_frame = None

        self._usuarios += 1
        return True

    def release(self):
        if self._usuarios > 0:
            self._usuarios -= 1

        if self._usuarios == 0 and self._captura is not None:
            self._captura.release()
            self._captura = None
            self._ultimo_frame = None

    def read(self):
        if self._captura is None:
            return None

        # Si dos componentes leen casi a la vez, comparten el mismo frame
        # en lugar de "robarse" frames entre sí.
        ahora = time.monotonic()
        if (
            self._ultimo_frame is not None
            and ahora - self._ultima_lectura < self.INTERVALO_MIN_LECTURA
        ):
            return self._ultimo_frame

        ok, frame = self._captura.read()
        if not ok or frame is None:
            return None

        if self._ultimo_frame is None:
            alto, ancho = frame.shape[:2]
            print(f"[Cámara] resolución real: {ancho}x{alto}")

        self._ultimo_frame = frame
        self._ultima_lectura = ahora
        return frame


_DISPOSITIVOS = {}


def _obtener_dispositivo(indice):
    if indice not in _DISPOSITIVOS:
        _DISPOSITIVOS[indice] = _DispositivoCamara(indice)
    return _DISPOSITIVOS[indice]


class CameraController:
    """
    Componente reutilizable para abrir, leer y cerrar la webcam del sistema
    con OpenCV. Cada pantalla (Asistencia por Captura Facial, ventana Tomar
    Foto) usa su propia instancia, pero todas comparten la misma webcam
    física a través de _DispositivoCamara: close() solo suelta la parte de
    esta instancia, y la webcam se apaga cuando nadie más la está usando.
    """

    def __init__(self, indice_camara=0):
        self.indice_camara = indice_camara
        self._dispositivo = _obtener_dispositivo(indice_camara)
        self._abierta = False

    def is_opened(self):
        return self._abierta

    def open(self):
        """Intenta abrir la cámara. Devuelve True/False según el resultado."""
        if self._abierta:
            return True

        if not self._dispositivo.acquire():
            return False

        self._abierta = True
        return True

    def read_frame(self):
        """Devuelve una copia del frame más reciente en formato BGR (como lo
        entrega OpenCV) o None si no hay cámara abierta o falló la lectura."""
        if not self._abierta:
            return None

        frame = self._dispositivo.read()
        return None if frame is None else frame.copy()

    def close(self):
        """Suelta la cámara. Seguro de llamar aunque ya esté cerrada."""
        if self._abierta:
            self._abierta = False
            self._dispositivo.release()
