"""Autenticación y permisos de ZEBRAGYM.

Las cuentas (usuario) tienen uno o más roles del sistema (usuario_rol):
'administrador', 'recepcionista' y 'entrenador'. Los socios no inician sesión.
La matriz de permisos vive acá (no en la base): cada servicio llama a
autorizar(sesion, permiso) antes de operar, sin depender de lo que muestre
el menú."""
from dataclasses import dataclass, field

import bcrypt

from config.database import usar_conexion

ADMINISTRADOR = "administrador"
RECEPCIONISTA = "recepcionista"
ENTRENADOR = "entrenador"
ROLES = (ADMINISTRADOR, RECEPCIONISTA, ENTRENADOR)

USUARIO_ADMINISTRAR = "usuario.administrar"
CONFIGURACION_GESTIONAR = "configuracion.gestionar"      # planes, horarios, días especiales
JORNADA_GESTIONAR = "jornada.gestionar"
SOCIO_REGISTRAR = "socio.registrar"
SOCIO_EDITAR = "socio.editar"
SOCIO_BAJA_REACTIVAR = "socio.baja_reactivar"
MEMBRESIA_CONSULTAR = "membresia.consultar"
PAGO_REGISTRAR = "pago.registrar"
MEMBRESIA_RENOVAR = "membresia.renovar"
ACCESO_OPERAR_CAMARA = "acceso.operar_camara"
PLAN_ENTRENAMIENTO_GESTIONAR = "plan_entrenamiento.gestionar"
REPORTE_CONSULTAR = "reporte.consultar"
FICHAJE_CONSULTAR_PROPIO = "fichaje.consultar_propio"   # con jornada.gestionar se ven todos

A, R, E = ADMINISTRADOR, RECEPCIONISTA, ENTRENADOR
MATRIZ_PERMISOS = {
    USUARIO_ADMINISTRAR:          {A},
    CONFIGURACION_GESTIONAR:      {A},
    JORNADA_GESTIONAR:            {A},
    SOCIO_REGISTRAR:              {A, R, E},
    SOCIO_EDITAR:                 {A, R, E},
    SOCIO_BAJA_REACTIVAR:         {A},
    MEMBRESIA_CONSULTAR:          {A, R, E},
    PAGO_REGISTRAR:               {A, R},
    MEMBRESIA_RENOVAR:            {A, R},
    ACCESO_OPERAR_CAMARA:         {A, R, E},
    PLAN_ENTRENAMIENTO_GESTIONAR: {A, E},
    REPORTE_CONSULTAR:            {A},
    FICHAJE_CONSULTAR_PROPIO:     {A, R, E},
}
del A, R, E

LARGO_MINIMO_CONTRASENIA = 8
COSTO_BCRYPT = 12


def permisos_de(roles):
    """Unión de los permisos de todos los roles recibidos."""
    roles = set(roles)
    return frozenset(p for p, permitidos in MATRIZ_PERMISOS.items() if roles & permitidos)


def hashear_contrasenia(contrasenia):
    return bcrypt.hashpw(contrasenia.encode("utf-8"), bcrypt.gensalt(COSTO_BCRYPT)).decode("ascii")


def verificar_contrasenia(contrasenia, contrasenia_hash):
    """Compara contra un hash bcrypt (incluye los $2a$ que genera pgcrypto en
    02-seed.sql). Un hash vacío o con otro formato nunca es válido."""
    try:
        return bcrypt.checkpw(contrasenia.encode("utf-8"), contrasenia_hash.encode("ascii"))
    except (ValueError, AttributeError):
        return False


# Hash fijo para gastar el mismo tiempo cuando la cuenta no existe: así no se
# puede averiguar qué nombres de usuario existen midiendo la demora.
_HASH_SIN_CUENTA = hashear_contrasenia("cuenta-inexistente")


class ErrorAutenticacion(Exception):
    """Credenciales inválidas o cuenta inactiva (mensaje genérico a propósito)."""


class AccesoDenegado(Exception):
    """La sesión no tiene el permiso requerido."""


class ReglaDeCuentas(Exception):
    """Operación sobre cuentas o roles que rompe una regla (ej.: último administrador)."""


@dataclass(frozen=True)
class Sesion:
    usuario_id: int
    persona_id: object
    nombre_usuario: str
    nombre_mostrado: str
    roles: frozenset
    debe_cambiar_contrasenia: bool = False
    permisos: frozenset = field(init=False)

    def __post_init__(self):
        object.__setattr__(self, "permisos", permisos_de(self.roles))

    def puede(self, permiso):
        return permiso in self.permisos

    def tiene_rol(self, rol):
        return rol in self.roles


def autorizar(sesion, permiso):
    if sesion is None or not sesion.puede(permiso):
        raise AccesoDenegado(f"No tiene permiso para esta operación ({permiso}).")


class AuthService:
    def __init__(self, user_repository=None, transaccion=usar_conexion):
        if user_repository is None:
            from repositories.user_repository import UserRepository
            user_repository = UserRepository()
        self._repo = user_repository
        self._transaccion = transaccion

    # --- Inicio de sesión ---

    def autenticar(self, identificador, contrasenia):
        """Devuelve una Sesion o lanza ErrorAutenticacion. identificador es el
        nombre de usuario o el DNI de la persona vinculada."""
        identificador = (identificador or "").strip()
        contrasenia = contrasenia or ""
        fila = self._repo.buscar_para_login(identificador) if identificador else None
        if fila is None:
            verificar_contrasenia(contrasenia, _HASH_SIN_CUENTA)
            raise ErrorAutenticacion("Usuario o contraseña incorrectos.")

        usuario_id, persona_id, nombre_usuario, contrasenia_hash, activo, debe_cambiar, nombre, apellido = fila
        if not verificar_contrasenia(contrasenia, contrasenia_hash) or not activo:
            raise ErrorAutenticacion("Usuario o contraseña incorrectos.")

        roles = frozenset(self._repo.obtener_roles(usuario_id))
        if not roles:
            raise ErrorAutenticacion("La cuenta no tiene ningún rol asignado.")

        self._repo.registrar_ingreso(usuario_id)
        nombre_mostrado = f"{nombre} {apellido}" if nombre else nombre_usuario
        return Sesion(usuario_id, persona_id, nombre_usuario, nombre_mostrado, roles,
                      bool(debe_cambiar))

    def cambiar_contrasenia(self, sesion, actual, nueva):
        """Cambia la contraseña de la propia cuenta y devuelve la sesión
        actualizada (sin la obligación de cambiarla)."""
        fila = self._repo.obtener_por_id(sesion.usuario_id)
        if fila is None or not verificar_contrasenia(actual or "", fila[3]):
            raise ErrorAutenticacion("La contraseña actual no es correcta.")
        self._validar_nueva(nueva)
        if nueva == actual:
            raise ReglaDeCuentas("La nueva contraseña debe ser distinta de la actual.")
        self._repo.actualizar_contrasenia(sesion.usuario_id, hashear_contrasenia(nueva), False)
        return Sesion(sesion.usuario_id, sesion.persona_id, sesion.nombre_usuario,
                      sesion.nombre_mostrado, sesion.roles, False)

    @staticmethod
    def _validar_nueva(nueva):
        if nueva is None or len(nueva) < LARGO_MINIMO_CONTRASENIA:
            raise ReglaDeCuentas(
                f"La contraseña debe tener al menos {LARGO_MINIMO_CONTRASENIA} caracteres.")

    # --- Administración de cuentas (solo administrador) ---

    def crear_usuario(self, sesion, persona_id, nombre_usuario, contrasenia_inicial, roles):
        """Crea una cuenta vinculada a una persona existente (sin duplicar sus
        datos) con los roles indicados. Obliga a cambiar la contraseña en el
        primer ingreso."""
        autorizar(sesion, USUARIO_ADMINISTRAR)
        roles = set(roles)
        if not roles:
            raise ReglaDeCuentas("La cuenta debe tener al menos un rol.")
        desconocidos = roles - set(ROLES)
        if desconocidos:
            raise ReglaDeCuentas(f"Rol inexistente: {', '.join(sorted(desconocidos))}")
        if not (nombre_usuario or "").strip():
            raise ReglaDeCuentas("El nombre de usuario es obligatorio.")
        self._validar_nueva(contrasenia_inicial)

        with self._transaccion() as conn:
            if self._repo.obtener_por_persona(persona_id, conn=conn) is not None:
                raise ReglaDeCuentas("Esa persona ya tiene una cuenta.")
            usuario_id = self._repo.crear(persona_id, nombre_usuario,
                                          hashear_contrasenia(contrasenia_inicial), True, conn=conn)
            for rol in sorted(roles):
                self._repo.asignar_rol(usuario_id, rol, sesion.usuario_id, conn=conn)
            return usuario_id

    def asignar_rol(self, sesion, usuario_id, rol):
        autorizar(sesion, USUARIO_ADMINISTRAR)
        if rol not in ROLES:
            raise ReglaDeCuentas(f"Rol inexistente: {rol}")
        return self._repo.asignar_rol(usuario_id, rol, sesion.usuario_id)

    def quitar_rol(self, sesion, usuario_id, rol):
        autorizar(sesion, USUARIO_ADMINISTRAR)
        with self._transaccion() as conn:
            if rol == ADMINISTRADOR:
                self._exigir_otro_administrador(usuario_id, conn)
            return self._repo.quitar_rol(usuario_id, rol, conn=conn)

    def desactivar_usuario(self, sesion, usuario_id):
        autorizar(sesion, USUARIO_ADMINISTRAR)
        with self._transaccion() as conn:
            self._exigir_otro_administrador(usuario_id, conn)
            return self._repo.actualizar_estado(usuario_id, False, conn=conn)

    def reactivar_usuario(self, sesion, usuario_id):
        autorizar(sesion, USUARIO_ADMINISTRAR)
        return self._repo.actualizar_estado(usuario_id, True)

    def _exigir_otro_administrador(self, usuario_id, conn):
        """Impide dejar el sistema sin ningún administrador activo."""
        fila = self._repo.obtener_por_id(usuario_id, conn=conn)
        es_admin_activo = (fila is not None and fila[4]
                           and ADMINISTRADOR in self._repo.obtener_roles(usuario_id, conn=conn))
        if es_admin_activo and self._repo.contar_activos_con_rol(ADMINISTRADOR, conn=conn) <= 1:
            raise ReglaDeCuentas("No se puede dejar el sistema sin un administrador activo.")
