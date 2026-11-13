"""Indicadores del Panel del administrador (todo calculado desde la base)."""
from dataclasses import dataclass, field
from decimal import Decimal

from config.database import usar_conexion
from services.auth_service import REPORTE_CONSULTAR, autorizar

DIAS_POR_VENCER = 5
DIAS_INGRESOS_POR_HORA = 30


@dataclass
class Indicadores:
    ingresos_hoy: int = 0
    ingresos_semana: int = 0
    socios_vigentes: int = 0
    por_vencer: list = field(default_factory=list)       # (nombre, apellido, plan, vence, dias)
    deben: list = field(default_factory=list)            # (nombre, apellido, saldo, estado_membresia)
    recaudacion_mes: Decimal = Decimal("0")
    rechazos_hoy: list = field(default_factory=list)     # (motivo, cantidad)
    ingresos_por_hora: dict = field(default_factory=dict)
    socios_por_plan: list = field(default_factory=list)  # (plan, cantidad)
    empleados_trabajando: list = field(default_factory=list)

    @property
    def total_rechazos_hoy(self):
        return sum(cantidad for _motivo, cantidad in self.rechazos_hoy)


class PanelService:
    def __init__(self, repo=None, transaccion=usar_conexion):
        if repo is None:
            from repositories.panel_repository import PanelRepository
            repo = PanelRepository()
        self._repo = repo
        self._transaccion = transaccion

    def indicadores(self, sesion):
        """Todos los indicadores en una sola conexión (una foto coherente)."""
        autorizar(sesion, REPORTE_CONSULTAR)
        with self._transaccion() as conn:
            hoy, semana = self._repo.ingresos(conn=conn)
            return Indicadores(
                ingresos_hoy=hoy,
                ingresos_semana=semana,
                socios_vigentes=self._repo.socios_vigentes(conn=conn),
                por_vencer=list(self._repo.por_vencer(DIAS_POR_VENCER, conn=conn)),
                deben=list(self._repo.deben(conn=conn)),
                recaudacion_mes=self._repo.recaudacion_mes(conn=conn),
                rechazos_hoy=list(self._repo.rechazos_hoy(conn=conn)),
                ingresos_por_hora=self._repo.ingresos_por_hora(DIAS_INGRESOS_POR_HORA, conn=conn),
                socios_por_plan=list(self._repo.socios_por_plan(conn=conn)),
                empleados_trabajando=list(self._repo.empleados_trabajando(conn=conn)),
            )
