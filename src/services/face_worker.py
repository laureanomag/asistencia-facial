"""Proceso de reconocimiento facial. Se ejecuta aparte de la interfaz para que
TensorFlow/DeepFace no la congelen. Protocolo: una línea JSON por mensaje por
stdin (comandos) y por stdout (respuestas). Los logs van a stderr."""
import base64
import json
import os
import sys
import traceback
from datetime import time as dtime

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SRC not in sys.path:
    sys.path.insert(0, SRC)


def main():
    # El canal de respuestas es el stdout original; cualquier print de las
    # librerías se redirige a stderr para no mezclarse con el protocolo.
    canal = os.fdopen(os.dup(sys.stdout.fileno()), "w", encoding="utf-8")
    sys.stdout = sys.stderr

    import cv2
    import numpy as np

    from repositories.attendance_repository import AttendanceRepository
    from repositories.student_repository import StudentRepository
    from services.attendance_service import AttendanceService
    from services.face_service import FaceRecognitionService
    from services.recognition_logic import Confirmador, procesar

    face = FaceRecognitionService(StudentRepository())
    asistencia = AttendanceService(AttendanceRepository())
    confirmador = Confirmador()

    def responder(datos):
        canal.write(json.dumps(datos) + "\n")  # ASCII: sin problemas de codificación
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
                responder({"estado": "MODELO_LISTO", "mensaje": "Esperando rostro."})
            elif cmd == "reconocer":
                datos = np.frombuffer(base64.b64decode(msg["imagen"]), np.uint8)
                rostro = cv2.imdecode(datos, cv2.IMREAD_COLOR)
                h_entrada = dtime.fromisoformat(msg["horario_entrada"])
                h_salida = dtime.fromisoformat(msg["horario_salida"])
                responder(procesar(face, asistencia, rostro, msg["jornada_id"],
                                   h_entrada, h_salida, confirmador))
            else:
                responder({"estado": "ERROR", "mensaje": f"Comando desconocido: {cmd}"})
        except Exception as error:
            traceback.print_exc()
            responder({"estado": "ERROR", "mensaje": f"Error en el reconocimiento: {error}"})


if __name__ == "__main__":
    main()
