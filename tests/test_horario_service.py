from datetime import datetime, time

import pytest

from services.horario_service import (
    HorarioService, estado_apertura, fecha_hora_titulo, hora_compacta, resumen_horario,
)
from services.reglas_ingreso import Franja

SEMANA = {d: [Franja(time(7, 30), time(23, 0))] for d in range(1, 6)}
SEMANA[6] = [Franja(time(10, 0), time(14, 0))]


def en(dia, hora, minuto=0):
    # 9/11/2026 es lunes: dia 1..7 -> 9..15 de noviembre
    return datetime(2026, 11, 8 + dia, hora, minuto)


def test_hora_compacta():
    assert (hora_compacta(time(7, 30)), hora_compacta(time(23, 0))) == ("7:30", "23")


def test_resumen_horario_del_gimnasio():
    assert resumen_horario(SEMANA) == "Lun a Vie 7:30–23 · Sáb 10–14"


def test_resumen_con_dias_sueltos_y_franjas_partidas():
    semana = {1: [Franja(time(16, 0), time(22, 0)), Franja(time(7, 0), time(12, 0))],
              2: [Franja(time(7, 0), time(12, 0)), Franja(time(16, 0), time(22, 0))],
              4: [Franja(time(9, 0), time(13, 0))]}
    assert resumen_horario(semana) == "Lun y Mar 7–12 y 16–22 · Jue 9–13"
    assert resumen_horario({}) == ""


@pytest.mark.parametrize("momento, esperado", [
    (en(4, 18, 42), (True, "Abierto · cierra a las 23:00")),
    (en(4, 7, 0), (False, "Cerrado · abre hoy a las 07:30")),
    (en(4, 23, 0), (False, "Cerrado · abre mañana a las 07:30")),
    (en(5, 23, 30), (False, "Cerrado · abre mañana a las 10:00")),
    (en(6, 14, 0), (False, "Cerrado · abre el lunes a las 07:30")),
    (en(7, 11, 0), (False, "Cerrado · abre mañana a las 07:30")),
    (en(6, 10, 0), (True, "Abierto · cierra a las 14:00")),
])
def test_estado_apertura(momento, esperado):
    assert estado_apertura(SEMANA, momento) == esperado


def test_sin_horario_cargado():
    assert estado_apertura({}, en(1, 10)) == (False, "Cerrado")


def test_fecha_hora_titulo():
    assert fecha_hora_titulo(datetime(2026, 11, 12, 18, 42)) == "Jueves 12/11 · 18:42"


class _RepoFalso:
    def listar(self, conn=None):
        return [(1, 1, time(7, 30), time(23, 0), True),
                (2, 6, time(10, 0), time(14, 0), True),
                (3, 6, time(16, 0), time(18, 0), False)]   # franja dada de baja

    def ahora(self, conn=None):
        return en(6, 15, 0)


def test_servicio_usa_solo_franjas_activas():
    servicio = HorarioService(_RepoFalso())
    assert servicio.franjas_semana() == {1: [Franja(time(7, 30), time(23, 0))],
                                         6: [Franja(time(10, 0), time(14, 0))]}
    assert servicio.estado_actual() == (False, "Cerrado · abre el lunes a las 07:30", en(6, 15, 0))
