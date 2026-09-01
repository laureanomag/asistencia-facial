from config.database import get_connection


class UserRepository:
    def find_by_credentials(self, identificador, contrasenia):
        query = """
            SELECT id, nombre_usuario, correo_electronico, dni, cuil
            FROM usuario
            WHERE contrasenia = %s
              AND (
                    nombre_usuario = %s
                 OR correo_electronico = %s
                 OR dni = %s
                 OR cuil = %s
              )
            LIMIT 1;
        """
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    query,
                    (contrasenia, identificador, identificador, identificador, identificador),
                )
                return cur.fetchone()
