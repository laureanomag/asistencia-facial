"""Estado del socio: membresía actual (v_socio_estado), historial de
membresías, pagos e ingresos. La dueña además puede dar de baja o reactivar."""
from config.database import usar_conexion
from services.auth_service import MEMBRESIA_CONSULTAR, SOCIO_BAJA_REACTIVAR, autorizar


class EstadoSocioService:
    def __init__(self, personas=None, socios=None, membresias=None, accesos=None, persona_service=None,
                 transaccion=usar_conexion):
        if personas is None:
            from repositories.person_repository import PersonRepository
            personas = PersonRepository()
        if socios is None:
            from repositories.socio_repository import SocioRepository
            socios = SocioRepository()
        if membresias is None:
            from repositories.membresia_repository import MembresiaRepository
            membresias = MembresiaRepository()
        if accesos is None:
            from repositories.acceso_repository import AccesoRepository
            accesos = AccesoRepository()
        if persona_service is None:
            from services.persona_service import PersonaService
            persona_service = PersonaService()
        self._personas, self._socios, self._membresias, self._accesos = personas, socios, membresias, accesos
        self._persona_service = persona_service
        self._transaccion = transaccion

    def buscar(self, sesion, texto):
        autorizar(sesion, MEMBRESIA_CONSULTAR)
        return self._socios.listar(texto)

    def ficha(self, sesion, socio_id):
        """dict con persona, socio, estado (None si está dado de baja),
        membresías, pagos y últimos ingresos; None si el socio no existe."""
        autorizar(sesion, MEMBRESIA_CONSULTAR)
        with self._transaccion() as conn:
            socio = self._socios.obtener_por_id(socio_id, conn=conn)
            if socio is None:
                return None
            persona = self._personas.obtener_por_id(socio[1], conn=conn)
            return {
                "socio_id": socio[0], "dni": persona[1], "nombre": f"{persona[2]} {persona[3]}",
                "celular": persona[4], "contacto_nombre": socio[2], "contacto_telefono": socio[3],
                "fecha_alta": socio[4], "activo": socio[5], "fecha_baja": socio[6],
                "estado": self._socios.obtener_estado(socio_id, conn=conn),
                "membresias": self._membresias.listar_por_socio(socio_id, conn=conn),
                "pagos": self._membresias.listar_pagos_por_socio(socio_id, 10, conn=conn),
                "accesos": self._accesos.listar_por_socio(socio_id, 10, conn=conn),
            }

    def puede_dar_de_baja(self, sesion):
        return sesion.puede(SOCIO_BAJA_REACTIVAR)

    def dar_baja(self, sesion, socio_id):
        return self._persona_service.dar_baja_socio(sesion, socio_id)

    def reactivar(self, sesion, socio_id):
        return self._persona_service.reactivar_socio(sesion, socio_id)
