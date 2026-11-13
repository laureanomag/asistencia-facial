from config.database import usar_conexion


class JornadaRepository:
    """Turnos del personal (jornada) y su historial de cambios (jornada_cambio)."""

    def listar(self, desde, hasta, usuario_id=None, conn=None):
        """(id, usuario_id, nombre, apellido, fecha, horario_entrada, horario_salida, estado),
        ordenadas por fecha, hora y empleado."""
        query = """
            SELECT j.id, j.usuario_id, p.nombre, p.apellido, j.fecha, j.horario_entrada,
                   j.horario_salida, j.estado
              FROM jornada j
              JOIN usuario u      ON u.id = j.usuario_id
              LEFT JOIN persona p ON p.id = u.persona_id
             WHERE j.fecha BETWEEN %s AND %s
               AND (%s::int IS NULL OR j.usuario_id = %s)
             ORDER BY j.fecha, j.horario_entrada, p.apellido, p.nombre;
        """
        with usar_conexion(conn) as c, c.cursor() as cur:
            cur.execute(query, (desde, hasta, usuario_id, usuario_id))
            return cur.fetchall()

    def crear(self, usuario_id, fecha, entrada, salida, estado="jornada", conn=None):
        query = """
            INSERT INTO jornada (usuario_id, fecha, horario_entrada, horario_salida, estado)
            VALUES (%s, %s, %s, %s, %s) RETURNING id;
        """
        with usar_conexion(conn) as c, c.cursor() as cur:
            cur.execute(query, (usuario_id, fecha, entrada, salida, estado))
            return cur.fetchone()[0]

    def obtener(self, jornada_id, bloquear=False, conn=None):
        query = ("SELECT id, usuario_id, fecha, horario_entrada, horario_salida, estado "
                 "FROM jornada WHERE id = %s" + (" FOR UPDATE;" if bloquear else ";"))
        with usar_conexion(conn) as c, c.cursor() as cur:
            cur.execute(query, (jornada_id,))
            return cur.fetchone()

    def cambiar(self, jornada_id, fecha, entrada, salida, estado, motivo, usuario_id, conn=None):
        """Cambia el turno y guarda el valor anterior en jornada_cambio."""
        with usar_conexion(conn) as c, c.cursor() as cur:
            cur.execute("""
                INSERT INTO jornada_cambio
                    (jornada_id, fecha_anterior, entrada_anterior, salida_anterior, estado_anterior,
                     fecha_nueva, entrada_nueva, salida_nueva, estado_nuevo, motivo, cambiado_por_usuario_id)
                SELECT id, fecha, horario_entrada, horario_salida, estado, %s, %s, %s, %s, %s, %s
                  FROM jornada WHERE id = %s;
            """, (fecha, entrada, salida, estado, motivo or None, usuario_id, jornada_id))
            cur.execute("""
                UPDATE jornada SET fecha = %s, horario_entrada = %s, horario_salida = %s, estado = %s
                 WHERE id = %s;
            """, (fecha, entrada, salida, estado, jornada_id))
            return cur.rowcount == 1

    def cambios(self, jornada_id, conn=None):
        """Historial: (cambiado_en, fecha_anterior, entrada_anterior, salida_anterior,
        estado_anterior, fecha_nueva, entrada_nueva, salida_nueva, estado_nuevo, motivo)."""
        query = """
            SELECT cambiado_en AT TIME ZONE 'America/Argentina/Buenos_Aires', fecha_anterior,
                   entrada_anterior, salida_anterior, estado_anterior, fecha_nueva, entrada_nueva,
                   salida_nueva, estado_nuevo, motivo
              FROM jornada_cambio WHERE jornada_id = %s ORDER BY cambiado_en, id;
        """
        with usar_conexion(conn) as c, c.cursor() as cur:
            cur.execute(query, (jornada_id,))
            return cur.fetchall()
