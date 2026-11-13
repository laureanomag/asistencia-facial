"""Pantalla "Control de acceso" (docs/diseno/diseno_camara_confirmar.png y
diseno_camara_rechazo.png).

Flujo: la cámara detecta un rostro (Haar) -> cada ~2 s se envía al proceso de
reconocimiento -> si la persona puede entrar o fichar llega una PROPUESTA: se
pausa el reconocimiento (la webcam sigue mostrando video) y se abre el modal
-> la opción elegida confirma; Cancelar o el cierre a los 60 s no guardan nada
-> al responder el proceso, se muestra el resultado y se reanuda el reconocimiento.
Los rechazos se muestran con su motivo y ya quedaron guardados en acceso.
A la derecha: "Ingresos de socios" (tabla acceso) y "Fichajes del personal"
(tabla fichaje, con llegada, salida y estado)."""
import base64
import time
from datetime import datetime

import cv2
from PySide6.QtCore import QSize, QTimer, Qt
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget,
)

from services.reglas_ingreso import ETIQUETAS_MOTIVO, hora_texto
from ui import tema
from ui.componentes import EtiquetaEstado, FranjaDecorativa, con_rol, etiqueta

# Colores BGR (OpenCV) para el marco del rostro
COLOR_MARCO = {"dorado": (32, 184, 240), "rojo": (113, 113, 248), "verde": (153, 211, 52)}


def dibujar_marco(frame, rect, color, grosor=3):
    """Esquinas del recuadro del rostro, como en el diseño."""
    x, y, w, h = rect
    largo = max(12, int(min(w, h) * 0.22))
    for (cx, cy, dx, dy) in ((x, y, 1, 1), (x + w, y, -1, 1), (x, y + h, 1, -1), (x + w, y + h, -1, -1)):
        cv2.line(frame, (cx, cy), (cx + dx * largo, cy), color, grosor, cv2.LINE_AA)
        cv2.line(frame, (cx, cy), (cx, cy + dy * largo), color, grosor, cv2.LINE_AA)


def frame_a_pixmap(frame_bgr, espejo=True):
    from ui.frame_utils import frame_to_pixmap
    return frame_to_pixmap(frame_bgr, espejo=espejo)


class Video(QLabel):
    """Muestra el video llenando el panel (recorta lo que sobra, sin deformar).
    Su tamaño no depende del frame, para que no crezca solo."""

    def __init__(self):
        super().__init__()
        con_rol(self, "video")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.setMinimumSize(480, 330)
        self._pixmap = None

    def sizeHint(self):
        return QSize(640, 420)

    def mostrar(self, pixmap):
        self._pixmap = pixmap
        self._pintar()

    def limpiar(self, texto=""):
        self._pixmap = None
        self.clear()
        self.setText(texto)

    def resizeEvent(self, evento):
        super().resizeEvent(evento)
        self._pintar()

    def _pintar(self):
        if self._pixmap is None or self.width() <= 0 or self.height() <= 0:
            return
        escalado = self._pixmap.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                       Qt.TransformationMode.SmoothTransformation)
        x = (escalado.width() - self.width()) // 2
        y = (escalado.height() - self.height()) // 2
        self.setPixmap(escalado.copy(x, y, self.width(), self.height()))


class AvisoResultado(QFrame):
    """Tarjeta sobre el video: ingreso rechazado, registrado, cancelado, etc."""

    ICONOS = {"rojo": "⊗", "verde": "✓", "ambar": "!", "neutro": "i"}

    def __init__(self):
        super().__init__()
        con_rol(self, "aviso", tono="rojo")
        self.icono = con_rol(QLabel("⊗"), "aviso-icono")
        self.icono.setFixedWidth(22)
        self.icono.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        self.titulo = QLabel()
        self.titulo.setStyleSheet("font-size: 15px; font-weight: 800;")
        self.mensaje = QLabel()
        self.mensaje.setWordWrap(True)
        self.mensaje.setStyleSheet("font-size: 13px;")
        textos = QVBoxLayout()
        textos.setSpacing(2)
        textos.addWidget(self.titulo)
        textos.addWidget(self.mensaje)
        fila = QHBoxLayout(self)
        fila.setContentsMargins(12, 9, 14, 9)
        fila.setSpacing(10)
        fila.addWidget(self.icono)
        fila.addLayout(textos, 1)
        self.hide()

    def mostrar(self, titulo, mensaje, tono):
        self.setProperty("tono", tono)
        self.icono.setText(self.ICONOS.get(tono, "i"))
        self.titulo.setText(titulo)
        self.mensaje.setText(mensaje)
        for widget in (self, self.icono):
            tema.refrescar_estilo(widget)
        self.show()


class PanelCamara(QFrame):
    def __init__(self):
        super().__init__()
        con_rol(self, "camara", tono="dorado")
        self.video = Video()
        self.chip_vivo = con_rol(QLabel('<span style="color:#F87171;">●</span>&nbsp; Cámara en vivo'),
                                 "chip-camara", tono="neutro")
        self.chip_vivo.setStyleSheet("color: #FFFFFF;")
        self.chip_estado = con_rol(QLabel("Cargando reconocimiento…"), "chip-camara", tono="neutro")
        self.aviso = AvisoResultado()

        capa = QWidget()
        capa.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        arriba = QHBoxLayout()
        arriba.addWidget(self.chip_vivo)
        arriba.addStretch()
        arriba.addWidget(self.chip_estado)
        columna = QVBoxLayout(capa)
        columna.setContentsMargins(16, 16, 16, 16)
        columna.addLayout(arriba)
        columna.addStretch()
        columna.addWidget(self.aviso)

        grilla = QGridLayout(self)
        grilla.setContentsMargins(2, 2, 2, 2)
        grilla.addWidget(self.video, 0, 0)
        grilla.addWidget(capa, 0, 0)

    def estado(self, texto, tono):
        self.chip_estado.setText(texto)
        if self.chip_estado.property("tono") != tono:
            self.chip_estado.setProperty("tono", tono)
            tema.refrescar_estilo(self.chip_estado)

    def borde(self, tono):
        if self.property("tono") != tono:
            self.setProperty("tono", tono)
            tema.refrescar_estilo(self)


class FilaIngreso(QFrame):
    def __init__(self, nombre, detalle, etiqueta_estado, tono):
        super().__init__()
        con_rol(self, "fila-ingreso")
        textos = QVBoxLayout()
        textos.setSpacing(2)
        titulo = QLabel(nombre)
        titulo.setStyleSheet("font-size: 15px; font-weight: 700;")
        textos.addWidget(titulo)
        textos.addWidget(etiqueta(detalle, "secundario"))
        fila = QHBoxLayout(self)
        fila.setContentsMargins(0, 12, 0, 12)
        fila.addLayout(textos, 1)
        fila.addWidget(EtiquetaEstado(etiqueta_estado, tono))


def describir_ingreso(fila):
    """(nombre, detalle, etiqueta, tono) para una fila de AccesoRepository.ultimos."""
    _id, momento, resultado, motivo, nombre, apellido, plan = fila
    detalle = f"{hora_texto(momento)} · {plan or '—'}"
    if resultado == "permitido":
        return f"{nombre} {apellido}", detalle, "Permitido", "verde"
    if nombre:
        return f"{nombre} {apellido}", detalle, ETIQUETAS_MOTIVO.get(motivo, "Rechazado"), "rojo"
    return ETIQUETAS_MOTIVO.get(motivo, "Rechazado"), detalle, "Rechazado", "rojo"


def describir_fichaje(fila):
    """(nombre, detalle, etiqueta, tono) para una fila de FichajeRepository.ultimos."""
    _id, nombre, apellido, entrada, salida, jornada_id, horario_entrada = fila
    salida_texto = hora_texto(salida) if salida else "en curso"
    detalle = f"Llegada {hora_texto(entrada)} · Salida {salida_texto}"
    persona = f"{nombre or ''} {apellido or ''}".strip() or "Empleado"
    if jornada_id is None:
        return persona, detalle, "Fuera de turno", "ambar"
    inicio = datetime.combine(entrada.date(), horario_entrada, tzinfo=entrada.tzinfo)
    tarde = int((entrada - inicio).total_seconds() // 60)
    if tarde > 0:
        return persona, detalle, f"{tarde} min tarde", "ambar"
    return persona, detalle, "En horario", "verde"


class ListaUltimos(QWidget):
    """Título y hasta N filas (o un texto cuando no hay ninguna)."""

    def __init__(self, titulo, vacio, describir):
        super().__init__()
        self._describir = describir
        self.texto_vacio = vacio
        self.filas = QVBoxLayout()
        self.filas.setSpacing(0)
        self.vacio = etiqueta(vacio, "secundario")
        self.vacio.setWordWrap(True)
        columna = QVBoxLayout(self)
        columna.setContentsMargins(0, 0, 0, 0)
        columna.addWidget(etiqueta(titulo, "titulo-panel"))
        columna.addSpacing(8)
        columna.addLayout(self.filas)
        columna.addWidget(self.vacio)

    def mostrar(self, filas, error=None):
        while self.filas.count():
            item = self.filas.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for fila in filas:
            self.filas.addWidget(FilaIngreso(*self._describir(fila)))
        self.vacio.setText(error or self.texto_vacio)
        self.vacio.setVisible(not filas)


class PanelUltimos(QFrame):
    def __init__(self):
        super().__init__()
        con_rol(self, "panel")
        self.setFixedWidth(350)
        self.socios = ListaUltimos("Ingresos de socios", "Todavía no hay ingresos de socios.",
                                   describir_ingreso)
        self.personal = ListaUltimos("Fichajes del personal", "Todavía no hay fichajes.",
                                     describir_fichaje)
        columna = QVBoxLayout(self)
        columna.setContentsMargins(20, 20, 20, 18)
        columna.addWidget(self.socios)
        columna.addSpacing(18)
        columna.addWidget(self.personal)
        columna.addStretch()


class ControlAccesoPage(QWidget):
    INTERVALO_MS = 30
    INTERVALO_RECONOCIMIENTO_S = 2.0
    RETENCION_AVISO_S = 5.0
    ULTIMOS = 4

    def __init__(self, worker=None, camara=None, detector=None, accesos=None, abrir_modal=None,
                 reloj=time.monotonic, horario=None, fichajes=None):
        super().__init__()
        from services.face_service import FaceDetector
        from services.recognition_task import SenalesReconocimiento
        self._reloj = reloj
        self._senales = SenalesReconocimiento()
        self._senales.terminado.connect(self.on_respuesta)
        if worker is None:
            from services.face_worker_client import FaceWorkerClient
            worker = FaceWorkerClient(self._senales)
        if camara is None:
            from hardware.camera_controller import CameraController
            camara = CameraController()
        if accesos is None:
            from repositories.acceso_repository import AccesoRepository
            accesos = AccesoRepository()
        if horario is None:
            from services.horario_service import HorarioService
            horario = HorarioService()
        if fichajes is None:
            from repositories.fichaje_repository import FichajeRepository
            fichajes = FichajeRepository()
        self.worker, self.camara, self.accesos, self.horario = worker, camara, accesos, horario
        self.fichajes = fichajes
        self.detector = detector or FaceDetector()
        self._abrir_modal = abrir_modal or self._modal_por_defecto

        self.modelo_listo = False
        self.procesando = False       # hay un rostro enviado esperando respuesta
        self.pausado = False          # modal abierto o confirmación en curso
        self._ultimo_intento = 0.0
        self._aviso_hasta = 0.0
        self._reintento_hasta = 0.0
        self._estado_texto = ("Cargando reconocimiento…", "neutro")
        self._tono = "dorado"
        self._rostro_desde = None     # para medir cuánto tarda en abrirse el modal
        self._modal = None            # modal de confirmación abierto (para cancelarlo al salir)
        self.liberada = False         # se cerró la sesión o la aplicación

        self.camara_panel = PanelCamara()
        self.ultimos = PanelUltimos()
        arriba = QHBoxLayout()
        arriba.setSpacing(20)
        arriba.addWidget(self.camara_panel, 1)
        arriba.addWidget(self.ultimos)
        columna = QVBoxLayout(self)
        columna.setContentsMargins(0, 0, 0, 0)
        columna.setSpacing(20)
        columna.addLayout(arriba, 1)
        self.franja = FranjaDecorativa()
        columna.addWidget(self.franja)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.actualizar)
        self.worker.iniciar()
        self.worker.enviar({"cmd": "precargar"})
        self._pintar_estado()

    # --- Ciclo de vida ---

    def showEvent(self, evento):
        super().showEvent(evento)
        if self.liberada:
            return
        self.refrescar_ultimos()
        self.refrescar_franja()
        if not self.camara.open():
            self.camara_panel.video.limpiar("No se pudo acceder a la cámara.")
            self.camara_panel.estado("Cámara no disponible", "rojo")
            return
        # El modelo y las referencias se cargan una sola vez (al crear la
        # pantalla). El proceso de reconocimiento recarga las referencias solo
        # si cambiaron las fotos en la base.
        self.timer.start(self.INTERVALO_MS)

    def hideEvent(self, evento):
        self.timer.stop()
        self.camara.close()
        super().hideEvent(evento)

    def liberar(self):
        """Al cerrar la sesión o la aplicación: cancela el modal abierto (sin
        registrar nada), suelta la webcam y termina el proceso de reconocimiento."""
        self.liberada = True
        self.timer.stop()
        if self._modal is not None:
            self._modal.reject()
        self.camara.close()
        self.worker.detener()

    def refrescar_franja(self):
        """"Hoy entrenaron N socios" y el horario, desde la base."""
        from services.horario_service import resumen_horario
        try:
            cantidad = self.accesos.socios_que_entrenaron_hoy()
            titulo = "Hoy entrenó 1 socio" if cantidad == 1 else f"Hoy entrenaron {cantidad} socios"
        except Exception:
            titulo = "Hoy entrenaron —"
        try:
            horario = resumen_horario(self.horario.franjas_semana())
        except Exception:
            horario = ""
        self.franja.mostrar(titulo, f"Horario: {horario}" if horario else "Horario no disponible")

    def refrescar_ultimos(self):
        try:
            self.ultimos.socios.mostrar(self.accesos.ultimos(self.ULTIMOS))
        except Exception:
            self.ultimos.socios.mostrar([], "No se pudieron consultar los ingresos.")
        try:
            self.ultimos.personal.mostrar(self.fichajes.ultimos(self.ULTIMOS))
        except Exception:
            self.ultimos.personal.mostrar([], "No se pudieron consultar los fichajes.")

    # --- Frames ---

    def actualizar(self):
        if self.liberada:
            return
        ahora = self._reloj()
        if self._aviso_hasta and ahora >= self._aviso_hasta:
            self._aviso_hasta = 0.0
            self.camara_panel.aviso.hide()
            self._tono = "dorado"
        self._pintar_estado()

        frame = self.camara.read_frame()
        if frame is None:
            return
        caras = self.detector.filtrar(self.detector.detectar(frame))
        if not caras:
            self._rostro_desde = None
        elif self._rostro_desde is None and not self.pausado:
            self._rostro_desde = ahora
        original = frame.copy()
        for rect in caras:
            dibujar_marco(frame, rect, COLOR_MARCO[self._tono])
        self.camara_panel.video.mostrar(frame_a_pixmap(frame))

        if (self.pausado or self.procesando or not self.modelo_listo or len(caras) != 1
                or ahora - self._ultimo_intento < self.INTERVALO_RECONOCIMIENTO_S):
            return
        self.enviar_rostro(self.detector.recortar(original, caras[0]), ahora)

    def enviar_rostro(self, rostro, ahora):
        ok, buffer = cv2.imencode(".jpg", rostro, [cv2.IMWRITE_JPEG_QUALITY, 95])
        if not ok:
            return
        self.procesando = True
        self._ultimo_intento = ahora
        self.worker.enviar({"cmd": "reconocer",
                            "imagen": base64.b64encode(buffer.tobytes()).decode("ascii")})

    # --- Respuestas del proceso de reconocimiento ---

    def on_respuesta(self, r):
        if self.liberada:             # respuesta tardía del proceso ya detenido
            return
        estado = r.get("estado")
        if estado == "MODELO_LISTO":
            self.modelo_listo = True
            self._estado_texto = ("Reconocimiento en curso", "dorado")
            self._pintar_estado()
            return
        self.procesando = False
        self._ultimo_intento = self._reloj()

        if estado in ("PROPUESTA", "RECHAZADO", "AVISO") and self._rostro_desde is not None:
            print(f"[Control de acceso] {estado.lower()} a los "
                  f"{self._reloj() - self._rostro_desde:.1f} s de detectar el rostro", flush=True)
            self._rostro_desde = None
        if estado == "PROPUESTA":
            self._proponer(r)
        elif estado == "CONFIRMADO":
            self.pausado = False
            titulo = "Asistencia laboral" if r.get("opcion") == "fichar" else "Entrada al gimnasio"
            self._resultado(f"{titulo} · {r.get('nombre', '')}", r["mensaje"], "verde")
            self.refrescar_ultimos()
            self.refrescar_franja()
        elif estado == "RECHAZADO":
            self.pausado = False
            nombre = r.get("nombre") or r.get("etiqueta") or ""
            self._resultado(f"Ingreso rechazado · {nombre}".rstrip(" ·"), r["mensaje"], "rojo")
            self._reintento_hasta = self._reloj() + r.get("reintento_s", 10)
            self.refrescar_ultimos()
        elif estado in ("CANCELADO", "PROPUESTA_VENCIDA"):
            self.pausado = False
            self._resultado("Cancelado" if estado == "CANCELADO" else "Confirmación vencida",
                            r["mensaje"], "neutro")
        elif estado == "AVISO":
            self._resultado(r.get("nombre") or "Aviso", r["mensaje"], "ambar")
        elif estado == "EN_ESPERA":
            self._reintento_hasta = self._reloj() + r.get("reintento_s", 10)
        elif estado == "ERROR":
            self.pausado = False
            self._resultado("Error", r.get("mensaje", ""), "rojo")
        else:
            self._estado_texto = self._texto_progreso(estado)
        self._pintar_estado()

    @staticmethod
    def _texto_progreso(estado):
        return {
            "CONFIRMANDO": ("Verificando identidad…", "dorado"),
            "NO_RECONOCIDO": ("Rostro no reconocido", "neutro"),
            "AMBIGUO": ("Mirá de frente, con buena luz", "ambar"),
            "SIN_REFERENCIAS": ("Sin fotos de referencia", "rojo"),
            "PROPUESTA_PENDIENTE": ("Confirmación abierta", "dorado"),
        }.get(estado, ("Reconocimiento en curso", "dorado"))

    def _proponer(self, r):
        self.pausado = True
        self._estado_texto = ("Confirmación abierta", "dorado")
        self._pintar_estado()
        opcion = self._abrir_modal(r["evaluacion"], r.get("cierre_s", 60))
        if self.liberada:             # se cerró la sesión con el modal abierto: no se registra nada
            return
        if opcion:
            self.worker.enviar({"cmd": "confirmar", "token": r["token"], "opcion": opcion})
        else:
            self.worker.enviar({"cmd": "cancelar", "token": r["token"]})
        # Sigue en pausa hasta que el proceso responda la confirmación o la cancelación.

    def _modal_por_defecto(self, evaluacion, cierre_s):
        from ui.modal_confirmacion import abrir_modal
        try:
            return abrir_modal(evaluacion, cierre_s, self.window(),
                               al_abrir=lambda modal: setattr(self, "_modal", modal))
        finally:
            self._modal = None

    def _resultado(self, titulo, mensaje, tono):
        self.camara_panel.aviso.mostrar(titulo, mensaje, tono)
        self._aviso_hasta = self._reloj() + self.RETENCION_AVISO_S
        self._tono = tono if tono in COLOR_MARCO else "dorado"
        self._estado_texto = ("Reconocimiento en curso", "dorado")

    def _pintar_estado(self):
        falta = self._reintento_hasta - self._reloj()
        if falta > 0:
            self.camara_panel.estado(f"Reintento en {int(falta + 0.999)} s", "rojo")
        elif self.pausado:
            self.camara_panel.estado("Confirmación abierta", "dorado")
        else:
            self.camara_panel.estado(*self._estado_texto)
        self.camara_panel.borde(self._tono if self.camara_panel.aviso.isVisible() else "dorado")
