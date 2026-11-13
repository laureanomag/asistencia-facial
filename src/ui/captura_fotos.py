"""Toma guiada de las 3 fotos de referencia (frente y dos perfiles), con la
misma ventana de captura del proyecto original (PhotoCaptureWindow).

Cada foto se revisa con el mismo detector que usa la carga de referencias
(Haar estricto y, si no encuentra, permisivo):
- Frente: obligatoria con rostro detectable; si no, hay que repetirla.
- Perfiles: si no tienen rostro detectable se avisa y se elige Repetir o
  Usar igual (como el original, que la guardaba y la omitía al reconocer).
Lo usan el script de prueba y la pantalla Socios."""
from PySide6.QtWidgets import QDialog, QMessageBox

INDICACION_PERFIL = "Girá levemente la cabeza hacia tu {lado}, unos 15°: que se vean los dos ojos."
ANGULOS = (
    ("frente", "Frente", "Mirá a la cámara, con buena luz de frente."),
    ("perfil_izquierdo", "Perfil izquierdo", INDICACION_PERFIL.format(lado="izquierda")),
    ("perfil_derecho", "Perfil derecho", INDICACION_PERFIL.format(lado="derecha")),
)
NOMBRES = {clave: nombre for clave, nombre, _ in ANGULOS}

OK = "ok"
FRENTE_SIN_ROSTRO = "frente_sin_rostro"
SIN_ROSTRO = "sin_rostro"
REPETIR = "repetir"
USAR_IGUAL = "usar_igual"

MENSAJE_FRENTE = ("No se detecta un rostro en la foto de frente. Repetila: es la que se usa "
                  "para reconocerte.")
MENSAJE_PERFIL = ("La foto de {nombre} no tiene un rostro detectable: no se va a usar para "
                  "reconocer. ¿Querés repetirla?")


def revisar_foto(angulo, imagen_bytes, detectable=None):
    """OK, FRENTE_SIN_ROSTRO o SIN_ROSTRO."""
    if detectable is None:
        from services.face_service import tiene_rostro_detectable
        detectable = tiene_rostro_detectable
    if detectable(imagen_bytes):
        return OK
    return FRENTE_SIN_ROSTRO if angulo == "frente" else SIN_ROSTRO


def avisar_frente(parent):
    QMessageBox.warning(parent, "Foto de frente", MENSAJE_FRENTE)


def preguntar_perfil(parent, nombre):
    caja = QMessageBox(parent)
    caja.setWindowTitle("Foto sin rostro detectable")
    caja.setIcon(QMessageBox.Icon.Warning)
    caja.setText(MENSAJE_PERFIL.format(nombre=nombre.lower()))
    repetir = caja.addButton("Repetir", QMessageBox.ButtonRole.AcceptRole)
    caja.addButton("Usar igual", QMessageBox.ButtonRole.RejectRole)
    repetir.setProperty("rol", "primario")
    from ui.tema import refrescar_estilo
    refrescar_estilo(repetir)
    caja.setDefaultButton(repetir)
    caja.exec()
    return REPETIR if caja.clickedButton() is repetir else USAR_IGUAL


def _ventana_por_defecto(parent, titulo, indicacion):
    from ui.photo_capture_window import PhotoCaptureWindow
    return PhotoCaptureWindow(parent, titulo=titulo, indicacion=indicacion)


def tomar_foto(angulo, parent=None, numero=None, crear_ventana=None, detectable=None,
               avisar=None, preguntar=None):
    """Toma (y revisa) una foto del ángulo pedido. Devuelve los bytes JPEG o
    None si se cancela la ventana."""
    crear_ventana = crear_ventana or _ventana_por_defecto
    avisar = avisar or avisar_frente
    preguntar = preguntar or preguntar_perfil
    nombre = NOMBRES[angulo]
    indicacion = next(texto for clave, _n, texto in ANGULOS if clave == angulo)
    titulo = f"Foto {numero} de 3 · {nombre}" if numero else f"Foto · {nombre}"
    while True:
        ventana = crear_ventana(parent, titulo, indicacion)
        if ventana.exec() != QDialog.DialogCode.Accepted:
            return None
        datos = ventana.get_image_bytes()
        resultado = revisar_foto(angulo, datos, detectable)
        if resultado == OK:
            return datos
        if resultado == FRENTE_SIN_ROSTRO:
            avisar(parent)
            continue
        if preguntar(parent, nombre) == USAR_IGUAL:
            return datos


class ConfirmarFotos(QDialog):
    """Muestra las 3 fotos antes de guardarlas. Cancelar es la opción por
    defecto; guardar requiere un clic en "Guardar fotos"."""

    def __init__(self, fotos, detectable=None, parent=None):
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QPixmap
        from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout
        from ui.componentes import con_rol, etiqueta
        super().__init__(parent)
        self.setWindowTitle("Confirmar fotos")
        miniaturas = QHBoxLayout()
        miniaturas.setSpacing(16)
        for angulo, nombre, _indicacion in ANGULOS:
            datos = fotos.get(angulo)
            imagen = QLabel()
            imagen.setFixedSize(200, 150)
            imagen.setAlignment(Qt.AlignmentFlag.AlignCenter)
            imagen.setStyleSheet("background: #0B0B0B; border: 1px solid #2A2A2A; border-radius: 10px;")
            pixmap = QPixmap()
            if datos and pixmap.loadFromData(datos):
                imagen.setPixmap(pixmap.scaled(200, 150, Qt.AspectRatioMode.KeepAspectRatio,
                                               Qt.TransformationMode.SmoothTransformation))
            ok = datos is not None and revisar_foto(angulo, datos, detectable) == OK
            columna = QVBoxLayout()
            columna.addWidget(etiqueta(nombre, "etiqueta"))
            columna.addWidget(imagen)
            columna.addWidget(etiqueta("Rostro detectable" if ok else "Sin rostro detectable", "secundario"))
            miniaturas.addLayout(columna)
        self.cancelar = QPushButton("Cancelar")
        self.guardar = con_rol(QPushButton("Guardar fotos"), "primario")
        self.guardar.setAutoDefault(False)
        self.guardar.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.cancelar.setDefault(True)
        self.cancelar.clicked.connect(self.reject)
        self.guardar.clicked.connect(self.accept)
        botones = QHBoxLayout()
        botones.addStretch()
        botones.addWidget(self.cancelar)
        botones.addWidget(self.guardar)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(14)
        layout.addWidget(etiqueta("¿Guardar estas 3 fotos de referencia?", "titulo-panel"))
        layout.addLayout(miniaturas)
        layout.addLayout(botones)


def confirmar_fotos(fotos, parent=None, detectable=None):
    """True solo si se hace clic en "Guardar fotos"."""
    return ConfirmarFotos(fotos, detectable, parent).exec() == QDialog.DialogCode.Accepted


def capturar_guiado(parent=None, **dependencias):
    """Las 3 fotos en orden. Devuelve {angulo: bytes} o None si se cancela."""
    fotos = {}
    for numero, (angulo, _nombre, _indicacion) in enumerate(ANGULOS, start=1):
        datos = tomar_foto(angulo, parent, numero, **dependencias)
        if datos is None:
            return None
        fotos[angulo] = datos
    return fotos
