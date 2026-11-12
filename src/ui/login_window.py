import psycopg
from PySide6.QtWidgets import (
    QDialog, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget, QMessageBox
)

from services.auth_service import AuthService, ErrorAutenticacion
from ui.cambiar_contrasenia_dialog import CambiarContraseniaDialog
from ui.main_window import MainWindow


class LoginWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.auth = AuthService()
        self.main_window = None
        self.setWindowTitle("ZEBRAGYM — Inicio de sesión")
        self.resize(420, 260)

        self.identifier_input = QLineEdit()
        self.identifier_input.setPlaceholderText("Usuario o DNI")
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Contraseña")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.returnPressed.connect(self.iniciar_sesion)

        self.login_button = QPushButton("Iniciar sesión")
        self.login_button.clicked.connect(self.iniciar_sesion)

        layout = QVBoxLayout()
        layout.addWidget(QLabel("Inicio de sesión"))
        layout.addWidget(self.identifier_input)
        layout.addWidget(self.password_input)
        layout.addWidget(self.login_button)
        self.setLayout(layout)

    def iniciar_sesion(self):
        identificador = self.identifier_input.text().strip()
        contrasenia = self.password_input.text()

        if identificador == "" or contrasenia == "":
            QMessageBox.warning(self, "Datos incompletos", "Ingrese usuario y contraseña.")
            return

        try:
            sesion = self.auth.autenticar(identificador, contrasenia)
        except ErrorAutenticacion as error:
            QMessageBox.critical(self, "Error", str(error))
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

        self.main_window = MainWindow(sesion)
        self.main_window.show()
        self.close()
