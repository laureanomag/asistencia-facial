from contextlib import contextmanager

import pytest

from services import auth_service as auth
from services.auth_service import (
    ADMINISTRADOR, ENTRENADOR, RECEPCIONISTA, AccesoDenegado, AuthService,
    ErrorAutenticacion, ReglaDeCuentas, Sesion, autorizar, hashear_contrasenia,
    verificar_contrasenia,
)


@pytest.fixture(autouse=True)
def bcrypt_rapido(monkeypatch):
    # Costo mínimo para que los tests no tarden; en la app se usa 12.
    monkeypatch.setattr(auth, "COSTO_BCRYPT", 4)


@contextmanager
def _sin_base():
    yield None


class _UsuariosFalsos:
    """Imita UserRepository en memoria (mismas columnas y valores de retorno)."""

    def __init__(self):
        self.usuarios = {}   # id -> dict
        self.roles = {}      # id -> set
        self.ingresos = []

    def agregar(self, nombre_usuario, contrasenia, roles, activo=True, debe_cambiar=False,
                persona=None):
        usuario_id = len(self.usuarios) + 1
        self.usuarios[usuario_id] = {
            "persona_id": persona and persona["id"], "nombre_usuario": nombre_usuario,
            "hash": hashear_contrasenia(contrasenia), "activo": activo,
            "debe_cambiar": debe_cambiar, "persona": persona,
        }
        self.roles[usuario_id] = set(roles)
        return usuario_id

    def buscar_para_login(self, identificador, conn=None):
        for uid, u in self.usuarios.items():
            dni = u["persona"] and u["persona"]["dni"]
            if u["nombre_usuario"].lower() == identificador.lower() or dni == identificador:
                p = u["persona"] or {}
                return (uid, u["persona_id"], u["nombre_usuario"], u["hash"], u["activo"],
                        u["debe_cambiar"], p.get("nombre"), p.get("apellido"))
        return None

    def obtener_por_id(self, usuario_id, conn=None):
        u = self.usuarios.get(usuario_id)
        if u is None:
            return None
        return (usuario_id, u["persona_id"], u["nombre_usuario"], u["hash"], u["activo"],
                u["debe_cambiar"])

    def obtener_por_persona(self, persona_id, conn=None):
        for uid, u in self.usuarios.items():
            if u["persona_id"] == persona_id:
                return (uid, u["nombre_usuario"], u["activo"])
        return None

    def obtener_roles(self, usuario_id, conn=None):
        return sorted(self.roles.get(usuario_id, ()))

    def registrar_ingreso(self, usuario_id, conn=None):
        self.ingresos.append(usuario_id)

    def actualizar_contrasenia(self, usuario_id, contrasenia_hash, debe_cambiar_contrasenia=False,
                               conn=None):
        self.usuarios[usuario_id]["hash"] = contrasenia_hash
        self.usuarios[usuario_id]["debe_cambiar"] = debe_cambiar_contrasenia
        return True

    def crear(self, persona_id, nombre_usuario, contrasenia_hash, debe_cambiar_contrasenia=True,
              conn=None):
        uid = len(self.usuarios) + 1
        self.usuarios[uid] = {"persona_id": persona_id, "nombre_usuario": nombre_usuario,
                              "hash": contrasenia_hash, "activo": True,
                              "debe_cambiar": debe_cambiar_contrasenia, "persona": None}
        self.roles[uid] = set()
        return uid

    def asignar_rol(self, usuario_id, rol_codigo, asignado_por_usuario_id=None, conn=None):
        nuevo = rol_codigo not in self.roles[usuario_id]
        self.roles[usuario_id].add(rol_codigo)
        return nuevo

    def quitar_rol(self, usuario_id, rol_codigo, conn=None):
        tenia = rol_codigo in self.roles[usuario_id]
        self.roles[usuario_id].discard(rol_codigo)
        return tenia

    def actualizar_estado(self, usuario_id, activo, conn=None):
        self.usuarios[usuario_id]["activo"] = activo
        return True

    def contar_activos_con_rol(self, rol_codigo, conn=None):
        return sum(1 for uid, u in self.usuarios.items()
                   if u["activo"] and rol_codigo in self.roles[uid])


ANA = {"id": 10, "dni": "30111222", "nombre": "Ana", "apellido": "Pérez"}


@pytest.fixture
def repo():
    r = _UsuariosFalsos()
    r.agregar("admin", "admin123", {ADMINISTRADOR}, debe_cambiar=True)
    r.agregar("ana", "clave-de-ana", {ENTRENADOR}, persona=ANA)
    r.agregar("rocio", "clave-rocio", {RECEPCIONISTA})
    return r


@pytest.fixture
def servicio(repo):
    return AuthService(repo, transaccion=_sin_base)


def _sesion(*roles, usuario_id=1):
    return Sesion(usuario_id, None, "x", "x", frozenset(roles))


# --- Contraseñas ---

def test_hash_bcrypt_nunca_guarda_texto_plano():
    h = hashear_contrasenia("secreta-123")
    assert h.startswith("$2") and "secreta-123" not in h
    assert verificar_contrasenia("secreta-123", h)
    assert not verificar_contrasenia("otra", h)


def test_acepta_hashes_con_prefijo_2a():
    # pgcrypto (02-seed.sql) genera hashes "$2a$"; el algoritmo es el mismo que
    # "$2b$". La verificación contra un hash real de PostgreSQL está en
    # test_esquema_db.py::test_seed_admin_valida_con_bcrypt.
    hash_2a = "$2a$" + hashear_contrasenia("admin123")[4:]
    assert verificar_contrasenia("admin123", hash_2a)
    assert not verificar_contrasenia("admin1234", hash_2a)


def test_hash_invalido_no_valida():
    assert not verificar_contrasenia("admin123", "admin123")   # texto plano heredado
    assert not verificar_contrasenia("admin123", None)


# --- Inicio de sesión ---

def test_login_por_nombre_de_usuario_sin_distinguir_mayusculas(servicio, repo):
    sesion = servicio.autenticar("ANA", "clave-de-ana")
    assert sesion.usuario_id == 2 and sesion.persona_id == 10
    assert sesion.nombre_mostrado == "Ana Pérez"
    assert sesion.roles == {ENTRENADOR}
    assert repo.ingresos == [2]


def test_login_por_dni_de_la_persona(servicio):
    assert servicio.autenticar("30111222", "clave-de-ana").nombre_usuario == "ana"


def test_admin_inicial_sin_persona_debe_cambiar_contrasenia(servicio):
    sesion = servicio.autenticar("admin", "admin123")
    assert sesion.persona_id is None and sesion.nombre_mostrado == "admin"
    assert sesion.debe_cambiar_contrasenia


@pytest.mark.parametrize("identificador, contrasenia", [
    ("ana", "incorrecta"), ("nadie", "clave-de-ana"), ("", "x"),
])
def test_credenciales_invalidas_dan_un_mensaje_generico(servicio, repo, identificador, contrasenia):
    with pytest.raises(ErrorAutenticacion, match="Usuario o contraseña incorrectos"):
        servicio.autenticar(identificador, contrasenia)
    assert repo.ingresos == []


def test_cuenta_inactiva_no_inicia_sesion(servicio, repo):
    repo.usuarios[2]["activo"] = False
    with pytest.raises(ErrorAutenticacion, match="Usuario o contraseña incorrectos"):
        servicio.autenticar("ana", "clave-de-ana")


def test_cuenta_sin_roles_no_inicia_sesion(servicio, repo):
    repo.roles[2] = set()
    with pytest.raises(ErrorAutenticacion, match="ningún rol"):
        servicio.autenticar("ana", "clave-de-ana")


def test_cambiar_contrasenia(servicio, repo):
    sesion = servicio.autenticar("admin", "admin123")
    nueva_sesion = servicio.cambiar_contrasenia(sesion, "admin123", "una-clave-larga")
    assert not nueva_sesion.debe_cambiar_contrasenia
    assert not repo.usuarios[1]["debe_cambiar"]
    assert servicio.autenticar("admin", "una-clave-larga").usuario_id == 1
    with pytest.raises(ErrorAutenticacion):
        servicio.autenticar("admin", "admin123")


@pytest.mark.parametrize("actual, nueva, error", [
    ("mal", "una-clave-larga", ErrorAutenticacion),
    ("admin123", "corta", ReglaDeCuentas),
    ("admin123", "admin123", ReglaDeCuentas),
])
def test_cambiar_contrasenia_rechaza(servicio, actual, nueva, error):
    sesion = servicio.autenticar("admin", "admin123")
    with pytest.raises(error):
        servicio.cambiar_contrasenia(sesion, actual, nueva)


# --- Matriz de permisos ---

MATRIZ_ESPERADA = {
    "usuario.administrar": "A",
    "configuracion.gestionar": "A",
    "jornada.gestionar": "A",
    "socio.registrar": "RE",
    "socio.editar": "RE",
    "socio.baja_reactivar": "A",
    "membresia.consultar": "ARE",
    "pago.registrar": "RE",
    "membresia.renovar": "RE",
    "acceso.operar_camara": "RE",
    "plan_entrenamiento.gestionar": "AE",
    "reporte.consultar": "A",
    "fichaje.consultar_propio": "ARE",
}
LETRAS = {"A": ADMINISTRADOR, "R": RECEPCIONISTA, "E": ENTRENADOR}


def test_matriz_de_permisos_es_la_aprobada():
    assert set(auth.MATRIZ_PERMISOS) == set(MATRIZ_ESPERADA)
    for permiso, letras in MATRIZ_ESPERADA.items():
        assert auth.MATRIZ_PERMISOS[permiso] == {LETRAS[l] for l in letras}, permiso


def test_recepcionista_no_administra_ni_configura():
    recepcion = _sesion(RECEPCIONISTA)
    for permiso in ("usuario.administrar", "configuracion.gestionar", "jornada.gestionar",
                    "socio.baja_reactivar", "reporte.consultar", "plan_entrenamiento.gestionar"):
        with pytest.raises(AccesoDenegado):
            autorizar(recepcion, permiso)
    for permiso in ("socio.registrar", "membresia.consultar", "pago.registrar",
                    "membresia.renovar"):
        autorizar(recepcion, permiso)


def test_entrenador_atiende_el_mostrador():
    # ZebraGym hoy no tiene recepcionista: el entrenador registra socios, cobra,
    # renueva y opera la cámara, pero no administra.
    entrenador = _sesion(ENTRENADOR)
    for permiso in ("socio.registrar", "socio.editar", "pago.registrar", "membresia.renovar",
                    "acceso.operar_camara", "plan_entrenamiento.gestionar"):
        assert entrenador.puede(permiso)
    for permiso in ("usuario.administrar", "socio.baja_reactivar", "reporte.consultar"):
        assert not entrenador.puede(permiso)


def test_varios_roles_suman_permisos():
    ambos = _sesion(ENTRENADOR, RECEPCIONISTA)
    assert ambos.puede("pago.registrar") and ambos.puede("plan_entrenamiento.gestionar")
    assert not ambos.puede("usuario.administrar")


def test_sin_sesion_se_deniega():
    with pytest.raises(AccesoDenegado):
        autorizar(None, "socio.registrar")


# --- Administración de cuentas ---

def test_crear_usuario_para_persona_existente(servicio, repo):
    admin = _sesion(ADMINISTRADOR)
    uid = servicio.crear_usuario(admin, 77, "lucas", "inicial-123", {ENTRENADOR, RECEPCIONISTA})
    assert repo.usuarios[uid]["persona_id"] == 77
    assert repo.usuarios[uid]["debe_cambiar"]
    assert repo.roles[uid] == {ENTRENADOR, RECEPCIONISTA}


@pytest.mark.parametrize("sesion", [_sesion(RECEPCIONISTA), _sesion(ENTRENADOR)])
def test_solo_el_administrador_crea_usuarios(servicio, sesion):
    with pytest.raises(AccesoDenegado):
        servicio.crear_usuario(sesion, 77, "lucas", "inicial-123", {ENTRENADOR})


@pytest.mark.parametrize("persona_id, nombre, roles, mensaje", [
    (10, "otra", {ENTRENADOR}, "ya tiene una cuenta"),
    (77, "lucas", set(), "al menos un rol"),
    (77, "lucas", {"duenio"}, "Rol inexistente"),
    (77, "  ", {ENTRENADOR}, "obligatorio"),
])
def test_crear_usuario_valida(servicio, persona_id, nombre, roles, mensaje):
    with pytest.raises(ReglaDeCuentas, match=mensaje):
        servicio.crear_usuario(_sesion(ADMINISTRADOR), persona_id, nombre, "inicial-123", roles)


def test_no_se_quita_el_ultimo_administrador(servicio, repo):
    admin = _sesion(ADMINISTRADOR)
    with pytest.raises(ReglaDeCuentas, match="sin un administrador"):
        servicio.quitar_rol(admin, 1, ADMINISTRADOR)
    with pytest.raises(ReglaDeCuentas, match="sin un administrador"):
        servicio.desactivar_usuario(admin, 1)
    assert ADMINISTRADOR in repo.roles[1] and repo.usuarios[1]["activo"]


def test_con_otro_administrador_si_se_puede_quitar(servicio, repo):
    repo.roles[2].add(ADMINISTRADOR)
    assert servicio.quitar_rol(_sesion(ADMINISTRADOR), 1, ADMINISTRADOR)
    assert repo.roles[1] == set()


def test_quitar_otro_rol_no_exige_administradores(servicio, repo):
    assert servicio.quitar_rol(_sesion(ADMINISTRADOR), 2, ENTRENADOR)


def test_asignar_rol_inexistente(servicio):
    with pytest.raises(ReglaDeCuentas):
        servicio.asignar_rol(_sesion(ADMINISTRADOR), 2, "socio")
