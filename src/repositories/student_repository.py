from config.database import get_connection


class StudentRepository:
    def registrar_alumno_completo(self, datos, fotos):
        query_alumno = """
            INSERT INTO alumno
                (nombre, apellido, dni, carrera, celular, correo_electronico,
                 fecha_nacimiento, anio_ingreso, domicilio, libreta)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id;
        """
        query_foto = """
            INSERT INTO foto_alumno (alumno_id, angulo, imagen)
            VALUES (%s, %s, %s);
        """

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query_alumno, (
                    datos["nombre"],
                    datos["apellido"],
                    datos["dni"],
                    datos["carrera"],
                    datos["celular"],
                    datos["correo_electronico"],
                    datos["fecha_nacimiento"],
                    datos["anio_ingreso"],
                    datos["domicilio"],
                    datos["libreta"],
                ))
                alumno_id = cur.fetchone()[0]

                for angulo, imagen_bytes in fotos.items():
                    cur.execute(query_foto, (alumno_id, angulo, imagen_bytes))

            return alumno_id

    def obtener_referencias(self):
        """Todas las fotos de referencia: (alumno_id, apellido, nombre, angulo, imagen)."""
        query = """
            SELECT f.alumno_id, a.apellido, a.nombre, f.angulo, f.imagen
              FROM foto_alumno f
              JOIN alumno a ON a.id = f.alumno_id;
        """
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query)
                return cur.fetchall()
