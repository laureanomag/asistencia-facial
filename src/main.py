import sys
import traceback

from PySide6.QtWidgets import QApplication, QMessageBox

from ui.aplicacion import Aplicacion
from ui.tema import aplicar_tema


def mensaje_de_error(tipo, valor):
    """Texto claro en español para un error inesperado."""
    nombre = tipo.__name__ if tipo else "Error"
    if nombre in ("OperationalError", "InterfaceError") or "psycopg" in (tipo.__module__ or ""):
        return ("No se pudo comunicar con la base de datos. Revisá que el servicio esté "
                f"funcionando e intentá de nuevo.\n\nDetalle: {valor}")
    return f"Ocurrió un error inesperado. La aplicación sigue funcionando.\n\nDetalle: {valor}"


def manejar_error(tipo, valor, rastro):
    """Ningún error cierra la aplicación: se registra en la consola y se
    muestra un aviso; el resto de las pantallas sigue funcionando."""
    traceback.print_exception(tipo, valor, rastro)
    if QApplication.instance() is not None:
        QMessageBox.critical(None, "ZebraGym", mensaje_de_error(tipo, valor))


def main():
    sys.excepthook = manejar_error
    app = QApplication(sys.argv)
    aplicar_tema(app)
    aplicacion = Aplicacion()
    aplicacion.iniciar()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
