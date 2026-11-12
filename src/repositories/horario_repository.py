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

    def ahora(self, conn=None):
        """Fecha y hora actuales de Argentina según el servidor de base de
        datos: el mismo reloj que usa v_socio_estado, así la app y la vista
        nunca discrepan por la hora de la PC. Devuelve un datetime sin zona."""
        with usar_conexion(conn) as c, c.cursor() as cur:
            cur.execute(f"SELECT NOW() AT TIME ZONE '{ZONA_HORARIA}';")
            return cur.fetchone()[0]
