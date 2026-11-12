import numpy as np
import pytest

from services import face_service
from services.face_service import FaceRecognitionService, ResultadoReconocimiento

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
    referencias = [(persona, distancia_a_la_consulta), ...]. _embedding se
    reemplaza para que no se cargue DeepFace."""
    servicio = FaceRecognitionService(person_repository=None)
    vectores = [_referencia(d, eje) for eje, (_a, d) in enumerate(referencias, start=1)]
    servicio._matriz = np.vstack(vectores) if vectores else np.empty((0, DIM), np.float32)
    servicio._etiquetas = [persona for persona, _d in referencias]
    monkeypatch.setattr(face_service, "_embedding", lambda _rostro: _consulta())
    return servicio


@pytest.fixture(autouse=True)
def entorno_por_defecto(monkeypatch):
    # Umbral 0.40 y margen 0.05 por defecto, sin importar lo que tenga el .env.
    monkeypatch.delenv("UMBRAL_RECONOCIMIENTO", raising=False)
    monkeypatch.delenv("MARGEN_AMBIGUEDAD", raising=False)
    monkeypatch.delenv("CONFIRMACIONES_RECONOCIMIENTO", raising=False)


# --- reconocer() ---

def test_persona_claramente_mas_cercana(monkeypatch, capsys):
    # Ana tiene 3 fotos: cuenta la mejor (0.15), no la primera ni el promedio.
    servicio = _servicio(monkeypatch, [(ANA, 0.30), (ANA, 0.15), (ANA, 0.25),
                                       (ALAN, 0.32), (LUIS, 0.70)])
    r = servicio.reconocer(rostro_bgr=None)

    assert (r.persona_id, r.nombre, r.ambiguo) == (1, "Pérez, Ana", None)
    assert r.distancia == pytest.approx(0.15, abs=1e-5)
    salida = capsys.readouterr().out
    assert ("[Reconocimiento] Distancias por persona: "
            "Pérez, Ana 0.150 | Pérez, Alan 0.320 | Gómez, Luis 0.700") in salida


def test_dos_personas_casi_iguales_es_ambiguo(monkeypatch):
    servicio = _servicio(monkeypatch, [(ANA, 0.20), (ALAN, 0.23), (ALAN, 0.35)])
    r = servicio.reconocer(rostro_bgr=None)

    assert r.persona_id is None and r.nombre is None
    assert r.distancia == pytest.approx(0.20, abs=1e-5)
    (n1, d1), (n2, d2) = r.ambiguo
    assert (n1, n2) == ("Pérez, Ana", "Pérez, Alan")
    assert (d1, d2) == (pytest.approx(0.20, abs=1e-5), pytest.approx(0.23, abs=1e-5))


def test_segunda_persona_justo_fuera_del_margen_no_es_ambigua(monkeypatch):
    servicio = _servicio(monkeypatch, [(ANA, 0.20), (ALAN, 0.26)])
    r = servicio.reconocer(rostro_bgr=None)
    assert r.persona_id == 1 and r.ambiguo is None


def test_margen_configurable_desde_el_entorno(monkeypatch):
    monkeypatch.setenv("MARGEN_AMBIGUEDAD", "0.01")
    servicio = _servicio(monkeypatch, [(ANA, 0.20), (ALAN, 0.23)])
    r = servicio.reconocer(rostro_bgr=None)
    assert r.persona_id == 1 and r.ambiguo is None


def test_desconocido(monkeypatch):
    servicio = _servicio(monkeypatch, [(ANA, 0.55), (ALAN, 0.62)])
    r = servicio.reconocer(rostro_bgr=None)

    assert (r.persona_id, r.nombre, r.ambiguo) == (None, None, None)
    assert r.distancia == pytest.approx(0.55, abs=1e-5)


def test_umbral_desde_el_entorno(monkeypatch):
    monkeypatch.setenv("UMBRAL_RECONOCIMIENTO", "0.30")
    servicio = _servicio(monkeypatch, [(ANA, 0.35), (ALAN, 0.60)])
    assert servicio.reconocer(rostro_bgr=None).persona_id is None


def test_sin_referencias(monkeypatch):
    servicio = _servicio(monkeypatch, [])

    def no_debe_llamarse(_rostro):
        raise AssertionError("sin referencias no hace falta calcular el embedding")

    monkeypatch.setattr(face_service, "_embedding", no_debe_llamarse)
    assert servicio.reconocer(rostro_bgr=None) == ResultadoReconocimiento()
