from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLineEdit, QMessageBox, QPushButton, QVBoxLayout,
)

from services.auth_service import LARGO_MINIMO_CONTRASENIA, ErrorAutenticacion, ReglaDeCuentas
from ui.componentes import con_rol, etiqueta


class CambiarContraseniaDialog(QDialog):
    """Pide la contraseña actual y la nueva (dos veces). Si el cambio es
    exitoso, deja la sesión actualizada en self.sesion."""

    def __init__(self, auth_service, sesion, obligatorio=False, parent=None):
        super().__init__(parent)
        self._auth = auth_service
        self.sesion = sesion
        self.setWindowTitle("Cambiar contraseña")
        self.setMinimumWidth(440)

        self.actual_input = QLineEdit()
        self.nueva_input = QLineEdit()
        self.repetir_input = QLineEdit()
        for campo in (self.actual_input, self.nueva_input, self.repetir_input):
            campo.setEchoMode(QLineEdit.EchoMode.Password)
        self.repetir_input.returnPressed.connect(self._confirmar)

        cancelar = QPushButton("Cancelar")
        cancelar.clicked.connect(self.reject)
        guardar = con_rol(QPushButton("Guardar contraseña"), "primario")
        guardar.clicked.connect(self._confirmar)
        botones = QHBoxLayout()
        botones.setSpacing(12)
        botones.addWidget(cancelar, 1)
        botones.addWidget(guardar, 2)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 26, 28, 26)
        layout.setSpacing(8)
        layout.addWidget(etiqueta("Cambiar contraseña", "titulo-panel"))
        if obligatorio:
            layout.addWidget(etiqueta("Es tu primer ingreso: elegí una contraseña nueva para continuar.",
                                      "secundario"))
        for texto, campo in (("Contraseña actual", self.actual_input),
                             (f"Nueva contraseña (mínimo {LARGO_MINIMO_CONTRASENIA} caracteres)",
                              self.nueva_input),
                             ("Repetir la nueva contraseña", self.repetir_input)):
            layout.addSpacing(8)
            layout.addWidget(etiqueta(texto, "etiqueta"))
            layout.addWidget(campo)
        layout.addSpacing(16)
        layout.addLayout(botones)

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
