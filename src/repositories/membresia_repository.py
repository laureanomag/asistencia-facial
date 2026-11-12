from config.database import usar_conexion

# vigencia se lee como texto ('1 mon', '1 day'): psycopg convierte un
# INTERVAL de 1 mes en timedelta(days=30), que no sirve para calcular
# vencimientos. Por eso fecha_vencimiento se calcula siempre en SQL.
COLUMNAS_PLAN = ("id, nombre, vigencia::text, entrenamientos_mensuales, max_dias_semanales, "
                 "max_ingresos_diarios, precio, activo")


class MembresiaRepository:
    """Planes, membresías (alta y renovación) y pagos."""

    # --- Planes ---

    def listar_planes(self, solo_activos=True, conn=None):
        query = f"SELECT {COLUMNAS_PLAN} FROM plan"
        if solo_activos:
            query += " WHERE activo = TRUE"
        query += " ORDER BY id;"
        with usar_conexion(conn) as c, c.cursor() as cur:
            cur.execute(query)
            return cur.fetchall()

    def obtener_plan(self, plan_id, conn=None):
        with usar_conexion(conn) as c, c.cursor() as cur:
            cur.execute(f"SELECT {COLUMNAS_PLAN} FROM plan WHERE id = %s;", (plan_id,))
            return cur.fetchone()

    def actualizar_plan(self, plan_id, precio, entrenamientos_mensuales, max_dias_semanales,
                        max_ingresos_diarios, activo, conn=None):
        """Cambia el precio y los límites del plan. Las membresías ya vendidas
        conservan las condiciones que copiaron al venderse."""
        query = """
            UPDATE plan
               SET precio = %s, entrenamientos_mensuales = %s, max_dias_semanales = %s,
                   max_ingresos_diarios = %s, activo = %s
             WHERE id = %s;
        """
        with usar_conexion(conn) as c, c.cursor() as cur:
            cur.execute(query, (precio, entrenamientos_mensuales, max_dias_semanales,
                                max_ingresos_diarios, activo, plan_id))
            return cur.rowcount == 1

    def calcular_vencimiento(self, plan_id, fecha_inicio, conn=None):
        """fecha_inicio + plan.vigencia calculado por PostgreSQL
        (20/10 -> 20/11; 31/01 -> 28/02, o 29/02 en año bisiesto)."""
        query = "SELECT (%s::date + vigencia)::date FROM plan WHERE id = %s;"
        with usar_conexion(conn) as c, c.cursor() as cur:
            cur.execute(query, (fecha_inicio, plan_id))
            fila = cur.fetchone()
            return fila[0] if fila else None

    # --- Membresías ---

    def crear(self, socio_id, plan_id, fecha_inicio, registrado_por_usuario_id=None, conn=None):
        """Crea la membresía copiando del plan el precio y los límites vigentes.
        Devuelve (id, fecha_vencimiento, precio)."""
        query = """
            INSERT INTO membresia
                (socio_id, plan_id, fecha_inicio, fecha_vencimiento, precio,
                 entrenamientos_mensuales, max_dias_semanales, max_ingresos_diarios,
                 registrado_por_usuario_id)
            SELECT %s, p.id, %s::date, (%s::date + p.vigencia)::date, p.precio,
                   p.entrenamientos_mensuales, p.max_dias_semanales, p.max_ingresos_diarios, %s
              FROM plan p
             WHERE p.id = %s
            RETURNING id, fecha_vencimiento, precio;
        """
        with usar_conexion(conn) as c, c.cursor() as cur:
            cur.execute(query, (socio_id, fecha_inicio, fecha_inicio, registrado_por_usuario_id,
                                plan_id))
            fila = cur.fetchone()
            if fila is None:
                raise ValueError(f"Plan inexistente: {plan_id}")
            return fila

    def obtener(self, membresia_id, conn=None):
        query = """
            SELECT m.id, m.socio_id, m.plan_id, p.nombre, m.fecha_inicio, m.fecha_vencimiento,
                   m.precio, m.entrenamientos_mensuales, m.max_dias_semanales,
                   m.max_ingresos_diarios, m.estado
              FROM membresia m
              JOIN plan p ON p.id = m.plan_id
             WHERE m.id = %s;
        """
        with usar_conexion(conn) as c, c.cursor() as cur:
            cur.execute(query, (membresia_id,))
            return cur.fetchone()

    def listar_por_socio(self, socio_id, conn=None):
        query = """
            SELECT m.id, p.nombre, m.fecha_inicio, m.fecha_vencimiento, m.precio, m.estado,
                   COALESCE(SUM(pg.monto), 0) AS pagado
              FROM membresia m
              JOIN plan p ON p.id = m.plan_id
              LEFT JOIN pago pg ON pg.membresia_id = m.id
             WHERE m.socio_id = %s
             GROUP BY m.id, p.nombre
             ORDER BY m.fecha_inicio DESC, m.id DESC;
        """
        with usar_conexion(conn) as c, c.cursor() as cur:
            cur.execute(query, (socio_id,))
            return cur.fetchall()

    def actualizar_estado(self, membresia_id, estado, conn=None):
        """estado: 'activa', 'suspendida' o 'cancelada' (lo controla el CHECK)."""
        with usar_conexion(conn) as c, c.cursor() as cur:
            cur.execute("UPDATE membresia SET estado = %s WHERE id = %s;", (estado, membresia_id))
            return cur.rowcount == 1

    # --- Pagos ---

    def registrar_pago(self, membresia_id, monto, metodo, registrado_por_usuario_id=None, conn=None):
        """metodo: efectivo, debito, credito, transferencia o mercado_pago (CHECK).
        Devuelve (id, fecha_pago) con la fecha en hora de Argentina."""
        query = """
            INSERT INTO pago (membresia_id, monto, metodo, registrado_por_usuario_id)
            VALUES (%s, %s, %s, %s)
            RETURNING id, fecha_pago AT TIME ZONE 'America/Argentina/Buenos_Aires';
        """
        with usar_conexion(conn) as c, c.cursor() as cur:
            cur.execute(query, (membresia_id, monto, metodo, registrado_por_usuario_id))
            return cur.fetchone()

    def listar_pagos_por_socio(self, socio_id, limite=20, conn=None):
        """(fecha_pago en hora de Argentina, monto, metodo, plan, membresia_id), más recientes primero."""
        query = """
            SELECT pg.fecha_pago AT TIME ZONE 'America/Argentina/Buenos_Aires', pg.monto, pg.metodo,
                   p.nombre, m.id
              FROM pago pg
              JOIN membresia m ON m.id = pg.membresia_id
              JOIN plan p ON p.id = m.plan_id
             WHERE m.socio_id = %s
             ORDER BY pg.fecha_pago DESC, pg.id DESC
             LIMIT %s;
        """
        with usar_conexion(conn) as c, c.cursor() as cur:
            cur.execute(query, (socio_id, limite))
            return cur.fetchall()
