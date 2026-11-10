from config.database import get_connection


class JornadaRepository:
    """Acceso a la tabla jornada. Toda operación sobre una Jornada existente
    exige también el usuario_id, para que un usuario sólo toque las suyas."""

    def crear(self, usuario_id, fecha, horario_entrada, horario_salida, catedra):
        query = """
            INSERT INTO jornada
                (fecha, horario_entrada, horario_salida, usuario_id, catedra)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id;
        """
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (fecha, horario_entrada, horario_salida, usuario_id, catedra))
                return cur.fetchone()[0]

    def actualizar(self, jornada_id, usuario_id, horario_entrada, horario_salida, catedra):
        query = """
            UPDATE jornada
               SET horario_entrada = %s, horario_salida = %s, catedra = %s
             WHERE id = %s AND usuario_id = %s;
        """
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (horario_entrada, horario_salida, catedra, jornada_id, usuario_id))
                return cur.rowcount == 1

    def listar_por_usuario(self, usuario_id):
        """Devuelve (id, fecha, catedra, horario_entrada, horario_salida) de
        todas las Jornadas del usuario, de la más reciente a la más antigua."""
        query = """
            SELECT id, fecha, catedra, horario_entrada, horario_salida
              FROM jornada
             WHERE usuario_id = %s
             ORDER BY fecha DESC, horario_entrada DESC;
        """
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (usuario_id,))
                return cur.fetchall()

    def obtener_de_usuario(self, jornada_id, usuario_id):
        """Devuelve la Jornada sólo si pertenece al usuario; si no, None."""
        query = """
            SELECT id, fecha, catedra, horario_entrada, horario_salida
              FROM jornada
             WHERE id = %s AND usuario_id = %s;
        """
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (jornada_id, usuario_id))
                return cur.fetchone()
