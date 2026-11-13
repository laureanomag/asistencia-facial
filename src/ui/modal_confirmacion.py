"""Modal de la cámara del control de acceso.

Recibe la evaluación que manda el proceso de reconocimiento (Evaluacion.a_dict)
y devuelve la opción elegida ("entrenar" o "fichar") o None si se canceló.
Si nadie responde en `cierre_s` segundos, se cierra solo como Cancelar.

Tres variantes, según evaluacion["modo"]:
  socio     "¡Hola, Ana!" · "¿Confirmás tu entrada al gimnasio?"  Cancelar · Entrar
  empleado  "Asistencia laboral" (rol, turno, hora y estado)       Cancelar · Llegué / Me voy
  ambos     "Hola, Ana" · "¿Qué vas a hacer?" (una línea por condición)
            Cancelar · Trabajar · Entrenar; la opción más probable va en dorado."""
from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QDialog, QFrame, QGridLayout, QHBoxLayout, QPushButton, QVBoxLayout, QWidget,
)

from ui.componentes import Avatar, EtiquetaEstado, FlujoLayout, con_rol, etiqueta

CIERRE_S = 60
ANCHO_MODAL = 580
MARGEN = 28
ALTO_BOTON = 52

TONO_ADVERTENCIA = (("Debe", "rojo"), ("Vence", "ambar"), ("Tiene una entrada abierta", "ambar"),
                    ("Hoy figura con", "ambar"), ("Hoy tenés", "ambar"), ("Tenés permiso", "ambar"))


def tono_advertencia(texto):
    for inicio, tono in TONO_ADVERTENCIA:
        if texto.startswith(inicio):
            return tono
    return "neutro"


def primer_nombre(nombre):
    partes = (nombre or "").split()
    return partes[0] if partes else ""


def textos_modal(evaluacion):
    """(título, encabezado, detalle) del modal según el modo."""
    nombre = evaluacion.get("nombre", "")
    dni = f"DNI {evaluacion['dni']}" if evaluacion.get("dni") else ""
    modo = evaluacion.get("modo")
    if modo == "empleado":
        return "Asistencia laboral", nombre, " · ".join(p for p in (dni, evaluacion.get("rol_texto")) if p)
    detalle = " · ".join(p for p in (nombre, dni) if p)
    if modo == "ambos":
        return f"Hola, {primer_nombre(nombre)}", "¿Qué vas a hacer?", detalle
    return f"¡Hola, {primer_nombre(nombre)}!", "¿Confirmás tu entrada al gimnasio?", detalle


class Velo(QWidget):
    """Oscurece la ventana principal mientras el modal está abierto."""

    def __init__(self, ventana):
        super().__init__(ventana)
        self.setObjectName("Velo")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setGeometry(ventana.rect())
        self.show()
        self.raise_()


class FilaBotones(QWidget):
    """Cancelar y las opciones en una fila. Si no entran en el ancho
    disponible, las opciones quedan arriba y Cancelar abajo: los botones
    nunca cortan su texto."""

    ESPACIO = 12

    def __init__(self, cancelar, opciones):
        super().__init__()
        self.cancelar, self.opciones = cancelar, list(opciones)
        self.grilla = QGridLayout(self)
        self.grilla.setContentsMargins(0, 0, 0, 0)
        self.grilla.setSpacing(self.ESPACIO)
        self.dos_filas = None

    def ancho_necesario(self):
        botones = [self.cancelar, *self.opciones]
        return sum(b.sizeHint().width() for b in botones) + self.ESPACIO * (len(botones) - 1)

    def acomodar(self, ancho):
        dos_filas = ancho < self.ancho_necesario()
        if dos_filas == self.dos_filas:
            return
        self.dos_filas = dos_filas
        for boton in (self.cancelar, *self.opciones):
            self.grilla.removeWidget(boton)
        columnas = len(self.opciones) if dos_filas else len(self.opciones) + 1
        for columna in range(len(self.opciones) + 1):
            self.grilla.setColumnStretch(columna, 1 if columna < columnas else 0)
        if dos_filas:
            for columna, boton in enumerate(self.opciones):
                self.grilla.addWidget(boton, 0, columna)
            self.grilla.addWidget(self.cancelar, 1, 0, 1, columnas)
        else:
            self.grilla.addWidget(self.cancelar, 0, 0)
            for columna, boton in enumerate(self.opciones, start=1):
                self.grilla.addWidget(boton, 0, columna)


class ModalConfirmacion(QDialog):
    def __init__(self, evaluacion, cierre_s=CIERRE_S, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setModal(True)
        self.opcion = None
        self._restante = int(cierre_s)
        self.evaluacion = evaluacion
        self.modo = evaluacion.get("modo") or "socio"

        caja = con_rol(QFrame(), "modal")
        caja.setFixedWidth(ANCHO_MODAL)
        columna = QVBoxLayout(caja)
        columna.setContentsMargins(MARGEN, 26, MARGEN, 24)
        columna.setSpacing(0)

        # Título y cuenta regresiva
        titulo, encabezado, detalle = textos_modal(evaluacion)
        self.titulo = etiqueta(titulo, "titulo-modal")
        self.cuenta = etiqueta("", "secundario")
        fila_titulo = QHBoxLayout()
        fila_titulo.addWidget(self.titulo)
        fila_titulo.addStretch()
        fila_titulo.addWidget(self.cuenta)
        columna.addLayout(fila_titulo)
        columna.addSpacing(22)

        # Persona
        self.encabezado = etiqueta(encabezado, "nombre-modal")
        self.encabezado.setWordWrap(True)
        self.detalle = etiqueta(detalle, "subtitulo")
        self.detalle.setWordWrap(True)
        textos = QVBoxLayout()
        textos.setSpacing(2)
        textos.addStretch()
        textos.addWidget(self.encabezado)
        textos.addWidget(self.detalle)
        textos.addStretch()
        persona = QHBoxLayout()
        persona.setSpacing(18)
        persona.addWidget(Avatar(evaluacion.get("nombre", ""), grande=True))
        persona.addLayout(textos, 1)
        columna.addLayout(persona)

        # Datos: tarjetas (socio: plan, esta semana, vence, estado contable; empleado: rol,
        # turno, hora y estado) o una línea por condición (socio y empleado).
        tarjetas = evaluacion.get("tarjetas", [])
        if tarjetas:
            columna.addSpacing(22)
            grilla = QGridLayout()
            grilla.setHorizontalSpacing(12)
            grilla.setVerticalSpacing(12)
            por_fila = 3 if len(tarjetas) == 3 else 2
            for indice, (titulo_dato, valor, tono) in enumerate(tarjetas):
                grilla.addWidget(self._tarjeta(titulo_dato, valor, tono), indice // por_fila,
                                 indice % por_fila)
            columna.addLayout(grilla)
        self.lineas = []
        if evaluacion.get("lineas"):
            columna.addSpacing(22)
            for texto, tono in evaluacion["lineas"]:
                self.lineas.append(self._linea(texto, tono))
                columna.addWidget(self.lineas[-1])
                columna.addSpacing(10)

        advertencias = evaluacion.get("advertencias", [])
        if advertencias:
            columna.addSpacing(14)
            fila = QWidget()
            flujo = FlujoLayout(fila)
            flujo.setContentsMargins(0, 0, 0, 0)
            for texto in advertencias:
                flujo.addWidget(EtiquetaEstado(texto, tono_advertencia(texto)))
            columna.addWidget(fila)

        # Botones: Cancelar y las opciones, la sugerida en dorado
        columna.addSpacing(20)
        self.boton_cancelar = QPushButton("Cancelar")
        self.boton_cancelar.setMinimumHeight(ALTO_BOTON)
        self.boton_cancelar.clicked.connect(self.reject)
        self.botones_opcion = {}
        motivos = []
        for opcion in evaluacion.get("opciones", []):
            boton = QPushButton(opcion["boton"])
            boton.setMinimumHeight(ALTO_BOTON)
            habilitada = opcion.get("habilitada", True)
            boton.setEnabled(habilitada)
            if habilitada and opcion["clave"] == evaluacion.get("sugerida"):
                con_rol(boton, "primario")
            if not habilitada and opcion.get("motivo"):
                motivos.append(f"{opcion['boton']} no disponible: {opcion['motivo']}")
            boton.clicked.connect(lambda _c=False, clave=opcion["clave"]: self._elegir(clave))
            self.botones_opcion[opcion["clave"]] = boton
        self.botones = FilaBotones(self.boton_cancelar, self.botones_opcion.values())
        self.botones.acomodar(ANCHO_MODAL - 2 * MARGEN)
        columna.addWidget(self.botones)

        self.motivo = etiqueta(" ".join(motivos), "secundario")
        self.motivo.setWordWrap(True)
        self.motivo.setVisible(bool(motivos))
        columna.addSpacing(12)
        columna.addWidget(self.motivo)

        columna.addSpacing(12)
        nota = etiqueta("La cámara sigue abierta y el reconocimiento se reanuda al cerrar este aviso. "
                        "Cancelar no guarda nada.", "secundario")
        nota.setWordWrap(True)
        columna.addWidget(nota)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(caja)

        self._reloj = QTimer(self)
        self._reloj.timeout.connect(self._tic)
        self._mostrar_cuenta()
        self._reloj.start(1000)

    @staticmethod
    def _tarjeta(titulo, valor, tono):
        tarjeta = con_rol(QFrame(), "tarjeta-dato")
        interior = QVBoxLayout(tarjeta)
        interior.setContentsMargins(14, 12, 14, 12)
        interior.setSpacing(4)
        interior.addWidget(etiqueta(titulo, "dato-titulo"))
        dato = etiqueta(valor, "dato-valor", tono=tono or "")
        dato.setWordWrap(True)
        interior.addWidget(dato)
        return tarjeta

    @staticmethod
    def _linea(texto, tono):
        tarjeta = con_rol(QFrame(), "tarjeta-dato")
        interior = QHBoxLayout(tarjeta)
        interior.setContentsMargins(14, 12, 14, 12)
        dato = etiqueta(texto, "dato-valor", tono=tono if tono in ("verde", "rojo", "ambar") else "")
        dato.setWordWrap(True)
        interior.addWidget(dato, 1)
        tarjeta.texto = dato
        return tarjeta

    def _mostrar_cuenta(self):
        self.cuenta.setText(f"Se cancela solo en {self._restante} s")

    def _tic(self):
        self._restante -= 1
        if self._restante <= 0:
            self.reject()                       # cierre automático = Cancelar
            return
        self._mostrar_cuenta()

    def _elegir(self, clave):
        self.opcion = clave
        self.accept()

    def done(self, resultado):
        self._reloj.stop()
        super().done(resultado)


def abrir_modal(evaluacion, cierre_s, ventana, al_abrir=None):
    """Muestra el modal sobre la ventana (con el velo) y devuelve la opción o None.
    al_abrir(modal) permite cancelarlo desde afuera (por ejemplo, al cerrar sesión)."""
    velo = Velo(ventana) if ventana is not None else None
    modal = ModalConfirmacion(evaluacion, cierre_s, ventana)
    if ventana is not None:
        modal.adjustSize()
        centro = ventana.mapToGlobal(ventana.rect().center())
        modal.move(centro.x() - modal.width() // 2, centro.y() - modal.height() // 2)
    if al_abrir is not None:
        al_abrir(modal)
    try:
        modal.exec()
        return modal.opcion
    finally:
        if velo is not None:
            velo.deleteLater()
