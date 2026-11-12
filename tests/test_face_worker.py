"""Protocolo del proceso de reconocimiento (face_worker.atender), sin cámara."""
import json

from services.face_worker import atender


class Grabador:
    def __init__(self):
        self.llamadas = []

    def __getattr__(self, nombre):
        def metodo(*args):
            self.llamadas.append((nombre, args))
            return {"estado": nombre.upper()}
        return metodo


def test_comandos_del_protocolo():
    face, control = Grabador(), Grabador()
    decodificar = lambda texto: f"imagen<{texto}>"  # noqa: E731

    assert atender({"cmd": "precargar"}, face, control)["estado"] == "MODELO_LISTO"
    assert atender({"cmd": "invalidar"}, face, control) is None
    assert atender({"cmd": "reconocer", "imagen": "abc"}, face, control, decodificar) == {"estado": "PROCESAR"}
    assert atender({"cmd": "confirmar", "token": "t1", "opcion": "fichar"}, face, control) == {"estado": "CONFIRMAR"}
    assert atender({"cmd": "cancelar", "token": "t1"}, face, control) == {"estado": "CANCELAR"}

    assert face.llamadas == [("precargar", ()), ("invalidar", ())]
    assert control.llamadas == [("reiniciar", ()), ("procesar", ("imagen<abc>",)),
                                ("confirmar", ("t1", "fichar")), ("cancelar", ("t1",))]


def test_comando_desconocido_y_respuestas_serializables():
    respuesta = atender({"cmd": "registrar_ingreso"}, Grabador(), Grabador())
    assert respuesta == {"estado": "ERROR", "mensaje": "Comando desconocido: registrar_ingreso"}
    assert json.loads(json.dumps(respuesta)) == respuesta
