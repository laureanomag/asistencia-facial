"""Configuración (solo la dueña): precios y límites de los planes y franjas
del horario de atención.

- Un plan con precio $0 se puede guardar (así viene del seed) pero no se
  vende hasta que tenga precio (ver CobroService).
- Cambiar un plan no modifica las membresías ya vendidas: copian el precio y
  los límites al venderse.
- Las franjas no se borran: se desactivan. No pueden superponerse con otra
  franja activa del mismo día."""
from config.database import usar_conexion
from services.auth_service import CONFIGURACION_GESTIONAR, autorizar
from services.cobro_service import parsear_monto
from services.horario_service import DIAS


class ErroresConfiguracion(Exception):
    def __init__(self, errores):
        super().__init__("; ".join(errores.values()))
        self.errores = errores


def _entero(texto, minimo, maximo=None):
    """(valor o None si está vacío, error o None)."""
    texto = (texto or "").strip()
    if not texto:
        return None, None
    if not texto.isdigit():
        return None, "Escribí un número entero o dejalo vacío (sin límite)."
    valor = int(texto)
    if valor < minimo or (maximo is not None and valor > maximo):
        rango = f"entre {minimo} y {maximo}" if maximo is not None else f"desde {minimo}"
        return None, f"Tiene que ser {rango}, o vacío (sin límite)."
    return valor, None


def validar_plan(datos):
    """datos: textos del formulario (precio, cupo, dias_semana, ingresos_dia) y activo.
    Devuelve (errores por campo, valores listos para guardar)."""
    errores, valores = {}, {"activo": bool(datos.get("activo", True))}
    precio = parsear_monto(datos.get("precio"))
    if precio is None:
        errores["precio"] = "Escribí el precio (por ejemplo, 25.000)."
    elif precio < 0:
        errores["precio"] = "El precio no puede ser negativo."
    valores["precio"] = precio
    for campo, minimo, maximo in (("cupo", 1, None), ("dias_semana", 1, 7), ("ingresos_dia", 1, None)):
        valor, error = _entero(datos.get(campo), minimo, maximo)
        if error:
            errores[campo] = error
        valores[campo] = valor
    return errores, valores


def validar_franja(dia, apertura, cierre, franjas, franja_id=None):
    """franjas: filas de HorarioRepository.listar (id, dia, apertura, cierre, activo)."""
    errores = {}
    if dia not in DIAS:
        errores["dia"] = "Elegí el día."
    if apertura is None or cierre is None or cierre <= apertura:
        errores["cierre"] = "La hora de cierre tiene que ser posterior a la de apertura."
        return errores
    for fid, fdia, fabre, fcierra, factiva in franjas:
        if fid == franja_id or fdia != dia:
            continue
        if fabre == apertura and franja_id is None:
            errores["apertura"] = ("Ya hay una franja que abre a esa hora ese día"
                                   + (": activala en la lista." if not factiva else "."))
        elif factiva and apertura < fcierra and fabre < cierre:
            errores["apertura"] = (f"Se superpone con la franja de {fabre.strftime('%H:%M')} a "
                                   f"{fcierra.strftime('%H:%M')}.")
    return errores


class ConfiguracionService:
    def __init__(self, membresias=None, horario=None, transaccion=usar_conexion):
        if membresias is None:
            from repositories.membresia_repository import MembresiaRepository
            membresias = MembresiaRepository()
        if horario is None:
            from repositories.horario_repository import HorarioRepository
            horario = HorarioRepository()
        self._membresias, self._horario = membresias, horario
        self._transaccion = transaccion

    # --- Planes ---

    def planes(self, sesion):
        autorizar(sesion, CONFIGURACION_GESTIONAR)
        return self._membresias.listar_planes(solo_activos=False)

    def guardar_plan(self, sesion, plan_id, datos):
        autorizar(sesion, CONFIGURACION_GESTIONAR)
        errores, v = validar_plan(datos)
        if errores:
            raise ErroresConfiguracion(errores)
        return self._membresias.actualizar_plan(plan_id, v["precio"], v["cupo"], v["dias_semana"],
                                                v["ingresos_dia"], v["activo"])

    # --- Horario de atención ---

    def franjas(self, sesion):
        autorizar(sesion, CONFIGURACION_GESTIONAR)
        return self._horario.listar()

    def agregar_franja(self, sesion, dia, apertura, cierre):
        autorizar(sesion, CONFIGURACION_GESTIONAR)
        with self._transaccion() as conn:
            errores = validar_franja(dia, apertura, cierre, self._horario.listar(conn=conn))
            if errores:
                raise ErroresConfiguracion(errores)
            return self._horario.crear_franja(dia, apertura, cierre, conn=conn)

    def cambiar_activa(self, sesion, franja_id, activa):
        autorizar(sesion, CONFIGURACION_GESTIONAR)
        with self._transaccion() as conn:
            franjas = self._horario.listar(conn=conn)
            franja = next((f for f in franjas if f[0] == franja_id), None)
            if franja is None:
                raise ErroresConfiguracion({"franja": "La franja ya no existe."})
            if activa:
                errores = validar_franja(franja[1], franja[2], franja[3], franjas, franja_id)
                if errores:
                    raise ErroresConfiguracion(errores)
            return self._horario.actualizar_franja(franja_id, franja[2], franja[3], activa, conn=conn)
