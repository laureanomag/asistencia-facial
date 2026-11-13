"""Configuración: validaciones, servicio contra la base y pantalla."""
import os
from datetime import time
from decimal import Decimal

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtCore import QTime  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from apoyo_db import membresia, persona, requiere_base, socio, valor  # noqa: E402
from services.auth_service import ADMINISTRADOR, ENTRENADOR, AccesoDenegado, Sesion  # noqa: E402
from services.configuracion_service import (  # noqa: E402
    ConfiguracionService, ErroresConfiguracion, validar_franja, validar_plan,
)
from ui import tema  # noqa: E402

DUENIA = Sesion(1, None, "admin", "Administrador", frozenset({ADMINISTRADOR}))
PROFE = Sesion(2, 2, "profe", "Sofía Romero", frozenset({ENTRENADOR}))
FRANJAS = [(1, 1, time(7, 30), time(23, 0), True), (2, 6, time(10, 0), time(14, 0), True),
           (3, 6, time(16, 0), time(18, 0), False)]


@pytest.fixture(scope="module")
def app():
    aplicacion = QApplication.instance() or QApplication([])
    tema.aplicar_tema(aplicacion)
    return aplicacion


# --- Validaciones ---

def test_validar_plan():
    errores, valores = validar_plan({"precio": "25.000", "cupo": "", "dias_semana": "3", "ingresos_dia": "1"})
    assert errores == {} and valores == {"activo": True, "precio": Decimal("25000.00"), "cupo": None,
                                         "dias_semana": 3, "ingresos_dia": 1}
    errores, _ = validar_plan({"precio": "", "cupo": "0", "dias_semana": "8", "ingresos_dia": "uno"})
    assert errores == {"precio": "Escribí el precio (por ejemplo, 25.000).",
                       "cupo": "Tiene que ser desde 1, o vacío (sin límite).",
                       "dias_semana": "Tiene que ser entre 1 y 7, o vacío (sin límite).",
                       "ingresos_dia": "Escribí un número entero o dejalo vacío (sin límite)."}
    assert validar_plan({"precio": "0"})[0] == {}           # se guarda en 0, pero no se vende


def test_validar_franja():
    assert validar_franja(6, time(14, 0), time(16, 0), FRANJAS) == {}
    assert validar_franja(6, time(16, 0), time(18, 0), FRANJAS) == {
        "apertura": "Ya hay una franja que abre a esa hora ese día: activala en la lista."}
    assert validar_franja(6, time(13, 0), time(15, 0), FRANJAS) == {
        "apertura": "Se superpone con la franja de 10:00 a 14:00."}
    assert validar_franja(7, time(12, 0), time(11, 0), FRANJAS) == {
        "cierre": "La hora de cierre tiene que ser posterior a la de apertura."}
    assert validar_franja(6, time(16, 30), time(17, 0), FRANJAS) == {}   # la desactivada no se superpone


# --- Servicio contra la base ---

@requiere_base
def test_precio_nuevo_no_cambia_lo_ya_vendido(db):
    servicio = ConfiguracionService()
    plan = next(p for p in servicio.planes(DUENIA) if p[1] == "Pase libre")
    sid = socio(db, persona(db))
    mid = membresia(db, sid, precio=Decimal("20000"))
    servicio.guardar_plan(DUENIA, plan[0], {"precio": "25.000", "cupo": "12", "dias_semana": "",
                                            "ingresos_dia": "1", "activo": True})
    fila = next(p for p in servicio.planes(DUENIA) if p[0] == plan[0])
    assert (fila[3], fila[4], fila[5], fila[6]) == (12, None, 1, Decimal("25000.00"))
    assert valor(db, "SELECT precio FROM membresia WHERE id = %s", (mid,)) == Decimal("20000")
    with pytest.raises(ErroresConfiguracion):
        servicio.guardar_plan(DUENIA, plan[0], {"precio": "-1"})
    with pytest.raises(AccesoDenegado):
        servicio.planes(PROFE)


@requiere_base
def test_franjas_se_agregan_y_se_desactivan(db):
    servicio = ConfiguracionService()
    franja = servicio.agregar_franja(DUENIA, 7, time(9, 0), time(12, 0))
    assert (7, time(9, 0), time(12, 0), True) in [f[1:] for f in servicio.franjas(DUENIA)]
    with pytest.raises(ErroresConfiguracion):
        servicio.agregar_franja(DUENIA, 7, time(11, 0), time(13, 0))
    servicio.cambiar_activa(DUENIA, franja, False)
    assert valor(db, "SELECT activo FROM horario_atencion WHERE id = %s", (franja,)) is False
    assert valor(db, "SELECT COUNT(*) FROM horario_atencion WHERE id = %s", (franja,)) == 1   # no se borra
    servicio.cambiar_activa(DUENIA, franja, True)
    assert valor(db, "SELECT activo FROM horario_atencion WHERE id = %s", (franja,)) is True


# --- Pantalla ---

class ServicioFalso:
    def __init__(self):
        self.guardados, self.agregadas, self.cambios = [], [], []

    def planes(self, sesion):
        return [(1, "Pase por día", "1 day", None, None, 1, Decimal("0"), True),
                (3, "Pase libre", "1 mon", None, None, None, Decimal("25000"), True)]

    def guardar_plan(self, sesion, plan_id, datos):
        self.guardados.append((plan_id, datos["precio"]))

    def franjas(self, sesion):
        return FRANJAS

    def agregar_franja(self, sesion, dia, apertura, cierre):
        self.agregadas.append((dia, apertura, cierre))

    def cambiar_activa(self, sesion, franja_id, activa):
        self.cambios.append((franja_id, activa))


def _pagina(app):
    from ui.configuracion_page import ConfiguracionPage
    pagina = ConfiguracionPage(DUENIA, ServicioFalso())
    pagina.resize(1200, 900)
    pagina.show()
    app.processEvents()
    return pagina


def test_editar_plan(app):
    pagina = _pagina(app)
    pase_dia, libre = pagina.editores
    assert pase_dia.precio.text() == "0,00" and libre.precio.text() == "25.000,00"
    pase_dia.dias_semana.setText("9")
    pase_dia.guardar()
    assert pase_dia.campos["dias_semana"].tiene_error() and pagina.servicio.guardados == []
    pase_dia.dias_semana.setText("")
    pase_dia.precio.setText("3.000")
    pase_dia.guardar()
    assert pagina.servicio.guardados == [(1, "3.000")]
    assert pase_dia.mensaje.text() == "Se guardó Pase por día."


def test_horario(app):
    from ui.tablas import textos
    pagina = _pagina(app)
    assert [f[:3] for f in textos(pagina.tabla_franjas)] == [
        ["Lunes", "07:30", "23:00"], ["Sábado", "10:00", "14:00"], ["Sábado", "16:00", "18:00"]]
    pagina.dia.setCurrentIndex(pagina.dia.findData(6))
    pagina.apertura.setTime(QTime(13, 0))
    pagina.cierre.setTime(QTime(15, 0))
    pagina.agregar_franja()
    assert pagina.campos_franja["apertura"].mensaje.text() == "Se superpone con la franja de 10:00 a 14:00."
    pagina.apertura.setTime(QTime(14, 0))
    pagina.agregar_franja()
    assert pagina.servicio.agregadas == [(6, time(14, 0), time(15, 0))]
    pagina.cambiar_activa(1, False)
    assert pagina.servicio.cambios == [(1, False)]
    assert pagina.mensaje_horario.text() == "Franja desactivada: ese horario queda cerrado."
