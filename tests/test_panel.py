"""Panel del administrador: servicio, pantalla y gráficos (sin base de datos)."""
import os
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from services.auth_service import ADMINISTRADOR, RECEPCIONISTA, AccesoDenegado, Sesion  # noqa: E402
from services.panel_service import Indicadores, PanelService  # noqa: E402
from ui import tema  # noqa: E402


@pytest.fixture(scope="module")
def app():
    aplicacion = QApplication.instance() or QApplication([])
    tema.aplicar_tema(aplicacion)
    return aplicacion


@contextmanager
def _sin_base():
    yield None


ADMIN = Sesion(1, None, "admin", "Administrador", frozenset({ADMINISTRADOR}))


class Repo:
    def ingresos(self, conn=None): return (4, 19)
    def socios_vigentes(self, conn=None): return 37
    def por_vencer(self, dias, conn=None): return [("Lucas", "Díaz", "3 veces por semana", date(2026, 11, 15), 2)]
    def deben(self, conn=None): return [("Eva", "Ruiz", Decimal("8000"), "vigente"), ("Ana", "Sosa", Decimal("0"), "vencida")]
    def recaudacion_mes(self, conn=None): return Decimal("1250000")
    def rechazos_hoy(self, conn=None): return [("limite_semanal", 3), ("no_reconocido", 1)]
    def ingresos_por_hora(self, dias, conn=None): return {8: 2, 18: 9, 19: 7}
    def socios_por_plan(self, conn=None): return [("Pase por día", 3), ("3 veces por semana", 20), ("Pase libre", 14)]
    def empleados_trabajando(self, conn=None): return [("Rocío", "Paz", "rocio", datetime(2026, 11, 13, 7, 25), "recepcionista")]


def test_servicio_arma_los_indicadores():
    d = PanelService(Repo(), transaccion=_sin_base).indicadores(ADMIN)
    assert (d.ingresos_hoy, d.ingresos_semana, d.socios_vigentes) == (4, 19, 37)
    assert d.total_rechazos_hoy == 4 and d.recaudacion_mes == Decimal("1250000")


def test_solo_el_administrador_ve_el_panel():
    with pytest.raises(AccesoDenegado):
        PanelService(Repo(), transaccion=_sin_base).indicadores(Sesion(2, 9, "r", "R", frozenset({RECEPCIONISTA})))


def test_pantalla_muestra_cada_indicador(app):
    from ui.panel_page import PanelPage
    pagina = PanelPage(ADMIN, PanelService(Repo(), transaccion=_sin_base))
    pagina.resize(1100, 900)
    pagina.show()
    app.processEvents()
    assert (pagina.hoy.valor.text(), pagina.hoy.detalle.text()) == ("4", "19 en la semana (desde el lunes)")
    assert pagina.vigentes.valor.text() == "37"
    assert pagina.recaudacion.valor.text() == "$1.250.000,00"
    assert pagina.trabajando.valor.text() == "1"
    assert pagina.trabajando.detalle.text() == "Rocío Paz · desde las 07:25"
    assert pagina.por_vencer.estado.text() == "1" and pagina.deben.estado.text() == "2"
    assert pagina.total_rechazos.text() == "4"
    assert pagina.rechazos._filas == [("Límite semanal", 3), ("No reconocido", 1)]
    assert pagina.por_plan._filas[1] == ("3 veces por semana", 20)
    assert not pagina.error.isVisible()


def test_sin_base_muestra_un_mensaje(app):
    from ui.panel_page import PanelPage

    class Falla:
        def indicadores(self, sesion):
            raise ConnectionError("servidor caído")
    pagina = PanelPage(ADMIN, Falla())
    pagina.show()
    app.processEvents()
    assert pagina.error.isVisible() and "servidor caído" in pagina.error.text()


def test_textos_de_las_listas():
    from ui.panel_page import filas_deben, filas_por_vencer, serie_por_hora
    assert filas_por_vencer([("Lucas", "Díaz", "Pase libre", date(2026, 11, 14), 1)]) == [
        ("Lucas Díaz", "Pase libre · vence mañana (14/11/2026)")]
    assert filas_deben([("Eva", "Ruiz", Decimal("8000"), "vencida")]) == [
        ("Eva Ruiz", "Debe $8.000,00 · Membresía vencida")]
    etiquetas, valores, tooltips = serie_por_hora({18: 9, 5: 1})
    assert etiquetas[0] == "5" and etiquetas[-1] == "23"         # se amplía si hay datos fuera de 6-23
    assert valores[etiquetas.index("18")] == 9
    assert tooltips[etiquetas.index("18")] == "18 a 19 h · 9 ingresos"


def test_graficos(app):
    from ui.graficos import BarrasHorizontales, BarrasVerticales, tope_redondo
    assert [tope_redondo(v) for v in (0, 3, 7, 12, 48, 120)] == [1, 5, 10, 20, 50, 200]
    vertical = BarrasVerticales()
    vertical.resize(400, 240)
    vertical.mostrar(["8", "9", "10"], [2, 0, 4])
    a, b = vertical.rect_barra(0), vertical.rect_barra(1)
    assert round(b.left() - a.right()) == 2                       # 2 px entre barras
    assert vertical.rect_barra(1).height() == 0
    assert vertical.indice_en(vertical.rect_barra(2).center().x()) == 2
    vertical.grab()                                               # se dibuja sin errores
    horizontal = BarrasHorizontales()
    horizontal.mostrar([("A", 1), ("B", 2)])
    assert horizontal.height() == 2 * horizontal.ALTO_FILA
    horizontal.resize(400, horizontal.height())
    horizontal.grab()
    vacio = BarrasVerticales(vacio="Sin datos")
    vacio.mostrar([], [])
    vacio.grab()


# --- Actualización del Panel ---

class Contador:
    """Servicio que cuenta las consultas; `cambiar()` simula datos nuevos."""

    def __init__(self):
        self.consultas = 0
        self.ingresos = 4
        self.servicio = PanelService(Repo(), transaccion=_sin_base)

    def indicadores(self, sesion):
        self.consultas += 1
        datos = self.servicio.indicadores(sesion)
        datos.ingresos_hoy = self.ingresos
        return datos


def _panel(app, servicio):
    from ui.panel_page import PanelPage
    horas = iter(["10:15:30", "10:15:45", "10:16:00", "10:16:15", "10:16:30"])
    pagina = PanelPage(ADMIN, servicio, reloj=lambda: datetime.strptime(next(horas), "%H:%M:%S"))
    pagina.resize(1100, 900)
    return pagina


def test_se_actualiza_cada_vez_que_se_abre(app):
    servicio = Contador()
    pagina = _panel(app, servicio)
    pagina.show()
    app.processEvents()
    assert servicio.consultas == 1 and pagina.timer.isActive()
    pagina.hide()
    assert not pagina.timer.isActive()        # oculto no consulta la base
    pagina.show()
    app.processEvents()
    assert servicio.consultas == 2


def test_refresco_cada_15_segundos_mientras_esta_abierto(app):
    from ui.panel_page import PanelPage
    assert PanelPage.INTERVALO_MS == 15_000
    pagina = _panel(app, Contador())
    pagina.show()
    app.processEvents()
    assert pagina.timer.interval() == 15_000


def test_boton_actualizar_y_hora_de_actualizacion(app):
    servicio = Contador()
    pagina = _panel(app, servicio)
    pagina.show()
    app.processEvents()
    assert pagina.actualizado.text() == "Actualizado a las 10:15:30"
    servicio.ingresos = 5
    pagina.boton_actualizar.click()
    assert servicio.consultas == 2 and pagina.hoy.valor.text() == "5"
    assert pagina.actualizado.text() == "Actualizado a las 10:15:45"
    assert pagina.timer.isActive()


def test_sin_cambios_no_se_vuelve_a_dibujar(app):
    servicio = Contador()
    pagina = _panel(app, servicio)
    pagina.show()
    app.processEvents()
    dibujos = []
    original = pagina.mostrar
    pagina.mostrar = lambda d: (dibujos.append(d), original(d))
    pagina.actualizar()                       # mismos datos: no se repinta (sin parpadeo)
    assert dibujos == [] and pagina.actualizado.text() == "Actualizado a las 10:15:45"
    servicio.ingresos = 9
    pagina.actualizar()
    assert len(dibujos) == 1 and pagina.hoy.valor.text() == "9"
    assert pagina.contenido.updatesEnabled()


def test_si_falla_conserva_los_ultimos_datos(app):
    servicio = Contador()
    pagina = _panel(app, servicio)
    pagina.show()
    app.processEvents()
    servicio.indicadores = lambda s: (_ for _ in ()).throw(ConnectionError("servidor caído"))
    pagina.actualizar()
    assert pagina.error.isVisible() and pagina.hoy.valor.text() == "4"
    assert pagina.actualizado.text() == "Actualizado a las 10:15:30"
