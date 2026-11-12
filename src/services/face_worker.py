"""Proceso de reconocimiento facial de ZebraGym.
Corre separado de la interfaz para que TensorFlow/DeepFace no la congelen.
Protocolo: una línea JSON por mensaje por stdin (comandos) y por stdout
(respuestas); los logs van a stderr.

Comandos:
  {"cmd": "precargar"}                       carga el modelo y las referencias
  {"cmd": "invalidar"}                       vuelve a leer las fotos de la base
  {"cmd": "reconocer", "imagen": base64}     un rostro recortado (JPEG)
  {"cmd": "confirmar", "token": t, "opcion": "entrenar" | "fichar"}   botón OK
  {"cmd": "cancelar", "token": t}            Cancelar o cierre automático (no escribe)
Las respuestas tienen "estado" y "mensaje" (ver recognition_logic.py)."""
import base64
import json
import os
import sys
import traceback

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SRC not in sys.path:
    sys.path.insert(0, SRC)


def decodificar_imagen(texto_base64):
    import cv2
    import numpy as np
    datos = np.frombuffer(base64.b64decode(texto_base64), np.uint8)
    return cv2.imdecode(datos, cv2.IMREAD_COLOR)


def atender(msg, face, control, decodificar=decodificar_imagen):
    """Ejecuta un comando y devuelve la respuesta (None si no hay que responder)."""
    cmd = msg["cmd"]
    if cmd == "invalidar":
        face.invalidar()
        control.reiniciar()
        return None
    if cmd == "precargar":
        face.precargar()
        return {"estado": "MODELO_LISTO", "mensaje": "Mirá a la cámara para ingresar."}
    if cmd == "reconocer":
        return control.procesar(decodificar(msg["imagen"]))
    if cmd == "confirmar":
        return control.confirmar(msg.get("token"), msg.get("opcion"))
    if cmd == "cancelar":
        return control.cancelar(msg.get("token"))
    return {"estado": "ERROR", "mensaje": f"Comando desconocido: {cmd}"}


def main():
    # El canal de respuestas es el stdout original; cualquier print de las
    # librerías se redirige a stderr para no mezclarse con el protocolo.
    canal = os.fdopen(os.dup(sys.stdout.fileno()), "w", encoding="utf-8")
    sys.stdout = sys.stderr

    from repositories.person_repository import PersonRepository
    from services.acceso_service import AccesoService
    from services.face_service import FaceRecognitionService
    from services.recognition_logic import ControlDeIngreso

    face = FaceRecognitionService(PersonRepository())
    control = ControlDeIngreso(face, AccesoService())

    def responder(datos):
        canal.write(json.dumps(datos, default=str) + "\n")
        canal.flush()

    for linea in sys.stdin:
        linea = linea.strip()
        if not linea:
            continue
        try:
            respuesta = atender(json.loads(linea), face, control)
            if respuesta is not None:
                responder(respuesta)
        except Exception as error:
            traceback.print_exc()
            responder({"estado": "ERROR", "mensaje": f"Error en el reconocimiento: {error}"})


if __name__ == "__main__":
    main()
