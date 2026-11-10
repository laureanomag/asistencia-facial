from datetime import datetime, time, timedelta

# Si attendance_service ya define una constante para la tolerancia de entrada,
# importala desde ahí para tener una única fuente de verdad.
TOLERANCIA_ENTRADA = timedelta(minutes=10)


def _a_hora(valor):
    """Acepta datetime.time o texto 'HH:MM' y devuelve datetime.time."""
    if isinstance(valor, time):
        return valor
    if isinstance(valor, str):
        return time.fromisoformat(valor)
    raise TypeError("El horario debe ser datetime.time o texto 'HH:MM'")


class JornadaService:
    """Edición de Jornadas. Valida los horarios y, si cambia la entrada,
    recalcula la tardanza de las asistencias ya registradas."""

    def __init__(self, jornada_repo, attendance_repo):
        self._jornadas = jornada_repo
        self._asistencias = attendance_repo

    def actualizar(self, jornada_id, usuario_id, horario_entrada, horario_salida, catedra):
        horario_entrada = _a_hora(horario_entrada)
        horario_salida = _a_hora(horario_salida)

        if horario_entrada >= horario_salida:
            raise ValueError("El horario de entrada debe ser anterior al de salida")

        actual = self._jornadas.obtener_de_usuario(jornada_id, usuario_id)
        if actual is None:
            raise LookupError("La jornada no existe o no pertenece al usuario")
        _id, fecha, _catedra, entrada_anterior, _salida = actual

        if not self._jornadas.actualizar(jornada_id, usuario_id,
                                         horario_entrada, horario_salida, catedra):
            raise LookupError("No se pudo actualizar la jornada")

        if horario_entrada != entrada_anterior:
            limite = datetime.combine(fecha, horario_entrada) + TOLERANCIA_ENTRADA
            self._asistencias.recalcular_tardanzas(jornada_id, limite)