"""Íconos de línea del menú, dibujados como SVG simples (originales del
proyecto). Se pintan en el color pedido para el estado normal y el activo."""
from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

_TRAZOS = {
    "camara": '<rect x="3" y="7" width="18" height="13" rx="2.5"/>'
              '<path d="M8.5 7 10 4.5h4L15.5 7"/><circle cx="12" cy="13.5" r="3.5"/>',
    "socios": '<circle cx="9" cy="8.5" r="3.2"/><path d="M3.5 19.5c.6-3.2 2.8-5 5.5-5s4.9 1.8 5.5 5"/>'
              '<path d="M15.5 5.6a3.1 3.1 0 0 1 0 5.8"/><path d="M17.5 14.8c1.6.7 2.7 2.3 3 4.7"/>',
    "cobros": '<rect x="2.5" y="5.5" width="19" height="13" rx="2.5"/><path d="M2.5 10h19"/>'
              '<path d="M6.5 14.5h4"/>',
    "estado": '<rect x="2.5" y="4.5" width="19" height="15" rx="2.5"/><circle cx="8.5" cy="11" r="2.3"/>'
              '<path d="M5.5 16.5c.5-1.6 1.6-2.5 3-2.5s2.5.9 3 2.5"/><path d="M14 9.5h4.5M14 13h4.5"/>',
    "fichajes": '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
    "jornadas": '<rect x="3" y="5" width="18" height="15.5" rx="2.5"/><path d="M3 10h18"/>'
                '<path d="M8 3v4M16 3v4"/><path d="M7.5 14h2M11 14h2M14.5 14h2"/>',
    "informes": '<path d="M3.5 20.5h17"/><path d="M6.5 17v-5M10.5 17V7M14.5 17v-7M18.5 17v-3"/>',
    "panel": '<rect x="3" y="3" width="7.5" height="9" rx="1.8"/><rect x="13.5" y="3" width="7.5" height="5.5" rx="1.8"/>'
             '<rect x="13.5" y="11.5" width="7.5" height="9.5" rx="1.8"/><rect x="3" y="15" width="7.5" height="6" rx="1.8"/>',
    "empleados": '<rect x="4" y="3" width="16" height="18" rx="2.5"/><path d="M9.5 3v2.5h5V3"/>'
                 '<circle cx="12" cy="11" r="2.6"/><path d="M7.8 17.5c.6-2 2.2-3.1 4.2-3.1s3.6 1.1 4.2 3.1"/>',
    "configuracion": '<circle cx="12" cy="12" r="3.2"/>'
                     '<path d="M12 2.8v2.4M12 18.8v2.4M2.8 12h2.4M18.8 12h2.4'
                     'M5.5 5.5l1.7 1.7M16.8 16.8l1.7 1.7M5.5 18.5l1.7-1.7M16.8 7.2l1.7-1.7"/>',
    "opciones": '<path d="M8 10l4 4 4-4"/>',
    "actualizar": '<path d="M19.5 12a7.5 7.5 0 1 1-2.2-5.3"/><path d="M19.5 4.5v4h-4"/>',
    "llave": '<circle cx="8" cy="15" r="4"/><path d="M11 12l8.5-8.5M16.5 6.5l2.5 2.5M14 9l2 2"/>',
    "salir": '<path d="M14.5 4.5h3a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2h-3"/>'
             '<path d="M10.5 16.5L6 12l4.5-4.5M6 12h9.5"/>',
}


def pixmap(nombre, color, tamanio=20):
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
           f'stroke="{color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">'
           f'{_TRAZOS[nombre]}</svg>')
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    imagen = QPixmap(tamanio * 2, tamanio * 2)      # doble resolución: bordes nítidos
    imagen.fill(Qt.GlobalColor.transparent)
    pintor = QPainter(imagen)
    renderer.render(pintor, QRectF(0, 0, tamanio * 2, tamanio * 2))
    pintor.end()
    imagen.setDevicePixelRatio(2)
    return imagen


def icono_menu(nombre, color_normal, color_activo):
    """Ícono con dos estados: el del botón sin marcar y el del botón activo."""
    icono = QIcon()
    icono.addPixmap(pixmap(nombre, color_normal), QIcon.Mode.Normal, QIcon.State.Off)
    icono.addPixmap(pixmap(nombre, color_activo), QIcon.Mode.Normal, QIcon.State.On)
    return icono


NOMBRES = tuple(_TRAZOS)
