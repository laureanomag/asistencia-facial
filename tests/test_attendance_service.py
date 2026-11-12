from datetime import date, datetime, time, timedelta

import pytest

from services import attendance_service as att
from services.attendance_service import AttendanceService
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


# --- Informe ---

def test_informe_muestra_tardanza_junto_a_la_entrada():
    datos = DatosInforme(HOY, "Algoritmos", H_ENTRADA, H_SALIDA, "admin", [
        FilaAlumno("Pérez", "Ana", "1", "L1", en(10, 20), None, True),
        FilaAlumno("Gómez", "Luis", "2", "L2", en(10, 2), en(11, 56), False),
    ])
    filas = _filas_tabla(datos)
    assert filas[0][1:] == ["Gómez", "Luis", "2", "L2", "10:02", "11:56"]
    assert filas[1][1:] == ["Pérez", "Ana", "1", "L1", "10:20 (Tardanza)", "Sin registrar"]
