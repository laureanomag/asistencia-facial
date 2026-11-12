"""Repositorios de membresía, pago, acceso y fichaje contra el esquema real.
Ver tests/apoyo_db.py: se ejecutan solo con ZEBRAGYM_TEST_DSN y nunca dejan datos."""
from datetime import date, datetime, time, timedelta
from decimal import Decimal

import pytest
from psycopg import errors

from apoyo_db import HOY_AR, falla, membresia, persona, requiere_base, socio, usuario, valor

pytestmark = requiere_base


def _plan_id(db, nombre):
    return valor(db, "SELECT id FROM plan WHERE nombre = %s", (nombre,))


def _hoy(db):
    return valor(db, f"SELECT {HOY_AR}")


# --- Planes y vencimientos ---

def test_planes_con_vigencia_como_texto(db):
    from repositories.membresia_repository import MembresiaRepository
    planes = {p[1]: p for p in MembresiaRepository().listar_planes()}
    assert set(planes) == {"Pase por día", "3 veces por semana", "Pase libre"}
    assert planes["Pase libre"][2] == "1 mon" and planes["Pase por día"][2] == "1 day"
    assert planes["3 veces por semana"][4] == 3 and planes["Pase por día"][5] == 1
    assert all(p[6] == 0 for p in planes.values())          # precios en 0 en el seed


@pytest.mark.parametrize("plan, inicio, vencimiento", [
    ("Pase libre", date(2026, 10, 20), date(2026, 11, 20)),
    ("Pase libre", date(2027, 1, 31), date(2027, 2, 28)),    # febrero de 28
    ("Pase libre", date(2028, 1, 31), date(2028, 2, 29)),    # febrero bisiesto
    ("Pase libre", date(2026, 3, 30), date(2026, 4, 30)),    # mes de 30
    ("Pase libre", date(2026, 3, 31), date(2026, 4, 30)),    # 31 -> mes de 30
    ("Pase libre", date(2026, 12, 15), date(2027, 1, 15)),   # cambio de año
    ("Pase por día", date(2026, 11, 12), date(2026, 11, 13)),
])
def test_vencimiento_calculado_por_postgresql(db, plan, inicio, vencimiento):
    from repositories.membresia_repository import MembresiaRepository
    assert MembresiaRepository().calcular_vencimiento(_plan_id(db, plan), inicio) == vencimiento


def test_membresia_copia_precio_y_limites_del_plan(db):
    from repositories.membresia_repository import MembresiaRepository
    repo = MembresiaRepository()
    tres = _plan_id(db, "3 veces por semana")
    assert repo.actualizar_plan(tres, Decimal("18000"), None, 3, None, True)
    s = socio(db, persona(db))
    m_id, vencimiento, precio = repo.crear(s, tres, date(2027, 1, 31), None)
    assert (vencimiento, precio) == (date(2027, 2, 28), Decimal("18000"))

    # Cambio de precio y de límites del plan: la membresía vendida no cambia.
    repo.actualizar_plan(tres, Decimal("21000"), 12, 2, 1, True)
    fila = repo.obtener(m_id)
    assert fila[3] == "3 veces por semana"
    assert (fila[6], fila[7], fila[8], fila[9]) == (Decimal("18000"), None, 3, None)


def test_cambio_de_plan_entre_membresias(db):
    from repositories.membresia_repository import MembresiaRepository
    repo = MembresiaRepository()
    s = socio(db, persona(db))
    repo.crear(s, _plan_id(db, "3 veces por semana"), date(2026, 10, 20))
    repo.crear(s, _plan_id(db, "Pase libre"), date(2026, 11, 20))
    historial = repo.listar_por_socio(s)
    assert [(h[1], h[2], h[3]) for h in historial] == [
        ("Pase libre", date(2026, 11, 20), date(2026, 12, 20)),
        ("3 veces por semana", date(2026, 10, 20), date(2026, 11, 20)),
    ]


def test_plan_inexistente(db):
    from repositories.membresia_repository import MembresiaRepository
    s = socio(db, persona(db))
    with pytest.raises(ValueError, match="Plan inexistente"):
        MembresiaRepository().crear(s, 999999, date(2026, 11, 12))


def test_estado_de_membresia_solo_los_que_decide_una_persona(db):
    from repositories.membresia_repository import MembresiaRepository
    repo = MembresiaRepository()
    m = membresia(db, socio(db, persona(db)))
    assert repo.actualizar_estado(m, "cancelada")
    falla(db, errors.CheckViolation, "UPDATE membresia SET estado = 'vencida' WHERE id = %s", (m,))


# --- Pagos ---

def test_pagos_parciales_y_saldo(db):
    from repositories.membresia_repository import MembresiaRepository
    from repositories.socio_repository import SocioRepository
    repo = MembresiaRepository()
    s = socio(db, persona(db))
    m = membresia(db, s, precio=Decimal("20000"))
    pago_id, fecha = repo.registrar_pago(m, Decimal("12000"), "efectivo")
    assert fecha.date() == _hoy(db)
    estado = SocioRepository().obtener_estado(s)
    assert (estado["saldo"], estado["estado_contable"]) == (Decimal("8000"), "debe")

    repo.registrar_pago(m, Decimal("8000"), "mercado_pago")
    estado = SocioRepository().obtener_estado(s)
    assert (estado["saldo"], estado["estado_contable"]) == (Decimal("0"), "al_dia")
    assert [(p[1], p[2]) for p in repo.listar_pagos_por_socio(s)] == [
        (Decimal("8000.00"), "mercado_pago"), (Decimal("12000.00"), "efectivo")]
    assert repo.listar_por_socio(s)[0][6] == Decimal("20000")


@pytest.mark.parametrize("monto, metodo", [(Decimal("0"), "efectivo"), (Decimal("100"), "cheque")])
def test_pago_invalido(db, monto, metodo):
    m = membresia(db, socio(db, persona(db)))
    falla(db, errors.CheckViolation,
          "INSERT INTO pago (membresia_id, monto, metodo) VALUES (%s, %s, %s)", (m, monto, metodo))


# --- Accesos ---

def test_accesos_permitidos_y_rechazados(db):
    from repositories.acceso_repository import AccesoRepository
    repo = AccesoRepository()
    ana = socio(db, persona(db))
    luis = socio(db, persona(db, "20333444", "Luis", "Gómez"))
    m_ana = membresia(db, ana, plan="3 veces por semana")

    _id, momento = repo.registrar_permitido(ana, m_ana, Decimal("0.1834"))
    assert momento.date() == _hoy(db)
    repo.registrar_rechazo("limite_semanal", luis)
    repo.registrar_rechazo("no_reconocido", distancia_facial=Decimal("0.6120"))

    ultimos = repo.ultimos(5)
    assert [(u[2], u[3], u[4], u[6]) for u in ultimos] == [
        ("rechazado", "no_reconocido", None, None),
        ("rechazado", "limite_semanal", "Luis", None),
        ("permitido", None, "Ana", "3 veces por semana"),
    ]
    assert [(a[1], a[2]) for a in repo.listar_por_socio(ana)] == [("permitido", None)]

    hoy = _hoy(db)
    assert len(repo.informe(hoy, hoy)) == 3
    assert [f[1:3] for f in repo.informe(hoy, hoy, socio_id=luis)] == [("rechazado", "limite_semanal")]
    assert repo.informe(hoy - timedelta(days=10), hoy - timedelta(days=1)) == []


def test_motivo_de_rechazo_invalido(db):
    from repositories.acceso_repository import AccesoRepository
    with pytest.raises(errors.CheckViolation):
        with db.transaction():
            AccesoRepository().registrar_rechazo("fuera_de_horario")


def test_bloquear_socio_para_confirmar(db):
    from repositories.socio_repository import SocioRepository
    s = socio(db, persona(db))
    assert SocioRepository().obtener_por_id(s, bloquear=True)[0] == s


# --- Fichajes ---

def test_fichaje_entrada_y_salida(db):
    from repositories.fichaje_repository import FichajeRepository
    repo = FichajeRepository()
    hoy = _hoy(db)
    ana = usuario(db, persona(db), "ana")
    jornada = valor(db, "INSERT INTO jornada (usuario_id, fecha, horario_entrada, horario_salida) "
                        "VALUES (%s, %s, '07:30', '15:30') RETURNING id", (ana, hoy))
    db.execute("INSERT INTO jornada (usuario_id, fecha, horario_entrada, horario_salida, estado) "
               "VALUES (%s, %s, '16:00', '20:00', 'permiso')", (ana, hoy))
    assert [(j[1], j[2], j[3]) for j in repo.jornadas_del_dia(ana, hoy)] == [
        (time(7, 30), time(15, 30), "jornada"), (time(16, 0), time(20, 0), "permiso")]

    assert repo.fichaje_abierto(ana) is None
    fichaje_id, entrada = repo.registrar_entrada(ana, jornada)
    assert repo.fichaje_abierto(ana, bloquear=True) == (fichaje_id, entrada)
    with pytest.raises(errors.UniqueViolation):          # una sola entrada abierta
        with db.transaction():
            repo.registrar_entrada(ana)

    # La salida tiene que ser posterior a la entrada (en la prueba todo ocurre
    # en una misma transacción, así que se adelanta la entrada).
    db.execute("UPDATE fichaje SET entrada = entrada - INTERVAL '8 hours' WHERE id = %s", (fichaje_id,))
    salida = repo.registrar_salida(fichaje_id)
    assert isinstance(salida, datetime) and repo.registrar_salida(fichaje_id) is None
    assert repo.fichaje_abierto(ana) is None

    fila = repo.listar(hoy - timedelta(days=1), hoy, usuario_id=ana)[0]
    assert (fila[2], fila[4], fila[7], fila[8]) == ("Ana", "ana", jornada, time(7, 30))


def test_fichaje_fuera_de_turno_y_filtro_por_empleado(db):
    from repositories.fichaje_repository import FichajeRepository
    repo = FichajeRepository()
    ana = usuario(db, persona(db), "ana")
    luis = usuario(db, persona(db, "20333444", "Luis", "Gómez"), "luis", ("recepcionista",))
    repo.registrar_entrada(ana)                    # sin jornada: fuera de turno
    repo.registrar_entrada(luis)
    hoy = _hoy(db)
    assert {f[1] for f in repo.listar(hoy, hoy)} == {ana, luis}
    assert [f[7] for f in repo.listar(hoy, hoy, usuario_id=ana)] == [None]


def test_empleados_que_fichan(db):
    from repositories.user_repository import UserRepository
    ana = usuario(db, persona(db), "ana", ("entrenador", "administrador"))
    luis = usuario(db, persona(db, "20333444", "Luis", "Gómez"), "luis", ("recepcionista",))
    usuario(db, persona(db, "25555666", "Eva", "Ruiz"), "eva", ("administrador",))
    empleados = [(e[0], e[1]) for e in UserRepository().listar_empleados()]
    assert empleados == [(luis, "Luis"), (ana, "Ana")]      # por apellido; sin admin
