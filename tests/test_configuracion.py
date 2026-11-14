"""Configuración: validaciones, servicio contra la base y pantalla."""
import os
from datetime import time
from decimal import Decimal

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from apoyo_db import membresia, persona, requiere_base, socio, valor  # noqa: E402
from services.auth_service import ADMINISTRADOR, ENTRENADOR, AccesoDenegado, Sesion  # noqa: E402
from services.configuracion_service import (  # noqa: E402
    ConfiguracionService, ErroresConfiguracion, aviso_cupo, horario_semanal, semanas_de_la_vigencia,
    validar_horario, validar_plan,
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


def test_horario_semanal_y_validacion():
    semana = horario_semanal(FRANJAS)
    assert semana[1] == (True, time(7, 30), time(23, 0))
    assert semana[6] == (True, time(10, 0), time(14, 0))     # la primera franja activa
    assert semana[7] == (False, time(8, 0), time(20, 0))     # nunca abrió: 8 a 20 por defecto
    assert horario_semanal([(9, 7, time(9, 0), time(12, 0), False)])[7] == (False, time(9, 0), time(12, 0))
    assert validar_horario(semana) == {}
    semana[2] = (True, time(12, 0), time(11, 0))
    semana[3] = (False, time(12, 0), time(11, 0))            # cerrado: no se valida
    assert validar_horario(semana) == {2: "El cierre tiene que ser posterior a la apertura."}


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
    servicio.guardar_plan(DUENIA, plan[0], {"precio": "25.000", "cupo": "", "dias_semana": "3",
                                            "ingresos_dia": "1", "activo": True})
    fila = next(p for p in servicio.planes(DUENIA) if p[0] == plan[0])
    assert (fila[3], fila[4], fila[5]) == (None, 3, 1)         # "Accesos en la vigencia" sin límite
    with pytest.raises(ErroresConfiguracion):
        servicio.guardar_plan(DUENIA, plan[0], {"precio": "-1"})
    with pytest.raises(AccesoDenegado):
        servicio.planes(PROFE)


def _filas(db):
    return [tuple(f) for f in db.execute(
        "SELECT id, dia_semana, hora_apertura, hora_cierre, activo FROM horario_atencion ORDER BY id")]


@requiere_base
def test_guardar_horario_sin_borrar_nada(db):
    servicio = ConfiguracionService()
    antes = _filas(db)                                        # seed: lunes a viernes y sábado
    semana = servicio.horario(DUENIA)
    assert semana[1] == (True, time(7, 30), time(23, 0)) and semana[7][0] is False
    semana[1] = (True, time(8, 0), time(22, 0))               # se actualiza la franja del lunes
    semana[6] = (False, *semana[6][1:])                       # el sábado se cierra
    semana[7] = (True, time(9, 0), time(12, 0))               # el domingo abre: franja nueva
    servicio.guardar_horario(DUENIA, semana)
    despues = _filas(db)
    assert len(despues) == len(antes) + 1                     # no se borró nada
    lunes = [f for f in despues if f[1] == 1]
    assert [(f[2], f[3], f[4]) for f in lunes] == [(time(8, 0), time(22, 0), True)]
    assert [f[4] for f in despues if f[1] == 6] == [False]
    assert [(f[2], f[3], f[4]) for f in despues if f[1] == 7] == [(time(9, 0), time(12, 0), True)]
    assert servicio.horario(DUENIA)[6] == (False, time(10, 0), time(14, 0))

    semana = servicio.horario(DUENIA)
    semana[6] = (True, time(10, 0), time(13, 0))              # reabre: reutiliza su franja
    servicio.guardar_horario(DUENIA, semana)
    assert len(_filas(db)) == len(despues)
    assert servicio.horario(DUENIA)[6] == (True, time(10, 0), time(13, 0))


@requiere_base
def test_un_dia_abierto_queda_con_una_sola_franja_activa(db):
    db.execute("INSERT INTO horario_atencion (dia_semana, hora_apertura, hora_cierre) VALUES (6, '16:00', '18:00')")
    servicio = ConfiguracionService()
    semana = servicio.horario(DUENIA)
    semana[6] = (True, time(16, 0), time(20, 0))              # coincide con la franja de las 16
    servicio.guardar_horario(DUENIA, semana)
    sabado = [f for f in _filas(db) if f[1] == 6]
    assert [(f[2], f[4]) for f in sabado] == [(time(10, 0), False), (time(16, 0), True)]
    semana[6] = (True, time(12, 0), time(11, 0))
    with pytest.raises(ErroresConfiguracion):
        servicio.guardar_horario(DUENIA, semana)
    with pytest.raises(AccesoDenegado):
        servicio.horario(PROFE)


# --- Pantalla ---

class ServicioFalso:
    def __init__(self):
        self.guardados, self.horarios = [], []

    def planes(self, sesion):
        return [(1, "Pase por día", "1 day", None, None, 1, Decimal("0"), True),
                (3, "Pase libre", "1 mon", None, None, None, Decimal("25000"), True)]

    def guardar_plan(self, sesion, plan_id, datos):
        self.guardados.append((plan_id, datos["precio"]))

    def horario(self, sesion):
        return horario_semanal(FRANJAS)

    def guardar_horario(self, sesion, semana):
        self.horarios.append(semana)


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


def test_semanas_y_aviso_de_cupo():
    assert [semanas_de_la_vigencia(v) for v in ("1 mon", "1 day", "7 days", "3 mons", "1 year")] == [5, 1, 1, 15, 60]
    assert aviso_cupo(3, 3, "1 mon") == (
        "Con 3 días por semana puede entrenar hasta 15 veces en la vigencia: con 3 accesos se queda "
        "sin cupo antes de que venza. Dejalo vacío (sin límite) o poné al menos 15.")
    assert aviso_cupo(12, 3, "1 mon") is not None             # un mes puede tocar 5 semanas
    assert aviso_cupo(15, 3, "1 mon") is None
    assert aviso_cupo(None, 3, "1 mon") is None                # sin límite
    assert aviso_cupo(8, None, "1 mon") is None                # sin límite semanal
    assert aviso_cupo(1, 1, "1 day") is None                   # pase por día


def test_aviso_de_cupo_en_pantalla_no_impide_guardar(app):
    pagina = _pagina(app)
    _pase, libre = pagina.editores
    campo = libre.campos["cupo"]
    libre.dias_semana.setText("3")
    libre.cupo.setText("3")
    assert campo.mensaje.property("rol") == "advertencia" and "al menos 15" in campo.mensaje.text()
    assert not campo.tiene_error()
    libre.guardar()
    assert pagina.servicio.guardados == [(3, "25.000,00")]     # es un aviso: guarda igual
    assert campo.mensaje.property("rol") == "advertencia"
    libre.cupo.setText("15")
    assert not campo.mensaje.isVisible()
    libre.cupo.setText("")                                     # sin límite
    assert not campo.mensaje.isVisible()


def test_horario(app):
    pagina = _pagina(app)
    lunes, sabado, domingo = pagina.dias[1], pagina.dias[6], pagina.dias[7]
    assert lunes.abierto.isChecked() and lunes.apertura.time().toString("HH:mm") == "07:30"
    assert not domingo.abierto.isChecked() and not domingo.apertura.isEnabled() and not domingo.cierre.isEnabled()
    domingo.abierto.setChecked(True)
    assert domingo.apertura.isEnabled() and domingo.cierre.isEnabled()
    domingo.cierre.setTime(domingo.apertura.time().addSecs(-3600))
    pagina.guardar_horario()
    assert domingo.campo_cierre.mensaje.text() == "El cierre tiene que ser posterior a la apertura."
    assert pagina.servicio.horarios == []
    domingo.cierre.setTime(domingo.apertura.time().addSecs(3 * 3600))
    sabado.abierto.setChecked(False)
    pagina.guardar_horario()
    (guardado,) = pagina.servicio.horarios
    assert guardado[7] == (True, time(8, 0), time(11, 0)) and guardado[6][0] is False
    assert len(guardado) == 7 and not domingo.campo_cierre.tiene_error()
    assert pagina.mensaje_horario.text() == "Se guardó el horario de atención."
