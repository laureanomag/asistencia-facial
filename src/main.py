import sys

from PySide6.QtWidgets import QApplication

from ui.login_window import LoginWindow
from ui.tema import aplicar_tema


def main():
    app = QApplication(sys.argv)
    aplicar_tema(app)
    window = LoginWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
