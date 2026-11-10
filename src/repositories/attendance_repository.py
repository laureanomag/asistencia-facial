from config.database import get_connection


class AttendanceRepository:
    def obtener(self, jornada_id, alumno_id):
        """Devuelve (id, entrada, salida) o None si el alumno aún no tiene
        asistencia en la Jornada."""
        query = """
            SELECT id, entrada, salida
              FROM asistencia
             WHERE jornada_id = %s AND alumno_id = %s;
        """
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (jornada_id, alumno_id))
                return cur.fetchone()

    def registrar_entrada(self, jornada_id, alumno_id, ahora, tardanza=False):
        """INSERT con salida NULL. Devuelve True si se creó la fila; False si
        ya existía (la restricción UNIQUE evita duplicados)."""
        query = """
            INSERT INTO asistencia (jornada_id, alumno_id, entrada, salida, tardanza)
            VALUES (%s, %s, %s, NULL, %s)
            ON CONFLICT (jornada_id, alumno_id) DO NOTHING
            RETURNING id;
        """
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (jornada_id, alumno_id, ahora, tardanza))
                return cur.fetchone() is not None

    def registrar_salida(self, jornada_id, alumno_id, ahora):
        """UPDATE de la misma fila, sólo si la salida todavía es NULL."""
        query = """
            UPDATE asistencia
               SET salida = %s
             WHERE jornada_id = %s AND alumno_id = %s AND salida IS NULL;
        """
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (ahora, jornada_id, alumno_id))
                return cur.rowcount == 1

    def recalcular_tardanzas(self, jornada_id, limite):
        """Recalcula la tardanza de todas las asistencias de la Jornada.
        limite = fecha y hora de entrada de la Jornada + tolerancia.
        Es tardanza sólo si la entrada es posterior al límite."""
        query = """
            UPDATE asistencia
               SET tardanza = (entrada > %s)
             WHERE jornada_id = %s;
        """
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (limite, jornada_id))
                return cur.rowcount
    def listar_para_informe(self, jornada_id, usuario_id):
        """Alumnos con asistencia en la Jornada. Vuelve a validar que la
        Jornada pertenezca al usuario (join con jornada.usuario_id)."""
        query = """
            SELECT al.apellido, al.nombre, al.dni, al.libreta, s.entrada, s.salida, s.tardanza
              FROM asistencia s
              JOIN jornada j ON j.id = s.jornada_id
              JOIN alumno al ON al.id = s.alumno_id
             WHERE s.jornada_id = %s AND j.usuario_id = %s;
        """
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (jornada_id, usuario_id))
                return cur.fetchall()
