import base64
import time

import cv2
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from hardware.camera_controller import CameraController
from services.face_service import FaceDetector
from services.face_worker_client import FaceWorkerClient
from services.recognition_task import SenalesReconocimiento
from ui.frame_utils import frame_to_pixmap
from ui.video_panel import VideoPanel


class FacialCaptureWidget(QWidget):
    """
    Primera opción del Menú Lateral: Asistencia por Captura Facial.

    - La cámara sólo se abre con una Jornada guardada y fuera de edición.
    - Haar Cascade se ejecuta en cada frame (rectángulo de feedback).
    - Con exactamente un rostro y cada ~2 s se envía el rostro recortado al
      proceso de reconocimiento (face_worker.py), que usa DeepFace +
      FaceNet512 + distancia coseno + umbral 0.40 y registra la entrada o la
      salida. Corre en un proceso aparte para que la ventana no se congele.
      Mientras hay un reconocimiento en curso no se inicia otro.
    """

    INTERVALO_MS = 30
    INTERVALO_RECONOCIMIENTO_S = 2.0
    RETENCION_RESULTADO_S = 3.0

    def __init__(self, jornada_widget):
        super().__init__()
        self.jornada_widget = jornada_widget
        self.camara_abierta = False
        self.camera_controller = CameraController()
        self.detector = FaceDetector()

        self.is_processing = False
        self._ultimo_intento = 0.0
        self._mostrar_resultado_hasta = 0.0
        self._senales = SenalesReconocimiento()
        self._senales.terminado.connect(self._on_reconocimiento_terminado)
        self._worker = FaceWorkerClient(self._senales)

        titulo = QLabel("Asistencia por Captura Facial")
        titulo.setStyleSheet("font-weight: bold; font-size: 16px;")

        self.abrir_button = QPushButton("Abrir Cámara")
        self.cerrar_button = QPushButton("Cerrar Cámara")
        self.abrir_button.clicked.connect(self.abrir_camara)
        self.cerrar_button.clicked.connect(self.cerrar_camara)

        botones_layout = QHBoxLayout()
        botones_layout.addWidget(self.abrir_button)
        botones_layout.addWidget(self.cerrar_button)

        self.estado_label = QLabel("Cámara cerrada.")
        self.video_panel = VideoPanel()

        layout = QVBoxLayout()
        layout.addWidget(titulo)
        layout.addLayout(botones_layout)
        layout.addWidget(self.estado_label)
        layout.addWidget(self.video_panel)
        layout.addStretch()
        self.setLayout(layout)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._actualizar_frame)

        self._actualizar_botones()

        # El modelo y las fotos de referencia se cargan en segundo plano apenas
        # inicia la aplicación, para que al abrir la cámara ya estén listos.
        self._worker.iniciar()
        self._worker.enviar({"cmd": "precargar"})

    # --- Cámara ---

    def abrir_camara(self):
        if not self.jornada_widget.camara_habilitada():
            if self.jornada_widget.modo_edicion:
                texto = "La Jornada está en modo edición. Guárdela antes de abrir la cámara."
            else:
                texto = ("Antes de abrir la Cámara del Sistema debe guardarse una Jornada "
                         "(segunda opción del Menú Lateral).")
            QMessageBox.warning(self, "Jornada no disponible", texto)
            return

        if not self.camera_controller.open():
            QMessageBox.critical(self, "Cámara no disponible",
                                 "No se pudo acceder a la cámara del sistema.")
            return

        self._ultimo_intento = 0.0
        self.camara_abierta = True
        self.timer.start(self.INTERVALO_MS)
        self._actualizar_botones()

        # Se vuelven a leer las fotos de la base de datos (por si se registró
        # algún alumno). Los pedidos se atienden en orden, así que si el modelo
        # todavía se está cargando, el reconocimiento simplemente espera.
        self.is_processing = False
        self.estado_label.setText("Esperando rostro.")
        self._worker.iniciar()
        self._worker.enviar({"cmd": "invalidar"})
        self._worker.enviar({"cmd": "precargar"})

    def cerrar_camara(self):
        self.timer.stop()
        self.camera_controller.close()
        self.camara_abierta = False
        self.video_panel.limpiar()
        self.estado_label.setText("Cámara cerrada.")
        self._actualizar_botones()

    def liberar_camara(self):
        """Se llama al cerrar la aplicación: suelta la webcam y detiene el
        proceso de reconocimiento."""
        self.timer.stop()
        self.camera_controller.close()
        self.camara_abierta = False
        self._worker.detener()

    def on_jornada_estado_cambiado(self, habilitada):
        if not habilitada and self.camara_abierta:
            self.cerrar_camara()

    # --- Frames y reconocimiento ---

    def _actualizar_frame(self):
        frame = self.camera_controller.read_frame()
        if frame is None:
            return

        caras = FaceDetector.filtrar(self.detector.detectar(frame))
        original = frame.copy()
        for (x, y, w, h) in caras:
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)

        alto, ancho = frame.shape[:2]
        self.video_panel.set_aspect_ratio(ancho, alto)
        self.video_panel.mostrar_frame(frame_to_pixmap(frame, espejo=True))

        ahora = time.monotonic()
        retiene = ahora < self._mostrar_resultado_hasta

        if self.is_processing:
            return
        if len(caras) == 0:
            if not retiene:
                self.estado_label.setText("Esperando rostro.")
            return
        if len(caras) > 1:
            if not retiene:
                self.estado_label.setText("Más de un rostro detectado.")
            return
        if ahora - self._ultimo_intento < self.INTERVALO_RECONOCIMIENTO_S:
            return

        self._iniciar_reconocimiento(original, caras[0], ahora)

    def _iniciar_reconocimiento(self, frame, rect, ahora):
        jornada_id = self.jornada_widget.jornada_id
        if jornada_id is None:
            return

        rostro = self.detector.recortar(frame, rect)
        ok, buffer = cv2.imencode(".jpg", rostro, [cv2.IMWRITE_JPEG_QUALITY, 95])
        if not ok:
            return

        self.is_processing = True
        self._ultimo_intento = ahora
        self.estado_label.setText("Procesando reconocimiento facial...")
        self._worker.enviar({
            "cmd": "reconocer",
            "jornada_id": jornada_id,
            "horario_entrada": self.jornada_widget.horario_entrada().isoformat(),
            "horario_salida": self.jornada_widget.horario_salida().isoformat(),
            "imagen": base64.b64encode(buffer.tobytes()).decode("ascii"),
        })

    def _on_reconocimiento_terminado(self, resultado):
        if resultado["estado"] == "MODELO_LISTO":
            return  # carga silenciosa: no cambia lo que muestra la pantalla

        self.is_processing = False
        self._ultimo_intento = time.monotonic()
        if not self.camara_abierta:
            return
        self.estado_label.setText(resultado["mensaje"])
        self._mostrar_resultado_hasta = time.monotonic() + self.RETENCION_RESULTADO_S

    def _actualizar_botones(self):
        self.abrir_button.setEnabled(not self.camara_abierta)
        self.cerrar_button.setEnabled(self.camara_abierta)

    def hideEvent(self, event):
        if self.camara_abierta:
            self.cerrar_camara()
        super().hideEvent(event)
