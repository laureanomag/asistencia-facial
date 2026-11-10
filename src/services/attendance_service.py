from datetime import datetime, timedelta

# Reglas horarias. Son constantes del código a propósito: NO se leen del .env
# ni de variables de entorno, para que nadie pueda desactivar la espera entre
# entrada y salida (antes, SEPARACION_ENTRADA_SALIDA_MIN=0 la anulaba).
#   TOLERANCIA_ENTRADA: pasado el horario de entrada más este tiempo, la
#       entrada se registra igual pero con tardanza.
#   TOLERANCIA_SALIDA: la salida se habilita desde el horario de salida menos
#       este tiempo.
#   ESPERA_ENTRADA_SALIDA: tiempo mínimo entre la entrada y la salida del
#       mismo alumno. Evita que la salida quede pegada a la entrada.
TOLERANCIA_ENTRADA = timedelta(minutes=10)
TOLERANCIA_SALIDA = timedelta(minutes=5)
ESPERA_ENTRADA_SALIDA = timedelta(minutes=10)

ENTRADA_REGISTRADA = "ENTRADA_REGISTRADA"
ENTRADA_CON_TARDANZA = "ENTRADA_CON_TARDANZA"
SALIDA_AUN_NO = "SALIDA_AUN_NO"
SALIDA_REGISTRADA = "SALIDA_REGISTRADA"
ASISTENCIA_COMPLETA = "ASISTENCIA_COMPLETA"


def hay_tardanza(entrada, horario_entrada):
    """True si la entrada (datetime) superó el horario de entrada de la
    Jornada más la tolerancia. Hasta 10 minutos después inclusive es entrada
    normal. El resultado se guarda en asistencia.tardanza."""
    limite = datetime.combine(entrada.date(), horario_entrada) + TOLERANCIA_ENTRADA
    return entrada > limite


def salida_habilitada_desde(entrada, horario_salida, ahora):
    """Hora desde la que se puede marcar la salida: el mayor entre
    (horario de salida - 5 min) y (entrada + 10 min)."""
    limite_horario = datetime.combine(ahora.date(), horario_salida) - TOLERANCIA_SALIDA
    return max(limite_horario, entrada + ESPERA_ENTRADA_SALIDA)


class AttendanceService:
    """Lógica de entrada/salida con una única fila por jornada_id + alumno_id."""

    def __init__(self, repository):
        self._repo = repository

    def procesar(self, jornada_id, alumno_id, horario_entrada, horario_salida, ahora=None):
        """Devuelve (estado, hora). La hora se informa en SALIDA_AUN_NO (desde
        cuándo se habilita la salida). Cada llamada hace como máximo UNA
        escritura: o registra la entrada, o registra la salida, nunca ambas."""
        ahora = ahora or datetime.now()
        fila = self._repo.obtener(jornada_id, alumno_id)

        if fila is None:
            tardanza = hay_tardanza(ahora, horario_entrada)
            if self._repo.registrar_entrada(jornada_id, alumno_id, ahora, tardanza):
                return (ENTRADA_CON_TARDANZA if tardanza else ENTRADA_REGISTRADA), None
            fila = self._repo.obtener(jornada_id, alumno_id)  # otro proceso insertó antes

        _id, entrada, salida = fila
        if salida is not None:
            return ASISTENCIA_COMPLETA, None

        disponible = salida_habilitada_desde(entrada, horario_salida, ahora)
        if ahora < disponible:
            return SALIDA_AUN_NO, disponible

        self._repo.registrar_salida(jornada_id, alumno_id, ahora)
        return SALIDA_REGISTRADA, None
