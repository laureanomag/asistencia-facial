"""Lógica de reconocimiento + asistencia, sin dependencias de interfaz.
La ejecuta el proceso de reconocimiento (face_worker.py)."""
import os
import time
from datetime import datetime, timedelta

from services import attendance_service as att

MENSAJES = {
    att.ENTRADA_REGISTRADA: "Entrada registrada",
    att.ENTRADA_CON_TARDANZA: "Entrada registrada con tardanza",
    att.SALIDA_REGISTRADA: "Salida registrada",
    att.ASISTENCIA_COMPLETA: "Entrada y salida ya registradas para esta Jornada",
}

# Cuántos intentos seguidos deben coincidir con el MISMO alumno antes de
# registrar la asistencia (reduce falsas coincidencias aisladas). Se puede
# cambiar con CONFIRMACIONES_RECONOCIMIENTO en el .env (1 = sin confirmación).
CONFIRMACIONES_REQUERIDAS = 2
VENTANA_CONFIRMACION_S = 8.0


def _confirmaciones_requeridas():
    try:
        return max(1, int(os.getenv("CONFIRMACIONES_RECONOCIMIENTO", CONFIRMACIONES_REQUERIDAS)))
    except ValueError:
        return CONFIRMACIONES_REQUERIDAS


class Confirmador:
    """Cuenta coincidencias del mismo alumno dentro de la ventana de tiempo.
    El conteo vuelve a empezar sólo si se reconoce a otro alumno o si pasó la
    ventana desde la última coincidencia; un intento fallido o ambiguo no lo
    modifica (no se llama a registrar)."""

    def __init__(self):
        self._alumno_id = None
        self._cantidad = 0
        self._ultimo = 0.0

    def reiniciar(self):
        self._alumno_id, self._cantidad = None, 0

    def registrar(self, alumno_id, ahora=None):
        ahora = time.monotonic() if ahora is None else ahora
        if alumno_id == self._alumno_id and ahora - self._ultimo <= VENTANA_CONFIRMACION_S:
            self._cantidad += 1
        else:
            self._alumno_id, self._cantidad = alumno_id, 1
        self._ultimo = ahora
        return self._cantidad


def _hora_redondeada_arriba(momento):
    """HH:MM sin anunciar un minuto en el que todavía no se habilita
    (08:50:25 + 10 min = 09:00:25 se muestra como 09:01)."""
    if momento.second or momento.microsecond:
        momento = momento.replace(second=0, microsecond=0) + timedelta(minutes=1)
    return momento.strftime("%H:%M")


def mensaje_salida_aun_no(disponible, horario_salida):
    texto = (f"Entrada ya registrada. A partir de las {_hora_redondeada_arriba(disponible)} "
             "se habilita el horario de salida")
    # Si manda la espera desde la entrada (y no el horario de salida de la
    # Jornada), se aclara para que no parezca que el horario no se actualizó.
    limite_horario = datetime.combine(disponible.date(), horario_salida) - att.TOLERANCIA_SALIDA
    if disponible > limite_horario:
        minutos = int(att.ESPERA_ENTRADA_SALIDA.total_seconds() // 60)
        entrada = disponible - att.ESPERA_ENTRADA_SALIDA
        texto += f" ({minutos} minutos después de su entrada a las {entrada.strftime('%H:%M')})"
    return texto


def mensaje_ambiguo(ambiguo):
    (nombre1, d1), (nombre2, d2) = ambiguo
    return (f"Coincidencia ambigua entre {nombre1} ({d1:.3f}) y {nombre2} ({d2:.3f}); "
            "no se registra. Mire de frente, con buena luz")


def procesar(face_service, attendance_service, rostro, jornada_id,
             horario_entrada, horario_salida, confirmador):
    resultado = face_service.reconocer(rostro)
    alumno_id, nombre, distancia = resultado.alumno_id, resultado.nombre, resultado.distancia

    # Los intentos sin reconocimiento no tocan el confirmador.
    if resultado.ambiguo is not None:
        return {"estado": "AMBIGUO", "mensaje": mensaje_ambiguo(resultado.ambiguo)}
    if alumno_id is None:
        if distancia is None:
            return {"estado": "SIN_REFERENCIAS",
                    "mensaje": "No hay fotografías de referencia utilizables"}
        return {"estado": "NO_RECONOCIDO",
                "mensaje": f"Rostro no reconocido (distancia mínima {distancia:.2f})"}

    requeridas = _confirmaciones_requeridas()
    cantidad = confirmador.registrar(alumno_id)
    if cantidad < requeridas:
        return {"estado": "CONFIRMANDO",
                "mensaje": (f"Verificando identidad: {nombre} (distancia {distancia:.2f}), "
                            f"confirmación {cantidad}/{requeridas}. Mantenga el rostro frente a la cámara")}

    estado, disponible = attendance_service.procesar(
        jornada_id, alumno_id, horario_entrada, horario_salida)
    if estado == att.SALIDA_AUN_NO:
        texto = mensaje_salida_aun_no(disponible, horario_salida)
    else:
        texto = MENSAJES[estado]
    return {"estado": estado,
            "mensaje": f"Alumno reconocido: {nombre} (distancia {distancia:.2f}). {texto}"}
