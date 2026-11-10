from datetime import date, datetime, time, timedelta

import pytest

from services import attendance_service as att
from services.attendance_service import AttendanceService
from services.face_service import ResultadoReconocimiento
from services.recognition_logic import procesar
from services.report_exporters import DatosInforme, FilaAlumno, _filas_tabla

JORNADA = 1
ALUMNO = 7
HOY = date(2026, 10, 26)
H_ENTRADA = time(10, 0)
H_SALIDA = time(12, 0)


def en(hora, minuto, segundo=0):
    return datetime.combine(HOY, time(hora, minuto, segundo))


class RepositorioFalso:
    """Imita AttendanceRepository en memoria, con la misma restricción UNIQUE
    (jornada_id, alumno_id) y el mismo UPDATE condicionado a salida NULL."""

    def __init__(self):
        self.filas = {}
        self.escrituras = []

    def obtener(self, jornada_id, alumno_id):
        fila = self.filas.get((jornada_id, alumno_id))
        return None if fila is None else (fila["id"], fila["entrada"], fila["salida"])

    def registrar_entrada(self, jornada_id, alumno_id, ahora, tardanza=False):
        clave = (jornada_id, alumno_id)
        if clave in self.filas:
            return False
        self.filas[clave] = {"id": len(self.filas) + 1, "entrada": ahora,
                             "salida": None, "tardanza": tardanza}
        self.escrituras.append("entrada")
        return True

    def registrar_salida(self, jornada_id, alumno_id, ahora):
        fila = self.filas.get((jornada_id, alumno_id))
        if fila is None or fila["salida"] is not None:
            return False
        fila["salida"] = ahora
        self.escrituras.append("salida")
        return True

    def fila(self):
        return self.filas[(JORNADA, ALUMNO)]


@pytest.fixture
def repo():
    return RepositorioFalso()


@pytest.fixture
def servicio(repo):
    return AttendanceService(repo)


def marcar(servicio, ahora):
    return servicio.procesar(JORNADA, ALUMNO, H_ENTRADA, H_SALIDA, ahora=ahora)


# --- Entrada ---

def test_entrada_a_tiempo(servicio, repo):
    assert marcar(servicio, en(10, 5)) == (att.ENTRADA_REGISTRADA, None)
    assert repo.fila()["tardanza"] is False
    assert repo.fila()["salida"] is None


def test_entrada_justo_a_los_10_minutos_no_es_tardanza(servicio, repo):
    assert marcar(servicio, en(10, 10)) == (att.ENTRADA_REGISTRADA, None)
    assert repo.fila()["tardanza"] is False


def test_entrada_con_tardanza(servicio, repo):
    assert marcar(servicio, en(10, 10, 1)) == (att.ENTRADA_CON_TARDANZA, None)
    assert repo.fila()["tardanza"] is True
    assert repo.fila()["entrada"] == en(10, 10, 1)


# --- Salida ---

def test_salida_2_segundos_despues_de_la_entrada(servicio, repo):
    # Incluso dentro de la ventana de salida, 2 s después no se puede salir.
    marcar(servicio, en(11, 56))
    estado, disponible = marcar(servicio, en(11, 56, 2))
    assert estado == att.SALIDA_AUN_NO
    assert disponible == en(12, 6)
    assert repo.fila()["salida"] is None
    assert repo.escrituras == ["entrada"]


def test_salida_antes_de_horario_salida_menos_5(servicio, repo):
    marcar(servicio, en(10, 0))
    estado, disponible = marcar(servicio, en(11, 54, 59))
    assert estado == att.SALIDA_AUN_NO
    assert disponible == en(11, 55)
    assert repo.fila()["salida"] is None


def test_salida_exactamente_a_horario_salida_menos_5_con_entrada_vieja(servicio, repo):
    marcar(servicio, en(10, 0))
    assert marcar(servicio, en(11, 55)) == (att.SALIDA_REGISTRADA, None)
    assert repo.fila()["salida"] == en(11, 55)


def test_entrada_tardia_dentro_de_la_ventana_de_salida(servicio, repo):
    assert marcar(servicio, en(11, 57)) == (att.ENTRADA_CON_TARDANZA, None)
    assert repo.fila()["salida"] is None  # el mismo reconocimiento no marca salida

    estado, disponible = marcar(servicio, en(12, 0))
    assert estado == att.SALIDA_AUN_NO
    assert disponible == en(12, 7)

    estado, _ = marcar(servicio, en(12, 6, 59))
    assert estado == att.SALIDA_AUN_NO

    assert marcar(servicio, en(12, 7)) == (att.SALIDA_REGISTRADA, None)
    assert repo.fila()["salida"] == en(12, 7)


def test_alumno_con_entrada_y_salida_completas(servicio, repo):
    marcar(servicio, en(10, 0))
    marcar(servicio, en(11, 58))
    assert marcar(servicio, en(12, 30)) == (att.ASISTENCIA_COMPLETA, None)
    assert repo.fila()["entrada"] == en(10, 0)
    assert repo.fila()["salida"] == en(11, 58)
    assert repo.escrituras == ["entrada", "salida"]
    assert len(repo.filas) == 1


# --- Reglas generales ---

def test_un_reconocimiento_nunca_registra_entrada_y_salida(servicio, repo):
    # Incluso después del horario de salida, la primera vez sólo se registra la entrada.
    marcar(servicio, en(13, 0))
    assert repo.escrituras == ["entrada"]


def test_la_espera_no_se_puede_cambiar_desde_el_entorno(monkeypatch, servicio, repo):
    for variable in ("SEPARACION_ENTRADA_SALIDA_MIN", "TOLERANCIA_ENTRADA_MIN",
                     "TOLERANCIA_SALIDA_MIN"):
        monkeypatch.setenv(variable, "0")
    marcar(servicio, en(11, 58))
    estado, disponible = marcar(servicio, en(11, 58, 2))
    assert estado == att.SALIDA_AUN_NO
    assert disponible == en(12, 8)
    assert att.ESPERA_ENTRADA_SALIDA == timedelta(minutes=10)


# --- Mensaje que ve el usuario ---

class _FaceFalso:
    def reconocer(self, _rostro):
        return ResultadoReconocimiento(ALUMNO, "Pérez, Ana", 0.12)


class _ConfirmadorFalso:
    def registrar(self, _alumno_id):
        return 99

    def reiniciar(self):
        pass


class _ServicioConHora:
    """Fija la hora de AttendanceService para probar el mensaje."""

    def __init__(self, servicio, ahora):
        self._servicio, self._ahora = servicio, ahora

    def procesar(self, *args):
        return self._servicio.procesar(*args, ahora=self._ahora)


def test_mensaje_salida_aun_no(servicio):
    marcar(servicio, en(10, 0))
    resultado = procesar(_FaceFalso(), _ServicioConHora(servicio, en(11, 0)), None,
                         JORNADA, H_ENTRADA, H_SALIDA, _ConfirmadorFalso())
    assert resultado["estado"] == att.SALIDA_AUN_NO
    assert resultado["mensaje"].endswith(
        "Entrada ya registrada. A partir de las 11:55 se habilita el horario de salida")


def test_mensaje_salida_aun_no_explica_la_espera_desde_la_entrada(servicio):
    # Caso de la prueba con el profe: salida cambiada a 8:55 y entrada del
    # alumno a las 8:50:25 -> manda la espera de 10 min, no el horario.
    marcar(servicio, en(8, 50).replace(second=25))
    resultado = procesar(_FaceFalso(), _ServicioConHora(servicio, en(8, 55)), None,
                         JORNADA, time(8, 0), time(8, 55), _ConfirmadorFalso())
    assert resultado["estado"] == att.SALIDA_AUN_NO
    assert resultado["mensaje"].endswith(
        "Entrada ya registrada. A partir de las 09:01 se habilita el horario de salida "
        "(10 minutos después de su entrada a las 08:50)")


# --- Informe ---

def test_informe_muestra_tardanza_junto_a_la_entrada():
    datos = DatosInforme(HOY, "Algoritmos", H_ENTRADA, H_SALIDA, "admin", [
        FilaAlumno("Pérez", "Ana", "1", "L1", en(10, 20), None, True),
        FilaAlumno("Gómez", "Luis", "2", "L2", en(10, 2), en(11, 56), False),
    ])
    filas = _filas_tabla(datos)
    assert filas[0][1:] == ["Gómez", "Luis", "2", "L2", "10:02", "11:56"]
    assert filas[1][1:] == ["Pérez", "Ana", "1", "L1", "10:20 (Tardanza)", "Sin registrar"]
