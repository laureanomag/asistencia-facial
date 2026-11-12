from PySide6.QtWidgets import (
    QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QWidget,
    QStackedWidget, QButtonGroup
)

from services.auth_service import ACCESO_OPERAR_CAMARA, REPORTE_CONSULTAR, SOCIO_REGISTRAR


class MainWindow(QWidget):
    """
    Ventana principal tras un inicio de sesión exitoso. El menú lateral
    muestra solo las opciones que permiten los roles de la cuenta; los
    servicios vuelven a verificar el permiso al operar.
    """

    def __init__(self, sesion):
        super().__init__()
        self.sesion = sesion
        roles = ", ".join(sorted(sesion.roles))
        self.setWindowTitle(f"ZEBRAGYM — {sesion.nombre_mostrado} ({roles})")
        self.resize(900, 600)

        self.jornada_widget = None
        self.facial_capture_widget = None

        # Las páginas se crean una sola vez y se conservan mientras la
        # ventana exista, para que los datos ingresados no se pierdan al
        # cambiar de opción del menú. Solo se crean las permitidas (la
        # cámara, por ejemplo, arranca el proceso de reconocimiento).
        paginas = []  # (texto del menú, widget)
        if sesion.puede(ACCESO_OPERAR_CAMARA):
            from ui.facial_capture_widget import FacialCaptureWidget
            from ui.jornada_widget import JornadaWidget
            self.jornada_widget = JornadaWidget(sesion.usuario_id)
            self.facial_capture_widget = FacialCaptureWidget(self.jornada_widget)
            # Si la Jornada deja de estar disponible (edición o terminada) con
            # la cámara abierta, FacialCaptureWidget la cierra automáticamente.
            self.jornada_widget.estado_cambiado.connect(
                self.facial_capture_widget.on_jornada_estado_cambiado
            )
            paginas.append(("Asistencia por Captura Facial", self.facial_capture_widget))
            paginas.append(("Configuración de la Jornada", self.jornada_widget))
        if sesion.puede(SOCIO_REGISTRAR):
            from ui.register_student_widget import RegisterStudentWidget
            paginas.append(("Registrar Alumno", RegisterStudentWidget()))
        if sesion.puede(REPORTE_CONSULTAR):
            from ui.export_reports_widget import ExportReportsWidget
            paginas.append(("Exportar Informes",
                            ExportReportsWidget(sesion.usuario_id, sesion.nombre_usuario)))

        self.stack = QStackedWidget()
        menu_layout = QVBoxLayout()
        self.button_group = QButtonGroup(self)
        self.button_group.setExclusive(True)

        for indice, (texto, widget) in enumerate(paginas):
            self.stack.addWidget(widget)
            boton = QPushButton(texto)
            boton.setCheckable(True)
            boton.clicked.connect(lambda _checked, i=indice: self.stack.setCurrentIndex(i))
            self.button_group.addButton(boton, indice)
            menu_layout.addWidget(boton)

        if paginas:
            self.stack.setCurrentIndex(0)
            self.button_group.button(0).setChecked(True)
        else:
            self.stack.addWidget(QLabel("Su cuenta no tiene opciones disponibles."))
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
        if self.jornada_widget is not None:
            self.jornada_widget.guardar_cambios_pendientes()
        if self.facial_capture_widget is not None:
            self.facial_capture_widget.liberar_camara()
        super().closeEvent(event)
