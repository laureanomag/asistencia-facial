from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit, QMessageBox, QVBoxLayout
)

from services.auth_service import ErrorAutenticacion, ReglaDeCuentas


class CambiarContraseniaDialog(QDialog):
    """Pide la contraseña actual y la nueva (dos veces). Si el cambio es
    exitoso, deja la sesión actualizada en self.sesion."""

    def __init__(self, auth_service, sesion, obligatorio=False, parent=None):
        super().__init__(parent)
        self._auth = auth_service
        self.sesion = sesion
        self.setWindowTitle("Cambiar contraseña")

        self.actual_input = QLineEdit()
        self.nueva_input = QLineEdit()
        self.repetir_input = QLineEdit()
        for campo in (self.actual_input, self.nueva_input, self.repetir_input):
            campo.setEchoMode(QLineEdit.EchoMode.Password)

        formulario = QFormLayout()
        formulario.addRow("Contraseña actual:", self.actual_input)
        formulario.addRow("Nueva contraseña:", self.nueva_input)
        formulario.addRow("Repetir nueva:", self.repetir_input)

        botones = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        botones.accepted.connect(self._confirmar)
        botones.rejected.connect(self.reject)

        layout = QVBoxLayout()
        if obligatorio:
            layout.addWidget(QLabel("Debe cambiar su contraseña antes de continuar."))
        layout.addLayout(formulario)
        layout.addWidget(botones)
        self.setLayout(layout)

    def _confirmar(self):
        nueva = self.nueva_input.text()
        if nueva != self.repetir_input.text():
            QMessageBox.warning(self, "Contraseña", "Las contraseñas nuevas no coinciden.")
            return
        try:
            self.sesion = self._auth.cambiar_contrasenia(self.sesion, self.actual_input.text(), nueva)
        except (ErrorAutenticacion, ReglaDeCuentas) as error:
            QMessageBox.warning(self, "Contraseña", str(error))
            return
        self.accept()
