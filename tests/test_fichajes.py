"""Jornadas y Fichajes: cálculo puro, servicio contra la base y pantallas."""
import os
from datetime import date, datetime, time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtCore import QDate, QTime  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from apoyo_db import HOY_AR, persona, requiere_base, usuario, valor  # noqa: E402
from services.auth_service import ADMINISTRADOR, ENTRENADOR, AccesoDenegado, Sesion  # noqa: E402
from services.fichajes_service import (  # noqa: E402
    ErroresJornada, FichajesService, calcular_fichajes, fechas_entre, validar_jornada,
)
from ui import tema  # noqa: E402

DUENIA = Sesion(1, None, "admin", "Administrador", frozenset({ADMINISTRADOR}))
JUEVES = date(2026, 11, 12)
AHORA = datetime(2026, 11, 13, 18, 0)        # viernes


def jornada(jid, fecha, entrada, salida, estado="jornada", nombre="Sofía"):
    return (jid, 7, nombre, "Romero", fecha, entrada, salida, estado)


def fichaje(fid, entrada, salida=None, jornada_id=None, turno=(None, None)):
    return (fid, 7, "Sofía", "Romero", "profe", entrada, salida, jornada_id, *turno)


@pytest.fixture(scope="module")
def app():
    aplicacion = QApplication.instance() or QApplication([])
    tema.aplicar_tema(aplicacion)
    return aplicacion


# --- Cálculo ---

def test_tarde_horas_trabajadas_y_en_horario():
    turno = (time(14, 0), time(22, 0))
    filas = calcular_fichajes(
        [jornada(1, JUEVES, *turno)],
        [fichaje(10, datetime(2026, 11, 12, 14, 12), datetime(2026, 11, 12, 22, 5), 1, turno)], AHORA)
    (fila,) = filas
    assert (fila.turno, fila.llegada, fila.salida, fila.tardanza, fila.trabajado, fila.estado) == (
        "14:00–22:00", "14:12", "22:05", "12 min", "7 h 53 min", "Tarde")
    temprano = calcular_fichajes([], [fichaje(10, datetime(2026, 11, 12, 13, 40), datetime(2026, 11, 12, 22, 0),
                                              1, turno)], AHORA)[0]
    assert (temprano.tardanza, temprano.estado) == ("—", "En horario")


def test_ausente_pendiente_y_licencia():
    filas = calcular_fichajes([jornada(1, JUEVES, time(14, 0), time(22, 0)),
                               jornada(2, date(2026, 11, 13), time(19, 0), time(23, 0)),
                               jornada(3, date(2026, 11, 13), time(8, 0), time(12, 0), "permiso", "Luis")],
                              [], AHORA)
    assert [(f.fecha.day, f.empleado, f.estado) for f in filas] == [
        (12, "Sofía Romero", "Ausente"), (13, "Luis Romero", "Permiso"), (13, "Sofía Romero", "Pendiente")]


def test_fichaje_incompleto_en_curso_y_fuera_de_turno():
    filas = calcular_fichajes([], [fichaje(10, datetime(2026, 11, 12, 14, 0)),
                                   fichaje(11, datetime(2026, 11, 13, 17, 0)),
                                   fichaje(12, datetime(2026, 11, 13, 9, 0), datetime(2026, 11, 13, 10, 30))],
                              AHORA)
    assert [(f.llegada, f.estado, f.turno) for f in filas] == [
        ("14:00", "Fichaje incompleto", "Sin turno"), ("09:00", "Fuera de turno", "Sin turno"),
        ("17:00", "En curso", "Sin turno")]
    turno = (time(8, 0), time(12, 0))
    olvidado = calcular_fichajes([], [fichaje(13, datetime(2026, 11, 13, 8, 0), None, 1, turno)], AHORA)[0]
    assert olvidado.estado == "Fichaje incompleto"              # el turno terminó hace más de 2 h


def test_validar_jornada_y_fechas():
    assert fechas_entre(date(2026, 11, 9), date(2026, 11, 15), {6}) == [date(2026, 11, 14)]
    assert len(fechas_entre(date(2026, 11, 9), date(2026, 11, 15), {1, 2, 3, 4, 5})) == 5
    existentes = [jornada(1, JUEVES, time(14, 0), time(22, 0))]
    assert validar_jornada(time(8, 0), time(13, 0), "jornada", [JUEVES], existentes) == {}
    assert validar_jornada(time(20, 0), time(23, 0), "jornada", [JUEVES], existentes) == {
        "entrada": "Se superpone con el turno del 12/11 de 14:00 a 22:00."}
    assert validar_jornada(time(20, 0), time(23, 0), "jornada", [JUEVES], existentes, jornada_id=1) == {}
    assert set(validar_jornada(time(9, 0), time(8, 0), "x", [], [])) == {"fechas", "salida", "estado"}


# --- Servicio contra la base ---

@requiere_base
def test_cargar_cambiar_y_consultar(db):
    servicio = FichajesService()
    profe = usuario(db, persona(db, "27555888", "Sofía", "Romero"), "profe")
    otro = usuario(db, persona(db, "20333444", "Luis", "Gómez"), "luis")
    hoy = valor(db, f"SELECT {HOY_AR}")
    ayer = hoy.fromordinal(hoy.toordinal() - 1)
    assert servicio.cargar_turnos(DUENIA, profe, [ayer, hoy], time(0, 0), time(0, 30)) == 2
    with pytest.raises(ErroresJornada):
        servicio.cargar_turnos(DUENIA, profe, [hoy], time(0, 15), time(1, 0))
    jornadas = servicio.jornadas(DUENIA, ayer, hoy, profe)
    servicio.cambiar_turno(DUENIA, jornadas[1][0], time(0, 0), time(0, 30), "permiso", "Trámite")
    from repositories.jornada_repository import JornadaRepository
    (cambio,) = JornadaRepository().cambios(jornadas[1][0])
    assert (cambio[4], cambio[8], cambio[9]) == ("jornada", "permiso", "Trámite")
    servicio.cargar_turnos(DUENIA, otro, [ayer], time(0, 0), time(0, 30))

    filas = servicio.fichajes(DUENIA, ayer, hoy)
    assert {(f.empleado, f.estado) for f in filas} == {
        ("Sofía Romero", "Ausente"), ("Sofía Romero", "Permiso"), ("Luis Gómez", "Ausente")}
    propia = Sesion(profe, None, "profe", "Sofía Romero", frozenset({ENTRENADOR}))
    assert {f.empleado for f in servicio.fichajes(propia, ayer, hoy, otro)} == {"Sofía Romero"}  # solo los suyos
    assert servicio.personal(propia) == [(profe, "Sofía Romero")]
    with pytest.raises(AccesoDenegado):
        servicio.cargar_turnos(propia, profe, [hoy], time(8, 0), time(9, 0))


# --- Pantallas ---

class ServicioFalso:
    def __init__(self, todos=True):
        self.todos = todos
        self.cargas, self.cambios, self.consultas = [], [], []
        self.lista = [jornada(1, JUEVES, time(14, 0), time(22, 0))]

    def ve_a_todos(self, sesion):
        return self.todos

    def personal(self, sesion):
        return [(7, "Sofía Romero"), (8, "Luis Gómez")] if self.todos else [(7, "Sofía Romero")]

    def fichajes(self, sesion, desde, hasta, usuario_id=None):
        self.consultas.append((desde, hasta, usuario_id))
        return calcular_fichajes([jornada(1, JUEVES, time(14, 0), time(22, 0))], [], AHORA)

    def jornadas(self, sesion, desde, hasta, usuario_id=None):
        return self.lista

    def cargar_turnos(self, sesion, usuario_id, fechas, entrada, salida, estado):
        self.cargas.append((usuario_id, fechas, entrada, salida, estado))
        return len(fechas)

    def cambiar_turno(self, sesion, jornada_id, entrada, salida, estado, motivo):
        self.cambios.append((jornada_id, entrada, salida, estado, motivo))


def test_pantalla_fichajes(app):
    from ui.fichajes_page import FichajesPage
    from ui.tablas import textos
    pagina = FichajesPage(DUENIA, ServicioFalso(), hoy=lambda: date(2026, 11, 13))
    pagina.resize(1200, 700)
    pagina.show()
    app.processEvents()
    assert [pagina.empleado.itemText(i) for i in range(pagina.empleado.count())] == [
        "Todo el personal", "Sofía Romero", "Luis Gómez"]
    assert pagina.servicio.consultas[-1] == (date(2026, 11, 9), date(2026, 11, 13), None)
    assert textos(pagina.tabla)[0][:7] == ["12/11/2026", "Sofía Romero", "14:00–22:00", "—", "—", "—", "—"]
    assert pagina.resumen.text() == "Ausente: 1"
    propia = FichajesPage(DUENIA, ServicioFalso(todos=False), hoy=lambda: date(2026, 11, 13))
    propia.show()
    app.processEvents()
    assert not propia.campos["empleado"].isVisible()


def test_pantalla_jornadas(app):
    from ui.jornadas_page import JornadasPage
    pagina = JornadasPage(DUENIA, ServicioFalso(), hoy=lambda: date(2026, 11, 9))
    pagina.resize(1200, 900)
    pagina.show()
    app.processEvents()
    pagina.cargar_turnos()
    assert pagina.campos["empleado"].mensaje.text() == "Elegí el empleado."
    pagina.empleado.setCurrentIndex(1)
    pagina.salida.setTime(QTime(13, 0))
    pagina.cargar_turnos()
    assert pagina.campos["salida"].mensaje.text() == "La salida tiene que ser posterior a la entrada."
    pagina.salida.setTime(QTime(22, 0))
    pagina.cargar_turnos()
    usuario_id, fechas, entrada, salida, estado = pagina.servicio.cargas[0]
    assert (usuario_id, len(fechas), entrada, salida, estado) == (7, 5, time(14, 0), time(22, 0), "jornada")
    assert pagina.mensaje.text() == "Se cargaron 5 turnos de Sofía Romero."

    pagina.cambiar_turno()
    assert pagina.mensaje.text() == "Elegí un turno de la lista."
    pagina.tabla.selectRow(0)
    pagina.cambio_estado.setCurrentIndex(pagina.cambio_estado.findData("licencia_vacaciones"))
    pagina.motivo.setText("Vacaciones")
    pagina.cambiar_turno()
    assert pagina.servicio.cambios == [(1, time(14, 0), time(22, 0), "licencia_vacaciones", "Vacaciones")]
