"""Jornadas (turnos del personal) y Fichajes (llegadas y salidas).

Fichajes se calcula siempre desde jornada y fichaje, por empleado y fecha:
  - turno, llegada, salida, minutos de tardanza y horas trabajadas;
  - "Ausente": turno de trabajo que ya terminó sin ninguna llegada marcada;
  - "Fichaje incompleto": llegada sin salida de un día anterior (o de un
    turno que ya terminó hace más de 2 horas);
  - "Fuera de turno": llegada sin jornada vinculada;
  - licencia, vacaciones o permiso se muestran como tales.
El entrenador ve solo sus fichajes; la dueña (jornada.gestionar) ve todos."""
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from config.database import usar_conexion
from services.auth_service import FICHAJE_CONSULTAR_PROPIO, JORNADA_GESTIONAR, autorizar
from services.reglas_ingreso import hora_texto

ESTADOS_JORNADA = {"jornada": "Turno de trabajo", "licencia_vacaciones": "Licencia o vacaciones",
                   "permiso": "Permiso"}
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


def calcular_fichajes(jornadas, fichajes, ahora):
    """jornadas: filas de JornadaRepository.listar; fichajes: filas de
    FichajeRepository.listar; ahora: datetime de Argentina sin zona.
    Devuelve [FilaFichaje] ordenadas por fecha y empleado."""
    filas, usadas = [], set()
    for (fid, usuario_id, nombre, apellido, _usuario, entrada, salida, jornada_id,
         j_entrada, j_salida) in fichajes:
        entrada = entrada.replace(tzinfo=None)
        salida = salida.replace(tzinfo=None) if salida else None
        empleado = f"{nombre or ''} {apellido or ''}".strip()
        if jornada_id is not None:
            usadas.add(jornada_id)
            turno = f"{hora_texto(j_entrada)}–{hora_texto(j_salida)}"
            tarde = _minutos(entrada - datetime.combine(entrada.date(), j_entrada))
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

    for jid, _uid, nombre, apellido, fecha, j_entrada, j_salida, estado_j in jornadas:
        if jid in usadas:
            continue
        empleado = f"{nombre or ''} {apellido or ''}".strip()
        turno = f"{hora_texto(j_entrada)}–{hora_texto(j_salida)}"
        if estado_j != "jornada":
            estado, tono = ESTADOS_JORNADA.get(estado_j, estado_j), "neutro"
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
    for jid, _uid, _n, _a, fecha, j_entrada, j_salida, _estado in existentes:
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
