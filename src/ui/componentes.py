"""Componentes visuales compartidos por las pantallas de ZebraGym."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ui import tema


def con_rol(widget, rol, **propiedades):
    widget.setProperty("rol", rol)
    for nombre, valor in propiedades.items():
        widget.setProperty(nombre, valor)
    return widget


def etiqueta(texto, rol, **propiedades):
    return con_rol(QLabel(texto), rol, **propiedades)


def iniciales(nombre):
    """'Juan Pérez' -> 'JP'; 'admin' -> 'AD'."""
    palabras = [p for p in (nombre or "").replace(",", " ").split() if p]
    if len(palabras) >= 2:
        return (palabras[0][0] + palabras[-1][0]).upper()
    return (palabras[0][:2] if palabras else "?").upper()


def logo(tamanio):
    etiqueta_logo = QLabel()
    etiqueta_logo.setFixedSize(tamanio, tamanio)
    if tema.LOGO.exists():
        imagen = QPixmap(str(tema.LOGO))
        ratio = 2
        escalada = imagen.scaled(tamanio * ratio, tamanio * ratio,
                                 Qt.AspectRatioMode.KeepAspectRatio,
                                 Qt.TransformationMode.SmoothTransformation)
        escalada.setDevicePixelRatio(ratio)
        etiqueta_logo.setPixmap(escalada)
    return etiqueta_logo


class Marca(QWidget):
    """Logo chico + 'ZEBRA' / 'GYM' (encabezado del menú lateral)."""

    def __init__(self):
        super().__init__()
        textos = QVBoxLayout()
        textos.setSpacing(0)
        textos.addStretch()
        textos.addWidget(etiqueta("ZEBRA", "marca"))
        textos.addWidget(etiqueta("GYM", "marca-gym"))
        textos.addStretch()
        fila = QHBoxLayout(self)
        fila.setContentsMargins(0, 0, 0, 0)
        fila.setSpacing(12)
        fila.addWidget(logo(52))
        fila.addLayout(textos)
        fila.addStretch()


class Avatar(QLabel):
    def __init__(self, nombre, grande=False):
        super().__init__(iniciales(nombre))
        lado = 74 if grande else 36
        self.setFixedSize(lado, lado)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        con_rol(self, "avatar-grande" if grande else "avatar")


class EtiquetaEstado(QLabel):
    """Etiqueta redondeada: verde (permitido, al día), rojo (rechazado, debe),
    ámbar (por vencer) o dorado."""

    def __init__(self, texto, tono):
        super().__init__(texto)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        con_rol(self, "etiqueta-estado", tono=tono)

    def cambiar(self, texto, tono):
        self.setText(texto)
        self.setProperty("tono", tono)
        tema.refrescar_estilo(self)


class IndicadorApertura(QFrame):
    """'● Abierto · cierra a las 23:00' (verde) o '● Cerrado · ...' (rojo)."""

    def __init__(self):
        super().__init__()
        con_rol(self, "indicador", tono="verde")
        self.setFixedHeight(34)
        self._punto = QLabel("●")
        self._punto.setStyleSheet("font-size: 10px;")
        self._texto = QLabel("")
        fila = QHBoxLayout(self)
        fila.setContentsMargins(14, 0, 16, 0)
        fila.setSpacing(8)
        fila.addWidget(self._punto)
        fila.addWidget(self._texto)

    def mostrar(self, abierto, texto):
        self._texto.setText(texto)
        self.setProperty("tono", "verde" if abierto else "rojo")
        tema.refrescar_estilo(self)
        for hijo in (self._punto, self._texto):
            tema.refrescar_estilo(hijo)

    def texto(self):
        return self._texto.text()


class EncabezadoPagina(QWidget):
    """Título grande, subtítulo gris y el indicador de apertura a la derecha."""

    def __init__(self, titulo, subtitulo, indicador=None):
        super().__init__()
        self.titulo = etiqueta(titulo, "titulo")
        self.subtitulo = etiqueta(subtitulo, "subtitulo")
        textos = QVBoxLayout()
        textos.setSpacing(4)
        textos.addWidget(self.titulo)
        textos.addWidget(self.subtitulo)
        fila = QHBoxLayout(self)
        fila.setContentsMargins(0, 0, 0, 0)
        fila.addLayout(textos)
        fila.addStretch()
        if indicador is not None:
            fila.addWidget(indicador, alignment=Qt.AlignmentFlag.AlignTop)


def panel():
    marco = con_rol(QFrame(), "panel")
    return marco
