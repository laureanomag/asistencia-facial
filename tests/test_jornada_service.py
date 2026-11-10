from datetime import date, datetime, time, timedelta

import pytest

from services.jornada_service import JornadaService

HOY = date(2026, 11, 9)


class JornadaRepoFalso:
    def __init__(self):
        self.datos = (1, HOY, "IA", time(10, 0), time(12, 0))
        self.actualizaciones = 0

    def obtener_de_usuario(self, jornada_id, usuario_id):
        return self.datos

    def actualizar(self, jornada_id, usuario_id, entrada, salida, catedra):
        self.datos = (jornada_id, HOY, catedra, entrada, salida)
        self.actualizaciones += 1
        return True


class AsistenciaRepoFalso:
    def __init__(self):
        self.limites = []

    def recalcular_tardanzas(self, jornada_id, limite):
        self.limites.append(limite)
        return 1


@pytest.fixture
def repos():
    return JornadaRepoFalso(), AsistenciaRepoFalso()


def test_cambiar_la_entrada_recalcula_tardanzas(repos):
    j, a = repos
    JornadaService(j, a).actualizar(1, 1, time(10, 30), time(12, 0), "IA")
    assert a.limites == [datetime.combine(HOY, time(10, 30)) + timedelta(minutes=10)]


def test_cambiar_solo_la_salida_o_la_catedra_no_recalcula(repos):
    j, a = repos
    JornadaService(j, a).actualizar(1, 1, time(10, 0), time(12, 30), "Otra")
    assert a.limites == []


def test_entrada_posterior_a_la_salida_se_rechaza(repos):
    j, a = repos
    with pytest.raises(ValueError):
        JornadaService(j, a).actualizar(1, 1, time(12, 0), time(10, 0), "IA")
    assert j.actualizaciones == 0 and a.limites == []


def test_acepta_horarios_como_texto(repos):
    j, a = repos
    JornadaService(j, a).actualizar(1, 1, "10:30", "12:00", "IA")
    assert j.datos[3] == time(10, 30)
    assert len(a.limites) == 1


def test_jornada_ajena_o_inexistente(repos):
    j, a = repos
    j.obtener_de_usuario = lambda *_args: None
    with pytest.raises(LookupError):
        JornadaService(j, a).actualizar(1, 1, time(10, 0), time(12, 0), "IA")
    assert j.actualizaciones == 0