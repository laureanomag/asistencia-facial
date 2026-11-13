"""Cobros y renovaciones: venta de un plan (alta o renovación de la
membresía) con su pago, y pago del saldo de una membresía.

Reglas:
- No se vende un plan con precio $0 (los planes del seed vienen en 0 hasta
  que la dueña carga los precios en Configuración).
- El pago puede ser parcial: el saldo queda como deuda en Estado del socio.
- La membresía comienza el día en que se registra el pago (trabajo final,
  punto 6.3), también en la renovación anticipada y en el cambio de plan: el
  plan nuevo reemplaza al actual desde ese día.
- El vencimiento lo calcula PostgreSQL (fecha_inicio + vigencia del plan):
  20/10 -> 20/11 y 31/01 -> 28/02 (29/02 en año bisiesto).
- La membresía y su pago se guardan en una sola transacción."""
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from config.database import usar_conexion
from services.auth_service import MEMBRESIA_RENOVAR, PAGO_REGISTRAR, autorizar
from services.persona_service import normalizar_dni
from services.reglas_ingreso import pesos

METODOS = {"efectivo": "Efectivo", "debito": "Débito", "credito": "Crédito",
           "transferencia": "Transferencia", "mercado_pago": "Mercado Pago"}


class ReglaDeCobro(Exception):
    """No se puede cobrar (socio dado de baja, plan sin precio, monto mayor al saldo...)."""


@dataclass(frozen=True)
class Venta:
    membresia_id: int
    plan: str
    fecha_inicio: object
    fecha_vencimiento: object
    precio: Decimal
    pagado: Decimal

    @property
    def saldo(self):
        return self.precio - self.pagado


def parsear_monto(texto):
    """'12.500' -> 12500, '12500,50' -> 12500.50, '$ 3.000,5' -> 3000.50.
    Devuelve None si no es un número."""
    limpio = re.sub(r"[\s$]", "", texto or "")
    if not limpio:
        return None
    if "," in limpio:
        limpio = limpio.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", limpio):
        limpio = limpio.replace(".", "")
    try:
        monto = Decimal(limpio)
    except InvalidOperation:
        return None
    return monto.quantize(Decimal("0.01")) if monto.is_finite() else None


def validar_cobro(plan, monto_texto, metodo, maximo=None):
    """(errores por campo, monto). plan: fila de listar_planes o None.
    maximo: tope del monto (el precio del plan o el saldo)."""
    errores = {}
    if plan is None:
        errores["plan"] = "Elegí un plan."
    elif Decimal(plan[6]) <= 0:
        errores["plan"] = (f"El plan {plan[1]} no tiene precio cargado ($0): la dueña lo carga "
                           "en Configuración antes de venderlo.")
    monto = parsear_monto(monto_texto)
    tope = maximo if maximo is not None else (Decimal(plan[6]) if plan is not None else None)
    if monto is None:
        errores["monto"] = "Escribí el monto que paga (por ejemplo, 12.500)."
    elif monto <= 0:
        errores["monto"] = "El monto tiene que ser mayor a $0."
    elif tope is not None and tope > 0 and monto > tope:
        errores["monto"] = f"No puede superar {pesos(tope)}."
    if metodo not in METODOS:
        errores["metodo"] = "Elegí cómo paga."
    return errores, monto


class CobroService:
    def __init__(self, personas=None, socios=None, membresias=None, horario=None,
                 transaccion=usar_conexion):
        if personas is None:
            from repositories.person_repository import PersonRepository
            personas = PersonRepository()
        if socios is None:
            from repositories.socio_repository import SocioRepository
            socios = SocioRepository()
        if membresias is None:
            from repositories.membresia_repository import MembresiaRepository
            membresias = MembresiaRepository()
        if horario is None:
            from repositories.horario_repository import HorarioRepository
            horario = HorarioRepository()
        self._personas, self._socios, self._membresias, self._horario = personas, socios, membresias, horario
        self._transaccion = transaccion

    def planes(self, sesion):
        autorizar(sesion, MEMBRESIA_RENOVAR)
        return self._membresias.listar_planes(solo_activos=True)

    def buscar_socio(self, sesion, dni):
        """dict con el socio del DNI, su estado y la fecha en que empezaría un
        plan nuevo (hoy, el día del pago), o None si no es socio. Lanza DatosInvalidos si el DNI es inválido."""
        autorizar(sesion, PAGO_REGISTRAR)
        dni = normalizar_dni(dni)
        with self._transaccion() as conn:
            persona = self._personas.obtener_por_dni(dni, conn=conn)
            socio = self._socios.obtener_por_persona(persona[0], conn=conn) if persona else None
            if socio is None:
                return None
            hoy = self._horario.ahora(conn=conn).date()
            membresias = self._membresias.listar_por_socio(socio[0], conn=conn)
            return {"socio_id": socio[0], "nombre": f"{persona[2]} {persona[3]}", "activo": socio[5],
                    "estado": self._socios.obtener_estado(socio[0], conn=conn),
                    "membresias": membresias, "inicio_nueva": hoy,
                    "pagos": self._membresias.listar_pagos_por_socio(socio[0], 5, conn=conn)}

    def vencimiento(self, plan_id, fecha_inicio):
        return self._membresias.calcular_vencimiento(plan_id, fecha_inicio)

    def vender(self, sesion, socio_id, plan_id, monto, metodo):
        """Alta o renovación: crea la membresía y registra el pago (puede ser parcial)."""
        autorizar(sesion, MEMBRESIA_RENOVAR)
        autorizar(sesion, PAGO_REGISTRAR)
        with self._transaccion() as conn:
            socio = self._socios.obtener_por_id(socio_id, bloquear=True, conn=conn)
            if socio is None or not socio[5]:
                raise ReglaDeCobro("El socio está dado de baja: la dueña puede reactivarlo en Estado del socio.")
            plan = self._membresias.obtener_plan(plan_id, conn=conn)
            errores, monto = validar_cobro(plan, str(monto).replace(".", ","), metodo)
            if errores:
                raise ReglaDeCobro(" ".join(errores.values()))
            if not plan[7]:
                raise ReglaDeCobro(f"El plan {plan[1]} no está a la venta.")
            inicio = self._horario.ahora(conn=conn).date()     # el día del pago
            membresia_id, vence, precio = self._membresias.crear(socio_id, plan_id, inicio,
                                                                 sesion.usuario_id, conn=conn)
            self._membresias.registrar_pago(membresia_id, monto, metodo, sesion.usuario_id, conn=conn)
        return Venta(membresia_id, plan[1], inicio, vence, Decimal(precio), monto)

    def pagar_saldo(self, sesion, socio_id, membresia_id, monto, metodo):
        """Pago de lo que falta de una membresía (pago parcial anterior)."""
        autorizar(sesion, PAGO_REGISTRAR)
        with self._transaccion() as conn:
            fila = next((m for m in self._membresias.listar_por_socio(socio_id, conn=conn)
                         if m[0] == membresia_id), None)
            if fila is None:
                raise ReglaDeCobro("La membresía no es de este socio.")
            saldo = Decimal(fila[4]) - Decimal(fila[6])
            if saldo <= 0:
                raise ReglaDeCobro("Esa membresía ya está paga.")
            errores, monto = validar_cobro((None, fila[1], None, None, None, None, fila[4], True),
                                           str(monto).replace(".", ","), metodo, maximo=saldo)
            if errores:
                raise ReglaDeCobro(" ".join(errores.values()))
            self._membresias.registrar_pago(membresia_id, monto, metodo, sesion.usuario_id, conn=conn)
        return saldo - monto
