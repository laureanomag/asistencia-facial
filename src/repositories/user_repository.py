from config.database import usar_conexion


class UserRepository:
    """Acceso a datos de usuario (cuentas del sistema) y usuario_rol.
    Los datos personales se leen de persona: no se duplican en la cuenta."""

    def buscar_para_login(self, identificador, conn=None):
        """Busca una cuenta por nombre de usuario (sin distinguir mayúsculas)
        o por el DNI de la persona vinculada. Devuelve
        (id, persona_id, nombre_usuario, contrasenia_hash, activo,
         debe_cambiar_contrasenia, nombre, apellido) o None.
        La contraseña NO se compara en SQL: la verifica AuthService con bcrypt."""
        query = """
            SELECT u.id, u.persona_id, u.nombre_usuario, u.contrasenia_hash, u.activo,
                   u.debe_cambiar_contrasenia, p.nombre, p.apellido
              FROM usuario u
              LEFT JOIN persona p ON p.id = u.persona_id
             WHERE LOWER(u.nombre_usuario) = LOWER(%s)
                OR p.dni = %s
             ORDER BY (LOWER(u.nombre_usuario) = LOWER(%s)) DESC
             LIMIT 1;
        """
        with usar_conexion(conn) as c, c.cursor() as cur:
            cur.execute(query, (identificador, identificador, identificador))
            return cur.fetchone()

    def obtener_por_id(self, usuario_id, conn=None):
        query = """
            SELECT id, persona_id, nombre_usuario, contrasenia_hash, activo, debe_cambiar_contrasenia
              FROM usuario
             WHERE id = %s;
        """
        with usar_conexion(conn) as c, c.cursor() as cur:
            cur.execute(query, (usuario_id,))
            return cur.fetchone()

    def obtener_por_persona(self, persona_id, conn=None):
        with usar_conexion(conn) as c, c.cursor() as cur:
            cur.execute("SELECT id, nombre_usuario, activo FROM usuario WHERE persona_id = %s;",
                        (persona_id,))
            return cur.fetchone()

    def listar_empleados(self, conn=None):
        """Cuentas con persona vinculada y rol entrenador o recepcionista
        (las que fichan): (id, nombre, apellido, nombre_usuario, activo)."""
        query = """
            SELECT u.id, p.nombre, p.apellido, u.nombre_usuario, u.activo
              FROM usuario u
              JOIN persona p ON p.id = u.persona_id
             WHERE EXISTS (SELECT 1 FROM usuario_rol ur
                            WHERE ur.usuario_id = u.id
                              AND ur.rol IN ('entrenador', 'recepcionista'))
             ORDER BY p.apellido, p.nombre;
        """
        with usar_conexion(conn) as c, c.cursor() as cur:
            cur.execute(query)
            return cur.fetchall()

    def existe_nombre_usuario(self, nombre_usuario, conn=None):
        with usar_conexion(conn) as c, c.cursor() as cur:
            cur.execute("SELECT 1 FROM usuario WHERE LOWER(nombre_usuario) = LOWER(%s);",
                        (nombre_usuario.strip(),))
            return cur.fetchone() is not None

    def listar_personal(self, conn=None):
        """Cuentas del personal (con persona y rol entrenador o recepcionista):
        (id, nombre, apellido, dni, nombre_usuario, activo, roles, ultimo_acceso)."""
        query = """
            SELECT u.id, p.nombre, p.apellido, p.dni, u.nombre_usuario, u.activo,
                   ARRAY_AGG(ur.rol ORDER BY ur.rol), u.ultimo_acceso
              FROM usuario u
              JOIN persona p     ON p.id = u.persona_id
              JOIN usuario_rol ur ON ur.usuario_id = u.id
             GROUP BY u.id, p.nombre, p.apellido, p.dni
            HAVING BOOL_OR(ur.rol IN ('entrenador', 'recepcionista'))
             ORDER BY u.activo DESC, p.apellido, p.nombre;
        """
        with usar_conexion(conn) as c, c.cursor() as cur:
            cur.execute(query)
            return [(*fila[:6], list(fila[6]), fila[7]) for fila in cur.fetchall()]

    def obtener_roles(self, usuario_id, conn=None):
        """Lista de roles de la cuenta ('administrador', 'recepcionista', 'entrenador')."""
        query = "SELECT rol FROM usuario_rol WHERE usuario_id = %s ORDER BY rol;"
        with usar_conexion(conn) as c, c.cursor() as cur:
            cur.execute(query, (usuario_id,))
            return [fila[0] for fila in cur.fetchall()]

    def crear(self, persona_id, nombre_usuario, contrasenia_hash, debe_cambiar_contrasenia=True,
              conn=None):
        query = """
            INSERT INTO usuario (persona_id, nombre_usuario, contrasenia_hash, debe_cambiar_contrasenia)
            VALUES (%s, %s, %s, %s)
            RETURNING id;
        """
        with usar_conexion(conn) as c, c.cursor() as cur:
            cur.execute(query, (persona_id, nombre_usuario.strip(), contrasenia_hash,
                                debe_cambiar_contrasenia))
            return cur.fetchone()[0]

    def actualizar_contrasenia(self, usuario_id, contrasenia_hash, debe_cambiar_contrasenia=False,
                               conn=None):
        query = """
            UPDATE usuario SET contrasenia_hash = %s, debe_cambiar_contrasenia = %s
             WHERE id = %s;
        """
        with usar_conexion(conn) as c, c.cursor() as cur:
            cur.execute(query, (contrasenia_hash, debe_cambiar_contrasenia, usuario_id))
            return cur.rowcount == 1

    def registrar_ingreso(self, usuario_id, conn=None):
        with usar_conexion(conn) as c, c.cursor() as cur:
            cur.execute("UPDATE usuario SET ultimo_acceso = NOW() WHERE id = %s;", (usuario_id,))

    def actualizar_estado(self, usuario_id, activo, conn=None):
        with usar_conexion(conn) as c, c.cursor() as cur:
            cur.execute("UPDATE usuario SET activo = %s WHERE id = %s;", (activo, usuario_id))
            return cur.rowcount == 1

    def asignar_rol(self, usuario_id, rol, asignado_por_usuario_id=None, conn=None):
        """Devuelve True si se asignó, False si la cuenta ya tenía el rol.
        Un rol fuera de la lista lo rechaza el CHECK de usuario_rol
        (psycopg.errors.CheckViolation); AuthService lo valida antes."""
        query = """
            INSERT INTO usuario_rol (usuario_id, rol, asignado_por_usuario_id)
            VALUES (%s, %s, %s)
            ON CONFLICT (usuario_id, rol) DO NOTHING;
        """
        with usar_conexion(conn) as c, c.cursor() as cur:
            cur.execute(query, (usuario_id, rol, asignado_por_usuario_id))
            return cur.rowcount == 1

    def quitar_rol(self, usuario_id, rol, conn=None):
        query = "DELETE FROM usuario_rol WHERE usuario_id = %s AND rol = %s;"
        with usar_conexion(conn) as c, c.cursor() as cur:
            cur.execute(query, (usuario_id, rol))
            return cur.rowcount == 1

    def contar_activos_con_rol(self, rol, conn=None):
        """Cuentas activas que tienen el rol. Bloquea esas filas hasta el fin
        de la transacción, para que dos cambios simultáneos no dejen el
        sistema sin administrador."""
        query = """
            SELECT u.id
              FROM usuario u
              JOIN usuario_rol ur ON ur.usuario_id = u.id
             WHERE ur.rol = %s AND u.activo = TRUE
               FOR UPDATE OF u;
        """
        with usar_conexion(conn) as c, c.cursor() as cur:
            cur.execute(query, (rol,))
            return len(cur.fetchall())
