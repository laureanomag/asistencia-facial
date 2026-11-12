"""Proceso de reconocimiento facial para Zebra Gym.
Corre separado de la interfaz para no congelar la GUI con TensorFlow/DeepFace.
Protocolo: una línea JSON por mensaje en stdin y stdout."""
import base64
import json
import os
import sys
import traceback

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SRC not in sys.path:
    sys.path.insert(0, SRC)


def main():
    canal = os.fdopen(os.dup(sys.stdout.fileno()), "w", encoding="utf-8")
    sys.stdout = sys.stderr

    import cv2
    import numpy as np

    from repositories.gym_repository import GymRepository
    from repositories.person_repository import PersonRepository
    from services.face_service import FaceRecognitionService
    from services.gym_service import GymService
    from services.recognition_logic import Confirmador, procesar

    person_repo = PersonRepository()
    gym_repo = GymRepository()
    face = FaceRecognitionService(person_repo)
    gym_service = GymService(gym_repo, person_repo)
    confirmador = Confirmador()

    def responder(datos):
        canal.write(json.dumps(datos, default=str) + "\n")
        canal.flush()

    for linea in sys.stdin:
        linea = linea.strip()
        if not linea:
            continue
        try:
            msg = json.loads(linea)
            cmd = msg["cmd"]

            if cmd == "invalidar":
                face.invalidar()
                confirmador.reiniciar()
            elif cmd == "precargar":
                face.precargar()
                responder({"estado": "MODELO_LISTO", "mensaje": "Esperando persona frente a cámara..."})
            elif cmd == "reconocer":
                datos = np.frombuffer(base64.b64decode(msg["imagen"]), np.uint8)
                rostro = cv2.imdecode(datos, cv2.IMREAD_COLOR)
                responder(procesar(face, gym_service, rostro, confirmador))
            elif cmd == "confirmar_ingreso_socio":
                ingreso_id = gym_service.confirmar_ingreso_socio(
                    msg["socio_id"], msg["membresia_id"]
                )
                confirmador.reiniciar()
                responder({"estado": "INGRESO_REGISTRADO", "ingreso_id": ingreso_id, "mensaje": "Ingreso registrado con éxito"})
            elif cmd == "confirmar_profesor":
                res = gym_service.confirmar_asistencia_profesor(
                    profesor_id=msg["profesor_id"],
                    operacion=msg["operacion"],
                    asistencia_id=msg.get("asistencia_id"),
                    turno_id=msg.get("turno_id"),
                    es_cambio_turno=msg.get("es_cambio_turno", False),
                    observaciones=msg.get("observaciones"),
                )
                confirmador.reiniciar()
                responder({"estado": "PROFESOR_REGISTRADO", "resultado": res, "mensaje": f"{msg['operacion']} registrada con éxito"})
            elif cmd == "cancelar_operacion":
                confirmador.reiniciar()
                responder({"estado": "OPERACION_CANCELADA", "mensaje": "Operación descartada por el usuario"})
            else:
                responder({"estado": "ERROR", "mensaje": f"Comando desconocido: {cmd}"})
        except Exception as error:
            traceback.print_exc()
            responder({"estado": "ERROR", "mensaje": f"Error en el proceso de reconocimiento: {error}"})


if __name__ == "__main__":
    main()
