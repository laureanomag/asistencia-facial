from config.database import usar_conexion

COLUMNAS_SOCIO = ("id, persona_id, contacto_emergencia_nombre, contacto_emergencia_telefono, "
                  "fecha_alta, activo, fecha_baja, registrado_por_usuario_id")


class SocioRepository:
    """Acceso a datos de socio: la relación de una persona con el gimnasio
    como cliente. Dar de baja o reactivar no toca la persona ni sus fotos."""

    def crear(self, persona_id, contacto_emergencia_telefono, contacto_emergencia_nombre=None,
              registrado_por_usuario_id=None, conn=None):
        query = """
            INSERT INTO socio
                (persona_id, contacto_emergencia_nombre, contacto_emergencia_telefono,
                 registrado_por_usuario_id)
            VALUES (%s, %s, %s, %s)
            RETURNING id;
        """
        with usar_conexion(conn) as c, c.cursor() as cur:
            cur.execute(query, (persona_id, contacto_emergencia_nombre or None,
                                contacto_emergencia_telefono, registrado_por_usuario_id))
            return cur.fetchone()[0]

    def obtener_por_id(self, socio_id, bloquear=False, conn=None):
        """Con bloquear=True la fila del socio queda bloqueada hasta el fin de
        la transacción: dos confirmaciones simultáneas del mismo socio se
        evalúan una después de la otra (no se pasan los límites)."""
        query = f"SELECT {COLUMNAS_SOCIO} FROM socio WHERE id = %s"
        query += " FOR UPDATE;" if bloquear else ";"
        with usar_conexion(conn) as c, c.cursor() as cur:
            cur.execute(query, (socio_id,))
            return cur.fetchone()

    def obtener_por_persona(self, persona_id, conn=None):
        with usar_conexion(conn) as c, c.cursor() as cur:
            cur.execute(f"SELECT {COLUMNAS_SOCIO} FROM socio WHERE persona_id = %s;", (persona_id,))
            return cur.fetchone()

    def dar_baja(self, socio_id, fecha_baja, conn=None):
        """Devuelve True si el socio estaba activo y quedó dado de baja."""
        query = """
            UPDATE socio SET activo = FALSE, fecha_baja = %s
             WHERE id = %s AND activo = TRUE;
        """
        with usar_conexion(conn) as c, c.cursor() as cur:
            cur.execute(query, (fecha_baja, socio_id))
            return cur.rowcount == 1

    def reactivar(self, socio_id, conn=None):
        """Devuelve True si el socio estaba dado de baja y quedó activo."""
        query = """
            UPDATE socio SET activo = TRUE, fecha_baja = NULL
             WHERE id = %s AND activo = FALSE;
        """
        with usar_conexion(conn) as c, c.cursor() as cur:
            cur.execute(query, (socio_id,))
            return cur.rowcount == 1

    def obtener_estado(self, socio_id, conn=None):
        """Estado del socio según la vista v_socio_estado, como dict con las
        claves de COLUMNAS_ESTADO, o None si no existe o está dado de baja.
        Membresía actual = la vigente hoy; si no hay, la más reciente.
        estado_membresia: vigente | agotada | no_vigente | vencida | sin_membresia.
        estado_contable: al_dia | por_vencer | debe | sin_pase.
        Los límites y accesos_restantes son None cuando el plan no tiene tope."""
        query = f"SELECT {', '.join(COLUMNAS_ESTADO)} FROM v_socio_estado WHERE socio_id = %s;"
        with usar_conexion(conn) as c, c.cursor() as cur:
            cur.execute(query, (socio_id,))
            fila = cur.fetchone()
        return dict(zip(COLUMNAS_ESTADO, fila)) if fila else None


COLUMNAS_ESTADO = (
    "socio_id", "dni", "nombre", "apellido", "contacto_emergencia_telefono",
    "membresia_id", "plan", "fecha_inicio", "fecha_vencimiento", "dias_para_vencer",
    "accesos_incluidos", "accesos_usados", "accesos_restantes", "accesos_hoy",
    "max_ingresos_diarios", "dias_entrenados_semana", "max_dias_semanales",
    "ultimo_pago", "precio", "pagado", "saldo", "estado_membresia", "estado_contable",
)
