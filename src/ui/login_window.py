import psycopg
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from services.auth_service import AuthService, ErrorAutenticacion
from ui import tema
from ui.cambiar_contrasenia_dialog import CambiarContraseniaDialog
from ui.componentes import con_rol, etiqueta, logo


def pie_login(horario_service):
    """Dirección del gimnasio y, debajo, el horario armado desde horario_atencion:
    'Av. Corrientes 2833 · San Pedrito, San Salvador de Jujuy\nLun a Vie 7:30–23 · Sáb 10–14'.
    Sin conexión a la base muestra solo la dirección."""
    from config.gimnasio import DIRECCION_CORTA
    from services.horario_service import resumen_horario
    try:
        resumen = resumen_horario(horario_service.franjas_semana())
    except Exception:
        resumen = ""
    return f"{DIRECCION_CORTA}\n{resumen}" if resumen else DIRECCION_CORTA


class LoginWindow(QWidget):
    """Pantalla de ingreso. Con la cuenta validada emite `ingreso(sesion)`;
    la aplicación (ui/aplicacion.py) abre la ventana principal."""

    ingreso = Signal(object)

    def __init__(self, auth_service=None, horario_service=None):
        super().__init__()
        self.setObjectName("Ventana")
        self.auth = auth_service or AuthService()
        if horario_service is None:
            from services.horario_service import HorarioService
            horario_service = HorarioService()
        self._horario = horario_service
        self.setWindowTitle(f"{tema.NOMBRE_GIMNASIO} — Ingresar")
        self.resize(1280, 800)

        raiz = QHBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)
        raiz.addWidget(self._crear_presentacion(), 1)
        separador = con_rol(QFrame(), "separador")
        separador.setFixedWidth(1)
        raiz.addWidget(separador)
        raiz.addWidget(self._crear_formulario(), 1)

    def _crear_presentacion(self):
        lado = QFrame()
        lado.setObjectName("LoginPresentacion")
        lado.setStyleSheet(
            "QFrame#LoginPresentacion { background: qradialgradient(cx:0.5, cy:0.45, radius:0.8,"
            " fx:0.5, fy:0.45, stop:0 #1C1C1C, stop:1 #060606); }")
        lema = etiqueta(tema.LEMA, "subtitulo")
        lema.setStyleSheet("font-size: 16px;")
        self.pie = etiqueta(pie_login(self._horario), "secundario")
        self.pie.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        columna = QVBoxLayout(lado)
        columna.addStretch()
        columna.addWidget(logo(264), alignment=Qt.AlignmentFlag.AlignHCenter)
        columna.addSpacing(20)
        columna.addWidget(lema, alignment=Qt.AlignmentFlag.AlignHCenter)
        columna.addSpacing(18)
        columna.addWidget(self.pie, alignment=Qt.AlignmentFlag.AlignHCenter)
        columna.addStretch()
        return lado

    def _crear_formulario(self):
        self.identifier_input = QLineEdit()
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.returnPressed.connect(self.iniciar_sesion)
        self.identifier_input.returnPressed.connect(self.password_input.setFocus)

        self.login_button = con_rol(QPushButton("Ingresar"), "primario")
        self.login_button.setMinimumHeight(52)
        self.login_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.login_button.clicked.connect(self.iniciar_sesion)

        nota = etiqueta("Si es tu primer ingreso, el sistema te va a pedir que cambies la contraseña.",
                        "secundario")
        nota.setWordWrap(True)

        formulario = QWidget()
        formulario.setFixedWidth(380)
        campos = QVBoxLayout(formulario)
        campos.setContentsMargins(0, 0, 0, 0)
        campos.setSpacing(0)
        campos.addWidget(etiqueta("Ingresar", "titulo-login"))
        campos.addSpacing(4)
        campos.addWidget(etiqueta("Usá tu usuario o tu DNI.", "subtitulo"))
        campos.addSpacing(22)
        campos.addWidget(etiqueta("Usuario o DNI", "etiqueta"))
        campos.addSpacing(8)
        campos.addWidget(self.identifier_input)
        campos.addSpacing(20)
        campos.addWidget(etiqueta("Contraseña", "etiqueta"))
        campos.addSpacing(8)
        campos.addWidget(self.password_input)
        campos.addSpacing(20)
        campos.addWidget(self.login_button)
        campos.addSpacing(22)
        campos.addWidget(nota)

        lado = QWidget()
        fila = QHBoxLayout(lado)
        fila.setContentsMargins(130, 0, 40, 0)
        columna = QVBoxLayout()
        columna.addStretch()
        columna.addWidget(formulario)
        columna.addStretch()
        fila.addLayout(columna)
        fila.addStretch()
        return lado

    def iniciar_sesion(self):
        identificador = self.identifier_input.text().strip()
        contrasenia = self.password_input.text()

        if identificador == "" or contrasenia == "":
            QMessageBox.warning(self, "Datos incompletos", "Ingresá tu usuario o DNI y la contraseña.")
            return

        try:
            sesion = self.auth.autenticar(identificador, contrasenia)
        except ErrorAutenticacion as error:
            QMessageBox.critical(self, "No se pudo ingresar", str(error))
            return
        except psycopg.Error as error:
            QMessageBox.critical(self, "Base de datos",
                                 f"No se pudo consultar la base de datos.\n\n{error}")
            return
        finally:
            self.password_input.clear()

        if sesion.debe_cambiar_contrasenia:
            dialogo = CambiarContraseniaDialog(self.auth, sesion, obligatorio=True, parent=self)
            if dialogo.exec() != QDialog.DialogCode.Accepted:
                return
            sesion = dialogo.sesion

        self.ingreso.emit(sesion)
