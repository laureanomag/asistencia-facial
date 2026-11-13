from config.database import usar_conexion

COLUMNAS_PERSONA = ("id, dni, nombre, apellido, celular, correo_electronico, "
                    "fecha_nacimiento, domicilio")


class PersonRepository:
    """Acceso a datos de persona (identidad única) y foto_persona (perfil facial).
    Una persona puede ser socio, tener una cuenta de usuario, o ambas cosas:
    sus datos y sus fotos se guardan una sola vez."""

    def crear(self, datos, conn=None):
        """Inserta una persona y devuelve su id. datos: dni (ya normalizado),
        nombre, apellido y opcionales celular, correo_electronico,
        fecha_nacimiento, domicilio."""
        query = """
            INSERT INTO persona
                (dni, nombre, apellido, celular, correo_electronico, fecha_nacimiento, domicilio)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id;
        """
        with usar_conexion(conn) as c, c.cursor() as cur:
            cur.execute(query, (
                datos["dni"],
                datos["nombre"].strip(),
                datos["apellido"].strip(),
                datos.get("celular") or None,
                datos.get("correo_electronico") or None,
                datos.get("fecha_nacimiento") or None,
                datos.get("domicilio") or None,
            ))
            return cur.fetchone()[0]

    def guardar_fotos(self, persona_id, fotos, conn=None):
        """Guarda las fotos {angulo: bytes}. Si la persona ya tenía una foto de
        ese ángulo, se reemplaza: nunca hay más de una por ángulo."""
        query = """
            INSERT INTO foto_persona (persona_id, angulo, imagen)
            VALUES (%s, %s, %s)
            ON CONFLICT (persona_id, angulo)
            DO UPDATE SET imagen = EXCLUDED.imagen, creado_en = NOW();
        """
        with usar_conexion(conn) as c, c.cursor() as cur:
            for angulo, imagen in fotos.items():
                if imagen is not None:
                    cur.execute(query, (persona_id, angulo, imagen))

    def contar_fotos(self, persona_id, conn=None):
        with usar_conexion(conn) as c, c.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM foto_persona WHERE persona_id = %s;", (persona_id,))
            return cur.fetchone()[0]

    def obtener_por_id(self, persona_id, conn=None):
        with usar_conexion(conn) as c, c.cursor() as cur:
            cur.execute(f"SELECT {COLUMNAS_PERSONA} FROM persona WHERE id = %s;", (persona_id,))
            return cur.fetchone()

    def obtener_por_dni(self, dni, conn=None):
        """dni ya normalizado (solo dígitos)."""
        with usar_conexion(conn) as c, c.cursor() as cur:
            cur.execute(f"SELECT {COLUMNAS_PERSONA} FROM persona WHERE dni = %s;", (dni,))
            return cur.fetchone()

    def obtener_roles(self, persona_id, conn=None):
        """Relaciones de la persona con el gimnasio y con el sistema:
        {'socio_id', 'socio_activo', 'usuario_id', 'usuario_activo', 'roles'}.
        Los valores son None (o lista vacía) cuando no existe la relación."""
        query = """
            SELECT s.id, s.activo, u.id, u.activo,
                   COALESCE(ARRAY_AGG(ur.rol ORDER BY ur.rol)
                            FILTER (WHERE ur.rol IS NOT NULL), '{}')
              FROM persona p
              LEFT JOIN socio s        ON s.persona_id = p.id
              LEFT JOIN usuario u      ON u.persona_id = p.id
              LEFT JOIN usuario_rol ur ON ur.usuario_id = u.id
             WHERE p.id = %s
             GROUP BY s.id, s.activo, u.id, u.activo;
        """
        with usar_conexion(conn) as c, c.cursor() as cur:
            cur.execute(query, (persona_id,))
            fila = cur.fetchone()
        if fila is None:
            return None
        socio_id, socio_activo, usuario_id, usuario_activo, roles = fila
        return {
            "socio_id": socio_id,
            "socio_activo": socio_activo,
            "usuario_id": usuario_id,
            "usuario_activo": usuario_activo,
            "roles": list(roles),
        }

    def firma_referencias(self, conn=None):
        """(cantidad, último id, última modificación) de foto_persona. Cambia
        cuando se agrega, reemplaza o borra una foto: el reconocimiento la
        compara para recargar las referencias solo cuando hace falta."""
        query = "SELECT COUNT(*), COALESCE(MAX(id), 0), MAX(creado_en) FROM foto_persona;"
        with usar_conexion(conn) as c, c.cursor() as cur:
            cur.execute(query)
            return tuple(cur.fetchone())

    def obtener_referencias(self, conn=None):
        """Fotos de referencia para el reconocimiento facial:
        (persona_id, apellido, nombre, angulo, imagen).
        Se incluyen todas las personas con fotos, aunque estén dadas de baja:
        el rostro identifica a la persona y las reglas de negocio deciden si
        puede entrar. Excluirlas haría que su rostro se confunda con otra
        persona parecida."""
        query = """
            SELECT f.persona_id, p.apellido, p.nombre, f.angulo, f.imagen
              FROM foto_persona f
              JOIN persona p ON p.id = f.persona_id
             ORDER BY f.persona_id, f.angulo;
        """
        with usar_conexion(conn) as c, c.cursor() as cur:
            cur.execute(query)
            return cur.fetchall()
