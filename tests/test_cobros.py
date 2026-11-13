"""Cobros y renovaciones: reglas puras, servicio contra la base y pantalla."""
import os
from datetime import date, timedelta
from decimal import Decimal

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from apoyo_db import HOY_AR, membresia, persona, requiere_base, socio, valor  # noqa: E402
from services.auth_service import ADMINISTRADOR, ENTRENADOR, AccesoDenegado, Sesion  # noqa: E402
from services.cobro_service import (  # noqa: E402
    CobroService, ReglaDeCobro, parsear_monto, validar_cobro,
)
from ui import tema  # noqa: E402

PROFE = Sesion(None, None, "profe", "Sofía Romero", frozenset({ENTRENADOR}))
DUENIA = Sesion(1, None, "admin", "Administrador", frozenset({ADMINISTRADOR}))
PLAN = (3, "Pase libre", "1 mon", None, None, None, Decimal("25000"), True)
PLAN_EN_CERO = (1, "Pase por día", "1 day", None, None, 1, Decimal("0"), True)


@pytest.fixture(scope="module")
def app():
    aplicacion = QApplication.instance() or QApplication([])
    tema.aplicar_tema(aplicacion)
    return aplicacion


# --- Reglas ---

@pytest.mark.parametrize("texto, monto", [
    ("12.500", Decimal("12500.00")), ("12500,5", Decimal("12500.50")), ("$ 3.000,00", Decimal("3000.00")),
    ("800", Decimal("800.00")), ("1.5", Decimal("1.50")), ("abc", None), ("", None),
])
def test_parsear_monto(texto, monto):
    assert parsear_monto(texto) == monto


def test_no_se_vende_un_plan_con_precio_cero():
    errores, _ = validar_cobro(PLAN_EN_CERO, "3000", "efectivo")
    assert errores == {"plan": "El plan Pase por día no tiene precio cargado ($0): la dueña lo carga "
                               "en Configuración antes de venderlo."}


def test_validacion_del_monto_y_el_medio_de_pago():
    assert validar_cobro(PLAN, "25.000", "efectivo") == ({}, Decimal("25000.00"))
    assert validar_cobro(PLAN, "10.000", "debito") == ({}, Decimal("10000.00"))     # pago parcial
    errores, _ = validar_cobro(PLAN, "30.000", None)
    assert errores == {"monto": "No puede superar $25.000,00.", "metodo": "Elegí cómo paga."}
    assert validar_cobro(PLAN, "0", "efectivo")[0] == {"monto": "El monto tiene que ser mayor a $0."}
    assert validar_cobro(None, "", "efectivo")[0].keys() == {"plan", "monto"}


# --- Servicio contra la base ---

def _precio(db, plan, precio):
    db.execute("UPDATE plan SET precio = %s WHERE nombre = %s", (precio, plan))
    return valor(db, "SELECT id FROM plan WHERE nombre = %s", (plan,))


@requiere_base
def test_venta_con_pago_parcial_y_saldo(db):
    sid = socio(db, persona(db))
    plan_id = _precio(db, "Pase libre", 25000)
    servicio = CobroService()
    venta = servicio.vender(PROFE, sid, plan_id, Decimal("10000"), "efectivo")
    hoy = valor(db, f"SELECT {HOY_AR}")
    assert venta.fecha_inicio == hoy and venta.saldo == Decimal("15000")
    assert venta.fecha_vencimiento == valor(db, "SELECT (%s::date + INTERVAL '1 month')::date", (hoy,))
    estado = servicio.buscar_socio(PROFE, "30111222")["estado"]
    assert (estado["estado_membresia"], estado["estado_contable"]) == ("vigente", "debe")

    resta = servicio.pagar_saldo(PROFE, sid, venta.membresia_id, Decimal("15000"), "transferencia")
    assert resta == 0
    assert servicio.buscar_socio(PROFE, "30111222")["estado"]["saldo"] == 0
    with pytest.raises(ReglaDeCobro):
        servicio.pagar_saldo(PROFE, sid, venta.membresia_id, Decimal("1"), "efectivo")


@requiere_base
def test_cambio_de_plan_empieza_el_dia_del_pago(db):
    sid = socio(db, persona(db))
    membresia(db, sid, desde=-5)                                  # Pase libre vigente
    plan_id = _precio(db, "3 veces por semana", 18000)
    servicio = CobroService()
    hoy = valor(db, f"SELECT {HOY_AR}")
    assert servicio.buscar_socio(PROFE, "30111222")["inicio_nueva"] == hoy
    venta = servicio.vender(PROFE, sid, plan_id, Decimal("18000"), "mercado_pago")
    assert venta.fecha_inicio == hoy and venta.plan == "3 veces por semana"
    assert venta.fecha_vencimiento == valor(db, "SELECT (%s::date + INTERVAL '1 month')::date", (hoy,))
    # El plan nuevo reemplaza al actual desde hoy.
    assert servicio.buscar_socio(PROFE, "30111222")["estado"]["plan"] == "3 veces por semana"


@requiere_base
def test_renovacion_anticipada_empieza_el_dia_del_pago(db):
    sid = socio(db, persona(db))
    membresia(db, sid, desde=-25)                                 # Pase libre que vence en pocos días
    plan_id = _precio(db, "Pase libre", 25000)
    servicio = CobroService()
    hoy = valor(db, f"SELECT {HOY_AR}")
    venta = servicio.vender(PROFE, sid, plan_id, Decimal("25000"), "efectivo")
    assert venta.fecha_inicio == hoy
    estado = servicio.buscar_socio(PROFE, "30111222")["estado"]
    assert (estado["membresia_id"], estado["fecha_inicio"]) == (venta.membresia_id, hoy)


@requiere_base
def test_el_seed_en_cero_no_se_vende(db):
    sid = socio(db, persona(db))
    plan_id = valor(db, "SELECT id FROM plan WHERE nombre = 'Pase por día'")
    db.execute("UPDATE plan SET precio = 0 WHERE id = %s", (plan_id,))
    with pytest.raises(ReglaDeCobro, match="no tiene precio cargado"):
        CobroService().vender(PROFE, sid, plan_id, Decimal("3000"), "efectivo")
    assert valor(db, "SELECT COUNT(*) FROM membresia WHERE socio_id = %s", (sid,)) == 0


@requiere_base
def test_socio_dado_de_baja_y_permisos(db):
    sid = socio(db, persona(db))
    db.execute("UPDATE socio SET activo = FALSE, fecha_baja = CURRENT_DATE WHERE id = %s", (sid,))
    plan_id = _precio(db, "Pase libre", 25000)
    with pytest.raises(ReglaDeCobro, match="dado de baja"):
        CobroService().vender(PROFE, sid, plan_id, Decimal("25000"), "efectivo")
    with pytest.raises(AccesoDenegado):
        CobroService().vender(DUENIA, sid, plan_id, Decimal("25000"), "efectivo")


# --- Pantalla ---

class ServicioFalso:
    def __init__(self, socio=None):
        self.socio = socio
        self.ventas, self.saldos = [], []

    def buscar_socio(self, sesion, dni):
        from services.persona_service import normalizar_dni
        return self.socio if normalizar_dni(dni) == "30111222" else None

    def planes(self, sesion):
        return [PLAN_EN_CERO, PLAN]

    def vencimiento(self, plan_id, inicio):
        return inicio + timedelta(days=30)

    def vender(self, sesion, socio_id, plan_id, monto, metodo):
        from services.cobro_service import Venta
        self.ventas.append((socio_id, plan_id, monto, metodo))
        return Venta(9, "Pase libre", date(2026, 11, 13), date(2026, 12, 13), Decimal("25000"), monto)

    def pagar_saldo(self, sesion, socio_id, membresia_id, monto, metodo):
        self.saldos.append((membresia_id, monto, metodo))
        return Decimal("0")


SOCIO = {"socio_id": 5, "nombre": "Juan Pérez", "activo": True, "inicio_nueva": date(2026, 11, 13),
         "estado": {"plan": "Pase libre", "fecha_vencimiento": date(2026, 11, 10),
                    "estado_membresia": "vencida", "estado_contable": "debe"},
         "membresias": [(7, "Pase libre", date(2026, 10, 10), date(2026, 11, 10), Decimal("25000"),
                         "activa", Decimal("20000"))],
         "pagos": []}


def _pagina(app, socio=SOCIO):
    from ui.cobros_page import CobrosPage
    pagina = CobrosPage(PROFE, ServicioFalso(socio))
    pagina.resize(1000, 900)
    pagina.show()
    app.processEvents()
    return pagina


def test_buscar_y_cobrar(app):
    pagina = _pagina(app)
    pagina.dni.setText("30111222")
    pagina.buscar()
    assert pagina.ficha.text() == "Juan Pérez" and pagina.venta.isVisible()
    assert pagina.plan.currentText() == "Pase libre · $25.000,00"          # el plan que tenía
    assert pagina.monto.text() == "25.000,00"
    assert pagina.periodo.text().startswith("Empieza hoy, 13/11/2026, y vence el 13/12/2026")
    pagina.cobrar()
    assert pagina.campos["metodo"].mensaje.text() == "Elegí cómo paga."      # al lado del campo
    pagina.metodo.setCurrentIndex(pagina.metodo.findData("efectivo"))
    pagina.monto.setText("10.000")
    pagina.cobrar()
    assert pagina.servicio.ventas == [(5, 3, Decimal("10000.00"), "efectivo")]
    assert "Queda debiendo $15.000,00." in pagina.resultado.text()


def test_plan_en_cero_no_se_puede_cobrar(app):
    pagina = _pagina(app)
    pagina.dni.setText("30111222")
    pagina.buscar()
    pagina.plan.setCurrentIndex(pagina.plan.findData(1))
    assert pagina.plan.currentText() == "Pase por día · sin precio"
    assert "no tiene precio cargado" in pagina.campos["plan"].mensaje.text()
    assert not pagina.cobrar_boton.isEnabled()


def test_cobrar_saldo(app):
    pagina = _pagina(app)
    pagina.dni.setText("30111222")
    pagina.buscar()
    assert pagina.saldo.isVisible() and pagina.saldo_texto.text() == "Debe $5.000,00 de Pase libre."
    pagina.saldo_metodo.setCurrentIndex(pagina.saldo_metodo.findData("debito"))
    pagina.cobrar_saldo()
    assert pagina.servicio.saldos == [(7, Decimal("5000.00"), "debito")]
    assert pagina.resultado.text() == "Pagó $5.000,00. La membresía quedó paga."


def test_dni_que_no_es_socio_o_dado_de_baja(app):
    pagina = _pagina(app)
    pagina.dni.setText("20333444")
    pagina.buscar()
    assert pagina.campo_dni.mensaje.text() == "No hay ningún socio con ese DNI. Registralo en Socios."
    assert not pagina.venta.isVisible()
    pagina = _pagina(app, dict(SOCIO, activo=False))
    pagina.dni.setText("30111222")
    pagina.buscar()
    assert "dado de baja" in pagina.campo_dni.mensaje.text() and not pagina.venta.isVisible()
    pagina.dni.setText("12")
    pagina.buscar()
    assert pagina.campo_dni.mensaje.text() == "El DNI debe tener 7 u 8 dígitos."
