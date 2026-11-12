"""Lógica de reconocimiento y evaluación de reglas de negocio para Zebra Gym.
La ejecuta el proceso de reconocimiento (face_worker.py)."""
import os
import time

CONFIRMACIONES_REQUERIDAS = 2
VENTANA_CONFIRMACION_S = 8.0


def _confirmaciones_requeridas():
    try:
        return max(1, int(os.getenv("CONFIRMACIONES_RECONOCIMIENTO", CONFIRMACIONES_REQUERIDAS)))
    except ValueError:
        return CONFIRMACIONES_REQUERIDAS


class Confirmador:
    """Cuenta coincidencias de la MISMA persona dentro de la ventana de tiempo
    para evitar falsos positivos esporádicos."""

    def __init__(self):
        self._persona_id = None
        self._cantidad = 0
        self._ultimo = 0.0

    def reiniciar(self):
        self._persona_id, self._cantidad = None, 0

    def registrar(self, persona_id, ahora=None):
        ahora = time.monotonic() if ahora is None else ahora
        if persona_id == self._persona_id and ahora - self._ultimo <= VENTANA_CONFIRMACION_S:
            self._cantidad += 1
        else:
            self._persona_id, self._cantidad = persona_id, 1
        self._ultimo = ahora
        return self._cantidad


def mensaje_ambiguo(ambiguo):
    (nombre1, d1), (nombre2, d2) = ambiguo
    return (f"Coincidencia ambigua entre {nombre1} ({d1:.3f}) y {nombre2} ({d2:.3f}); "
            "no se registra. Mire de frente, con buena luz")


def procesar(face_service, gym_service, rostro, confirmador):
    """Ejecuta el reconocimiento facial y, si identifica a una persona,
    evalúa las reglas de negocio de Zebra Gym. El rostro identifica a la
    persona; si actúa como socio o como entrenador lo decide gym_service."""
    resultado_recon = face_service.reconocer(rostro)
    persona_id = resultado_recon.persona_id
    nombre = resultado_recon.nombre
    distancia = resultado_recon.distancia

    # Los intentos sin reconocimiento no tocan el confirmador.
    if resultado_recon.ambiguo is not None:
        return {"estado": "AMBIGUO", "mensaje": mensaje_ambiguo(resultado_recon.ambiguo)}

    if persona_id is None:
        if distancia is None:
            return {"estado": "SIN_REFERENCIAS",
                    "mensaje": "No hay fotografías de referencia utilizables"}
        return {"estado": "NO_RECONOCIDO",
                "mensaje": f"Rostro no reconocido (distancia mínima {distancia:.2f})"}

    requeridas = _confirmaciones_requeridas()
    cantidad = confirmador.registrar(persona_id)
    if cantidad < requeridas:
        return {"estado": "CONFIRMANDO",
                "mensaje": (f"Verificando identidad: {nombre} (distancia {distancia:.2f}), "
                            f"confirmación {cantidad}/{requeridas}. Mantenga el rostro frente a la cámara")}

    # Identidad confirmada: evaluamos las reglas de negocio sin persistir aún
    evaluacion = gym_service.evaluar_acceso(persona_id)

    if not evaluacion["permitido"]:
        confirmador.reiniciar()  # Reset para que no se quede trabado tras un rechazo
        return {
            "estado": "ACCESO_DENEGADO",
            "tipo_persona": evaluacion.get("tipo_persona"),
            "nombre": nombre,
            "distancia": distancia,
            "motivo": evaluacion["motivo"],
            "mensaje": f"ACCESO DENEGADO a {nombre}: {evaluacion['motivo']}",
            "evaluacion": evaluacion,
        }

    # Acceso permitido: se genera la propuesta para el modal de confirmación
    return {
        "estado": "PROPUESTA_CONFIRMACION",
        "tipo_persona": evaluacion["tipo_persona"],
        "nombre": nombre,
        "distancia": distancia,
        "mensaje": evaluacion["mensaje"],
        "propuesta": evaluacion,
    }
