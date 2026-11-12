"""Control de ingreso por reconocimiento facial, sin dependencias de interfaz.
Lo ejecuta el proceso de reconocimiento (face_worker.py).

Estados que se informan a la interfaz (clave "estado"):
  SIN_REFERENCIAS, NO_RECONOCIDO, AMBIGUO, CONFIRMANDO   reconocimiento en curso
  EN_ESPERA      la misma persona dentro del antirrebote (10 s): no se evalúa
  PROPUESTA      abrir el modal; trae "token" y la "evaluacion" (opciones y tarjetas)
  RECHAZADO      se muestra el motivo; ya quedó registrado en acceso
  AVISO          mensaje sin registro (p. ej., entrada fichada hace instantes)
  CONFIRMADO     el OK registró el ingreso o el fichaje
  CANCELADO      Cancelar (o el cierre automático del modal): no se registró nada
  PROPUESTA_VENCIDA  el token ya se usó o venció
Mientras hay una propuesta pendiente no se intentan reconocimientos nuevos."""
import os
import time
from decimal import Decimal

from services import reglas_ingreso as reglas
from services.acceso_service import (
    AVISO, PROPUESTA, RECHAZADO, Antirrebote, ContadorNoReconocidos, GestorPropuestas,
)

CONFIRMACIONES_REQUERIDAS = 2
VENTANA_CONFIRMACION_S = 8.0
CIERRE_AUTOMATICO_S = 30
CLAVE_DESCONOCIDO = "desconocido"


def _confirmaciones_requeridas():
    try:
        return max(1, int(os.getenv("CONFIRMACIONES_RECONOCIMIENTO", CONFIRMACIONES_REQUERIDAS)))
    except ValueError:
        return CONFIRMACIONES_REQUERIDAS


class Confirmador:
    """Cuenta coincidencias de la MISMA persona dentro de la ventana de tiempo
    para evitar falsos positivos esporádicos. Un intento fallido o ambiguo no
    modifica la cuenta."""

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


def _distancia(valor):
    return None if valor is None else Decimal(str(round(float(valor), 4)))


class ControlDeIngreso:
    """Une el reconocimiento facial con las reglas de ingreso y guarda el
    estado entre intentos: confirmación de identidad, propuesta pendiente,
    antirrebote por persona y conteo de rostros no reconocidos."""

    def __init__(self, face_service, acceso_service, confirmador=None, propuestas=None,
                 antirrebote=None, desconocidos=None):
        self._face = face_service
        self._acceso = acceso_service
        self._confirmador = confirmador or Confirmador()
        self._propuestas = propuestas or GestorPropuestas()
        self._antirrebote = antirrebote or Antirrebote()
        self._desconocidos = desconocidos or ContadorNoReconocidos()

    def reiniciar(self):
        self._confirmador.reiniciar()
        self._desconocidos.reiniciar()

    # --- Reconocimiento ---

    def procesar(self, rostro):
        if self._propuestas.pendiente():
            return {"estado": "PROPUESTA_PENDIENTE",
                    "mensaje": "Hay una confirmación abierta: respondé el aviso en pantalla."}

        resultado = self._face.reconocer(rostro)
        persona_id, nombre, distancia = resultado.persona_id, resultado.nombre, resultado.distancia

        if resultado.ambiguo is not None:
            return {"estado": "AMBIGUO", "mensaje": mensaje_ambiguo(resultado.ambiguo)}
        if persona_id is None:
            return self._no_reconocido(distancia)

        self._desconocidos.reiniciar()
        espera = self._antirrebote.restante(persona_id)
        if espera > 0:
            return {"estado": "EN_ESPERA", "reintento_s": int(espera + 0.999),
                    "mensaje": f"{nombre}: esperá unos segundos para volver a intentar."}

        requeridas = _confirmaciones_requeridas()
        cantidad = self._confirmador.registrar(persona_id)
        if cantidad < requeridas:
            return {"estado": "CONFIRMANDO",
                    "mensaje": (f"Verificando identidad: {nombre} (distancia {distancia:.2f}), "
                                f"confirmación {cantidad}/{requeridas}. "
                                "Mantenga el rostro frente a la cámara")}

        self._confirmador.reiniciar()
        evaluacion = self._acceso.evaluar(persona_id, _distancia(distancia))
        if evaluacion.estado == PROPUESTA:
            token = self._propuestas.crear(evaluacion)
            return {"estado": PROPUESTA, "token": token, "cierre_s": CIERRE_AUTOMATICO_S,
                    "mensaje": evaluacion.mensaje, "evaluacion": evaluacion.a_dict()}

        self._antirrebote.registrar(persona_id)
        respuesta = {"estado": evaluacion.estado, "mensaje": evaluacion.mensaje,
                     "nombre": evaluacion.nombre, "reintento_s": int(self._antirrebote.segundos)}
        if evaluacion.estado == RECHAZADO:
            respuesta["motivo"] = evaluacion.motivo
            respuesta["etiqueta"] = reglas.ETIQUETAS_MOTIVO[evaluacion.motivo]
        return respuesta

    def _no_reconocido(self, distancia):
        if distancia is None:
            return {"estado": "SIN_REFERENCIAS",
                    "mensaje": "No hay fotografías de referencia utilizables"}
        mensaje = f"Rostro no reconocido (distancia mínima {distancia:.2f})"
        if self._antirrebote.bloqueado(CLAVE_DESCONOCIDO) or not self._desconocidos.fallo():
            return {"estado": "NO_RECONOCIDO", "mensaje": mensaje}
        # Tercer intento seguido sin reconocer: recién ahora se registra.
        self._acceso.registrar_no_reconocido(_distancia(distancia))
        self._antirrebote.registrar(CLAVE_DESCONOCIDO)
        return {"estado": RECHAZADO, "motivo": reglas.NO_RECONOCIDO,
                "etiqueta": reglas.ETIQUETAS_MOTIVO[reglas.NO_RECONOCIDO], "nombre": None,
                "reintento_s": int(self._antirrebote.segundos),
                "mensaje": "No pudimos reconocerte. Acercate a recepción."}

    # --- Respuesta al modal ---

    def confirmar(self, token, opcion):
        evaluacion = self._propuestas.tomar(token)
        if evaluacion is None:
            return {"estado": "PROPUESTA_VENCIDA",
                    "mensaje": "La confirmación ya no está vigente. Volvé a mirar a la cámara."}
        resultado = self._acceso.confirmar(evaluacion, opcion)
        self._antirrebote.registrar(evaluacion.persona_id)
        self._confirmador.reiniciar()
        respuesta = {"estado": "CONFIRMADO" if resultado.registrado else RECHAZADO,
                     "mensaje": resultado.mensaje, "tono": resultado.tono,
                     "nombre": evaluacion.nombre, "opcion": opcion}
        if resultado.motivo:
            respuesta["motivo"] = resultado.motivo
            respuesta["etiqueta"] = reglas.ETIQUETAS_MOTIVO[resultado.motivo]
        return respuesta

    def cancelar(self, token):
        """Cancelar o cierre automático del modal: no escribe nada en la base."""
        evaluacion = self._propuestas.tomar(token)
        if evaluacion is not None:
            self._antirrebote.registrar(evaluacion.persona_id)
        self._confirmador.reiniciar()
        return {"estado": "CANCELADO", "mensaje": "Operación cancelada. No se registró nada."}


__all__ = ["AVISO", "PROPUESTA", "RECHAZADO", "Confirmador", "ControlDeIngreso", "mensaje_ambiguo"]
