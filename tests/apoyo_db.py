"""Apoyo para las pruebas contra PostgreSQL (esquema real de database/initdb).

Se ejecutan solo si está definida ZEBRAGYM_TEST_DSN. Todo corre en un
esquema temporal (zg_prueba) dentro de una transacción que siempre termina
en rollback: no crea ni deja nada en la base. Las fixtures `base` y `db`
están en conftest.py."""
import os
from pathlib import Path

import pytest

DSN = os.getenv("ZEBRAGYM_TEST_DSN")
requiere_base = pytest.mark.skipif(not DSN, reason="ZEBRAGYM_TEST_DSN no definida")
INITDB = Path(__file__).resolve().parent.parent / "database" / "initdb"
HOY_AR = "(NOW() AT TIME ZONE 'America/Argentina/Buenos_Aires')::date"


class MismaConexion:
    """Hace que los repositorios usen la conexión de la prueba (sin commit)."""

    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self.conn

    def __exit__(self, *exc):
        return False


def falla(conn, error, sql, params=()):
    with pytest.raises(error):
        with conn.transaction():
            conn.execute(sql, params)


def valor(conn, sql, params=()):
    return conn.execute(sql, params).fetchone()[0]


def persona(conn, dni="30111222", nombre="Ana", apellido="Pérez"):
    return valor(conn, "INSERT INTO persona (dni, nombre, apellido) VALUES (%s,%s,%s) RETURNING id",
                 (dni, nombre, apellido))


def socio(conn, persona_id):
    return valor(conn, "INSERT INTO socio (persona_id, contacto_emergencia_telefono) "
                       "VALUES (%s, '388') RETURNING id", (persona_id,))


def usuario(conn, persona_id, nombre, roles=("entrenador",)):
    from services.auth_service import hashear_contrasenia
    uid = valor(conn, "INSERT INTO usuario (persona_id, nombre_usuario, contrasenia_hash) "
                      "VALUES (%s, %s, %s) RETURNING id",
                (persona_id, nombre, hashear_contrasenia("clave-segura")))
    for rol in roles:
        conn.execute("INSERT INTO usuario_rol (usuario_id, rol) VALUES (%s, %s)", (uid, rol))
    return uid


def membresia(conn, socio_id, plan="Pase libre", precio=100, desde=0, cupo=None):
    """Membresía que empieza `desde` días después de hoy (hora de Argentina) y
    vence en fecha_inicio + plan.vigencia, como la calcula la app."""
    return valor(conn, f"""
        INSERT INTO membresia (socio_id, plan_id, fecha_inicio, fecha_vencimiento, precio,
                               entrenamientos_mensuales, max_dias_semanales, max_ingresos_diarios)
        SELECT %s, id, h.d + %s, (h.d + %s + vigencia)::date, %s,
               COALESCE(%s, entrenamientos_mensuales), max_dias_semanales, max_ingresos_diarios
          FROM plan, (SELECT {HOY_AR} AS d) h
         WHERE nombre = %s RETURNING id""", (socio_id, desde, desde, precio, cupo, plan))


def acceso_permitido(conn, socio_id, membresia_id):
    conn.execute("INSERT INTO acceso (socio_id, membresia_id, resultado) VALUES (%s, %s, 'permitido')",
                 (socio_id, membresia_id))
