"""Gráficos de barras del Panel, dibujados con Qt.

Reglas: una sola serie por gráfico (un color, sin leyenda; el título la
nombra), barras finas con 4 px redondeados en la punta y anclas en la base,
2 px de separación entre barras, grilla y ejes discretos, etiqueta solo en el
valor pico y tooltip al pasar el mouse por cada barra. Los textos usan los
colores de texto del tema, nunca el color de la serie."""
import math

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QToolTip, QWidget

from ui import tema

SEPARACION = 2
RADIO = 4


def tope_redondo(maximo):
    """Valor máximo del eje: 1, 2, 5, 10, 20, 50... por encima del dato."""
    if maximo <= 0:
        return 1
    base = 10 ** math.floor(math.log10(maximo))
    for paso in (1, 2, 5, 10):
        if paso * base >= maximo:
            return paso * base
    return 10 * base


def barra(rect, horizontal=False):
    """Barra con la punta redondeada (4 px) y la base recta."""
    radio = min(RADIO, (rect.height() if horizontal else rect.width()) / 2,
                (rect.width() if horizontal else rect.height()))
    camino = QPainterPath()
    camino.addRoundedRect(rect, radio, radio)
    recta = QPainterPath()
    if horizontal:          # base a la izquierda
        recta.addRect(QRectF(rect.left(), rect.top(), min(radio, rect.width()), rect.height()))
    else:                   # base abajo
        recta.addRect(QRectF(rect.left(), rect.bottom() - min(radio, rect.height()), rect.width(),
                             min(radio, rect.height())))
    return camino.united(recta)


def _fuente(px, negrita=False):
    fuente = QFont(tema.FAMILIA_TEXTO)
    fuente.setPixelSize(px)
    fuente.setBold(negrita)
    return fuente


class BarrasVerticales(QWidget):
    """Una serie en columnas (por ejemplo, ingresos por hora)."""

    MARGEN_IZQ, MARGEN_ARRIBA, MARGEN_ABAJO = 34, 22, 24

    def __init__(self, color=tema.DORADO, vacio="Sin datos para mostrar."):
        super().__init__()
        self.setMouseTracking(True)
        self.setMinimumHeight(200)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._color = QColor(color)
        self._vacio = vacio
        self._etiquetas, self._valores, self._tooltips = [], [], []
        self._resaltada = None

    def sizeHint(self):
        return QSize(520, 240)

    def mostrar(self, etiquetas, valores, tooltips=None):
        self._etiquetas, self._valores = list(etiquetas), list(valores)
        self._tooltips = list(tooltips) if tooltips else [f"{e}: {v}" for e, v in zip(etiquetas, valores)]
        self._resaltada = None
        self.update()

    def _area(self):
        return QRectF(self.MARGEN_IZQ, self.MARGEN_ARRIBA,
                      max(1, self.width() - self.MARGEN_IZQ - 6),
                      max(1, self.height() - self.MARGEN_ARRIBA - self.MARGEN_ABAJO))

    def rect_barra(self, indice):
        area = self._area()
        ancho_slot = area.width() / max(1, len(self._valores))
        tope = tope_redondo(max(self._valores, default=0))
        alto = area.height() * self._valores[indice] / tope
        x = area.left() + indice * ancho_slot + SEPARACION / 2
        return QRectF(x, area.bottom() - alto, max(1, ancho_slot - SEPARACION), alto)

    def paintEvent(self, evento):
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self._valores or max(self._valores) == 0:
            pintor.setPen(QColor(tema.TEXTO_SECUNDARIO))
            pintor.setFont(_fuente(14))
            pintor.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._vacio)
            return
        area = self._area()
        tope = tope_redondo(max(self._valores))
        # Grilla discreta: 0, mitad y tope
        pintor.setFont(_fuente(11))
        for fraccion in (0, 0.5, 1):
            y = area.bottom() - area.height() * fraccion
            pintor.setPen(QPen(QColor(tema.BORDE), 1))
            pintor.drawLine(QPointF(area.left(), y), QPointF(area.right(), y))
            pintor.setPen(QColor(tema.TEXTO_SECUNDARIO))
            valor = tope * fraccion
            texto = f"{valor:g}"
            pintor.drawText(QRectF(0, y - 8, self.MARGEN_IZQ - 6, 16),
                            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, texto)
        # Barras
        ancho_slot = area.width() / len(self._valores)
        cada = max(1, math.ceil(30 / ancho_slot))        # etiquetas del eje x sin superponerse
        pico = self._valores.index(max(self._valores))
        for i, valor in enumerate(self._valores):
            rect = self.rect_barra(i)
            if valor > 0:
                color = QColor("#F5C842") if i == self._resaltada else self._color
                pintor.fillPath(barra(rect), color)
            if i % cada == 0:
                pintor.setPen(QColor(tema.TEXTO_SECUNDARIO))
                pintor.drawText(QRectF(rect.center().x() - 20, area.bottom() + 4, 40, 18),
                                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                                self._etiquetas[i])
        # Etiqueta solo en el pico
        rect = self.rect_barra(pico)
        pintor.setPen(QColor(tema.TEXTO))
        pintor.setFont(_fuente(12, negrita=True))
        pintor.drawText(QRectF(rect.center().x() - 30, rect.top() - 20, 60, 18),
                        Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom,
                        str(self._valores[pico]))

    def indice_en(self, x):
        area = self._area()
        if not self._valores or not area.left() <= x <= area.right():
            return None
        return min(len(self._valores) - 1, int((x - area.left()) / (area.width() / len(self._valores))))

    def mouseMoveEvent(self, evento):
        indice = self.indice_en(evento.position().x())
        if indice != self._resaltada:
            self._resaltada = indice
            self.update()
        if indice is None:
            QToolTip.hideText()
        else:
            QToolTip.showText(evento.globalPosition().toPoint(), self._tooltips[indice], self)

    def leaveEvent(self, evento):
        self._resaltada = None
        self.update()
        super().leaveEvent(evento)


class BarrasHorizontales(QWidget):
    """Una serie por categoría: etiqueta, barra y valor (p. ej., socios por plan)."""

    ALTO_FILA = 32
    ANCHO_ETIQUETA = 130
    ANCHO_VALOR = 36

    def __init__(self, color=tema.DORADO, vacio="Sin datos para mostrar."):
        super().__init__()
        self.setMouseTracking(True)
        self._color = QColor(color)
        self._vacio = vacio
        self._filas = []
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(self.ALTO_FILA)
        self.setMinimumWidth(self.ANCHO_ETIQUETA + self.ANCHO_VALOR + 40)

    def mostrar(self, filas):
        """filas: [(etiqueta, valor)]."""
        self._filas = list(filas)
        self.setFixedHeight(max(1, len(self._filas)) * self.ALTO_FILA)
        self.update()

    def rect_barra(self, indice):
        tope = tope_redondo(max((v for _e, v in self._filas), default=0))
        izquierda = self.ANCHO_ETIQUETA + 8
        ancho_total = max(1, self.width() - izquierda - self.ANCHO_VALOR)
        valor = self._filas[indice][1]
        y = indice * self.ALTO_FILA + SEPARACION + 7
        return QRectF(izquierda, y, ancho_total * valor / tope, self.ALTO_FILA - 2 * SEPARACION - 14)

    def paintEvent(self, evento):
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
        pintor.setFont(_fuente(13))
        if not self._filas:
            pintor.setPen(QColor(tema.TEXTO_SECUNDARIO))
            pintor.drawText(self.rect(), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                            self._vacio)
            return
        metricas = pintor.fontMetrics()
        for i, (etiqueta, valor) in enumerate(self._filas):
            y = i * self.ALTO_FILA
            pintor.setPen(QColor(tema.TEXTO_SECUNDARIO))
            texto = metricas.elidedText(etiqueta, Qt.TextElideMode.ElideRight, self.ANCHO_ETIQUETA)
            pintor.drawText(QRectF(0, y, self.ANCHO_ETIQUETA, self.ALTO_FILA),
                            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, texto)
            rect = self.rect_barra(i)
            if valor > 0:
                pintor.fillPath(barra(rect, horizontal=True), self._color)
            pintor.setPen(QColor(tema.TEXTO))
            pintor.drawText(QRectF(rect.right() + 8, y, self.ANCHO_VALOR, self.ALTO_FILA),
                            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, str(valor))

    def mouseMoveEvent(self, evento):
        indice = int(evento.position().y() // self.ALTO_FILA)
        if 0 <= indice < len(self._filas):
            etiqueta, valor = self._filas[indice]
            QToolTip.showText(evento.globalPosition().toPoint(), f"{etiqueta}: {valor}", self)
        else:
            QToolTip.hideText()
