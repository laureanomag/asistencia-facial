from config.database import usar_conexion

AR = "AT TIME ZONE 'America/Argentina/Buenos_Aires'"
AUSENCIAS = ("licencia_vacaciones", "permiso")

# Una licencia o un permiso en un día sin turno crea una fila de jornada (su alta
# queda en jornada_cambio con el mismo estado antes y después). Si después se
# anula, la fila vuelve a 'jornada' (no se borra nada), pero no era un turno:
# esta condición la deja afuera de los turnos. Si más tarde se carga un turno a
# esa hora, se reutiliza la fila y vuelve a contar.
SIN_ANULADAS = """
    NOT (j.estado = 'jornada'
         AND EXISTS (SELECT 1 FROM jornada_cambio c0
                      WHERE c0.jornada_id = j.id AND c0.estado_anterior = c0.estado_nuevo
                        AND c0.estado_nuevo <> 'jornada')
         AND (SELECT c1.estado_anterior FROM jornada_cambio c1
               WHERE c1.jornada_id = j.id ORDER BY c1.cambiado_en DESC, c1.id DESC LIMIT 1)
             <> 'jornada')
"""


class JornadaRepository:
    """Turnos del personal (jornada), licencias y permisos, y su historial de
    cambios (jornada_cambio: quién lo aprobó, cuándo y por qué)."""

    def listar(self, desde, hasta, usuario_id=None, conn=None):
        """(id, usuario_id, nombre, apellido, fecha, horario_entrada, horario_salida, estado),
        ordenadas por fecha, hora y empleado."""
        query = f"""
            SELECT j.id, j.usuario_id, p.nombre, p.apellido, j.fecha, j.horario_entrada,
                   j.horario_salida, j.estado
              FROM jornada j
              JOIN usuario u      ON u.id = j.usuario_id
              LEFT JOIN persona p ON p.id = u.persona_id
             WHERE j.fecha BETWEEN %s AND %s
               AND (%s::int IS NULL OR j.usuario_id = %s)
               AND {SIN_ANULADAS}
             ORDER BY j.fecha, j.horario_entrada, p.apellido, p.nombre;
        """
        with usar_conexion(conn) as c, c.cursor() as cur:
            cur.execute(query, (desde, hasta, usuario_id, usuario_id))
            return cur.fetchall()

    def del_dia(self, usuario_id, fecha, conn=None):
        """Todas las filas del día, también las anuladas sin turno:
        (id, horario_entrada, horario_salida, estado, anulada)."""
        query = f"""
            SELECT j.id, j.horario_entrada, j.horario_salida, j.estado, NOT ({SIN_ANULADAS})
              FROM jornada j
             WHERE j.usuario_id = %s AND j.fecha = %s
             ORDER BY j.horario_entrada;
        """
        with usar_conexion(conn) as c, c.cursor() as cur:
            cur.execute(query, (usuario_id, fecha))
            return cur.fetchall()

    def crear(self, usuario_id, fecha, entrada, salida, estado="jornada", conn=None):
        query = """
            INSERT INTO jornada (usuario_id, fecha, horario_entrada, horario_salida, estado)
            VALUES (%s, %s, %s, %s, %s) RETURNING id;
        """
        with usar_conexion(conn) as c, c.cursor() as cur:
            cur.execute(query, (usuario_id, fecha, entrada, salida, estado))
            return cur.fetchone()[0]

    def crear_aprobada(self, usuario_id, fecha, entrada, salida, estado, motivo, aprobado_por, conn=None):
        """Licencia o permiso en un día sin turno: crea la fila y registra el alta
        en jornada_cambio (mismo estado antes y después) con quién y cuándo."""
        jornada_id = self.crear(usuario_id, fecha, entrada, salida, estado, conn=conn)
        with usar_conexion(conn) as c, c.cursor() as cur:
            cur.execute("""
                INSERT INTO jornada_cambio
                    (jornada_id, fecha_anterior, entrada_anterior, salida_anterior, estado_anterior,
                     fecha_nueva, entrada_nueva, salida_nueva, estado_nuevo, motivo, cambiado_por_usuario_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
            """, (jornada_id, fecha, entrada, salida, estado, fecha, entrada, salida, estado,
                  motivo or None, aprobado_por))
        return jornada_id

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

    def ultimo_cambio(self, jornada_id, conn=None):
        """(fecha_anterior, entrada_anterior, salida_anterior, estado_anterior, estado_nuevo,
        cambiado_en, cambiado_por_usuario_id) o None."""
        query = f"""
            SELECT fecha_anterior, entrada_anterior, salida_anterior, estado_anterior, estado_nuevo,
                   cambiado_en {AR}, cambiado_por_usuario_id
              FROM jornada_cambio WHERE jornada_id = %s
             ORDER BY cambiado_en DESC, id DESC LIMIT 1;
        """
        with usar_conexion(conn) as c, c.cursor() as cur:
            cur.execute(query, (jornada_id,))
            return cur.fetchone()

    def ausencias(self, desde, hasta, usuario_id=None, conn=None):
        """Licencias y permisos con su aprobación (el último cambio de cada fila):
        (jornada_id, usuario_id, nombre, apellido, fecha, entrada, salida, estado,
         aprobado_en, aprobado_por, motivo)."""
        query = f"""
            SELECT j.id, j.usuario_id, p.nombre, p.apellido, j.fecha, j.horario_entrada,
                   j.horario_salida, j.estado, c.cambiado_en {AR},
                   COALESCE(pa.nombre || ' ' || pa.apellido, ua.nombre_usuario), c.motivo
              FROM jornada j
              JOIN usuario u       ON u.id = j.usuario_id
              LEFT JOIN persona p  ON p.id = u.persona_id
              LEFT JOIN LATERAL (SELECT * FROM jornada_cambio c
                                  WHERE c.jornada_id = j.id
                                  ORDER BY c.cambiado_en DESC, c.id DESC LIMIT 1) c ON TRUE
              LEFT JOIN usuario ua ON ua.id = c.cambiado_por_usuario_id
              LEFT JOIN persona pa ON pa.id = ua.persona_id
             WHERE j.fecha BETWEEN %s AND %s
               AND (%s::int IS NULL OR j.usuario_id = %s)
               AND j.estado IN ('licencia_vacaciones', 'permiso')
             ORDER BY j.fecha, j.horario_entrada, p.apellido;
        """
        with usar_conexion(conn) as c, c.cursor() as cur:
            cur.execute(query, (desde, hasta, usuario_id, usuario_id))
            return cur.fetchall()

    def mismo_lote(self, jornada_id, conn=None):
        """Ids de las licencias o permisos aprobados juntos con esta fila (mismo
        empleado, mismo estado y el mismo cambio: misma hora y misma persona)."""
        query = """
            WITH ult AS (
                SELECT DISTINCT ON (c.jornada_id) c.jornada_id, c.cambiado_en, c.cambiado_por_usuario_id
                  FROM jornada_cambio c
                 ORDER BY c.jornada_id, c.cambiado_en DESC, c.id DESC)
            SELECT j.id
              FROM jornada j
              JOIN jornada base ON base.id = %s
              JOIN ult u        ON u.jornada_id = j.id
              JOIN ult ub       ON ub.jornada_id = base.id
             WHERE j.usuario_id = base.usuario_id AND j.estado = base.estado
               AND j.estado IN ('licencia_vacaciones', 'permiso')
               AND u.cambiado_en = ub.cambiado_en
               AND u.cambiado_por_usuario_id IS NOT DISTINCT FROM ub.cambiado_por_usuario_id
             ORDER BY j.fecha, j.horario_entrada;
        """
        with usar_conexion(conn) as c, c.cursor() as cur:
            cur.execute(query, (jornada_id,))
            return [fila[0] for fila in cur.fetchall()]

    def cambios(self, jornada_id, conn=None):
        """Historial: (cambiado_en, fecha_anterior, entrada_anterior, salida_anterior,
        estado_anterior, fecha_nueva, entrada_nueva, salida_nueva, estado_nuevo, motivo)."""
        query = f"""
            SELECT cambiado_en {AR}, fecha_anterior,
                   entrada_anterior, salida_anterior, estado_anterior, fecha_nueva, entrada_nueva,
                   salida_nueva, estado_nuevo, motivo
              FROM jornada_cambio WHERE jornada_id = %s ORDER BY cambiado_en, id;
        """
        with usar_conexion(conn) as c, c.cursor() as cur:
            cur.execute(query, (jornada_id,))
            return cur.fetchall()
