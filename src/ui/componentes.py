"""Componentes visuales compartidos por las pantallas de ZebraGym."""
from PySide6.QtCore import QPoint, QRect, QRectF, QSize, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLayout, QSizePolicy, QVBoxLayout, QWidget

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
        self.setMinimumHeight(24)   # el radio (11 px) necesita al menos 22 px de alto

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


class FranjaDecorativa(QWidget):
    """Franja de cebra a todo el ancho (assets/franja_cebra.svg o .png) con un
    título y un subtítulo sobre la parte lisa de la izquierda. La imagen se
    recorta para cubrir el espacio (nunca se deforma) y conserva su lado
    izquierdo; si el archivo no está, se pinta un panel liso."""

    ALTO = 140
    RADIO = 16

    def __init__(self, titulo="", subtitulo=""):
        super().__init__()
        self.setFixedHeight(self.ALTO)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._svg, self._imagen = None, None
        svg, png = tema.ASSETS / "franja_cebra.svg", tema.ASSETS / "franja_cebra.png"
        if svg.exists():
            from PySide6.QtSvg import QSvgRenderer
            renderer = QSvgRenderer(str(svg))
            self._svg = renderer if renderer.isValid() else None
        elif png.exists():
            imagen = QPixmap(str(png))
            self._imagen = None if imagen.isNull() else imagen
        self.titulo = QLabel(titulo)
        self.titulo.setStyleSheet(f'font-family: "{tema.FAMILIA_TITULOS}"; font-size: 24px; '
                                  "font-weight: 800; color: #FFFFFF; background: transparent;")
        self.subtitulo = QLabel(subtitulo)
        self.subtitulo.setStyleSheet(f"font-size: 15px; color: {tema.TEXTO_SECUNDARIO}; background: transparent;")
        columna = QVBoxLayout(self)
        columna.setContentsMargins(32, 0, 32, 0)
        columna.setSpacing(6)
        columna.addStretch()
        columna.addWidget(self.titulo)
        columna.addWidget(self.subtitulo)
        columna.addStretch()

    def tiene_imagen(self):
        return self._svg is not None or self._imagen is not None

    def mostrar(self, titulo, subtitulo):
        self.titulo.setText(titulo)
        self.subtitulo.setText(subtitulo)

    def _destino(self, ancho_origen, alto_origen):
        """Rectángulo donde dibujar la imagen para cubrir la franja sin
        deformarla, anclada a la izquierda y centrada en vertical."""
        escala = max(self.width() / ancho_origen, self.height() / alto_origen)
        ancho, alto = ancho_origen * escala, alto_origen * escala
        return QRectF(0, (self.height() - alto) / 2, ancho, alto)

    def paintEvent(self, evento):
        from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
        borde = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        forma = QPainterPath()
        forma.addRoundedRect(borde, self.RADIO, self.RADIO)
        pintor.setClipPath(forma)
        pintor.fillRect(self.rect(), QColor(tema.PANEL))
        if self._svg is not None:
            tamanio = self._svg.defaultSize()
            self._svg.render(pintor, self._destino(tamanio.width(), tamanio.height()))
        elif self._imagen is not None:
            destino = self._destino(self._imagen.width(), self._imagen.height())
            pintor.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            pintor.drawPixmap(destino, self._imagen, QRectF(self._imagen.rect()))
        pintor.setClipping(False)
        pintor.setPen(QPen(QColor(tema.BORDE), 1))
        pintor.drawPath(forma)
        pintor.end()


class FlujoLayout(QLayout):
    """Ubica los widgets en filas y pasa a la fila siguiente cuando no entran
    (para las etiquetas de "Mensajes que puede mostrar la cámara")."""

    def __init__(self, parent=None, espacio=8):
        super().__init__(parent)
        self._items = []
        self._espacio = espacio

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, indice):
        return self._items[indice] if 0 <= indice < len(self._items) else None

    def takeAt(self, indice):
        return self._items.pop(indice) if 0 <= indice < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, ancho):
        return self._acomodar(QRect(0, 0, ancho, 0), aplicar=False)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._acomodar(rect, aplicar=True)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        tamanio = QSize()
        for item in self._items:
            tamanio = tamanio.expandedTo(item.minimumSize())
        margenes = self.contentsMargins()
        return tamanio + QSize(margenes.left() + margenes.right(), margenes.top() + margenes.bottom())

    def _acomodar(self, rect, aplicar):
        margenes = self.contentsMargins()
        x, y = rect.x() + margenes.left(), rect.y() + margenes.top()
        derecha = rect.right() - margenes.right()
        alto_fila = 0
        for item in self._items:
            ancho = item.sizeHint().width()
            if x + ancho > derecha and alto_fila > 0:
                x = rect.x() + margenes.left()
                y += alto_fila + self._espacio
                alto_fila = 0
            if aplicar:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))
            x += ancho + self._espacio
            alto_fila = max(alto_fila, item.sizeHint().height())
        return y + alto_fila - rect.y() + margenes.bottom()


class CampoFormulario(QWidget):
    """Etiqueta + campo + mensaje de error debajo del campo (oculto si no hay error)."""

    def __init__(self, texto, campo, ayuda=""):
        super().__init__()
        self.campo = campo
        self.etiqueta = etiqueta(texto, "etiqueta")
        self.mensaje = etiqueta(ayuda, "secundario")
        self.mensaje.setWordWrap(True)
        self.mensaje.setVisible(bool(ayuda))
        self._ayuda = ayuda
        columna = QVBoxLayout(self)
        columna.setContentsMargins(0, 0, 0, 0)
        columna.setSpacing(6)
        columna.addWidget(self.etiqueta)
        columna.addWidget(campo)
        columna.addWidget(self.mensaje)

    def mostrar_error(self, texto):
        self.mensaje.setText(texto)
        self.mensaje.setProperty("rol", "error")
        self.mensaje.show()
        self.campo.setProperty("error", True)
        for widget in (self.mensaje, self.campo):
            tema.refrescar_estilo(widget)

    def limpiar_error(self):
        self.mensaje.setText(self._ayuda)
        self.mensaje.setProperty("rol", "secundario")
        self.mensaje.setVisible(bool(self._ayuda))
        self.campo.setProperty("error", False)
        for widget in (self.mensaje, self.campo):
            tema.refrescar_estilo(widget)

    def tiene_error(self):
        return bool(self.campo.property("error"))
