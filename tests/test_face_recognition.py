from datetime import time

import numpy as np
import pytest

from services import attendance_service as att
from services import face_service, recognition_logic
from services.face_service import FaceRecognitionService, ResultadoReconocimiento
from services.recognition_logic import Confirmador, procesar

DIM = 512
ANA = (1, "Pérez, Ana")
ALAN = (2, "Pérez, Alan")
LUIS = (3, "Gómez, Luis")


def _consulta():
    v = np.zeros(DIM, np.float32)
    v[0] = 1.0
    return v


def _referencia(distancia, eje):
    """Vector unitario a una distancia coseno exacta de la consulta (eje 0).
    Cada referencia usa otro eje para la parte ortogonal."""
    v = np.zeros(DIM, np.float32)
    v[0] = 1.0 - distancia
    v[eje] = np.sqrt(1.0 - (1.0 - distancia) ** 2)
    return v


def _servicio(monkeypatch, referencias):
    """FaceRecognitionService con referencias sintéticas ya cargadas:
    referencias = [(alumno, distancia_a_la_consulta), ...]. _embedding se
    reemplaza para que no se cargue DeepFace."""
    servicio = FaceRecognitionService(student_repository=None)
    vectores = [_referencia(d, eje) for eje, (_a, d) in enumerate(referencias, start=1)]
    servicio._matriz = np.vstack(vectores) if vectores else np.empty((0, DIM), np.float32)
    servicio._etiquetas = [alumno for alumno, _d in referencias]
    monkeypatch.setattr(face_service, "_embedding", lambda _rostro: _consulta())
    return servicio


@pytest.fixture(autouse=True)
def entorno_por_defecto(monkeypatch):
    # Umbral 0.40 y margen 0.05 por defecto, sin importar lo que tenga el .env.
    monkeypatch.delenv("UMBRAL_RECONOCIMIENTO", raising=False)
    monkeypatch.delenv("MARGEN_AMBIGUEDAD", raising=False)
    monkeypatch.delenv("CONFIRMACIONES_RECONOCIMIENTO", raising=False)


# --- reconocer() ---

def test_alumno_claramente_mas_cercano(monkeypatch, capsys):
    # Ana tiene 3 fotos: cuenta la mejor (0.15), no la primera ni el promedio.
    servicio = _servicio(monkeypatch, [(ANA, 0.30), (ANA, 0.15), (ANA, 0.25),
                                       (ALAN, 0.32), (LUIS, 0.70)])
    r = servicio.reconocer(rostro_bgr=None)

    assert (r.alumno_id, r.nombre, r.ambiguo) == (1, "Pérez, Ana", None)
    assert r.distancia == pytest.approx(0.15, abs=1e-5)
    salida = capsys.readouterr().out
    assert ("[Reconocimiento] Distancias por alumno: "
            "Pérez, Ana 0.150 | Pérez, Alan 0.320 | Gómez, Luis 0.700") in salida


def test_dos_alumnos_casi_iguales_es_ambiguo(monkeypatch):
    servicio = _servicio(monkeypatch, [(ANA, 0.20), (ALAN, 0.23), (ALAN, 0.35)])
    r = servicio.reconocer(rostro_bgr=None)

    assert r.alumno_id is None and r.nombre is None
    assert r.distancia == pytest.approx(0.20, abs=1e-5)
    (n1, d1), (n2, d2) = r.ambiguo
    assert (n1, n2) == ("Pérez, Ana", "Pérez, Alan")
    assert (d1, d2) == (pytest.approx(0.20, abs=1e-5), pytest.approx(0.23, abs=1e-5))


def test_segundo_alumno_justo_fuera_del_margen_no_es_ambiguo(monkeypatch):
    servicio = _servicio(monkeypatch, [(ANA, 0.20), (ALAN, 0.26)])
    r = servicio.reconocer(rostro_bgr=None)
    assert r.alumno_id == 1 and r.ambiguo is None


def test_margen_configurable_desde_el_entorno(monkeypatch):
    monkeypatch.setenv("MARGEN_AMBIGUEDAD", "0.01")
    servicio = _servicio(monkeypatch, [(ANA, 0.20), (ALAN, 0.23)])
    r = servicio.reconocer(rostro_bgr=None)
    assert r.alumno_id == 1 and r.ambiguo is None


def test_desconocido(monkeypatch):
    servicio = _servicio(monkeypatch, [(ANA, 0.55), (ALAN, 0.62)])
    r = servicio.reconocer(rostro_bgr=None)

    assert (r.alumno_id, r.nombre, r.ambiguo) == (None, None, None)
    assert r.distancia == pytest.approx(0.55, abs=1e-5)


def test_umbral_desde_el_entorno(monkeypatch):
    monkeypatch.setenv("UMBRAL_RECONOCIMIENTO", "0.30")
    servicio = _servicio(monkeypatch, [(ANA, 0.35), (ALAN, 0.60)])
    assert servicio.reconocer(rostro_bgr=None).alumno_id is None


def test_sin_referencias(monkeypatch):
    servicio = _servicio(monkeypatch, [])

    def no_debe_llamarse(_rostro):
        raise AssertionError("sin referencias no hace falta calcular el embedding")

    monkeypatch.setattr(face_service, "_embedding", no_debe_llamarse)
    assert servicio.reconocer(rostro_bgr=None) == ResultadoReconocimiento()


# --- procesar() y confirmaciones ---

class _FaceSecuencia:
    def __init__(self, resultados):
        self._resultados = list(resultados)

    def reconocer(self, _rostro):
        return self._resultados.pop(0)


class _AsistenciaFalsa:
    def __init__(self):
        self.llamadas = []

    def procesar(self, jornada_id, alumno_id, horario_entrada, horario_salida):
        self.llamadas.append(alumno_id)
        return att.ENTRADA_REGISTRADA, None


RECONOCE_ANA = ResultadoReconocimiento(1, "Pérez, Ana", 0.18)
RECONOCE_ALAN = ResultadoReconocimiento(2, "Pérez, Alan", 0.19)
AMBIGUO = ResultadoReconocimiento(distancia=0.20,
                                  ambiguo=(("Pérez, Ana", 0.20), ("Pérez, Alan", 0.23)))
DESCONOCIDO = ResultadoReconocimiento(distancia=0.62)
SIN_REFERENCIAS = ResultadoReconocimiento()


def _intentos(monkeypatch, secuencia):
    """Ejecuta procesar() para cada (segundo, resultado) y devuelve los
    estados y el servicio de asistencia falso."""
    face = _FaceSecuencia(r for _t, r in secuencia)
    asistencia = _AsistenciaFalsa()
    confirmador = Confirmador()
    estados = []
    for segundo, _r in secuencia:
        monkeypatch.setattr(recognition_logic.time, "monotonic", lambda s=segundo: 1000.0 + s)
        resultado = procesar(face, asistencia, None, 1, time(10, 0), time(12, 0), confirmador)
        estados.append(resultado["estado"])
    return estados, asistencia


def test_procesar_ambiguo_no_registra_asistencia(monkeypatch):
    estados, asistencia = _intentos(monkeypatch, [(0, AMBIGUO)])
    assert estados == ["AMBIGUO"]
    assert asistencia.llamadas == []


def test_mensaje_ambiguo():
    face = _FaceSecuencia([AMBIGUO])
    resultado = procesar(face, _AsistenciaFalsa(), None, 1, time(10, 0), time(12, 0),
                         Confirmador())
    assert resultado["mensaje"] == ("Coincidencia ambigua entre Pérez, Ana (0.200) y "
                                    "Pérez, Alan (0.230); no se registra. "
                                    "Mire de frente, con buena luz")


def test_procesar_sin_referencias_y_desconocido(monkeypatch):
    estados, asistencia = _intentos(monkeypatch, [(0, SIN_REFERENCIAS), (2, DESCONOCIDO)])
    assert estados == ["SIN_REFERENCIAS", "NO_RECONOCIDO"]
    assert asistencia.llamadas == []


def test_fallidos_y_ambiguos_no_reinician_la_confirmacion(monkeypatch):
    estados, asistencia = _intentos(monkeypatch, [
        (0, RECONOCE_ANA), (2, AMBIGUO), (4, DESCONOCIDO), (6, RECONOCE_ANA),
    ])
    assert estados == ["CONFIRMANDO", "AMBIGUO", "NO_RECONOCIDO", att.ENTRADA_REGISTRADA]
    assert asistencia.llamadas == [1]


def test_otro_alumno_reinicia_la_confirmacion(monkeypatch):
    estados, asistencia = _intentos(monkeypatch, [
        (0, RECONOCE_ANA), (2, RECONOCE_ALAN), (4, RECONOCE_ANA), (6, RECONOCE_ANA),
    ])
    assert estados == ["CONFIRMANDO", "CONFIRMANDO", "CONFIRMANDO", att.ENTRADA_REGISTRADA]
    assert asistencia.llamadas == [1]


def test_pasada_la_ventana_se_reinicia_la_confirmacion(monkeypatch):
    estados, asistencia = _intentos(monkeypatch, [
        (0, RECONOCE_ANA), (4, DESCONOCIDO), (8.5, RECONOCE_ANA), (10, RECONOCE_ANA),
    ])
    assert estados == ["CONFIRMANDO", "NO_RECONOCIDO", "CONFIRMANDO", att.ENTRADA_REGISTRADA]
    assert asistencia.llamadas == [1]
