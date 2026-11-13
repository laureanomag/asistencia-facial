"""Consultas del Panel contra el esquema real (ver tests/apoyo_db.py)."""
from decimal import Decimal

from apoyo_db import HOY_AR, membresia, persona, requiere_base, socio, usuario, valor

pytestmark = requiere_base


def test_indicadores_desde_la_base(db):
    from repositories.panel_repository import PanelRepository
    repo = PanelRepository()
    ana = socio(db, persona(db))
    luis = socio(db, persona(db, "20333444", "Luis", "Gómez"))
    eva = socio(db, persona(db, "25555666", "Eva", "Ruiz"))
    m_ana = membresia(db, ana, plan="Pase por día", precio=Decimal("3000"))   # vence mañana
    m_luis = membresia(db, luis, plan="Pase libre", precio=Decimal("20000"))
    membresia(db, eva, plan="Pase libre", precio=Decimal("20000"), desde=-40)  # vencida
    db.execute("INSERT INTO pago (membresia_id, monto, metodo) VALUES (%s, 3000, 'efectivo'), "
               "(%s, 12000, 'transferencia')", (m_ana, m_luis))
    db.execute("INSERT INTO acceso (socio_id, membresia_id, resultado) VALUES (%s, %s, 'permitido'), "
               "(%s, %s, 'permitido')", (ana, m_ana, luis, m_luis))
    db.execute("INSERT INTO acceso (socio_id, resultado, motivo_rechazo) VALUES "
               "(%s, 'rechazado', 'membresia_vencida'), (%s, 'rechazado', 'membresia_vencida'), "
               "(NULL, 'rechazado', 'no_reconocido')", (eva, eva))
    rocio = usuario(db, persona(db, "30999888", "Rocío", "Paz"), "rocio", ("recepcionista",))
    db.execute("INSERT INTO fichaje (usuario_id) VALUES (%s)", (rocio,))

    assert repo.ingresos() == (2, 2)
    assert repo.socios_vigentes() == 2
    assert [(f[0], f[2], f[4]) for f in repo.por_vencer()] == [("Ana", "Pase por día", 1)]
    deben = {f[0]: (f[2], f[3]) for f in repo.deben()}
    assert deben == {"Luis": (Decimal("8000.00"), "vigente"), "Eva": (Decimal("20000.00"), "vencida")}
    assert repo.recaudacion_mes() == Decimal("15000.00")
    assert repo.rechazos_hoy() == [("membresia_vencida", 2), ("no_reconocido", 1)]
    hora = valor(db, "SELECT EXTRACT(HOUR FROM NOW() AT TIME ZONE 'America/Argentina/Buenos_Aires')::int")
    assert repo.ingresos_por_hora() == {hora: 2}
    assert dict(repo.socios_por_plan()) == {"Pase por día": 1, "3 veces por semana": 0, "Pase libre": 1}
    trabajando = repo.empleados_trabajando()
    assert [(t[0], t[2], t[4]) for t in trabajando] == [("Rocío", "rocio", "recepcionista")]
    assert trabajando[0][3].date() == valor(db, f"SELECT {HOY_AR}")
