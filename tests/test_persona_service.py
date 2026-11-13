from contextlib import contextmanager
from datetime import date

import pytest

from services.auth_service import (
    ADMINISTRADOR, ENTRENADOR, RECEPCIONISTA, AccesoDenegado, Sesion,
)
from services.persona_service import (
    DatosInvalidos, PersonaService, SocioYaRegistrado, normalizar_dni,
)

FOTOS = {"frente": b"f", "perfil_izquierdo": b"i", "perfil_derecho": b"d"}
DATOS_ANA = {"dni": "30.111.222", "nombre": " Ana ", "apellido": "Pérez"}


@contextmanager
def _sin_base():
    yield None


class _PersonasFalsas:
    def __init__(self):
        self.personas = {}   # id -> datos
        self.fotos = {}      # (persona_id, angulo) -> bytes

    def crear(self, datos, conn=None):
        pid = len(self.personas) + 1
        self.personas[pid] = dict(datos)
        return pid

    def obtener_por_dni(self, dni, conn=None):
        for pid, d in self.personas.items():
            if d["dni"] == dni:
                return (pid, dni, d["nombre"], d["apellido"], None, None, None, None)
        return None

    def guardar_fotos(self, persona_id, fotos, conn=None):
        for angulo, imagen in fotos.items():
            self.fotos[(persona_id, angulo)] = imagen   # upsert: una por ángulo

    def contar_fotos(self, persona_id, conn=None):
        return sum(1 for (pid, _a) in self.fotos if pid == persona_id)

    def obtener_roles(self, persona_id, conn=None):
        return {"persona_id": persona_id}


class _SociosFalsos:
    def __init__(self):
        self.socios = {}   # id -> dict

    def crear(self, persona_id, contacto_emergencia_telefono, contacto_emergencia_nombre=None,
              registrado_por_usuario_id=None, conn=None):
        sid = len(self.socios) + 1
        self.socios[sid] = {"persona_id": persona_id, "tel": contacto_emergencia_telefono,
                            "activo": True, "fecha_baja": None,
                            "registrado_por": registrado_por_usuario_id}
        return sid

    def obtener_por_persona(self, persona_id, conn=None):
        for sid, s in self.socios.items():
            if s["persona_id"] == persona_id:
                return (sid, persona_id, None, s["tel"], None, s["activo"], s["fecha_baja"],
                        s["registrado_por"])
        return None

    def dar_baja(self, socio_id, fecha_baja, conn=None):
        s = self.socios[socio_id]
        if not s["activo"]:
            return False
        s["activo"], s["fecha_baja"] = False, fecha_baja
        return True

    def reactivar(self, socio_id, conn=None):
        s = self.socios[socio_id]
        if s["activo"]:
            return False
        s["activo"], s["fecha_baja"] = True, None
        return True


def _sesion(*roles, usuario_id=5):
    return Sesion(usuario_id, None, "x", "x", frozenset(roles))


@pytest.fixture
def personas():
    return _PersonasFalsas()


@pytest.fixture
def socios():
    return _SociosFalsos()


@pytest.fixture
def servicio(personas, socios):
    return PersonaService(personas, socios, transaccion=_sin_base)


# --- DNI ---

@pytest.mark.parametrize("entrada, esperado", [
    ("30.111.222", "30111222"), (" 30 111 222 ", "30111222"), ("1234567", "1234567"),
])
def test_normalizar_dni(entrada, esperado):
    assert normalizar_dni(entrada) == esperado


@pytest.mark.parametrize("entrada", ["", None, "123456", "123456789", "30A11222"])
def test_dni_invalido(entrada):
    with pytest.raises(DatosInvalidos):
        normalizar_dni(entrada)


# --- Registro de socios ---

@pytest.mark.parametrize("rol", [RECEPCIONISTA, ENTRENADOR])
def test_registrar_socio_nuevo(servicio, personas, socios, rol):
    r = servicio.registrar_socio(_sesion(rol), DATOS_ANA, FOTOS, "388-4000000", "Juan Pérez")
    assert not r.persona_reutilizada and r.fotos_guardadas == 3
    assert personas.personas[r.persona_id]["dni"] == "30111222"
    assert socios.socios[r.socio_id]["registrado_por"] == 5
    assert personas.contar_fotos(r.persona_id) == 3


def test_entrenador_existente_se_registra_como_socio_sin_duplicarse(servicio, personas, socios):
    # Ana ya existe como persona (por ejemplo, es entrenadora) con su perfil facial.
    pid = personas.crear({"dni": "30111222", "nombre": "Ana", "apellido": "Pérez"})
    personas.guardar_fotos(pid, FOTOS)

    r = servicio.registrar_socio(_sesion(RECEPCIONISTA),
                                 {"dni": "30111222", "nombre": "Otro", "apellido": "Nombre"},
                                 {}, "388-4000000")

    assert r.persona_reutilizada and r.persona_id == pid
    assert len(personas.personas) == 1                    # no se duplicó la persona
    assert personas.personas[pid]["nombre"] == "Ana"      # ni se pisaron sus datos
    assert personas.contar_fotos(pid) == 3                # ni sus fotos
    assert socios.socios[r.socio_id]["persona_id"] == pid


def test_persona_existente_reemplaza_solo_el_angulo_recibido(servicio, personas):
    pid = personas.crear({"dni": "30111222", "nombre": "Ana", "apellido": "Pérez"})
    personas.guardar_fotos(pid, FOTOS)
    servicio.registrar_socio(_sesion(ENTRENADOR), DATOS_ANA, {"frente": b"nueva"}, "388")
    assert personas.contar_fotos(pid) == 3
    assert personas.fotos[(pid, "frente")] == b"nueva"


def test_ya_socio_no_se_registra_dos_veces(servicio):
    servicio.registrar_socio(_sesion(RECEPCIONISTA), DATOS_ANA, FOTOS, "388")
    with pytest.raises(SocioYaRegistrado, match="activo"):
        servicio.registrar_socio(_sesion(RECEPCIONISTA), DATOS_ANA, FOTOS, "388")


def test_socio_dado_de_baja_se_reactiva_no_se_registra(servicio):
    r = servicio.registrar_socio(_sesion(RECEPCIONISTA), DATOS_ANA, FOTOS, "388")
    servicio.dar_baja_socio(_sesion(ADMINISTRADOR), r.socio_id)
    with pytest.raises(SocioYaRegistrado, match="reactivarse"):
        servicio.registrar_socio(_sesion(RECEPCIONISTA), DATOS_ANA, FOTOS, "388")


@pytest.mark.parametrize("datos, fotos, telefono, mensaje", [
    ({**DATOS_ANA, "nombre": " "}, FOTOS, "388", "nombre"),
    ({**DATOS_ANA, "dni": "12"}, FOTOS, "388", "DNI"),
    (DATOS_ANA, FOTOS, "  ", "emergencia"),
    (DATOS_ANA, {"frente": b"f"}, "388", "3 fotos"),
    (DATOS_ANA, {**FOTOS, "nuca": b"n"}, "388", "Ángulo"),
])
def test_registrar_socio_valida(servicio, personas, datos, fotos, telefono, mensaje):
    with pytest.raises(DatosInvalidos, match=mensaje):
        servicio.registrar_socio(_sesion(RECEPCIONISTA), datos, fotos, telefono)
    assert personas.personas == {}


def test_persona_existente_sin_fotos_necesita_perfil(servicio, personas):
    personas.crear({"dni": "30111222", "nombre": "Ana", "apellido": "Pérez"})
    with pytest.raises(DatosInvalidos, match="perfil facial"):
        servicio.registrar_socio(_sesion(RECEPCIONISTA), DATOS_ANA, {}, "388")


def test_registrar_socio_requiere_permiso(servicio):
    with pytest.raises(AccesoDenegado):
        servicio.registrar_socio(_sesion(), DATOS_ANA, FOTOS, "388")


def test_la_duenia_no_registra_socios(servicio):
    with pytest.raises(AccesoDenegado):
        servicio.registrar_socio(_sesion(ADMINISTRADOR), DATOS_ANA, FOTOS, "388")


# --- Baja y reactivación ---

def test_baja_y_reactivacion_conservan_la_persona(servicio, personas, socios):
    r = servicio.registrar_socio(_sesion(RECEPCIONISTA), DATOS_ANA, FOTOS, "388")
    admin = _sesion(ADMINISTRADOR)

    assert servicio.dar_baja_socio(admin, r.socio_id, date(2026, 11, 12))
    assert socios.socios[r.socio_id]["fecha_baja"] == date(2026, 11, 12)
    assert not servicio.dar_baja_socio(admin, r.socio_id)          # ya estaba de baja

    assert servicio.reactivar_socio(admin, r.socio_id)
    assert socios.socios[r.socio_id]["activo"] and socios.socios[r.socio_id]["fecha_baja"] is None
    assert len(personas.personas) == 1 and personas.contar_fotos(r.persona_id) == 3


@pytest.mark.parametrize("rol", [RECEPCIONISTA, ENTRENADOR])
def test_solo_el_administrador_da_de_baja(servicio, rol):
    r = servicio.registrar_socio(_sesion(RECEPCIONISTA), DATOS_ANA, FOTOS, "388")
    with pytest.raises(AccesoDenegado):
        servicio.dar_baja_socio(_sesion(rol), r.socio_id)
    with pytest.raises(AccesoDenegado):
        servicio.reactivar_socio(_sesion(rol), r.socio_id)
