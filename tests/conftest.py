import os
import sys

import pytest

# Los módulos del proyecto se importan como en la app: desde src/.
SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)


@pytest.fixture(scope="session")
def base():
    """Esquema real (01-schema.sql + 02-seed.sql) cargado en zg_prueba dentro
    de una transacción que termina en rollback. Ver tests/apoyo_db.py."""
    from apoyo_db import DSN, INITDB
    if not DSN:
        pytest.skip("ZEBRAGYM_TEST_DSN no definida")
    import psycopg
    with psycopg.connect(DSN, autocommit=True) as conn:
        with conn.transaction(force_rollback=True):
            conn.execute("CREATE SCHEMA zg_prueba")
            conn.execute("SET LOCAL search_path TO zg_prueba, public")
            conn.execute((INITDB / "01-schema.sql").read_text(encoding="utf-8"))
            conn.execute((INITDB / "02-seed.sql").read_text(encoding="utf-8"))
            yield conn


@pytest.fixture
def db(base, monkeypatch):
    """Cada prueba en su propio savepoint: lo que inserta se descarta al terminar.
    Los repositorios usan esta misma conexión (sin abrir otra ni hacer commit)."""
    from apoyo_db import MismaConexion
    from config import database
    monkeypatch.setattr(database, "get_connection", lambda: MismaConexion(base))
    with base.transaction(force_rollback=True):
        yield base
