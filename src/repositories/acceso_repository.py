from config.database import usar_conexion

AR = "AT TIME ZONE 'America/Argentina/Buenos_Aires'"


class AccesoRepository:
    """Intentos de ingreso de socios (tabla acceso): permitidos y rechazados.
    Las fechas se devuelven en hora de Argentina."""

    def registrar_permitido(self, socio_id, membresia_id, distancia_facial=None, conn=None):
        """Devuelve (id, fecha_hora)."""
        query = f"""
            INSERT INTO acceso (socio_id, membresia_id, resultado, distancia_facial)
            VALUES (%s, %s, 'permitido', %s)
            RETURNING id, fecha_hora {AR};
        """
        with usar_conexion(conn) as c, c.cursor() as cur:
            cur.execute(query, (socio_id, membresia_id, distancia_facial))
            return cur.fetchone()

    def registrar_rechazo(self, motivo, socio_id=None, membresia_id=None, distancia_facial=None,
                          conn=None):
        """motivo: uno de los códigos del CHECK de acceso.motivo_rechazo.
        socio_id es None cuando no se reconoció a nadie o la persona no es socio.
        Devuelve (id, fecha_hora)."""
        query = f"""
            INSERT INTO acceso (socio_id, membresia_id, resultado, motivo_rechazo, distancia_facial)
            VALUES (%s, %s, 'rechazado', %s, %s)
            RETURNING id, fecha_hora {AR};
        """
        with usar_conexion(conn) as c, c.cursor() as cur:
            cur.execute(query, (socio_id, membresia_id, motivo, distancia_facial))
            return cur.fetchone()

    def ultimos(self, limite=5, conn=None):
        """Panel "Últimos ingresos":
        (id, fecha_hora, resultado, motivo_rechazo, nombre, apellido, plan)."""
        query = f"""
            SELECT a.id, a.fecha_hora {AR}, a.resultado, a.motivo_rechazo,
                   p.nombre, p.apellido, pl.nombre
              FROM acceso a
              LEFT JOIN socio s     ON s.id = a.socio_id
              LEFT JOIN persona p   ON p.id = s.persona_id
              LEFT JOIN membresia m ON m.id = a.membresia_id
              LEFT JOIN plan pl     ON pl.id = m.plan_id
             ORDER BY a.fecha_hora DESC, a.id DESC
             LIMIT %s;
        """
        with usar_conexion(conn) as c, c.cursor() as cur:
            cur.execute(query, (limite,))
            return cur.fetchall()

    def listar_por_socio(self, socio_id, limite=10, conn=None):
        """(fecha_hora, resultado, motivo_rechazo), más recientes primero."""
        query = f"""
            SELECT fecha_hora {AR}, resultado, motivo_rechazo
              FROM acceso
             WHERE socio_id = %s
             ORDER BY fecha_hora DESC, id DESC
             LIMIT %s;
        """
        with usar_conexion(conn) as c, c.cursor() as cur:
            cur.execute(query, (socio_id, limite))
            return cur.fetchall()

    def informe(self, desde, hasta, socio_id=None, conn=None):
        """Accesos entre dos fechas (incluidas, en hora de Argentina):
        (fecha_hora, resultado, motivo_rechazo, dni, nombre, apellido, plan, distancia_facial)."""
        query = f"""
            SELECT a.fecha_hora {AR}, a.resultado, a.motivo_rechazo,
                   p.dni, p.nombre, p.apellido, pl.nombre, a.distancia_facial
              FROM acceso a
              LEFT JOIN socio s     ON s.id = a.socio_id
              LEFT JOIN persona p   ON p.id = s.persona_id
              LEFT JOIN membresia m ON m.id = a.membresia_id
              LEFT JOIN plan pl     ON pl.id = m.plan_id
             WHERE (a.fecha_hora {AR})::date BETWEEN %s AND %s
               AND (%s::int IS NULL OR a.socio_id = %s)
             ORDER BY a.fecha_hora, a.id;
        """
        with usar_conexion(conn) as c, c.cursor() as cur:
            cur.execute(query, (desde, hasta, socio_id, socio_id))
            return cur.fetchall()
