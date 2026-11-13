"""Estado del socio: servicio contra la base y pantalla con servicio falso."""
import os
from datetime import date, datetime
from decimal import Decimal

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel  # noqa: E402

from apoyo_db import acceso_permitido, membresia, persona, requiere_base, socio  # noqa: E402
from services.auth_service import ADMINISTRADOR, ENTRENADOR, AccesoDenegado, Sesion  # noqa: E402
from ui import tema  # noqa: E402

PROFE = Sesion(2, 2, "profe", "Sofía Romero", frozenset({ENTRENADOR}))
DUENIA = Sesion(1, None, "admin", "Administrador", frozenset({ADMINISTRADOR}))


@pytest.fixture(scope="module")
def app():
    aplicacion = QApplication.instance() or QApplication([])
    tema.aplicar_tema(aplicacion)
    return aplicacion


# --- Servicio contra la base ---

@requiere_base
def test_ficha_completa_y_baja_de_la_duenia(db):
    from services.estado_socio_service import EstadoSocioService
    sid = socio(db, persona(db))
    mid = membresia(db, sid, plan="3 veces por semana", precio=Decimal("18000"))
    acceso_permitido(db, sid, mid)
    servicio = EstadoSocioService()
    ficha = servicio.ficha(PROFE, sid)
    assert (ficha["nombre"], ficha["activo"]) == ("Ana Pérez", True)
    assert ficha["estado"]["plan"] == "3 veces por semana" and ficha["estado"]["dias_entrenados_semana"] == 1
    assert len(ficha["membresias"]) == 1 and ficha["accesos"][0][1] == "permitido"
    assert [f[3] for f in servicio.buscar(PROFE, "pérez")] == ["Ana"]

    with pytest.raises(AccesoDenegado):                    # el entrenador no da de baja
        servicio.dar_baja(PROFE, sid)
    assert servicio.dar_baja(DUENIA, sid)
    ficha = servicio.ficha(DUENIA, sid)
    assert ficha["activo"] is False and ficha["estado"] is None and ficha["fecha_baja"] is not None
    assert servicio.reactivar(DUENIA, sid)
    assert servicio.ficha(DUENIA, sid)["estado"]["plan"] == "3 veces por semana"


# --- Pantalla ---

ESTADO = {"membresia_id": 7, "plan": "3 veces por semana", "fecha_inicio": date(2026, 11, 5),
          "fecha_vencimiento": date(2026, 12, 5), "dias_para_vencer": 22, "accesos_incluidos": None,
          "accesos_usados": 4, "accesos_restantes": None, "accesos_hoy": 1, "max_ingresos_diarios": None,
          "dias_entrenados_semana": 2, "max_dias_semanales": 3, "ultimo_pago": datetime(2026, 11, 5, 10),
          "precio": Decimal("18000"), "pagado": Decimal("10000"), "saldo": Decimal("8000"),
          "estado_membresia": "vigente", "estado_contable": "debe"}
FICHA = {"socio_id": 5, "dni": "30111222", "nombre": "Juan Pérez", "celular": "3884111111",
         "contacto_nombre": "María", "contacto_telefono": "3884222222", "fecha_alta": date(2026, 11, 1),
         "activo": True, "fecha_baja": None, "estado": ESTADO,
         "membresias": [(7, "3 veces por semana", date(2026, 11, 5), date(2026, 12, 5), Decimal("18000"),
                         "activa", Decimal("10000"))],
         "pagos": [(datetime(2026, 11, 5, 10, 0), Decimal("10000"), "efectivo", "3 veces por semana", 7)],
         "accesos": [(datetime(2026, 11, 13, 9, 0), "permitido", None),
                     (datetime(2026, 11, 12, 9, 0), "rechazado", "gimnasio_cerrado")]}


class ServicioFalso:
    def __init__(self, duenia=False):
        self.duenia = duenia
        self.ficha_actual = dict(FICHA)
        self.bajas = []

    def buscar(self, sesion, texto):
        return [(5, 1, "30111222", "Juan", "Pérez", None, True, None, None, None, None, None)]

    def ficha(self, sesion, socio_id):
        return dict(self.ficha_actual)

    def puede_dar_de_baja(self, sesion):
        return self.duenia

    def dar_baja(self, sesion, socio_id):
        self.bajas.append(socio_id)
        self.ficha_actual.update(activo=False, estado=None, fecha_baja=date(2026, 11, 13))


def _pagina(app, servicio, confirma=True):
    from ui.estado_socio_page import EstadoSocioPage
    pagina = EstadoSocioPage(PROFE, servicio, confirmar_accion=lambda *_: confirma)
    pagina.resize(1300, 900)
    pagina.show()
    app.processEvents()
    return pagina


def _textos(widget):
    return " ".join(l.text() for l in widget.findChildren(QLabel))


def test_buscar_y_ver_el_estado(app):
    from ui.tablas import textos
    pagina = _pagina(app, ServicioFalso())
    pagina.busqueda.setText("Juan")
    pagina.buscar()                                       # un solo resultado: se abre directo
    assert pagina.ficha.isVisible() and pagina.nombre.text() == "Juan Pérez"
    texto = _textos(pagina.ficha)
    for esperado in ("2 de 3 días", "$8.000,00", "05/12/2026 · en 22 días", "Vigente", "Debe"):
        assert esperado in texto
    assert not pagina.boton_estado.isVisible()            # el entrenador no da de baja
    assert textos(pagina.accesos) == [["13/11/2026 09:00", "Permitido"], ["12/11/2026 09:00", "Gimnasio cerrado"]]


def test_la_duenia_da_de_baja_con_confirmacion(app):
    servicio = ServicioFalso(duenia=True)
    pagina = _pagina(app, servicio, confirma=False)
    pagina.mostrar(5)
    assert pagina.boton_estado.text() == "Dar de baja"
    pagina.cambiar_estado()
    assert servicio.bajas == []                            # canceló la confirmación
    pagina._confirmar = lambda *_: True
    pagina.cambiar_estado()
    assert servicio.bajas == [5] and pagina.boton_estado.text() == "Reactivar"
    assert pagina.sin_membresia.text() == "Dado de baja: no puede entrar."
    assert "Dado de baja" in _textos(pagina.ficha)


def test_socio_sin_plan(app):
    servicio = ServicioFalso()
    servicio.ficha_actual.update(estado={"membresia_id": None, "estado_membresia": "sin_membresia",
                                         "estado_contable": "sin_pase"}, membresias=[], pagos=[], accesos=[])
    pagina = _pagina(app, servicio)
    pagina.mostrar(5)
    assert pagina.sin_membresia.text().startswith("Todavía no tiene ningún plan.")
