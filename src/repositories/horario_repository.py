from config.database import usar_conexion

ZONA_HORARIA = "America/Argentina/Buenos_Aires"


class HorarioRepository:
    """Horario de atención (horario_atencion) y reloj del sistema.
    dia_semana es ISO: 1 = lunes ... 7 = domingo (date.isoweekday()).
    Un día sin franjas activas es un día cerrado."""

    def franjas_del_dia(self, dia_semana, conn=None):
        """[(hora_apertura, hora_cierre)] activas del día, ordenadas."""
        query = """
            SELECT hora_apertura, hora_cierre
              FROM horario_atencion
             WHERE dia_semana = %s AND activo = TRUE
             ORDER BY hora_apertura;
        """
        with usar_conexion(conn) as c, c.cursor() as cur:
            cur.execute(query, (dia_semana,))
            return cur.fetchall()

    def listar(self, conn=None):
        query = """
            SELECT id, dia_semana, hora_apertura, hora_cierre, activo
              FROM horario_atencion
             ORDER BY dia_semana, hora_apertura;
        """
        with usar_conexion(conn) as c, c.cursor() as cur:
            cur.execute(query)
            return cur.fetchall()

    def crear_franja(self, dia_semana, apertura, cierre, conn=None):
        query = """
            INSERT INTO horario_atencion (dia_semana, hora_apertura, hora_cierre)
            VALUES (%s, %s, %s) RETURNING id;
        """
        with usar_conexion(conn) as c, c.cursor() as cur:
            cur.execute(query, (dia_semana, apertura, cierre))
            return cur.fetchone()[0]

    def actualizar_franja(self, franja_id, apertura, cierre, activo, conn=None):
        """Las franjas no se borran: se desactivan (un día sin franjas activas = cerrado)."""
        query = """
            UPDATE horario_atencion SET hora_apertura = %s, hora_cierre = %s, activo = %s
             WHERE id = %s;
        """
        with usar_conexion(conn) as c, c.cursor() as cur:
            cur.execute(query, (apertura, cierre, activo, franja_id))
            return cur.rowcount == 1

    def ahora(self, conn=None):
        """Fecha y hora actuales de Argentina según el servidor de base de
        datos: el mismo reloj que usa v_socio_estado, así la app y la vista
        nunca discrepan por la hora de la PC. Devuelve un datetime sin zona."""
        with usar_conexion(conn) as c, c.cursor() as cur:
            cur.execute(f"SELECT NOW() AT TIME ZONE '{ZONA_HORARIA}';")
            return cur.fetchone()[0]
