"""Pruebas del esquema real (database/initdb/01-schema.sql + 02-seed.sql) en PostgreSQL.

Se ejecutan solo si está definida la variable ZEBRAGYM_TEST_DSN, por ejemplo:
    ZEBRAGYM_TEST_DSN="host=localhost port=5432 dbname=asistencia_gimnasio user=admin password=..."
Todo corre dentro de un esquema temporal (zg_prueba) en una transacción que
SIEMPRE termina en rollback: no crea ni deja nada en la base."""
import os
from datetime import date
from pathlib import Path

import pytest

psycopg = pytest.importorskip("psycopg")
from psycopg import errors  # noqa: E402

DSN = os.getenv("ZEBRAGYM_TEST_DSN")
pytestmark = pytest.mark.skipif(not DSN, reason="ZEBRAGYM_TEST_DSN no definida")

INITDB = Path(__file__).resolve().parent.parent / "database" / "initdb"


class _MismaConexion:
    """Hace que los repositorios usen la conexión de la prueba (sin commit)."""

    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self.conn

    def __exit__(self, *exc):
        return False


@pytest.fixture(scope="module")
def base():
    with psycopg.connect(DSN, autocommit=True) as conn:
        with conn.transaction(force_rollback=True):
            conn.execute("CREATE SCHEMA zg_prueba")
            conn.execute("SET LOCAL search_path TO zg_prueba, public")
            conn.execute((INITDB / "01-schema.sql").read_text(encoding="utf-8"))
            conn.execute((INITDB / "02-seed.sql").read_text(encoding="utf-8"))
            yield conn


@pytest.fixture
def db(base, monkeypatch):
    from config import database
    monkeypatch.setattr(database, "get_connection", lambda: _MismaConexion(base))
    with base.transaction(force_rollback=True):
        yield base


def _falla(conn, error, sql, params=()):
    with pytest.raises(error):
        with conn.transaction():
            conn.execute(sql, params)


def _valor(conn, sql, params=()):
    return conn.execute(sql, params).fetchone()[0]


def _persona(conn, dni="30111222", nombre="Ana", apellido="Pérez"):
    return _valor(conn, "INSERT INTO persona (dni, nombre, apellido) VALUES (%s,%s,%s) RETURNING id",
                  (dni, nombre, apellido))


def _socio(conn, persona_id):
    return _valor(conn, "INSERT INTO socio (persona_id, contacto_emergencia_telefono) "
                        "VALUES (%s, '388') RETURNING id", (persona_id,))


def _usuario(conn, persona_id, nombre, roles=("entrenador",)):
    from services.auth_service import hashear_contrasenia
    uid = _valor(conn, "INSERT INTO usuario (persona_id, nombre_usuario, contrasenia_hash) "
                       "VALUES (%s, %s, %s) RETURNING id",
                 (persona_id, nombre, hashear_contrasenia("clave-segura")))
    for rol in roles:
        conn.execute("INSERT INTO usuario_rol (usuario_id, rol) VALUES (%s, %s)", (uid, rol))
    return uid


def _membresia(conn, socio_id, plan="Pase libre", precio=100, desde=0, cupo=None):
    """Membresía que empieza `desde` días después de hoy (hora de Argentina) y
    vence en fecha_inicio + plan.vigencia, como la calcula la app."""
    return _valor(conn, """
        INSERT INTO membresia (socio_id, plan_id, fecha_inicio, fecha_vencimiento, precio,
                               entrenamientos_mensuales, max_dias_semanales, max_ingresos_diarios)
        SELECT %s, id, h.d + %s, (h.d + %s + vigencia)::date, %s,
               COALESCE(%s, entrenamientos_mensuales), max_dias_semanales, max_ingresos_diarios
          FROM plan,
               (SELECT (NOW() AT TIME ZONE 'America/Argentina/Buenos_Aires')::date AS d) h
         WHERE nombre = %s RETURNING id""", (socio_id, desde, desde, precio, cupo, plan))


def _acceso_permitido(conn, socio_id, membresia_id):
    conn.execute("INSERT INTO acceso (socio_id, membresia_id, resultado) VALUES (%s, %s, 'permitido')",
                 (socio_id, membresia_id))


# --- Datos iniciales ---

def test_seed_roles_planes_y_horarios(db):
    tablas = [r[0] for r in db.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'zg_prueba' AND table_type = 'BASE TABLE' ORDER BY table_name")]
    assert len(tablas) == 14 and "rol" not in tablas and "dia_especial" not in tablas
    roles_admin = [r[0] for r in db.execute(
        "SELECT ur.rol FROM usuario_rol ur JOIN usuario u ON u.id = ur.usuario_id "
        "WHERE u.nombre_usuario = 'admin'")]
    assert roles_admin == ["administrador"]
    planes = db.execute("""
        SELECT nombre, vigencia = INTERVAL '1 month', vigencia = INTERVAL '1 day',
               max_ingresos_diarios, max_dias_semanales, entrenamientos_mensuales
          FROM plan ORDER BY nombre""").fetchall()
    assert planes == [
        ("3 veces por semana", True, False, None, 3, None),
        ("Pase libre", True, False, None, None, None),
        ("Pase por día", False, True, 1, None, None),
    ]
    assert _valor(db, "SELECT COUNT(*) FROM horario_atencion WHERE dia_semana = 7") == 0
    # Mensualidad: un mes calendario exacto (20/10 -> 20/11; 31/01 -> 28/02).
    assert _valor(db, "SELECT ('2026-10-20'::date + INTERVAL '1 month')::date") == date(2026, 11, 20)
    assert _valor(db, "SELECT ('2027-01-31'::date + INTERVAL '1 month')::date") == date(2027, 2, 28)


def test_seed_admin_valida_con_bcrypt(db):
    from services.auth_service import verificar_contrasenia
    persona_id, hash_, debe_cambiar = db.execute(
        "SELECT persona_id, contrasenia_hash, debe_cambiar_contrasenia FROM usuario "
        "WHERE nombre_usuario = 'admin'").fetchone()
    assert persona_id is None and debe_cambiar
    assert hash_.startswith("$2") and verificar_contrasenia("admin123", hash_)


def test_login_del_admin_de_punta_a_punta(db):
    from services.auth_service import ADMINISTRADOR, AuthService
    sesion = AuthService().autenticar("ADMIN", "admin123")
    assert sesion.roles == {ADMINISTRADOR} and sesion.debe_cambiar_contrasenia
    assert _valor(db, "SELECT ultimo_acceso IS NOT NULL FROM usuario WHERE id = %s",
                  (sesion.usuario_id,))


# --- Identidad única y multirrol ---

def test_dni_unico_y_con_formato(db):
    _persona(db)
    _falla(db, errors.UniqueViolation, "INSERT INTO persona (dni, nombre, apellido) "
                                       "VALUES ('30111222', 'Otra', 'Persona')")
    _falla(db, errors.CheckViolation, "INSERT INTO persona (dni, nombre, apellido) "
                                      "VALUES ('30.111.2', 'Otra', 'Persona')")


def test_socio_y_entrenador_son_la_misma_persona(db):
    from repositories.person_repository import PersonRepository
    pid = _persona(db)
    socio_id = _socio(db, pid)
    usuario_id = _usuario(db, pid, "ana", ("entrenador", "recepcionista"))

    roles = PersonRepository().obtener_roles(pid)
    assert roles == {"socio_id": socio_id, "socio_activo": True, "usuario_id": usuario_id,
                     "usuario_activo": True, "roles": ["entrenador", "recepcionista"]}
    _falla(db, errors.UniqueViolation, "INSERT INTO socio (persona_id, contacto_emergencia_telefono) "
                                       "VALUES (%s, '1')", (pid,))
    _falla(db, errors.UniqueViolation, "INSERT INTO usuario (persona_id, nombre_usuario, contrasenia_hash) "
                                       "VALUES (%s, 'ana2', 'x')", (pid,))


def test_registrar_como_socio_a_un_entrenador_reutiliza_la_persona(db):
    from services.auth_service import Sesion
    from services.persona_service import PersonaService
    pid = _persona(db)
    _usuario(db, pid, "ana")
    db.execute("INSERT INTO foto_persona (persona_id, angulo, imagen) VALUES "
               "(%s,'frente','\\x01'), (%s,'perfil_izquierdo','\\x02'), (%s,'perfil_derecho','\\x03')",
               (pid, pid, pid))
    recepcion = Sesion(1, None, "admin", "admin", frozenset({"recepcionista"}))

    r = PersonaService().registrar_socio(recepcion, {"dni": "30.111.222", "nombre": "X",
                                                     "apellido": "Y"}, {}, "388")
    assert r.persona_reutilizada and r.persona_id == pid
    assert _valor(db, "SELECT COUNT(*) FROM persona") == 1
    assert _valor(db, "SELECT COUNT(*) FROM foto_persona WHERE persona_id = %s", (pid,)) == 3


def test_login_por_dni_de_la_persona(db):
    from repositories.user_repository import UserRepository
    pid = _persona(db)
    uid = _usuario(db, pid, "ana")
    fila = UserRepository().buscar_para_login("30111222")
    assert fila[0] == uid and fila[6:] == ("Ana", "Pérez")


def test_nombre_de_usuario_unico_sin_distinguir_mayusculas(db):
    _falla(db, errors.UniqueViolation, "INSERT INTO usuario (nombre_usuario, contrasenia_hash) "
                                       "VALUES ('Admin', 'x')")


def test_rol_repetido_o_inexistente(db):
    uid = _usuario(db, _persona(db), "ana")
    _falla(db, errors.UniqueViolation, "INSERT INTO usuario_rol (usuario_id, rol) "
                                       "VALUES (%s, 'entrenador')", (uid,))
    for rol in ("duenio", "socio", "profesor"):
        _falla(db, errors.CheckViolation, "INSERT INTO usuario_rol (usuario_id, rol) "
                                          "VALUES (%s, %s)", (uid, rol))


def test_roles_de_cuenta_con_user_repository(db):
    from repositories.user_repository import UserRepository
    repo = UserRepository()
    uid = _usuario(db, _persona(db), "ana", ())
    assert repo.asignar_rol(uid, "entrenador") and not repo.asignar_rol(uid, "entrenador")
    assert repo.asignar_rol(uid, "recepcionista")
    assert repo.obtener_roles(uid) == ["entrenador", "recepcionista"]
    assert repo.quitar_rol(uid, "recepcionista") and not repo.quitar_rol(uid, "recepcionista")
    assert repo.contar_activos_con_rol("administrador") == 1      # el admin del seed
    assert repo.contar_activos_con_rol("entrenador") == 1


# --- Perfil facial ---

def test_una_foto_por_angulo_y_upsert(db):
    from repositories.person_repository import PersonRepository
    pid = _persona(db)
    repo = PersonRepository()
    repo.guardar_fotos(pid, {"frente": b"a", "perfil_izquierdo": b"b", "perfil_derecho": b"c"})
    repo.guardar_fotos(pid, {"frente": b"nueva"})
    assert repo.contar_fotos(pid) == 3
    assert bytes(_valor(db, "SELECT imagen FROM foto_persona WHERE persona_id = %s "
                            "AND angulo = 'frente'", (pid,))) == b"nueva"
    _falla(db, errors.UniqueViolation, "INSERT INTO foto_persona (persona_id, angulo, imagen) "
                                       "VALUES (%s, 'frente', '\\x00')", (pid,))
    _falla(db, errors.CheckViolation, "INSERT INTO foto_persona (persona_id, angulo, imagen) "
                                      "VALUES (%s, 'nuca', '\\x00')", (pid,))


def test_referencias_incluyen_socios_dados_de_baja(db):
    from repositories.person_repository import PersonRepository
    pid = _persona(db)
    socio_id = _socio(db, pid)
    db.execute("INSERT INTO foto_persona (persona_id, angulo, imagen) VALUES (%s, 'frente', '\\x01')",
               (pid,))
    db.execute("UPDATE socio SET activo = FALSE, fecha_baja = CURRENT_DATE WHERE id = %s", (socio_id,))
    filas = PersonRepository().obtener_referencias()
    assert [(f[0], f[1], f[2], f[3]) for f in filas] == [(pid, "Pérez", "Ana", "frente")]


# --- Baja y reactivación ---

def test_baja_coherente_y_reactivacion(db):
    from repositories.socio_repository import SocioRepository
    pid = _persona(db)
    socio_id = _socio(db, pid)
    _falla(db, errors.CheckViolation, "UPDATE socio SET activo = FALSE WHERE id = %s", (socio_id,))

    repo = SocioRepository()
    assert repo.dar_baja(socio_id, "2026-11-12") and not repo.dar_baja(socio_id, "2026-11-12")
    assert repo.reactivar(socio_id)
    assert repo.obtener_por_id(socio_id)[5:7] == (True, None)
    assert _valor(db, "SELECT COUNT(*) FROM persona WHERE id = %s", (pid,)) == 1


def test_no_se_borra_una_persona_con_relaciones(db):
    pid = _persona(db)
    _socio(db, pid)
    _falla(db, errors.ForeignKeyViolation, "DELETE FROM persona WHERE id = %s", (pid,))


# --- Coherencia de accesos y fichajes ---

def test_acceso_con_membresia_de_otro_socio(db):
    socio_ana = _socio(db, _persona(db))
    socio_luis = _socio(db, _persona(db, "20333444", "Luis", "Gómez"))
    m_ana = _membresia(db, socio_ana)
    _falla(db, errors.ForeignKeyViolation,
           "INSERT INTO acceso (socio_id, membresia_id, resultado) VALUES (%s, %s, 'permitido')",
           (socio_luis, m_ana))
    db.execute("INSERT INTO acceso (socio_id, membresia_id, resultado) VALUES (%s, %s, 'permitido')",
               (socio_ana, m_ana))


def test_acceso_coherente(db):
    socio_id = _socio(db, _persona(db))
    _falla(db, errors.CheckViolation,
           "INSERT INTO acceso (socio_id, resultado) VALUES (%s, 'permitido')", (socio_id,))
    _falla(db, errors.CheckViolation,
           "INSERT INTO acceso (socio_id, resultado) VALUES (%s, 'rechazado')", (socio_id,))
    _falla(db, errors.CheckViolation, "INSERT INTO acceso (socio_id, resultado, motivo_rechazo) "
                                      "VALUES (%s, 'rechazado', 'fuera_de_horario')", (socio_id,))
    db.execute("INSERT INTO acceso (resultado, motivo_rechazo) VALUES ('rechazado', 'no_reconocido')")
    for motivo in ("no_es_socio", "membresia_no_vigente", "gimnasio_cerrado"):
        db.execute("INSERT INTO acceso (socio_id, resultado, motivo_rechazo) "
                   "VALUES (%s, 'rechazado', %s)", (socio_id, motivo))


def test_membresia_vence_despues_de_empezar(db):
    socio_id = _socio(db, _persona(db))
    _falla(db, errors.CheckViolation, """
        INSERT INTO membresia (socio_id, plan_id, fecha_inicio, fecha_vencimiento, precio)
        SELECT %s, id, '2026-11-12', '2026-11-12', 0 FROM plan WHERE nombre = 'Pase libre'""",
           (socio_id,))


def test_un_solo_fichaje_abierto_y_jornada_del_mismo_usuario(db):
    ana = _usuario(db, _persona(db), "ana")
    luis = _usuario(db, _persona(db, "20333444", "Luis", "Gómez"), "luis")
    jornada_luis = _valor(db, "INSERT INTO jornada (usuario_id, fecha, horario_entrada, horario_salida) "
                              "VALUES (%s, CURRENT_DATE, '10:00', '14:00') RETURNING id", (luis,))
    _falla(db, errors.ForeignKeyViolation,
           "INSERT INTO fichaje (usuario_id, jornada_id) VALUES (%s, %s)", (ana, jornada_luis))
    db.execute("INSERT INTO fichaje (usuario_id) VALUES (%s)", (ana,))
    _falla(db, errors.UniqueViolation, "INSERT INTO fichaje (usuario_id) VALUES (%s)", (ana,))


# --- Vista de estado ---

def test_v_socio_estado(db):
    from repositories.socio_repository import SocioRepository
    repo = SocioRepository()
    nuevo = lambda dni: _socio(db, _persona(db, dni, "N" + dni, "A" + dni))  # noqa: E731

    # Sin membresía
    s = nuevo("10000001")
    e = repo.obtener_estado(s)
    assert (e["estado_membresia"], e["estado_contable"], e["plan"]) == ("sin_membresia", "sin_pase", None)

    # Pagada y vigente, con renovación futura cargada: la actual es la vigente
    s = nuevo("10000002")
    vigente = _membresia(db, s, precio=100)
    db.execute("INSERT INTO pago (membresia_id, monto, metodo) VALUES (%s, 100, 'efectivo')", (vigente,))
    _membresia(db, s, precio=100, desde=31)
    _acceso_permitido(db, s, vigente)
    e = repo.obtener_estado(s)
    assert e["membresia_id"] == vigente and e["plan"] == "Pase libre"
    assert (e["estado_membresia"], e["estado_contable"], e["saldo"]) == ("vigente", "al_dia", 0)
    assert (e["accesos_usados"], e["accesos_hoy"], e["accesos_incluidos"], e["accesos_restantes"]) == \
        (1, 1, None, None)                                           # pase libre: sin cupo

    # Impaga
    s = nuevo("10000003")
    _membresia(db, s, precio=100)
    assert repo.obtener_estado(s)["estado_contable"] == "debe"

    # Vence hoy: el día del vencimiento ya no es vigente
    s = nuevo("10000004")
    m = _membresia(db, s, precio=0, desde=-1, plan="Pase por día")
    e = repo.obtener_estado(s)
    assert e["membresia_id"] == m and e["dias_para_vencer"] == 0
    assert (e["estado_membresia"], e["estado_contable"]) == ("vencida", "debe")

    # Empieza mañana
    s = nuevo("10000005")
    _membresia(db, s, precio=0, desde=1)
    assert repo.obtener_estado(s)["estado_membresia"] == "no_vigente"

    # Cupo agotado
    s = nuevo("10000006")
    m = _membresia(db, s, precio=0, cupo=1)
    _acceso_permitido(db, s, m)
    e = repo.obtener_estado(s)
    assert (e["accesos_incluidos"], e["accesos_restantes"], e["estado_membresia"]) == (1, 0, "agotada")

    # Dado de baja: no aparece
    db.execute("UPDATE socio SET activo = FALSE, fecha_baja = CURRENT_DATE WHERE id = %s", (s,))
    assert repo.obtener_estado(s) is None
