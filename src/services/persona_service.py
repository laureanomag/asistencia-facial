"""Registro de personas y socios de ZEBRAGYM.

Una persona tiene una sola identidad (un DNI, un perfil facial) aunque sea
socio y entrenador a la vez. Registrar como socio a alguien que ya existe
(por ejemplo, un entrenador) reutiliza su persona en lugar de duplicarla."""
import re
from dataclasses import dataclass
from datetime import date

from config.database import usar_conexion
from services.auth_service import SOCIO_BAJA_REACTIVAR, SOCIO_REGISTRAR, autorizar

ANGULOS = ("frente", "perfil_izquierdo", "perfil_derecho")
_DNI_VALIDO = re.compile(r"^[0-9]{7,8}$")


class DatosInvalidos(ValueError):
    pass


class SocioYaRegistrado(Exception):
    pass


def normalizar_dni(dni):
    """Quita puntos, espacios y guiones: '12.345.678' -> '12345678'.
    Lanza DatosInvalidos si no quedan 7 u 8 dígitos (como exige la base)."""
    limpio = re.sub(r"[\s.\-]", "", dni or "")
    if not _DNI_VALIDO.match(limpio):
        raise DatosInvalidos("El DNI debe tener 7 u 8 dígitos.")
    return limpio


@dataclass(frozen=True)
class ResultadoRegistroSocio:
    persona_id: int
    socio_id: int
    persona_reutilizada: bool   # True si la persona ya existía (p. ej. un entrenador)
    fotos_guardadas: int


class PersonaService:
    def __init__(self, person_repository=None, socio_repository=None, transaccion=usar_conexion):
        if person_repository is None:
            from repositories.person_repository import PersonRepository
            person_repository = PersonRepository()
        if socio_repository is None:
            from repositories.socio_repository import SocioRepository
            socio_repository = SocioRepository()
        self._personas = person_repository
        self._socios = socio_repository
        self._transaccion = transaccion

    def registrar_socio(self, sesion, datos_persona, fotos, contacto_emergencia_telefono,
                        contacto_emergencia_nombre=None):
        """Registra un socio en una sola transacción.
        - Si el DNI no existe: crea la persona, sus fotos y el socio.
        - Si el DNI ya existe (p. ej. un entrenador): reutiliza esa persona sin
          modificar sus datos, crea el socio y agrega o reemplaza solo las
          fotos recibidas (nunca más de una por ángulo).
        fotos: {angulo: bytes}. Una persona nueva necesita las 3 fotos."""
        autorizar(sesion, SOCIO_REGISTRAR)
        dni = normalizar_dni(datos_persona.get("dni"))
        for campo in ("nombre", "apellido"):
            if not (datos_persona.get(campo) or "").strip():
                raise DatosInvalidos(f"El campo {campo} es obligatorio.")
        if not (contacto_emergencia_telefono or "").strip():
            raise DatosInvalidos("El teléfono de contacto de emergencia es obligatorio.")
        fotos = {a: img for a, img in (fotos or {}).items() if img is not None}
        invalidos = set(fotos) - set(ANGULOS)
        if invalidos:
            raise DatosInvalidos(f"Ángulo de foto inválido: {', '.join(sorted(invalidos))}")

        with self._transaccion() as conn:
            persona = self._personas.obtener_por_dni(dni, conn=conn)
            if persona is None:
                if set(fotos) != set(ANGULOS):
                    raise DatosInvalidos("Una persona nueva necesita las 3 fotos "
                                         "(frente, perfil izquierdo y perfil derecho).")
                persona_id = self._personas.crear({**datos_persona, "dni": dni}, conn=conn)
                reutilizada = False
            else:
                persona_id = persona[0]
                reutilizada = True
                socio = self._socios.obtener_por_persona(persona_id, conn=conn)
                if socio is not None:
                    estado = "activo" if socio[5] else "dado de baja (puede reactivarse)"
                    raise SocioYaRegistrado(f"La persona con DNI {dni} ya es socio, {estado}.")
                if not fotos and self._personas.contar_fotos(persona_id, conn=conn) == 0:
                    raise DatosInvalidos("La persona no tiene perfil facial: cargue las 3 fotos.")

            socio_id = self._socios.crear(
                persona_id, contacto_emergencia_telefono.strip(), contacto_emergencia_nombre,
                sesion.usuario_id, conn=conn)
            if fotos:
                self._personas.guardar_fotos(persona_id, fotos, conn=conn)

        return ResultadoRegistroSocio(persona_id, socio_id, reutilizada, len(fotos))

    def dar_baja_socio(self, sesion, socio_id, fecha_baja=None):
        """La persona, sus fotos, membresías y accesos se conservan."""
        autorizar(sesion, SOCIO_BAJA_REACTIVAR)
        return self._socios.dar_baja(socio_id, fecha_baja or date.today())

    def reactivar_socio(self, sesion, socio_id):
        autorizar(sesion, SOCIO_BAJA_REACTIVAR)
        return self._socios.reactivar(socio_id)

    def roles_de_persona(self, persona_id):
        """Relaciones de la persona: socio_id/socio_activo, usuario_id/usuario_activo
        y roles del sistema. Lo usa el reconocimiento para decidir si ofrece
        'Entrenar', 'Fichar' o ambas opciones."""
        return self._personas.obtener_roles(persona_id)
