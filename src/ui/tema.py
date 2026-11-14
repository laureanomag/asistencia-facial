"""Identidad visual de ZebraGym: colores, tipografías y hoja de estilos global.

Es el único lugar con colores y tipografías: las pantallas solo asignan un
"rol" (propiedad de Qt) a cada widget, por ejemplo setProperty("rol", "titulo").
Las tipografías (Montserrat para títulos, Inter para el texto) se cargan desde
assets/fonts; si falta algún archivo se usa la fuente del sistema."""
from pathlib import Path

from PySide6.QtGui import QFont, QFontDatabase, QIcon

from config import gimnasio

RAIZ = Path(__file__).resolve().parents[2]
ASSETS = RAIZ / "assets"
LOGO = gimnasio.LOGO
FUENTES = ("Montserrat[wght].ttf", "Inter[opsz,wght].ttf")

NOMBRE_GIMNASIO = gimnasio.NOMBRE      # nombre y dirección: config/gimnasio.py
LEMA = "Control de acceso por reconocimiento facial"

# Paleta
FONDO = "#060606"
PANEL = "#151515"
BORDE = "#2A2A2A"
TEXTO = "#FFFFFF"
TEXTO_SECUNDARIO = "#A8A8A8"
DORADO = "#F0B820"
VERDE = "#34D399"
ROJO = "#F87171"
AMBAR = "#FBBF24"

# Fondos y bordes translúcidos de las etiquetas de estado (sobre fondo oscuro)
TONOS = {
    "verde": (VERDE, "rgba(52, 211, 153, 0.12)", "rgba(52, 211, 153, 0.45)"),
    "rojo": (ROJO, "rgba(248, 113, 113, 0.12)", "rgba(248, 113, 113, 0.45)"),
    "ambar": (AMBAR, "rgba(251, 191, 36, 0.12)", "rgba(251, 191, 36, 0.45)"),
    "dorado": (DORADO, "rgba(240, 184, 32, 0.10)", "rgba(240, 184, 32, 0.55)"),
    "neutro": (TEXTO_SECUNDARIO, "rgba(255, 255, 255, 0.06)", "rgba(255, 255, 255, 0.18)"),
}

# Fondo sólido con tinte para avisos que se dibujan sobre el video
FONDOS_AVISO = {"rojo": "#2A1414", "verde": "#0E261C", "ambar": "#2A2110", "dorado": "#29220F",
                "neutro": "#1B1B1B"}

FAMILIA_TITULOS = "Montserrat"
FAMILIA_TEXTO = "Inter"
_familias_cargadas = set()


def cargar_tipografias():
    """Registra las tipografías de assets/fonts. Devuelve las familias que
    quedaron disponibles; las que falten se reemplazan por la del sistema."""
    for archivo in FUENTES:
        ruta = ASSETS / "fonts" / archivo
        if not ruta.exists():
            continue
        indice = QFontDatabase.addApplicationFont(str(ruta))
        if indice >= 0:
            _familias_cargadas.update(QFontDatabase.applicationFontFamilies(indice))
    return set(_familias_cargadas)


def _familia(preferida):
    return preferida if preferida in _familias_cargadas else QFont().defaultFamily()


def hoja_de_estilos():
    titulos = _familia(FAMILIA_TITULOS)
    texto = _familia(FAMILIA_TEXTO)
    reglas = [f"""
    QWidget {{
        background: transparent; color: {TEXTO};
        font-family: "{texto}"; font-size: 14px;
    }}
    QMainWindow, QDialog, QWidget#Ventana {{ background: {FONDO}; }}
    QToolTip {{ background: {PANEL}; color: {TEXTO}; border: 1px solid {BORDE}; padding: 6px; }}

    /* Textos */
    QLabel[rol="titulo"] {{ font-family: "{titulos}"; font-size: 30px; font-weight: 800; }}
    QLabel[rol="titulo-login"] {{ font-family: "{titulos}"; font-size: 34px; font-weight: 800; }}
    QLabel[rol="titulo-panel"] {{ font-family: "{titulos}"; font-size: 17px; font-weight: 700; }}
    QLabel[rol="subtitulo"] {{ color: {TEXTO_SECUNDARIO}; font-size: 15px; }}
    QLabel[rol="secundario"] {{ color: {TEXTO_SECUNDARIO}; font-size: 13px; }}
    QLabel[rol="etiqueta"] {{ font-size: 13px; font-weight: 700; }}
    QLabel[rol="marca"] {{ font-family: "{titulos}"; font-size: 21px; font-weight: 800; }}
    QLabel[rol="marca-gym"] {{
        font-family: "{titulos}"; font-size: 12px; font-weight: 800; color: {DORADO};
        letter-spacing: 4px;
    }}

    /* Paneles */
    QFrame[rol="panel"] {{ background: {PANEL}; border: 1px solid {BORDE}; border-radius: 16px; }}
    QFrame[rol="panel"] QLabel {{ background: transparent; border: none; }}
    QFrame#Sidebar {{ background: {PANEL}; border: none; border-right: 1px solid {BORDE}; }}
    QFrame[rol="tarjeta-usuario"] {{ border: 1px solid {BORDE}; border-radius: 12px; }}
    QFrame[rol="tarjeta-usuario"]:hover {{ border-color: {TEXTO_SECUNDARIO}; background: #1A1A1A; }}
    QMenu {{
        background: {PANEL}; border: 1px solid {BORDE}; border-radius: 10px; padding: 6px;
        color: {TEXTO}; font-size: 14px;
    }}
    QMenu::item {{ padding: 9px 18px 9px 12px; border-radius: 6px; }}
    QMenu::item:selected {{ background: #232323; }}
    QMenu::icon {{ padding-left: 10px; }}
    QMenu::separator {{ height: 1px; background: {BORDE}; margin: 5px 8px; }}
    QFrame[rol="separador"] {{ background: {BORDE}; border: none; }}

    /* Campos */
    QLineEdit, QDateEdit, QSpinBox, QComboBox, QTimeEdit {{
        background: {PANEL}; border: 1px solid {BORDE}; border-radius: 10px;
        padding: 0 14px; min-height: 46px; font-size: 15px;
        selection-background-color: {DORADO}; selection-color: {FONDO};
    }}
    QLineEdit:focus, QDateEdit:focus, QSpinBox:focus, QComboBox:focus, QTimeEdit:focus {{
        border: 1px solid {DORADO};
    }}

    /* Botones */
    QPushButton {{
        background: {PANEL}; border: 1px solid {BORDE}; border-radius: 12px;
        padding: 0 20px; min-height: 44px; font-size: 15px; font-weight: 600;
    }}
    QPushButton:hover {{ border-color: {TEXTO_SECUNDARIO}; }}
    QLineEdit:disabled, QDateEdit:disabled, QSpinBox:disabled, QComboBox:disabled, QTimeEdit:disabled {{
        color: #5A5A5A; background: {FONDO};
    }}
    QPushButton:disabled {{ color: #5A5A5A; }}
    QPushButton[rol="primario"] {{
        background: {DORADO}; color: {FONDO}; border: none; font-weight: 700;
    }}
    QPushButton[rol="primario"]:hover {{ background: #F5C842; }}
    QPushButton[rol="primario"]:disabled {{ background: #5C4A12; color: #2A2A2A; }}
    QPushButton[rol="menu"] {{
        background: transparent; border: none; border-radius: 10px;
        text-align: left; padding: 0 14px; min-height: 44px; font-size: 15px; font-weight: 600;
    }}
    QPushButton[rol="menu"]:hover {{ background: #1E1E1E; }}
    QPushButton[rol="menu"]:checked {{ background: {DORADO}; color: {FONDO}; }}
    QLabel[rol="texto-menu"] {{ font-size: 15px; font-weight: 600; }}
    QLabel[rol="texto-menu"][activo="true"] {{ color: {FONDO}; font-weight: 700; }}

    /* Avatar con iniciales */
    QLabel[rol="avatar"] {{
        background: {BORDE}; color: {DORADO}; border-radius: 18px;
        font-family: "{titulos}"; font-size: 13px; font-weight: 800;
    }}
    QLabel[rol="avatar-grande"] {{
        background: #222222; color: {DORADO}; border: 2px solid {DORADO}; border-radius: 37px;
        font-family: "{titulos}"; font-size: 24px; font-weight: 800;
    }}

    /* Casillas */
    QCheckBox {{ spacing: 8px; }}
    QCheckBox::indicator {{
        width: 18px; height: 18px; border-radius: 5px; border: 1px solid {TEXTO_SECUNDARIO};
        background: {FONDO};
    }}
    QCheckBox::indicator:checked {{ background: {DORADO}; border-color: {DORADO}; }}

    /* Tablas */
    QTableWidget, QTableView {{
        background: transparent; border: none; gridline-color: {BORDE};
        alternate-background-color: #111111;
        selection-background-color: {FONDOS_AVISO["dorado"]}; selection-color: {TEXTO};
    }}
    QTableWidget::item:selected {{ background: {FONDOS_AVISO["dorado"]}; color: {DORADO}; }}
    QHeaderView::section {{
        background: {DORADO}; color: {FONDO}; border: none; padding: 10px 12px;
        font-size: 12px; font-weight: 800;
    }}
    QScrollBar:vertical {{ background: transparent; width: 10px; }}
    QScrollBar::handle:vertical {{ background: {BORDE}; border-radius: 5px; min-height: 30px; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
    QMessageBox {{ background: {PANEL}; }}

    /* Control de acceso */
    QLabel[rol="video"] {{ background: #0B0B0B; border-radius: 14px; }}
    QLabel[rol="chip-camara"] {{
        background: rgba(0, 0, 0, 0.65); border-radius: 13px; padding: 4px 12px;
        font-size: 13px; font-weight: 700;
    }}
    QPushButton[rol="enlace"] {{
        background: transparent; border: none; color: {DORADO}; padding: 0;
        min-height: 24px; font-size: 14px; font-weight: 700; text-align: left;
    }}
    QPushButton[rol="enlace"]:hover {{ color: #F5C842; }}
    QFrame[rol="fila-ingreso"] {{ border: none; border-top: 1px solid {BORDE}; }}
    QFrame[rol="fila-ingreso"] QLabel {{ background: transparent; }}

    /* Panel y formularios */
    QLabel[rol="dato-panel"] {{
        color: {TEXTO_SECUNDARIO}; font-size: 12px; font-weight: 700; letter-spacing: 1px;
    }}
    QLabel[rol="numero-panel"] {{ font-family: "{titulos}"; font-size: 30px; font-weight: 800; }}
    QLabel[rol="error"] {{ color: {ROJO}; font-size: 13px; }}
    QLabel[rol="ok"] {{ color: {VERDE}; font-size: 13px; }}
    QLabel[rol="advertencia"] {{ color: {AMBAR}; font-size: 13px; }}
    QLineEdit[error="true"], QComboBox[error="true"] {{ border: 1px solid {ROJO}; }}
    QComboBox QAbstractItemView {{
        background: {PANEL}; border: 1px solid {BORDE}; selection-background-color: {DORADO};
        selection-color: {FONDO};
    }}
    QFrame[rol="slot-foto"] {{ background: #0F0F0F; border: 1px solid {BORDE}; border-radius: 12px; }}
    QFrame[rol="slot-foto"] QLabel {{ background: transparent; border: none; }}
    QLabel[rol="miniatura"] {{ background: #0B0B0B; border: 1px solid {BORDE}; border-radius: 10px; color: {TEXTO_SECUNDARIO}; }}

    /* Modal de confirmación */
    QWidget#Velo {{ background: rgba(0, 0, 0, 0.62); }}
    QFrame[rol="modal"] {{ background: {PANEL}; border: 1px solid {DORADO}; border-radius: 20px; }}
    QFrame[rol="modal"] QLabel {{ background: transparent; border: none; }}
    QFrame[rol="tarjeta-dato"] {{ background: #0F0F0F; border: 1px solid {BORDE}; border-radius: 12px; }}
    QFrame[rol="tarjeta-dato"] QLabel {{ background: transparent; border: none; }}
    QLabel[rol="dato-titulo"] {{ color: {TEXTO_SECUNDARIO}; font-size: 13px; }}
    QLabel[rol="dato-valor"] {{ font-size: 16px; font-weight: 700; }}
    QLabel[rol="dato-valor"][tono="verde"] {{ color: {VERDE}; }}
    QLabel[rol="dato-valor"][tono="rojo"] {{ color: {ROJO}; }}
    QLabel[rol="dato-valor"][tono="ambar"] {{ color: {AMBAR}; }}
    QLabel[rol="nombre-modal"] {{ font-family: "{titulos}"; font-size: 24px; font-weight: 700; }}
    QLabel[rol="titulo-modal"] {{ font-family: "{titulos}"; font-size: 21px; font-weight: 800; }}
    QFrame[rol="modal"] QLabel[rol="avatar-grande"] {{
        background: #222222; color: {DORADO}; border: 2px solid {DORADO}; border-radius: 37px;
        font-family: "{titulos}"; font-size: 24px; font-weight: 800;
    }}
    """]
    for tono, (color, fondo, borde) in TONOS.items():
        reglas.append(f"""
    QLabel[rol="etiqueta-estado"][tono="{tono}"] {{
        color: {color}; background: {fondo}; border-radius: 11px;
        padding: 3px 10px; font-size: 12px; font-weight: 700;
    }}
    QFrame[rol="indicador"][tono="{tono}"] {{
        background: {fondo}; border: 1px solid {borde}; border-radius: 17px;
    }}
    QFrame[rol="indicador"][tono="{tono}"] QLabel {{
        color: {color}; background: transparent; font-size: 14px; font-weight: 700;
    }}
    QFrame[rol="camara"][tono="{tono}"] {{
        background: {PANEL}; border: 2px solid {color}; border-radius: 16px;
    }}
    QLabel[rol="chip-camara"][tono="{tono}"] {{ color: {color}; border: 1px solid {borde}; }}
    QFrame[rol="aviso"][tono="{tono}"] {{
        background: {FONDOS_AVISO[tono]}; border: 1px solid {borde}; border-radius: 14px;
    }}
    QFrame[rol="aviso"][tono="{tono}"] QLabel {{ background: transparent; border: none; }}
    QFrame[rol="aviso"][tono="{tono}"] QLabel[rol="aviso-icono"] {{ color: {color}; font-size: 22px; }}""")
    return "\n".join(reglas)


def aplicar_tema(app):
    """Carga tipografías, hoja de estilos e ícono. Se llama una vez en main."""
    cargar_tipografias()
    fuente = QFont(_familia(FAMILIA_TEXTO))
    fuente.setPixelSize(14)
    app.setFont(fuente)
    app.setStyleSheet(hoja_de_estilos())
    if LOGO.exists():
        app.setWindowIcon(QIcon(str(LOGO)))


def refrescar_estilo(widget):
    """Vuelve a aplicar la hoja de estilos después de cambiar una propiedad."""
    widget.style().unpolish(widget)
    widget.style().polish(widget)
