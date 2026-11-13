from config.database import usar_conexion
from repositories.jornada_repository import SIN_ANULADAS

AR = "AT TIME ZONE 'America/Argentina/Buenos_Aires'"


class FichajeRepository:
    """Entradas y salidas del personal (fichaje) y sus jornadas del día.
    Las fechas y horas se devuelven en hora de Argentina."""

    def jornadas_del_dia(self, usuario_id, fecha, conn=None):
        """(id, horario_entrada, horario_salida, estado) del empleado en esa fecha
        (turnos, licencias y permisos; sin las licencias o permisos anulados en días sin turno)."""
        query = f"""
            SELECT j.id, j.horario_entrada, j.horario_salida, j.estado
              FROM jornada j
             WHERE j.usuario_id = %s AND j.fecha = %s AND {SIN_ANULADAS}
             ORDER BY j.horario_entrada;
        """
        with usar_conexion(conn) as c, c.cursor() as cur:
            cur.execute(query, (usuario_id, fecha))
            return cur.fetchall()

    def fichaje_abierto(self, usuario_id, bloquear=False, conn=None):
        """(id, entrada) de la entrada sin salida, o None. Con bloquear=True
        la fila queda bloqueada hasta el fin de la transacción (confirmación)."""
        query = f"""
            SELECT id, entrada {AR}
              FROM fichaje
             WHERE usuario_id = %s AND salida IS NULL
        """ + (" FOR UPDATE" if bloquear else "") + ";"
        with usar_conexion(conn) as c, c.cursor() as cur:
            cur.execute(query, (usuario_id,))
            return cur.fetchone()

    def registrar_entrada(self, usuario_id, jornada_id=None, conn=None):
        """Devuelve (id, entrada). El índice único parcial de la base impide
        una segunda entrada abierta del mismo empleado."""
        query = f"""
            INSERT INTO fichaje (usuario_id, jornada_id)
            VALUES (%s, %s)
            RETURNING id, entrada {AR};
        """
        with usar_conexion(conn) as c, c.cursor() as cur:
            cur.execute(query, (usuario_id, jornada_id))
            return cur.fetchone()

    def registrar_salida(self, fichaje_id, conn=None):
        """Devuelve la hora de salida, o None si el fichaje ya estaba cerrado."""
        query = f"""
            UPDATE fichaje SET salida = NOW()
             WHERE id = %s AND salida IS NULL
            RETURNING salida {AR};
        """
        with usar_conexion(conn) as c, c.cursor() as cur:
            cur.execute(query, (fichaje_id,))
            fila = cur.fetchone()
            return fila[0] if fila else None

    def listar(self, desde, hasta, usuario_id=None, conn=None):
        """Fichajes con entrada entre dos fechas (incluidas):
        (id, usuario_id, nombre, apellido, nombre_usuario, entrada, salida,
         jornada_id, horario_entrada, horario_salida)."""
        query = f"""
            SELECT f.id, f.usuario_id, p.nombre, p.apellido, u.nombre_usuario,
                   f.entrada {AR}, f.salida {AR}, f.jornada_id, j.horario_entrada, j.horario_salida
              FROM fichaje f
              JOIN usuario u      ON u.id = f.usuario_id
              LEFT JOIN persona p ON p.id = u.persona_id
              LEFT JOIN jornada j ON j.id = f.jornada_id
             WHERE (f.entrada {AR})::date BETWEEN %s AND %s
               AND (%s::int IS NULL OR f.usuario_id = %s)
             ORDER BY f.entrada DESC, f.id DESC;
        """
        with usar_conexion(conn) as c, c.cursor() as cur:
            cur.execute(query, (desde, hasta, usuario_id, usuario_id))
            return cur.fetchall()

    def ultimos(self, limite=4, conn=None):
        """Panel "Fichajes del personal" de Control de acceso, más recientes primero:
        (id, nombre, apellido, entrada, salida, jornada_id, horario_entrada)."""
        query = f"""
            SELECT f.id, p.nombre, p.apellido, f.entrada {AR}, f.salida {AR},
                   f.jornada_id, j.horario_entrada
              FROM fichaje f
              JOIN usuario u      ON u.id = f.usuario_id
              LEFT JOIN persona p ON p.id = u.persona_id
              LEFT JOIN jornada j ON j.id = f.jornada_id
             ORDER BY GREATEST(f.entrada, COALESCE(f.salida, f.entrada)) DESC, f.id DESC
             LIMIT %s;
        """
        with usar_conexion(conn) as c, c.cursor() as cur:
            cur.execute(query, (limite,))
            return cur.fetchall()
