"""Empleados de ZebraGym (solo el administrador): alta con persona, 3 fotos
(fichan con la cara), usuario, contraseña inicial y UN rol (entrenador o
recepcionista); lista y activación o desactivación de la cuenta.

Si el DNI ya existe (por ejemplo, un socio que pasa a ser entrenador) se
reutiliza la persona: no se duplican sus datos ni sus fotos. Desde la
interfaz no se crean administradores ni se asignan varios roles."""
import re

from config.database import usar_conexion
from services.auth_service import (
    ENTRENADOR, LARGO_MINIMO_CONTRASENIA, RECEPCIONISTA, USUARIO_ADMINISTRAR, ReglaDeCuentas,
    autorizar, hashear_contrasenia,
)
from services.persona_service import DatosInvalidos, normalizar_dni

# Hoy no hay recepcionista: los entrenadores atienden el mostrador. Recepción
# queda como rol opcional para el futuro.
ROLES_EMPLEADO = {ENTRENADOR: "Entrenador", RECEPCIONISTA: "Recepcionista"}
ROL_POR_DEFECTO = ENTRENADOR
ANGULOS = ("frente", "perfil_izquierdo", "perfil_derecho")
_USUARIO_VALIDO = re.compile(r"^[A-Za-z0-9._-]{3,30}$")


class ErroresFormulario(Exception):
    """Errores de validación por campo: {campo: mensaje}."""

    def __init__(self, errores):
        super().__init__("; ".join(errores.values()))
        self.errores = errores


class EmpleadoService:
    def __init__(self, personas=None, usuarios=None, transaccion=usar_conexion, detectable=None):
        if personas is None:
            from repositories.person_repository import PersonRepository
            personas = PersonRepository()
        if usuarios is None:
            from repositories.user_repository import UserRepository
            usuarios = UserRepository()
        if detectable is None:
            from services.face_service import tiene_rostro_detectable
            detectable = tiene_rostro_detectable
        self._personas, self._usuarios = personas, usuarios
        self._transaccion = transaccion
        self._detectable = detectable

    # --- Consulta previa por DNI ---

    def buscar_por_dni(self, sesion, dni):
        """dict con la persona existente (para no duplicarla) o None.
        Lanza DatosInvalidos si el DNI no tiene 7 u 8 dígitos."""
        autorizar(sesion, USUARIO_ADMINISTRAR)
        dni = normalizar_dni(dni)
        with self._transaccion() as conn:
            persona = self._personas.obtener_por_dni(dni, conn=conn)
            if persona is None:
                return None
            return {
                "persona_id": persona[0], "nombre": persona[2], "apellido": persona[3],
                "fotos": self._personas.contar_fotos(persona[0], conn=conn),
                "tiene_cuenta": self._usuarios.obtener_por_persona(persona[0], conn=conn) is not None,
            }

    # --- Alta ---

    def validar(self, datos, fotos, existente):
        """{campo: mensaje} con los errores del formulario (vacío si está bien)."""
        errores = {}
        try:
            normalizar_dni(datos.get("dni"))
        except DatosInvalidos as error:
            errores["dni"] = str(error)
        if existente is not None and existente["tiene_cuenta"]:
            errores["dni"] = "Esa persona ya tiene una cuenta de usuario."
        if existente is None:
            for campo, texto in (("nombre", "El nombre es obligatorio."),
                                 ("apellido", "El apellido es obligatorio.")):
                if not (datos.get(campo) or "").strip():
                    errores[campo] = texto
        usuario = (datos.get("usuario") or "").strip()
        if not usuario:
            errores["usuario"] = "El nombre de usuario es obligatorio."
        elif not _USUARIO_VALIDO.match(usuario):
            errores["usuario"] = "Usá de 3 a 30 letras, números, punto, guion o guion bajo, sin espacios."
        if len(datos.get("contrasenia") or "") < LARGO_MINIMO_CONTRASENIA:
            errores["contrasenia"] = f"La contraseña debe tener al menos {LARGO_MINIMO_CONTRASENIA} caracteres."
        if datos.get("rol") not in ROLES_EMPLEADO:
            errores["rol"] = "Elegí un rol: entrenador o recepcionista."
        fotos = fotos or {}
        if set(fotos) - set(ANGULOS):
            errores["fotos"] = "Ángulo de foto inválido."
        elif existente is None or existente["fotos"] == 0:
            if set(fotos) != set(ANGULOS):
                errores["fotos"] = "Faltan fotos: cargá frente, perfil izquierdo y perfil derecho."
            elif not self._detectable(fotos["frente"]):
                errores["fotos"] = "La foto de frente no tiene un rostro detectable: repetila."
        elif "frente" in fotos and not self._detectable(fotos["frente"]):
            errores["fotos"] = "La foto de frente no tiene un rostro detectable: repetila."
        return errores

    def registrar(self, sesion, datos, fotos):
        """Crea la cuenta del empleado (y la persona si no existía) en una sola
        transacción. Devuelve el id de la cuenta. Lanza ErroresFormulario."""
        autorizar(sesion, USUARIO_ADMINISTRAR)
        try:
            dni = normalizar_dni(datos.get("dni"))
        except DatosInvalidos as error:
            raise ErroresFormulario({"dni": str(error)})
        fotos = {a: f for a, f in (fotos or {}).items() if f is not None}
        with self._transaccion() as conn:
            persona = self._personas.obtener_por_dni(dni, conn=conn)
            existente = None
            if persona is not None:
                existente = {"persona_id": persona[0], "fotos": self._personas.contar_fotos(persona[0], conn=conn),
                             "tiene_cuenta": self._usuarios.obtener_por_persona(persona[0], conn=conn) is not None}
            errores = self.validar(datos, fotos, existente)
            usuario = (datos.get("usuario") or "").strip()
            if "usuario" not in errores and self._usuarios.existe_nombre_usuario(usuario, conn=conn):
                errores["usuario"] = "Ese nombre de usuario ya existe."
            if errores:
                raise ErroresFormulario(errores)
            if persona is None:
                persona_id = self._personas.crear({**datos, "dni": dni}, conn=conn)
            else:
                persona_id = persona[0]
            if fotos:
                self._personas.guardar_fotos(persona_id, fotos, conn=conn)
            usuario_id = self._usuarios.crear(persona_id, usuario, hashear_contrasenia(datos["contrasenia"]),
                                              True, conn=conn)
            self._usuarios.asignar_rol(usuario_id, datos["rol"], sesion.usuario_id, conn=conn)
            return usuario_id

    # --- Lista y estado ---

    def listar(self, sesion):
        autorizar(sesion, USUARIO_ADMINISTRAR)
        return self._usuarios.listar_personal()

    def cambiar_estado(self, sesion, usuario_id, activo):
        """Activa o desactiva la cuenta de un empleado (nunca la del administrador)."""
        autorizar(sesion, USUARIO_ADMINISTRAR)
        roles = set(self._usuarios.obtener_roles(usuario_id))
        if not roles & set(ROLES_EMPLEADO) or "administrador" in roles:
            raise ReglaDeCuentas("Solo se pueden activar o desactivar cuentas del personal.")
        return self._usuarios.actualizar_estado(usuario_id, activo)
