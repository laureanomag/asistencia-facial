"""Configuración (solo la dueña): precios y límites de los planes y el
horario de atención de la semana.

- Un plan con precio $0 se puede guardar (así viene del seed) pero no se
  vende hasta que tenga precio (ver CobroService).
- Cambiar un plan no modifica las membresías ya vendidas: copian el precio y
  los límites al venderse.
- Horario: un renglón por día (lunes a domingo) con "Abierto", apertura y
  cierre. Al guardar, un día abierto queda con una sola franja activa de
  horario_atencion (se actualiza la existente o se crea) y un día cerrado
  desactiva sus franjas. Nunca se borra nada."""
from datetime import time

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


HORARIO_POR_DEFECTO = (time(8, 0), time(20, 0))      # para un día que nunca abrió


def horario_semanal(franjas):
    """{dia: (abierto, apertura, cierre)} para los 7 días a partir de las filas de
    HorarioRepository.listar (id, dia, apertura, cierre, activo). Un día abierto
    muestra su primera franja activa; uno cerrado, la última que tuvo (o 8 a 20)."""
    semana = {}
    for dia in DIAS:
        del_dia = [f for f in franjas if f[1] == dia]
        activas = [f for f in del_dia if f[4]]
        if activas:
            semana[dia] = (True, activas[0][2], activas[0][3])
        elif del_dia:
            semana[dia] = (False, del_dia[-1][2], del_dia[-1][3])
        else:
            semana[dia] = (False, *HORARIO_POR_DEFECTO)
    return semana


def validar_horario(semana):
    """Errores por día {dia: mensaje}: el cierre tiene que ser posterior a la apertura."""
    return {dia: "El cierre tiene que ser posterior a la apertura."
            for dia, (abierto, apertura, cierre) in semana.items()
            if abierto and (apertura is None or cierre is None or cierre <= apertura)}


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

    def horario(self, sesion):
        autorizar(sesion, CONFIGURACION_GESTIONAR)
        return horario_semanal(self._horario.listar())

    def guardar_horario(self, sesion, semana):
        """semana: {dia: (abierto, apertura, cierre)}. Abierto: una sola franja
        activa con esas horas (la que ya abría a esa hora, la primera activa o una
        nueva). Cerrado: se desactivan sus franjas. No se borra nada."""
        autorizar(sesion, CONFIGURACION_GESTIONAR)
        errores = validar_horario(semana)
        if errores:
            raise ErroresConfiguracion(errores)
        with self._transaccion() as conn:
            franjas = self._horario.listar(conn=conn)
            for dia, (abierto, apertura, cierre) in semana.items():
                del_dia = [f for f in franjas if f[1] == dia]
                elegida = None
                if abierto:
                    # (dia, apertura) es único: si ya hay una fila que abre a esa hora, se reutiliza.
                    elegida = next((f for f in del_dia if f[2] == apertura), None) \
                        or next((f for f in del_dia if f[4]), None)
                for fid, _dia, f_abre, f_cierra, activa in del_dia:
                    if activa and (elegida is None or fid != elegida[0]):
                        self._horario.actualizar_franja(fid, f_abre, f_cierra, False, conn=conn)
                if not abierto:
                    continue
                if elegida is None:
                    self._horario.crear_franja(dia, apertura, cierre, conn=conn)
                elif (elegida[2], elegida[3], elegida[4]) != (apertura, cierre, True):
                    self._horario.actualizar_franja(elegida[0], apertura, cierre, True, conn=conn)
        return True
