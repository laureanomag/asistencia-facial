from repositories.attendance_repository import AttendanceRepository
from repositories.jornada_repository import JornadaRepository
from services.report_exporters import DatosInforme, FilaAlumno


class JornadaAjenaError(Exception):
    """La Jornada solicitada no pertenece al usuario autenticado."""


class ReportService:
    """Arma los datos de un informe verificando siempre la propiedad de la Jornada."""

    def __init__(self):
        self._jornadas = JornadaRepository()
        self._asistencias = AttendanceRepository()

    def listar_jornadas(self, usuario_id):
        return self._jornadas.listar_por_usuario(usuario_id)

    def preparar(self, jornada_id, usuario_id, nombre_usuario):
        jornada = self._jornadas.obtener_de_usuario(jornada_id, usuario_id)
        if jornada is None:
            raise JornadaAjenaError("La Jornada seleccionada no pertenece al usuario autenticado.")

        _id, fecha, catedra, h_entrada, h_salida = jornada
        filas = self._asistencias.listar_para_informe(jornada_id, usuario_id)
        alumnos = [FilaAlumno(*f) for f in filas]
        return DatosInforme(fecha, catedra, h_entrada, h_salida, nombre_usuario, alumnos)
