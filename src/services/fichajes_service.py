"""Jornadas (turnos del personal) y Fichajes (llegadas y salidas).

Fichajes se calcula siempre desde jornada y fichaje, por empleado y fecha:
  - turno, llegada, salida, minutos de tardanza y horas trabajadas;
  - "Ausente": turno de trabajo que ya terminó sin ninguna llegada marcada;
  - "Fichaje incompleto": llegada sin salida de un día anterior (o de un
    turno que ya terminó hace más de 2 horas);
  - "Fuera de turno": llegada sin jornada vinculada;
  - "Licencia" o "Permiso": esos días nunca figuran como Ausente y no cuentan
    tardanza (con un permiso que cubre el inicio del turno, la tardanza se
    cuenta desde que termina el permiso).
El entrenador ve solo sus fichajes; la dueña (jornada.gestionar) ve todos.

Licencias y permisos (la dueña): se guardan en jornada (estado
'licencia_vacaciones' o 'permiso') y cada aprobación o anulación queda en
jornada_cambio con el motivo, quién y cuándo.
  - Licencia de un rango de fechas: los turnos de cada día pasan a licencia;
    un día sin turno se crea como licencia de día completo.
  - Permiso de un día, de día completo o de un rango de horas. Con los turnos
    del día: si el permiso cubre el inicio, el turno empieza cuando termina el
    permiso; si cubre el final, el turno se acorta; si cubre el turno entero,
    el turno pasa a 'permiso'. Cada cambio queda en jornada_cambio con el motivo
    "Permiso de HH:MM a HH:MM", y el permiso tiene su propia fila.
  - Anular: cada fila vuelve a como estaba antes (los turnos, a su horario
    original); una fila creada por la licencia o el permiso deja de contar."""
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from config.database import usar_conexion
from services.auth_service import FICHAJE_CONSULTAR_PROPIO, JORNADA_GESTIONAR, autorizar
from services.reglas_ingreso import DIA_COMPLETO, es_dia_completo, hora_texto, inicio_efectivo

ESTADOS_JORNADA = {"jornada": "Turno de trabajo", "licencia_vacaciones": "Licencia o vacaciones",
                   "permiso": "Permiso"}
LICENCIA, PERMISO = "licencia_vacaciones", "permiso"
MAXIMO_DIAS_LICENCIA = 366
GRACIA_INCOMPLETO = timedelta(hours=2)


class ErroresJornada(Exception):
    def __init__(self, errores):
        super().__init__("; ".join(errores.values()))
        self.errores = errores


@dataclass(frozen=True)
class FilaFichaje:
    fecha: date
    empleado: str
    turno: str          # "14:00–22:00", "Sin turno"
    llegada: str        # "14:05" o "—"
    salida: str
    tardanza: str       # "5 min", "—"
    trabajado: str      # "7 h 56 min", "—"
    estado: str         # En horario, Tarde, Fuera de turno, En curso, Fichaje incompleto, Ausente, Permiso...
    tono: str


def _minutos(delta):
    return max(0, int(delta.total_seconds() // 60))


def _horas(minutos):
    return f"{minutos // 60} h {minutos % 60:02d} min"


def texto_horario(entrada, salida):
    return "Día completo" if es_dia_completo(entrada, salida) else f"{hora_texto(entrada)}–{hora_texto(salida)}"


def _ausencias_por_dia(jornadas):
    """{(usuario_id, fecha): {"licencia": bool, "permisos": [(desde, hasta)]}}."""
    dias = {}
    for _jid, usuario_id, _n, _a, fecha, entrada, salida, estado in jornadas:
        if estado in (LICENCIA, PERMISO):
            dia = dias.setdefault((usuario_id, fecha), {"licencia": False, "permisos": []})
            if estado == LICENCIA:
                dia["licencia"] = True
            else:
                dia["permisos"].append((entrada, salida))
    return dias


def calcular_fichajes(jornadas, fichajes, ahora):
    """jornadas: filas de JornadaRepository.listar; fichajes: filas de
    FichajeRepository.listar; ahora: datetime de Argentina sin zona.
    Devuelve [FilaFichaje] ordenadas por fecha y empleado."""
    ausencias = _ausencias_por_dia(jornadas)
    filas, usadas = [], set()
    for (fid, usuario_id, nombre, apellido, _usuario, entrada, salida, jornada_id,
         j_entrada, j_salida) in fichajes:
        entrada = entrada.replace(tzinfo=None)
        salida = salida.replace(tzinfo=None) if salida else None
        empleado = f"{nombre or ''} {apellido or ''}".strip()
        dia = ausencias.get((usuario_id, entrada.date()))
        if jornada_id is not None:
            usadas.add(jornada_id)
            turno = f"{hora_texto(j_entrada)}–{hora_texto(j_salida)}"
            desde = inicio_efectivo(j_entrada, dia["permisos"] if dia else [])
            tarde = _minutos(entrada - datetime.combine(entrada.date(), desde))
            if dia and dia["licencia"]:
                tarde = 0                                   # día de licencia: no cuenta tardanza
            fin_turno = datetime.combine(entrada.date(), j_salida)
        else:
            turno, tarde, fin_turno = "Sin turno", 0, None
        if salida is not None:
            trabajado = _horas(_minutos(salida - entrada))
            if jornada_id is None:
                estado, tono = "Fuera de turno", "ambar"
            elif tarde > 0:
                estado, tono = "Tarde", "ambar"
            else:
                estado, tono = "En horario", "verde"
        else:
            trabajado = "—"
            vencido = entrada.date() < ahora.date() or (fin_turno is not None and ahora > fin_turno + GRACIA_INCOMPLETO)
            estado, tono = ("Fichaje incompleto", "rojo") if vencido else ("En curso", "neutro")
        filas.append(FilaFichaje(entrada.date(), empleado, turno, hora_texto(entrada),
                                 hora_texto(salida) if salida else "—",
                                 f"{tarde} min" if tarde else "—", trabajado, estado, tono))

    for jid, usuario_id, nombre, apellido, fecha, j_entrada, j_salida, estado_j in jornadas:
        if jid in usadas:
            continue
        empleado = f"{nombre or ''} {apellido or ''}".strip()
        turno = texto_horario(j_entrada, j_salida)
        dia = ausencias.get((usuario_id, fecha))
        if estado_j == LICENCIA:
            estado, tono = "Licencia", "neutro"
        elif estado_j == PERMISO:
            estado, tono = "Permiso", "neutro"
        elif dia:                                   # turno de un día con licencia o permiso: nunca Ausente
            estado, tono = ("Licencia" if dia["licencia"] else "Permiso"), "neutro"
        elif datetime.combine(fecha, j_salida) <= ahora:
            estado, tono = "Ausente", "rojo"
        else:
            estado, tono = "Pendiente", "neutro"
        filas.append(FilaFichaje(fecha, empleado, turno, "—", "—", "—", "—", estado, tono))
    return sorted(filas, key=lambda f: (f.fecha, f.empleado, f.llegada))


def validar_jornada(entrada, salida, estado, fechas, existentes, jornada_id=None):
    """existentes: jornadas del empleado en esas fechas (filas de listar)."""
    errores = {}
    if not fechas:
        errores["fechas"] = "Elegí al menos un día."
    if entrada is None or salida is None or salida <= entrada:
        errores["salida"] = "La salida tiene que ser posterior a la entrada."
    if estado not in ESTADOS_JORNADA:
        errores["estado"] = "Elegí el tipo de jornada."
    if errores:
        return errores
    for jid, _uid, _n, _a, fecha, j_entrada, j_salida, estado_j in existentes:
        if estado_j != "jornada":                   # licencias y permisos no son turnos
            continue
        if jid != jornada_id and fecha in fechas and entrada < j_salida and j_entrada < salida:
            errores["entrada"] = (f"Se superpone con el turno del {fecha:%d/%m} de {hora_texto(j_entrada)} "
                                  f"a {hora_texto(j_salida)}.")
            break
    return errores


def fechas_entre(desde, hasta, dias_semana):
    """Fechas desde..hasta (incluidas) cuyos días ISO estén en dias_semana."""
    fechas, dia = [], desde
    while dia <= hasta:
        if dia.isoweekday() in dias_semana:
            fechas.append(dia)
        dia += timedelta(days=1)
    return fechas


class FichajesService:
    def __init__(self, jornadas=None, fichajes=None, usuarios=None, horario=None, transaccion=usar_conexion):
        if jornadas is None:
            from repositories.jornada_repository import JornadaRepository
            jornadas = JornadaRepository()
        if fichajes is None:
            from repositories.fichaje_repository import FichajeRepository
            fichajes = FichajeRepository()
        if usuarios is None:
            from repositories.user_repository import UserRepository
            usuarios = UserRepository()
        if horario is None:
            from repositories.horario_repository import HorarioRepository
            horario = HorarioRepository()
        self._jornadas, self._fichajes, self._usuarios, self._horario = jornadas, fichajes, usuarios, horario
        self._transaccion = transaccion

    @staticmethod
    def ve_a_todos(sesion):
        return sesion.puede(JORNADA_GESTIONAR)

    def personal(self, sesion):
        """[(usuario_id, "Nombre Apellido")] del personal activo que la sesión puede ver."""
        autorizar(sesion, FICHAJE_CONSULTAR_PROPIO)
        filas = [(f[0], f"{f[1]} {f[2]}") for f in self._usuarios.listar_personal() if f[5]]
        if self.ve_a_todos(sesion):
            return filas
        return [f for f in filas if f[0] == sesion.usuario_id]

    def fichajes(self, sesion, desde, hasta, usuario_id=None):
        autorizar(sesion, FICHAJE_CONSULTAR_PROPIO)
        if not self.ve_a_todos(sesion):
            usuario_id = sesion.usuario_id                      # solo los propios
        with self._transaccion() as conn:
            ahora = self._horario.ahora(conn=conn)
            jornadas = self._jornadas.listar(desde, hasta, usuario_id, conn=conn)
            fichajes = self._fichajes.listar(desde, hasta, usuario_id, conn=conn)
        return calcular_fichajes(jornadas, fichajes, ahora)

    # --- Jornadas (solo la dueña) ---

    def jornadas(self, sesion, desde, hasta, usuario_id=None):
        autorizar(sesion, JORNADA_GESTIONAR)
        return self._jornadas.listar(desde, hasta, usuario_id)

    def cargar_turnos(self, sesion, usuario_id, fechas, entrada, salida, estado="jornada"):
        """Crea un turno por fecha. Devuelve la cantidad creada."""
        autorizar(sesion, JORNADA_GESTIONAR)
        with self._transaccion() as conn:
            existentes = self._jornadas.listar(min(fechas), max(fechas), usuario_id, conn=conn) if fechas else []
            errores = validar_jornada(entrada, salida, estado, fechas, existentes)
            if usuario_id is None:
                errores["empleado"] = "Elegí el empleado."
            if errores:
                raise ErroresJornada(errores)
            for fecha in fechas:
                # Una licencia o permiso anulado en un día sin turno dejó su fila: si abre a la
                # misma hora, se reutiliza (la fila es única por empleado, fecha y hora de entrada).
                anulada = next((f for f in self._jornadas.del_dia(usuario_id, fecha, conn=conn)
                                if f[4] and f[1] == entrada), None)
                if anulada:
                    self._jornadas.cambiar(anulada[0], fecha, entrada, salida, estado, "Turno cargado",
                                           sesion.usuario_id, conn=conn)
                else:
                    self._jornadas.crear(usuario_id, fecha, entrada, salida, estado, conn=conn)
        return len(fechas)

    def cambiar_turno(self, sesion, jornada_id, entrada, salida, estado, motivo=""):
        """Cambia horario o estado de un turno; el anterior queda en jornada_cambio."""
        autorizar(sesion, JORNADA_GESTIONAR)
        with self._transaccion() as conn:
            actual = self._jornadas.obtener(jornada_id, bloquear=True, conn=conn)
            if actual is None:
                raise ErroresJornada({"jornada": "El turno ya no existe."})
            _id, usuario_id, fecha, *_ = actual
            existentes = self._jornadas.listar(fecha, fecha, usuario_id, conn=conn)
            errores = validar_jornada(entrada, salida, estado, [fecha], existentes, jornada_id)
            if errores:
                raise ErroresJornada(errores)
            return self._jornadas.cambiar(jornada_id, fecha, entrada, salida, estado, motivo,
                                          sesion.usuario_id, conn=conn)

    # --- Licencias y permisos (solo la dueña) ---

    def dar_licencia(self, sesion, usuario_id, desde, hasta, motivo=""):
        """Licencia de desde a hasta (incluidos). Devuelve la cantidad de días."""
        autorizar(sesion, JORNADA_GESTIONAR)
        errores = {}
        if usuario_id is None:
            errores["empleado"] = "Elegí el empleado."
        if hasta < desde:
            errores["hasta"] = "No puede ser anterior a Desde."
        elif (hasta - desde).days >= MAXIMO_DIAS_LICENCIA:
            errores["hasta"] = "La licencia no puede durar más de un año."
        if errores:
            raise ErroresJornada(errores)
        fechas = fechas_entre(desde, hasta, set(range(1, 8)))
        with self._transaccion() as conn:
            for fecha in fechas:
                filas = self._jornadas.del_dia(usuario_id, fecha, conn=conn)
                turnos = [f for f in filas if not f[4]]
                if turnos:
                    for jid, entrada, salida, estado, _anulada in turnos:
                        if estado != LICENCIA:
                            self._jornadas.cambiar(jid, fecha, entrada, salida, LICENCIA, motivo,
                                                   sesion.usuario_id, conn=conn)
                else:
                    self._crear_o_reusar(usuario_id, fecha, filas, DIA_COMPLETO, LICENCIA, motivo,
                                         sesion.usuario_id, conn)
        return len(fechas)

    def dar_permiso(self, sesion, usuario_id, fecha, desde=None, hasta=None, motivo=""):
        """Permiso de un día: de día completo o de desde a hasta."""
        autorizar(sesion, JORNADA_GESTIONAR)
        errores = {}
        if usuario_id is None:
            errores["empleado"] = "Elegí el empleado."
        if (desde is None) != (hasta is None) or (desde is not None and hasta <= desde):
            errores["hasta"] = "La hora final tiene que ser posterior a la inicial."
        if errores:
            raise ErroresJornada(errores)
        d, h = (desde, hasta) if desde is not None else DIA_COMPLETO
        por = sesion.usuario_id
        with self._transaccion() as conn:
            filas = self._jornadas.del_dia(usuario_id, fecha, conn=conn)
            reales = [f for f in filas if not f[4]]
            if any(f[3] == PERMISO and (f[1], f[2]) == (d, h) for f in reales):
                return False                                    # ya tenía ese permiso
            corre = f"Permiso de {hora_texto(d)} a {hora_texto(h)}"
            turnos = [f for f in reales if f[3] == "jornada" and f[1] < h and d < f[2]]
            cubiertos = [f for f in turnos if d <= f[1] and f[2] <= h]
            for jid, entrada, salida, _estado, _anulada in turnos:
                if (jid, entrada, salida, _estado, _anulada) in cubiertos:
                    continue
                if d <= entrada:                                # cubre el inicio: el turno empieza después
                    self._jornadas.cambiar(jid, fecha, h, salida, "jornada", corre, por, conn=conn)
                elif salida <= h:                               # cubre el final: el turno se acorta
                    self._jornadas.cambiar(jid, fecha, entrada, d, "jornada", corre, por, conn=conn)
            # La fila del permiso: un turno cubierto entero pasa a 'permiso' con el horario del
            # permiso; si no hay ninguno, se crea (o se reutiliza una anulada).
            destino = next((f for f in cubiertos if f[1] == d), None) or (cubiertos[0] if cubiertos else None)
            ocupadas = {f[1] for f in self._jornadas.del_dia(usuario_id, fecha, conn=conn)
                        if not f[4] and (destino is None or f[0] != destino[0])}
            if d in ocupadas:
                raise ErroresJornada({"hasta": "Ya hay una licencia o un permiso que empieza a esa hora."})
            for jid, entrada, salida, _estado, _anulada in cubiertos:
                horas = (d, h) if destino is not None and jid == destino[0] else (entrada, salida)
                self._jornadas.cambiar(jid, fecha, *horas, PERMISO, motivo, por, conn=conn)
            if destino is None:
                anuladas = [f for f in self._jornadas.del_dia(usuario_id, fecha, conn=conn) if f[4]]
                # Si una anulada ocupa esa hora, se reutiliza esa; si no, cualquiera del día.
                reusada = next((f for f in anuladas if f[1] == d), None) or (anuladas[0] if anuladas else None)
                if reusada:
                    self._jornadas.cambiar(reusada[0], fecha, d, h, PERMISO, motivo, por, conn=conn)
                else:
                    self._jornadas.crear_aprobada(usuario_id, fecha, d, h, PERMISO, motivo, por, conn=conn)
        return True

    def _crear_o_reusar(self, usuario_id, fecha, filas, horas, estado, motivo, aprobado_por, conn):
        """Crea la fila de una licencia de día completo en un día sin turno (o
        reutiliza una anulada del día, de preferencia la que empieza a esa hora)."""
        entrada, salida = horas
        anuladas = [f for f in filas if f[4]]
        reusada = next((f for f in anuladas if f[1] == entrada), None) or (anuladas[0] if anuladas else None)
        if reusada:
            self._jornadas.cambiar(reusada[0], fecha, entrada, salida, estado, motivo, aprobado_por, conn=conn)
        else:
            self._jornadas.crear_aprobada(usuario_id, fecha, entrada, salida, estado, motivo, aprobado_por, conn=conn)

    def anular(self, sesion, jornada_id, motivo=""):
        """Anula la licencia o el permiso aprobado junto con esta fila (todos los
        días del mismo lote y los turnos que corrió). Devuelve la cantidad de
        filas de licencia o permiso anuladas."""
        autorizar(sesion, JORNADA_GESTIONAR)
        texto = "Anulación" + (f": {motivo}" if motivo else "")
        por = sesion.usuario_id
        with self._transaccion() as conn:
            ids = self._jornadas.mismo_lote(jornada_id, conn=conn)
            if not ids:
                raise ErroresJornada({"jornada": "No hay una licencia o un permiso para anular."})
            filas = []
            for jid in ids:
                actual = self._jornadas.obtener(jid, bloquear=True, conn=conn)
                ultimo = self._jornadas.ultimo_cambio(jid, conn=conn)
                creada = ultimo is None or tuple(ultimo[:4]) == tuple(ultimo[4:])
                filas.append((jid, actual, ultimo, creada))
            # Horarios a los que vuelven los turnos (los turnos se restauran al final).
            destinos = {(u[0], u[1]) for _jid, _a, u, creada in filas if not creada}
            for jid, (_id, usuario_id, fecha, entrada, salida, _estado), _u, creada in filas:
                if not creada:
                    continue
                # Se creó con la licencia o el permiso: vuelve a 'jornada' y deja de contar. Si su
                # hora de entrada la necesita un turno que vuelve a su horario, queda en un minuto libre.
                if (fecha, entrada) in destinos:
                    entrada, salida = self._minuto_libre(usuario_id, fecha, jid, destinos, conn)
                self._jornadas.cambiar(jid, fecha, entrada, salida, "jornada", texto, por, conn=conn)
            for jid, _actual, ultimo, creada in filas:
                if not creada:                                  # vuelve a como estaba (turno original)
                    self._jornadas.cambiar(jid, *ultimo[:4], texto, por, conn=conn)
        return sum(1 for _j, actual, _u, _c in filas if actual[5] in (LICENCIA, PERMISO))

    def _minuto_libre(self, usuario_id, fecha, jornada_id, destinos, conn):
        ocupadas = {f[1] for f in self._jornadas.del_dia(usuario_id, fecha, conn=conn) if f[0] != jornada_id}
        ocupadas |= {hora for dia, hora in destinos if dia == fecha}
        minuto = datetime.combine(fecha, time(0, 0))
        while minuto.time() in ocupadas:
            minuto += timedelta(minutes=1)
        return minuto.time(), (minuto + timedelta(minutes=1)).time()

    def ausencias(self, sesion, desde, hasta, usuario_id=None):
        """Licencias y permisos agrupados por aprobación: [dict] con jornada_id,
        empleado, tipo, desde, hasta, horario, aprobado_por, aprobado_en, motivo."""
        autorizar(sesion, JORNADA_GESTIONAR)
        lotes = {}
        for (jid, uid, nombre, apellido, fecha, entrada, salida, estado, aprobado_en, aprobado_por,
             motivo) in self._jornadas.ausencias(desde, hasta, usuario_id):
            clave = (uid, estado, aprobado_en, aprobado_por, motivo)
            lote = lotes.setdefault(clave, {
                "jornada_id": jid, "empleado": f"{nombre or ''} {apellido or ''}".strip(),
                "tipo": "Licencia" if estado == LICENCIA else "Permiso", "desde": fecha, "hasta": fecha,
                "horario": texto_horario(entrada, salida) if estado == PERMISO else "Día completo",
                "aprobado_por": aprobado_por or "—", "aprobado_en": aprobado_en, "motivo": motivo or ""})
            lote["desde"], lote["hasta"] = min(lote["desde"], fecha), max(lote["hasta"], fecha)
        return sorted(lotes.values(), key=lambda l: (l["desde"], l["empleado"]))
