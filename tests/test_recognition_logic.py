"""ControlDeIngreso: reconocimiento + reglas + modal, con dobles de prueba
(sin cámara, sin DeepFace y sin base de datos)."""
import pytest

from services import recognition_logic
from services.acceso_service import (
    AVISO, ENTRENAR, PROPUESTA, RECHAZADO, Antirrebote, Confirmacion, Evaluacion,
    GestorPropuestas, Opcion,
)
from services.face_service import ResultadoReconocimiento
from services.recognition_logic import ControlDeIngreso, mensaje_ambiguo

ANA = ResultadoReconocimiento(1, "Pérez, Ana", 0.18)
ALAN = ResultadoReconocimiento(2, "Pérez, Alan", 0.19)
AMBIGUO = ResultadoReconocimiento(distancia=0.20,
                                  ambiguo=(("Pérez, Ana", 0.20), ("Pérez, Alan", 0.23)))
DESCONOCIDO = ResultadoReconocimiento(distancia=0.62)
SIN_REFERENCIAS = ResultadoReconocimiento()


class Reloj:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class FaceFalso:
    def __init__(self):
        self.siguiente = ANA

    def reconocer(self, _rostro):
        return self.siguiente


class AccesoFalso:
    """Devuelve la evaluación configurada y anota lo que se escribiría."""

    def __init__(self):
        self.estado = PROPUESTA
        self.evaluados, self.confirmados, self.no_reconocidos = [], [], []
        self.resultado = Confirmacion(True, "Ingreso registrado a las 18:42.", "verde")

    def evaluar(self, persona_id, distancia=None):
        self.evaluados.append((persona_id, distancia))
        if self.estado == PROPUESTA:
            return Evaluacion(PROPUESTA, "Bienvenido/a", persona_id=persona_id, nombre="Ana Pérez",
                              opciones=(Opcion(ENTRENAR, "Entrenar", "registrar ingreso"),))
        if self.estado == RECHAZADO:
            return Evaluacion(RECHAZADO, "Ya entrenó 3 días esta semana.", persona_id=persona_id,
                              nombre="Ana Pérez", motivo="limite_semanal")
        return Evaluacion(AVISO, "Ya registraste tu entrada a las 07:05.", persona_id=persona_id,
                          nombre="Ana Pérez")

    def confirmar(self, evaluacion, opcion):
        self.confirmados.append((evaluacion.persona_id, opcion))
        return self.resultado

    def registrar_no_reconocido(self, distancia=None):
        self.no_reconocidos.append(distancia)


@pytest.fixture
def entorno(monkeypatch):
    reloj = Reloj()
    monkeypatch.setattr(recognition_logic.time, "monotonic", reloj)
    monkeypatch.delenv("CONFIRMACIONES_RECONOCIMIENTO", raising=False)
    face, acceso = FaceFalso(), AccesoFalso()
    control = ControlDeIngreso(face, acceso, propuestas=GestorPropuestas(reloj=reloj),
                               antirrebote=Antirrebote(reloj=reloj))
    return reloj, face, acceso, control


def _intentos(entorno, secuencia):
    """(segundo, resultado del rostro) -> lista de estados."""
    reloj, face, _acceso, control = entorno
    estados = []
    inicio = reloj.t
    for segundo, resultado in secuencia:
        reloj.t = inicio + segundo
        face.siguiente = resultado
        estados.append(control.procesar(None)["estado"])
    return estados


# --- Confirmación de identidad (2 coincidencias en 8 s) ---

def test_ambiguo_no_evalua_reglas(entorno):
    assert _intentos(entorno, [(0, AMBIGUO)]) == ["AMBIGUO"]
    assert entorno[2].evaluados == []


def test_mensaje_ambiguo():
    assert mensaje_ambiguo(AMBIGUO.ambiguo) == (
        "Coincidencia ambigua entre Pérez, Ana (0.200) y Pérez, Alan (0.230); no se registra. "
        "Mire de frente, con buena luz")


def test_sin_referencias_y_desconocido(entorno):
    assert _intentos(entorno, [(0, SIN_REFERENCIAS), (2, DESCONOCIDO)]) == [
        "SIN_REFERENCIAS", "NO_RECONOCIDO"]
    assert entorno[2].evaluados == []


def test_fallidos_y_ambiguos_no_reinician_la_confirmacion(entorno):
    assert _intentos(entorno, [(0, ANA), (2, AMBIGUO), (4, DESCONOCIDO), (6, ANA)]) == [
        "CONFIRMANDO", "AMBIGUO", "NO_RECONOCIDO", PROPUESTA]
    assert entorno[2].evaluados == [(1, recognition_logic._distancia(0.18))]


def test_otra_persona_reinicia_la_confirmacion(entorno):
    assert _intentos(entorno, [(0, ANA), (2, ALAN), (4, ANA), (6, ANA)]) == [
        "CONFIRMANDO", "CONFIRMANDO", "CONFIRMANDO", PROPUESTA]


def test_pasada_la_ventana_se_reinicia_la_confirmacion(entorno):
    assert _intentos(entorno, [(0, ANA), (4, DESCONOCIDO), (8.5, ANA), (10, ANA)]) == [
        "CONFIRMANDO", "NO_RECONOCIDO", "CONFIRMANDO", PROPUESTA]


# --- Propuesta y modal ---

def test_propuesta_trae_token_y_pausa_el_reconocimiento(entorno):
    _reloj, _face, acceso, control = entorno
    control.procesar(None)
    respuesta = control.procesar(None)
    assert respuesta["estado"] == PROPUESTA and respuesta["cierre_s"] == 30
    assert respuesta["evaluacion"]["opciones"][0]["clave"] == ENTRENAR
    # Con el modal abierto no se intentan reconocimientos nuevos.
    assert control.procesar(None)["estado"] == "PROPUESTA_PENDIENTE"
    assert len(acceso.evaluados) == 1


def test_ok_confirma_una_sola_vez(entorno):
    _reloj, _face, acceso, control = entorno
    control.procesar(None)
    token = control.procesar(None)["token"]
    assert control.confirmar(token, ENTRENAR)["estado"] == "CONFIRMADO"
    assert control.confirmar(token, ENTRENAR)["estado"] == "PROPUESTA_VENCIDA"    # doble OK
    assert acceso.confirmados == [(1, ENTRENAR)]


def test_confirmacion_rechazada_informa_el_motivo(entorno):
    _reloj, _face, acceso, control = entorno
    acceso.resultado = Confirmacion(False, "Ya ingresó hoy.", "rojo", "limite_diario")
    control.procesar(None)
    token = control.procesar(None)["token"]
    respuesta = control.confirmar(token, ENTRENAR)
    assert (respuesta["estado"], respuesta["etiqueta"]) == (RECHAZADO, "Ya ingresó hoy")


def test_cancelar_no_escribe_y_reanuda(entorno):
    reloj, _face, acceso, control = entorno
    control.procesar(None)
    token = control.procesar(None)["token"]
    assert control.cancelar(token)["estado"] == "CANCELADO"
    assert acceso.confirmados == []
    # Antirrebote de 10 s también después de Cancelar; después se reanuda.
    reloj.t += 9
    assert control.procesar(None)["estado"] == "EN_ESPERA"
    reloj.t += 1.5
    assert control.procesar(None)["estado"] == "CONFIRMANDO"


def test_cierre_automatico_del_modal(entorno):
    reloj, _face, acceso, control = entorno
    control.procesar(None)
    token = control.procesar(None)["token"]
    reloj.t += 36                       # pasó el cierre de 30 s y la vigencia del token
    assert control.procesar(None)["estado"] != "PROPUESTA_PENDIENTE"
    assert control.confirmar(token, ENTRENAR)["estado"] == "PROPUESTA_VENCIDA"
    assert acceso.confirmados == []


# --- Rechazos, antirrebote y no reconocidos ---

def test_rechazo_con_motivo_y_reintento(entorno):
    reloj, _face, acceso, control = entorno
    acceso.estado = RECHAZADO
    control.procesar(None)
    respuesta = control.procesar(None)
    assert respuesta == {"estado": RECHAZADO, "mensaje": "Ya entrenó 3 días esta semana.",
                         "nombre": "Ana Pérez", "reintento_s": 10, "motivo": "limite_semanal",
                         "etiqueta": "Límite semanal"}
    # Intentos repetidos en pocos segundos: no se evalúa ni se registra de nuevo.
    reloj.t += 3
    espera = control.procesar(None)
    assert (espera["estado"], espera["reintento_s"]) == ("EN_ESPERA", 7)
    assert len(acceso.evaluados) == 1


def test_aviso_sin_registro(entorno):
    _reloj, _face, acceso, control = entorno
    acceso.estado = AVISO
    control.procesar(None)
    assert control.procesar(None)["estado"] == AVISO


def test_no_reconocido_se_registra_al_tercer_intento(entorno):
    reloj, face, acceso, control = entorno
    estados = _intentos(entorno, [(0, DESCONOCIDO), (2, DESCONOCIDO), (4, DESCONOCIDO)])
    assert estados == ["NO_RECONOCIDO", "NO_RECONOCIDO", RECHAZADO]
    assert len(acceso.no_reconocidos) == 1
    # Durante los 10 s siguientes no se vuelve a registrar.
    assert _intentos(entorno, [(1, DESCONOCIDO), (2, DESCONOCIDO), (3, DESCONOCIDO)]) == [
        "NO_RECONOCIDO"] * 3
    assert len(acceso.no_reconocidos) == 1


def test_reconocer_a_alguien_reinicia_los_no_reconocidos(entorno):
    _reloj, _face, acceso, _control = entorno
    _intentos(entorno, [(0, DESCONOCIDO), (2, DESCONOCIDO), (4, ANA), (6, DESCONOCIDO)])
    assert acceso.no_reconocidos == []
