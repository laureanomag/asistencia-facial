from datetime import datetime, date
from config.database import get_connection


class GymRepository:
    """Acceso a datos para planes, membresías, ingresos, turnos, horarios y feriados."""

    # --- Planes ---
    def listar_planes(self, solo_activos=True):
        query = "SELECT id, codigo, nombre, descripcion, cupo_mensual, max_ingresos_por_dia, precio, activo FROM plan"
        if solo_activos:
            query += " WHERE activo = TRUE"
        query += " ORDER BY id;"
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query)
                return cur.fetchall()

    def obtener_plan_por_id(self, plan_id):
        query = "SELECT id, codigo, nombre, descripcion, cupo_mensual, max_ingresos_por_dia, precio, activo FROM plan WHERE id = %s;"
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (plan_id,))
                return cur.fetchone()

    # --- Membresías ---
    def crear_membresia(self, socio_id, plan_id, fecha_inicio, fecha_vencimiento, cupos_totales, monto_abonado):
        query = """
            INSERT INTO membresia
                (socio_id, plan_id, fecha_pago, fecha_inicio, fecha_vencimiento, cupos_totales, monto_abonado, estado)
            VALUES (%s, %s, CURRENT_DATE, %s, %s, %s, %s, 'activa')
            RETURNING id;
        """
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (socio_id, plan_id, fecha_inicio, fecha_vencimiento, cupos_totales, monto_abonado))
                return cur.fetchone()[0]

    def obtener_membresia_activa(self, socio_id, fecha_referencia=None):
        """Devuelve la membresía vigente para la fecha indicada (o hoy)."""
        fecha_ref = fecha_referencia or date.today()
        query = """
            SELECT m.id, m.socio_id, m.plan_id, m.fecha_pago, m.fecha_inicio, m.fecha_vencimiento,
                   m.cupos_totales, m.monto_abonado, m.estado,
                   p.codigo, p.nombre, p.cupo_mensual, p.max_ingresos_por_dia
              FROM membresia m
              JOIN plan p ON p.id = m.plan_id
             WHERE m.socio_id = %s
               AND m.estado = 'activa'
               AND %s BETWEEN m.fecha_inicio AND m.fecha_vencimiento
             ORDER BY m.id DESC
             LIMIT 1;
        """
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (socio_id, fecha_ref))
                return cur.fetchone()

    def listar_membresias_socio(self, socio_id):
        query = """
            SELECT m.id, p.nombre AS plan_nombre, m.fecha_pago, m.fecha_inicio, m.fecha_vencimiento,
                   m.cupos_totales, m.monto_abonado, m.estado
              FROM membresia m
              JOIN plan p ON p.id = m.plan_id
             WHERE m.socio_id = %s
             ORDER BY m.fecha_inicio DESC;
        """
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (socio_id,))
                return cur.fetchall()

    def actualizar_estado_membresia(self, membresia_id, nuevo_estado):
        query = "UPDATE membresia SET estado = %s WHERE id = %s;"
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (nuevo_estado, membresia_id))
                return cur.rowcount == 1

    # --- Ingresos de Socios ---
    def registrar_ingreso(self, socio_id, membresia_id, fecha_hora=None):
        momento = fecha_hora or datetime.now()
        query = """
            INSERT INTO ingreso_socio (socio_id, membresia_id, fecha_hora)
            VALUES (%s, %s, %s)
            RETURNING id;
        """
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (socio_id, membresia_id, momento))
                return cur.fetchone()[0]

    def contar_ingresos_membresia(self, membresia_id):
        query = "SELECT COUNT(*) FROM ingreso_socio WHERE membresia_id = %s;"
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (membresia_id,))
                return cur.fetchone()[0]

    def contar_ingresos_hoy(self, socio_id, fecha=None):
        f = fecha or date.today()
        query = "SELECT COUNT(*) FROM ingreso_socio WHERE socio_id = %s AND DATE(fecha_hora) = %s;"
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (socio_id, f))
                return cur.fetchone()[0]

    def contar_ingresos_semana_actual(self, socio_id, fecha_referencia=None):
        """Cuenta ingresos desde el lunes de la semana actual."""
        ref = fecha_referencia or date.today()
        # En PostgreSQL, DATE_TRUNC('week', ...) toma la semana empezando en lunes
        query = """
            SELECT COUNT(*)
              FROM ingreso_socio
             WHERE socio_id = %s
               AND DATE_TRUNC('week', fecha_hora) = DATE_TRUNC('week', %s::timestamp);
        """
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (socio_id, ref))
                return cur.fetchone()[0]

    def listar_ingresos_para_informe(self, fecha_desde=None, fecha_hasta=None, socio_id=None):
        query = """
            SELECT i.id, p.apellido, p.nombre, p.dni, pl.nombre AS plan_nombre,
                   i.fecha_hora, m.fecha_vencimiento
              FROM ingreso_socio i
              JOIN persona p ON p.id = i.socio_id
              JOIN membresia m ON m.id = i.membresia_id
              JOIN plan pl ON pl.id = m.plan_id
             WHERE 1=1
        """
        params = []
        if fecha_desde:
            query += " AND DATE(i.fecha_hora) >= %s"
            params.append(fecha_desde)
        if fecha_hasta:
            query += " AND DATE(i.fecha_hora) <= %s"
            params.append(fecha_hasta)
        if socio_id:
            query += " AND i.socio_id = %s"
            params.append(socio_id)
        query += " ORDER BY i.fecha_hora DESC;"

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, tuple(params))
                return cur.fetchall()

    # --- Horarios de Atención y Feriados ---
    def obtener_horario_dia(self, dia_semana):
        """0=Lunes, 1=Martes, ..., 6=Domingo."""
        query = """
            SELECT id, dia_semana, nombre_dia, abierto, horario_apertura, horario_cierre
              FROM horario_atencion
             WHERE dia_semana = %s;
        """
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (dia_semana,))
                return cur.fetchone()

    def listar_horarios_semana(self):
        query = """
            SELECT id, dia_semana, nombre_dia, abierto, horario_apertura, horario_cierre
              FROM horario_atencion
             ORDER BY dia_semana ASC;
        """
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query)
                return cur.fetchall()

    def actualizar_horario_dia(self, dia_semana, abierto, apertura, cierre):
        query = """
            UPDATE horario_atencion
               SET abierto = %s, horario_apertura = %s, horario_cierre = %s
             WHERE dia_semana = %s;
        """
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (abierto, apertura, cierre, dia_semana))
                return cur.rowcount == 1

    def obtener_feriado(self, fecha):
        query = """
            SELECT id, fecha, descripcion, es_nacional, abre_gimnasio
              FROM feriado
             WHERE fecha = %s;
        """
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (fecha,))
                return cur.fetchone()

    def listar_feriados(self):
        query = """
            SELECT id, fecha, descripcion, es_nacional, abre_gimnasio
              FROM feriado
             ORDER BY fecha ASC;
        """
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query)
                return cur.fetchall()

    # --- Turnos y Asistencias de Profesores ---
    def obtener_turno_profesor_hoy(self, profesor_id, fecha=None):
        f = fecha or date.today()
        dia_semana = f.weekday()
        # Busca primero turno específico por fecha (ej. sábado rotativo puntual), sino por día semanal
        query = """
            SELECT id, profesor_id, dia_semana, fecha_especifica, horario_inicio, horario_fin, es_rotativo, observaciones
              FROM turno_profesor
             WHERE profesor_id = %s
               AND (fecha_especifica = %s OR (fecha_especifica IS NULL AND dia_semana = %s))
             ORDER BY fecha_especifica NULLS LAST, id DESC
             LIMIT 1;
        """
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (profesor_id, f, dia_semana))
                return cur.fetchone()

    def obtener_asistencia_profesor_hoy(self, profesor_id, fecha=None):
        f = fecha or date.today()
        query = """
            SELECT id, profesor_id, turno_id, entrada, salida, es_cambio_turno, observaciones
              FROM asistencia_profesor
             WHERE profesor_id = %s AND DATE(entrada) = %s
             ORDER BY id DESC
             LIMIT 1;
        """
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (profesor_id, f))
                return cur.fetchone()

    def registrar_entrada_profesor(self, profesor_id, turno_id=None, ahora=None, es_cambio_turno=False, observaciones=None):
        momento = ahora or datetime.now()
        query = """
            INSERT INTO asistencia_profesor
                (profesor_id, turno_id, entrada, salida, es_cambio_turno, observaciones)
            VALUES (%s, %s, %s, NULL, %s, %s)
            RETURNING id;
        """
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (profesor_id, turno_id, momento, es_cambio_turno, observaciones))
                return cur.fetchone()[0]

    def registrar_salida_profesor(self, asistencia_id, ahora=None):
        momento = ahora or datetime.now()
        query = """
            UPDATE asistencia_profesor
               SET salida = %s
             WHERE id = %s AND salida IS NULL;
        """
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (momento, asistencia_id))
                return cur.rowcount == 1

    def listar_turnos_profesores(self):
        query = """
            SELECT t.id, p.apellido, p.nombre, t.dia_semana, t.fecha_especifica,
                   t.horario_inicio, t.horario_fin, t.es_rotativo, t.observaciones
              FROM turno_profesor t
              JOIN persona p ON p.id = t.profesor_id
             ORDER BY t.fecha_especifica NULLS LAST, t.dia_semana, t.horario_inicio;
        """
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query)
                return cur.fetchall()

    def asignar_turno(self, profesor_id, dia_semana, fecha_especifica, h_inicio, h_fin, es_rotativo, observaciones=None):
        query = """
            INSERT INTO turno_profesor
                (profesor_id, dia_semana, fecha_especifica, horario_inicio, horario_fin, es_rotativo, observaciones)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id;
        """
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (profesor_id, dia_semana, fecha_especifica, h_inicio, h_fin, es_rotativo, observaciones))
                return cur.fetchone()[0]

    def listar_asistencias_profesores(self, fecha_desde=None, fecha_hasta=None):
        query = """
            SELECT a.id, p.apellido, p.nombre, p.dni, a.entrada, a.salida,
                   a.es_cambio_turno, a.observaciones
              FROM asistencia_profesor a
              JOIN persona p ON p.id = a.profesor_id
             WHERE 1=1
        """
        params = []
        if fecha_desde:
            query += " AND DATE(a.entrada) >= %s"
            params.append(fecha_desde)
        if fecha_hasta:
            query += " AND DATE(a.entrada) <= %s"
            params.append(fecha_hasta)
        query += " ORDER BY a.entrada DESC;"

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, tuple(params))
                return cur.fetchall()

    # --- Auditoría de Rechazos ---
    def registrar_rechazo(self, persona_id, tipo_persona, motivo, detalle=None, ahora=None):
        momento = ahora or datetime.now()
        query = """
            INSERT INTO rechazo_acceso (persona_id, tipo_persona, motivo, detalle, fecha_hora)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id;
        """
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (persona_id, tipo_persona, motivo, detalle, momento))
                return cur.fetchone()[0]

    def listar_rechazos(self, limit=100):
        query = """
            SELECT r.id, p.apellido, p.nombre, r.tipo_persona, r.motivo, r.detalle, r.fecha_hora
              FROM rechazo_acceso r
              LEFT JOIN persona p ON p.id = r.persona_id
             ORDER BY r.fecha_hora DESC
             LIMIT %s;
        """
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (limit,))
                return cur.fetchall()
