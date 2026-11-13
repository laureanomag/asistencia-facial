"""Informes: servicio contra la base, exportación a Excel y PDF y pantalla."""
import os
from datetime import date, timedelta
from decimal import Decimal

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from openpyxl import load_workbook  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from apoyo_db import HOY_AR, acceso_permitido, membresia, persona, requiere_base, socio, valor  # noqa: E402
from services.auth_service import ADMINISTRADOR, ENTRENADOR, AccesoDenegado, Sesion  # noqa: E402
from services.exportar import Informe, exportar_excel, exportar_pdf, nombre_archivo  # noqa: E402
from services.persona_service import DatosInvalidos  # noqa: E402
from ui import tema  # noqa: E402

DUENIA = Sesion(1, None, "admin", "Administrador", frozenset({ADMINISTRADOR}))
PROFE = Sesion(2, 2, "profe", "Sofía Romero", frozenset({ENTRENADOR}))
INFORME = Informe("Ingresos y rechazos", "Del 06/11/2026 al 13/11/2026 · todos los socios",
                  ["Fecha", "Hora", "Socio", "DNI", "Plan", "Resultado", "Motivo"],
                  [["13/11/2026", "09:00", "Juan Pérez", "30.111.222", "Pase libre", "Permitido", ""],
                   ["13/11/2026", "23:10", "Juan Pérez", "30.111.222", "Pase libre", "Rechazado",
                    "Gimnasio cerrado"]],
                  ["Permitidos: 1 · Rechazados: 1"])


@pytest.fixture(scope="module")
def app():
    aplicacion = QApplication.instance() or QApplication([])
    tema.aplicar_tema(aplicacion)
    return aplicacion


# --- Exportación ---

def test_exportar_excel_y_pdf(tmp_path):
    ruta = exportar_excel(INFORME, tmp_path / "informe.xlsx")
    hoja = load_workbook(ruta).active
    valores = [[c for c in fila if c is not None] for fila in hoja.iter_rows(values_only=True)]
    assert valores[0] == ["Ingresos y rechazos"]
    assert ["Fecha", "Hora", "Socio", "DNI", "Plan", "Resultado", "Motivo"] in valores
    assert valores[-1][-1] == "Gimnasio cerrado"
    pdf = exportar_pdf(INFORME, tmp_path / "informe.pdf")
    with open(pdf, "rb") as archivo:
        assert archivo.read(5) == b"%PDF-"
    vacio = Informe("Estado de membresías y cupos", "Al 13/11/2026", ["Socio"], [])
    exportar_pdf(vacio, tmp_path / "vacio.pdf")
    assert load_workbook(exportar_excel(vacio, tmp_path / "vacio.xlsx")).active.max_row >= 3


def test_nombre_de_archivo():
    assert nombre_archivo("Estado de membresías y cupos", "pdf") == "estado_de_membresias_y_cupos.pdf"


# --- Servicio contra la base ---

@requiere_base
def test_ingresos_y_rechazos_por_socio_y_fechas(db):
    from services.informe_service import InformeService
    from repositories.acceso_repository import AccesoRepository
    juan = socio(db, persona(db, "30111222", "Juan", "Pérez"))
    mid = membresia(db, juan)
    acceso_permitido(db, juan, mid)
    AccesoRepository().registrar_rechazo("limite_diario", juan, mid)
    luis = socio(db, persona(db, "20333444", "Luis", "Gómez"))
    AccesoRepository().registrar_rechazo("sin_membresia", luis)
    hoy = valor(db, f"SELECT {HOY_AR}")
    servicio = InformeService()

    todos = servicio.ingresos(DUENIA, hoy, hoy)
    assert [f[2] for f in todos.filas] == ["Juan Pérez", "Juan Pérez", "Luis Gómez"]
    assert todos.resumen[0] == "Permitidos: 1 · Rechazados: 2"
    del_socio = servicio.ingresos(DUENIA, hoy - timedelta(days=7), hoy, "30.111.222")
    assert [f[5:] for f in del_socio.filas] == [["Permitido", ""], ["Rechazado", "Ya ingresó hoy"]]
    assert del_socio.subtitulo.endswith("Juan Pérez")
    assert servicio.ingresos(DUENIA, hoy - timedelta(days=9), hoy - timedelta(days=8)).filas == []
    with pytest.raises(DatosInvalidos):
        servicio.ingresos(DUENIA, hoy, hoy, "99999999")
    with pytest.raises(AccesoDenegado):
        servicio.ingresos(PROFE, hoy, hoy)


@requiere_base
def test_estado_de_membresias_y_cupos(db):
    from services.informe_service import InformeService
    juan = socio(db, persona(db, "30111222", "Juan", "Pérez"))
    mid = membresia(db, juan, cupo=8, precio=Decimal("20000"))
    acceso_permitido(db, juan, mid)
    socio(db, persona(db, "20333444", "Luis", "Gómez"))
    informe = InformeService().membresias(DUENIA, date(2026, 11, 13))
    filas = {f[0]: f for f in informe.filas}
    assert filas["Juan Pérez"][4] == "1 de 8" and filas["Juan Pérez"][6] == "Vigente"
    assert filas["Juan Pérez"][8] == "$20.000,00"                    # no pagó nada
    assert filas["Luis Gómez"][6] == "Sin membresía"
    assert informe.resumen[0] == "Socios activos: 2"


# --- Pantalla ---

class ServicioFalso:
    def __init__(self):
        self.pedidos = []

    def ingresos(self, sesion, desde, hasta, dni=None):
        self.pedidos.append((desde, hasta, dni))
        if dni == "1":
            raise DatosInvalidos("El DNI debe tener 7 u 8 dígitos.")
        return INFORME

    def membresias(self, sesion, hoy):
        return Informe("Estado de membresías y cupos", "Al 13/11/2026", ["Socio", "Plan"], [], ["Socios activos: 0"])


def _pagina(app, elegir=None):
    from ui.informes_page import InformesPage
    pagina = InformesPage(DUENIA, ServicioFalso(), elegir=elegir, hoy=lambda: date(2026, 11, 13))
    pagina.resize(1200, 800)
    pagina.show()
    app.processEvents()
    return pagina


def test_ver_y_exportar(app, tmp_path):
    from ui.tablas import textos
    rutas = []

    def elegir(_parent, sugerido, _filtro):
        rutas.append(sugerido)
        return str(tmp_path / sugerido.split(".")[0])          # sin extensión: se agrega sola
    pagina = _pagina(app, elegir)
    assert not pagina.boton_excel.isEnabled()
    pagina.ver()
    assert pagina.servicio.pedidos == [(date(2026, 11, 7), date(2026, 11, 13), "")]
    assert textos(pagina.tabla)[1][6] == "Gimnasio cerrado"
    pagina.exportar("xlsx")
    pagina.exportar("pdf")
    assert rutas == ["ingresos_y_rechazos.xlsx", "ingresos_y_rechazos.pdf"]
    assert (tmp_path / "ingresos_y_rechazos.xlsx").exists() and (tmp_path / "ingresos_y_rechazos.pdf").exists()
    assert pagina.mensaje.text().startswith("Informe guardado en")


def test_filtros_con_errores_y_otro_informe(app):
    pagina = _pagina(app)
    pagina.dni.setText("1")
    pagina.ver()
    assert pagina.campos["dni"].mensaje.text() == "El DNI debe tener 7 u 8 dígitos."
    pagina.desde.setDate(pagina.hasta.date().addDays(1))
    pagina.ver()
    assert pagina.campos["hasta"].mensaje.text() == "No puede ser anterior a Desde."
    pagina.tipo.setCurrentIndex(1)
    assert not pagina.filtros.isVisible()
    pagina.ver()
    assert pagina.vacio.isVisible() and pagina.vacio.text() == "No hay datos para los filtros elegidos."
