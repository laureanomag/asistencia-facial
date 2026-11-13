"""Ciclo de la aplicación: login → ventana principal → (Cerrar sesión) → login,
sin cerrar el programa. Cada ingreso arma una ventana principal nueva, con el
menú y las pantallas según los permisos de esa cuenta: no queda nada del
usuario anterior."""
from PySide6.QtCore import QObject


def _crear_login(auth_service, horario_service):
    from ui.login_window import LoginWindow
    return LoginWindow(auth_service, horario_service)


def _crear_principal(sesion, auth_service, horario_service):
    from ui.main_window import MainWindow
    return MainWindow(sesion, horario_service, auth_service=auth_service)


class Aplicacion(QObject):
    def __init__(self, auth_service=None, horario_service=None,
                 crear_login=_crear_login, crear_principal=_crear_principal):
        super().__init__()
        self._auth, self._horario = auth_service, horario_service
        self._crear_login, self._crear_principal = crear_login, crear_principal
        self.login = None
        self.principal = None

    def iniciar(self):
        self.mostrar_login()

    def mostrar_login(self, geometria=None, maximizada=False):
        self.login = self._crear_login(self._auth, self._horario)
        self.login.ingreso.connect(self.abrir_principal)
        if geometria is not None:
            self.login.setGeometry(geometria)
        self.login.showMaximized() if maximizada else self.login.show()

    def abrir_principal(self, sesion):
        login, self.login = self.login, None
        self.principal = self._crear_principal(sesion, self._auth, self._horario)
        self.principal.sesion_cerrada.connect(self.volver_al_login)
        if login is not None:
            self.principal.setGeometry(login.geometry())
            maximizada = login.isMaximized()
        else:
            maximizada = False
        self.principal.showMaximized() if maximizada else self.principal.show()
        if login is not None:
            login.close()
            login.deleteLater()

    def volver_al_login(self):
        principal, self.principal = self.principal, None
        if principal is None:
            return
        # Primero se muestra el login: si no quedara ninguna ventana abierta,
        # Qt terminaría el programa.
        self.mostrar_login(principal.geometry(), principal.isMaximized())
        principal.finalizar()
        principal.close()
        principal.deleteLater()
