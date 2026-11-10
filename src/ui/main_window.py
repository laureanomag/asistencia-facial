from PySide6.QtWidgets import (
    QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QWidget,
    QStackedWidget, QButtonGroup
)

from ui.export_reports_widget import ExportReportsWidget
from ui.facial_capture_widget import FacialCaptureWidget
from ui.jornada_widget import JornadaWidget
from ui.register_student_widget import RegisterStudentWidget


class MainWindow(QWidget):
    """
    Ventana principal tras un inicio de sesión exitoso. Tiene un menú
    lateral con 3 opciones que cambian dinámicamente el área de contenido.
    Por defecto se muestra la primera opción: Asistencia por Captura Facial.
    """

    def __init__(self, usuario):
        super().__init__()
        usuario_id, nombre_usuario = usuario[0], usuario[1]
        self.setWindowTitle(f"Sistema de Asistencia por Reconocimiento Facial — {nombre_usuario}")
        self.resize(900, 600)

        # Las páginas se crean una sola vez y se conservan mientras la
        # ventana exista, para que los datos ingresados no se pierdan al
        # cambiar de opción del menú.
        self.jornada_widget = JornadaWidget(usuario_id)
        self.facial_capture_widget = FacialCaptureWidget(self.jornada_widget)
        self.register_student_widget = RegisterStudentWidget()
        self.export_reports_widget = ExportReportsWidget(usuario_id, nombre_usuario)

        # Si la Jornada deja de estar disponible (edición o terminada) con
        # la cámara abierta, FacialCaptureWidget la cierra automáticamente.
        self.jornada_widget.estado_cambiado.connect(
            self.facial_capture_widget.on_jornada_estado_cambiado
        )

        self.stack = QStackedWidget()
        self.stack.addWidget(self.facial_capture_widget)   # índice 0
        self.stack.addWidget(self.jornada_widget)           # índice 1
        self.stack.addWidget(self.register_student_widget)  # índice 2
        self.stack.addWidget(self.export_reports_widget)    # índice 3
        self.stack.setCurrentIndex(0)

        menu_layout = QVBoxLayout()
        self.button_group = QButtonGroup(self)
        self.button_group.setExclusive(True)

        opciones = [
            "Asistencia por Captura Facial",
            "Configuración de la Jornada",
            "Registrar Alumno",
            "Exportar Informes",
        ]

        for indice, texto in enumerate(opciones):
            boton = QPushButton(texto)
            boton.setCheckable(True)
            boton.clicked.connect(lambda _checked, i=indice: self.stack.setCurrentIndex(i))
            self.button_group.addButton(boton, indice)
            menu_layout.addWidget(boton)

        self.button_group.button(0).setChecked(True)
        menu_layout.addStretch()

        menu_widget = QWidget()
        menu_widget.setLayout(menu_layout)
        menu_widget.setFixedWidth(220)

        layout = QHBoxLayout()
        layout.addWidget(menu_widget)
        layout.addWidget(self.stack)
        self.setLayout(layout)

    def closeEvent(self, event):
        # Evita dejar la webcam ocupada si la app se cierra con la cámara
        # todavía abierta (por ejemplo, con la X de la ventana).
        self.jornada_widget.guardar_cambios_pendientes()
        self.facial_capture_widget.liberar_camara()
        super().closeEvent(event)
