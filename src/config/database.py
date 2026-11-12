import os
from contextlib import contextmanager

import psycopg
from dotenv import load_dotenv

load_dotenv()


def get_connection():
    return psycopg.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=os.getenv("POSTGRES_PORT"),
        dbname=os.getenv("POSTGRES_DB"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
    )


@contextmanager
def usar_conexion(conn=None):
    """Usa la conexión recibida (así varias operaciones comparten una misma
    transacción) o abre una nueva, que hace commit al salir sin errores y
    rollback si hubo una excepción."""
    if conn is not None:
        yield conn
        return
    with get_connection() as nueva:
        yield nueva
