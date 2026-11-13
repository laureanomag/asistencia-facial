"""Los 3 recuadros de fotos de referencia (frente, perfil izquierdo y perfil
derecho), cada uno con "Cargar foto" y "Tomar foto", como en el proyecto
original. Cada foto se revisa con el mismo detector que usa el reconocimiento:
el frente es obligatorio con rostro detectable; un perfil sin rostro se puede
repetir o usar igual (no se usa para reconocer). Lo usan Empleados y Socios."""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFileDialog, QFrame, QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from ui import captura_fotos as cf
from ui.componentes import con_rol, etiqueta


def elegir_archivo(parent):
    ruta, _ = QFileDialog.getOpenFileName(parent, "Seleccionar foto", "", "Imágenes (*.png *.jpg *.jpeg)")
    return Path(ruta).read_bytes() if ruta else None


class SlotFoto(QFrame):
    ANCHO, ALTO = 152, 114

    def __init__(self, angulo, nombre, dependencias):
        super().__init__()
        con_rol(self, "slot-foto")
        self.angulo, self.nombre = angulo, nombre
        self._dep = dependencias
        self.datos = None
        self.detectable = False
        self.miniatura = con_rol(etiqueta("Sin foto", "miniatura"), "miniatura")
        self.miniatura.setFixedSize(self.ANCHO, self.ALTO)
        self.miniatura.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.estado = etiqueta("", "secundario")
        self.estado.setWordWrap(True)
        self.cargar = QPushButton("Cargar foto")
        self.tomar = QPushButton("Tomar foto")
        self.quitar = QPushButton("Quitar")
        for boton in (self.cargar, self.tomar, self.quitar):
            boton.setMinimumHeight(36)
            boton.setStyleSheet("font-size: 13px; padding: 0 10px;")
        self.cargar.clicked.connect(self.cargar_foto)
        self.tomar.clicked.connect(self.tomar_foto)
        self.quitar.clicked.connect(self.limpiar)
        columna = QVBoxLayout(self)
        columna.setContentsMargins(12, 12, 12, 12)
        columna.setSpacing(8)
        columna.addWidget(etiqueta(nombre, "etiqueta"))
        columna.addWidget(self.miniatura, alignment=Qt.AlignmentFlag.AlignHCenter)
        columna.addWidget(self.estado)
        columna.addWidget(self.tomar)
        columna.addWidget(self.cargar)
        columna.addWidget(self.quitar)
        columna.addStretch()
        self.limpiar()

    def tomar_foto(self):
        datos = self._dep["tomar"](self.angulo, self.window())
        if datos is not None:
            self.establecer(datos)

    def cargar_foto(self):
        datos = self._dep["elegir_archivo"](self.window())
        if datos is None:
            return
        resultado = cf.revisar_foto(self.angulo, datos, self._dep["detectable"])
        if resultado == cf.FRENTE_SIN_ROSTRO:
            self._dep["avisar"](self.window())
            return
        if resultado == cf.SIN_ROSTRO and self._dep["preguntar"](self.window(), self.nombre) == cf.REPETIR:
            return
        self.establecer(datos)

    def establecer(self, datos):
        self.datos = datos
        self.detectable = cf.revisar_foto(self.angulo, datos, self._dep["detectable"]) == cf.OK
        imagen = QPixmap()
        if imagen.loadFromData(datos):
            self.miniatura.setPixmap(imagen.scaled(self.ANCHO, self.ALTO, Qt.AspectRatioMode.KeepAspectRatio,
                                                   Qt.TransformationMode.SmoothTransformation))
        self.estado.setText("Rostro detectable" if self.detectable
                            else "Sin rostro detectable: no se usa para reconocer")
        self.estado.setProperty("rol", "ok" if self.detectable else "error")
        self.estado.style().unpolish(self.estado)
        self.estado.style().polish(self.estado)
        self.quitar.setEnabled(True)

    def limpiar(self):
        self.datos, self.detectable = None, False
        self.miniatura.clear()
        self.miniatura.setText("Sin foto")
        self.estado.setText("")
        self.quitar.setEnabled(False)


class FotosReferencia(QWidget):
    def __init__(self, tomar=None, elegir=None, detectable=None, avisar=None, preguntar=None):
        super().__init__()
        dependencias = {
            "tomar": tomar or (lambda angulo, parent: cf.tomar_foto(angulo, parent)),
            "elegir_archivo": elegir or elegir_archivo,
            "detectable": detectable,
            "avisar": avisar or cf.avisar_frente,
            "preguntar": preguntar or cf.preguntar_perfil,
        }
        self.slots = {angulo: SlotFoto(angulo, nombre, dependencias) for angulo, nombre, _ in cf.ANGULOS}
        fila = QHBoxLayout(self)
        fila.setContentsMargins(0, 0, 0, 0)
        fila.setSpacing(12)
        for slot in self.slots.values():
            fila.addWidget(slot)
        fila.addStretch()

    def fotos(self):
        return {angulo: slot.datos for angulo, slot in self.slots.items() if slot.datos is not None}

    def completas(self):
        return len(self.fotos()) == len(self.slots)

    def frente_detectable(self):
        return self.slots["frente"].detectable

    def limpiar(self):
        for slot in self.slots.values():
            slot.limpiar()
