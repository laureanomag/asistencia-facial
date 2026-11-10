from PySide6.QtCore import QObject, Signal


class SenalesReconocimiento(QObject):
    """Señal con la que el proceso de reconocimiento avisa a la interfaz.
    El diccionario trae "estado" y "mensaje"."""
    terminado = Signal(object)
