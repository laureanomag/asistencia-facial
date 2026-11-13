from config.database import usar_conexion

AR = "AT TIME ZONE 'America/Argentina/Buenos_Aires'"
HOY = f"(NOW() {AR})::date"


class PanelRepository:
    """Consultas de los indicadores del Panel del administrador. Todo se
    calcula en el momento desde la base (hora de Argentina)."""

    def _uno(self, query, params=(), conn=None):
        with usar_conexion(conn) as c, c.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchone()

    def _todos(self, query, params=(), conn=None):
        with usar_conexion(conn) as c, c.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchall()

    def ingresos(self, conn=None):
        """(ingresos permitidos hoy, ingresos permitidos desde el lunes)."""
        return tuple(self._uno(f"""
            SELECT COUNT(*) FILTER (WHERE (fecha_hora {AR})::date = {HOY}),
                   COUNT(*) FILTER (WHERE (fecha_hora {AR})::date >= DATE_TRUNC('week', {HOY})::date)
              FROM acceso
             WHERE resultado = 'permitido';""", conn=conn))

    def socios_vigentes(self, conn=None):
        return self._uno("SELECT COUNT(*) FROM v_socio_estado WHERE estado_membresia = 'vigente';",
                         conn=conn)[0]

    def por_vencer(self, dias=5, conn=None):
        """(nombre, apellido, plan, fecha_vencimiento, dias_para_vencer) de las
        membresías vigentes que vencen en `dias` días o menos."""
        return self._todos("""
            SELECT nombre, apellido, plan, fecha_vencimiento, dias_para_vencer
              FROM v_socio_estado
             WHERE estado_membresia = 'vigente' AND dias_para_vencer <= %s
             ORDER BY dias_para_vencer, apellido, nombre;""", (dias,), conn=conn)

    def deben(self, conn=None):
        """(nombre, apellido, saldo, estado_membresia) de los socios con saldo
        pendiente o con la membresía vencida (estado_contable = 'debe')."""
        return self._todos("""
            SELECT nombre, apellido, saldo, estado_membresia
              FROM v_socio_estado
             WHERE estado_contable = 'debe'
             ORDER BY apellido, nombre;""", conn=conn)

    def recaudacion_mes(self, conn=None):
        return self._uno(f"""
            SELECT COALESCE(SUM(monto), 0)
              FROM pago
             WHERE DATE_TRUNC('month', fecha_pago {AR}) = DATE_TRUNC('month', NOW() {AR});""",
                         conn=conn)[0]

    def rechazos_hoy(self, conn=None):
        """[(motivo_rechazo, cantidad)] de hoy, de mayor a menor."""
        return self._todos(f"""
            SELECT motivo_rechazo, COUNT(*)
              FROM acceso
             WHERE resultado = 'rechazado' AND (fecha_hora {AR})::date = {HOY}
             GROUP BY motivo_rechazo
             ORDER BY COUNT(*) DESC, motivo_rechazo;""", conn=conn)

    def ingresos_por_hora(self, dias=30, conn=None):
        """{hora: cantidad} de ingresos permitidos en los últimos `dias` días."""
        filas = self._todos(f"""
            SELECT EXTRACT(HOUR FROM fecha_hora {AR})::int, COUNT(*)
              FROM acceso
             WHERE resultado = 'permitido'
               AND (fecha_hora {AR})::date > {HOY} - %s
             GROUP BY 1;""", (dias,), conn=conn)
        return dict(filas)

    def socios_por_plan(self, conn=None):
        """[(plan, socios con membresía vigente de ese plan)] de los planes activos."""
        return self._todos("""
            SELECT pl.nombre, COUNT(v.socio_id)
              FROM plan pl
              LEFT JOIN v_socio_estado v
                     ON v.plan = pl.nombre AND v.estado_membresia = 'vigente'
             WHERE pl.activo
             GROUP BY pl.id, pl.nombre
             ORDER BY pl.id;""", conn=conn)

    def empleados_trabajando(self, conn=None):
        """(nombre, apellido, nombre_usuario, entrada, roles) con fichaje abierto."""
        return self._todos(f"""
            SELECT p.nombre, p.apellido, u.nombre_usuario, f.entrada {AR},
                   STRING_AGG(ur.rol, ',' ORDER BY ur.rol)
              FROM fichaje f
              JOIN usuario u           ON u.id = f.usuario_id
              LEFT JOIN persona p      ON p.id = u.persona_id
              LEFT JOIN usuario_rol ur ON ur.usuario_id = u.id
             WHERE f.salida IS NULL
             GROUP BY f.id, p.nombre, p.apellido, u.nombre_usuario, f.entrada
             ORDER BY f.entrada;""", conn=conn)
