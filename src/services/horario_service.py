"""Textos del horario de atención para la interfaz de ZebraGym.

- estado_apertura: "Abierto · cierra a las 23:00" / "Cerrado · abre hoy a las 07:30".
- resumen_horario: "Lun a Vie 7:30–23 · Sáb 10–14" (pie del login).
- fecha_hora_titulo: "Jueves 12/11 · 18:42" (subtítulo de las pantallas).
Todo sale de horario_atencion: si el administrador cambia el horario desde
Configuración, los textos se actualizan solos."""
from services.reglas_ingreso import Franja, franja_actual, hora_texto

DIAS = {1: "lunes", 2: "martes", 3: "miércoles", 4: "jueves", 5: "viernes",
        6: "sábado", 7: "domingo"}
DIAS_CORTOS = {1: "Lun", 2: "Mar", 3: "Mié", 4: "Jue", 5: "Vie", 6: "Sáb", 7: "Dom"}


def hora_compacta(valor):
    """07:30 -> '7:30'; 23:00 -> '23'."""
    return f"{valor.hour}" if valor.minute == 0 else f"{valor.hour}:{valor.minute:02d}"


def _ordenadas(franjas):
    return sorted(franjas, key=lambda f: f.apertura)


def resumen_horario(franjas_semana):
    """{dia_iso: [Franja]} -> 'Lun a Vie 7:30–23 · Sáb 10–14'. Agrupa días
    seguidos con el mismo horario y omite los días cerrados."""
    grupos = []   # [dia_inicio, dia_fin, horario]
    for dia in range(1, 8):
        franjas = _ordenadas(franjas_semana.get(dia, []))
        if not franjas:
            continue
        horario = " y ".join(f"{hora_compacta(f.apertura)}–{hora_compacta(f.cierre)}"
                             for f in franjas)
        if grupos and grupos[-1][1] == dia - 1 and grupos[-1][2] == horario:
            grupos[-1][1] = dia
        else:
            grupos.append([dia, dia, horario])

    partes = []
    for inicio, fin, horario in grupos:
        if fin == inicio:
            dias = DIAS_CORTOS[inicio]
        elif fin == inicio + 1:
            dias = f"{DIAS_CORTOS[inicio]} y {DIAS_CORTOS[fin]}"
        else:
            dias = f"{DIAS_CORTOS[inicio]} a {DIAS_CORTOS[fin]}"
        partes.append(f"{dias} {horario}")
    return " · ".join(partes)


def estado_apertura(franjas_semana, ahora):
    """(abierto, texto) para el indicador de la esquina superior derecha."""
    hoy = ahora.isoweekday()
    hora = ahora.time()
    actual = franja_actual(franjas_semana.get(hoy, []), hora)
    if actual is not None:
        return True, f"Abierto · cierra a las {hora_texto(actual.cierre)}"

    for desplazamiento in range(8):
        dia = (hoy - 1 + desplazamiento) % 7 + 1
        for franja in _ordenadas(franjas_semana.get(dia, [])):
            if desplazamiento == 0 and franja.apertura <= hora:
                continue
            if desplazamiento == 0:
                cuando = "hoy"
            elif desplazamiento == 1:
                cuando = "mañana"
            else:
                cuando = f"el {DIAS[dia]}"
            return False, f"Cerrado · abre {cuando} a las {hora_texto(franja.apertura)}"
    return False, "Cerrado"


def fecha_hora_titulo(ahora):
    return f"{DIAS[ahora.isoweekday()].capitalize()} {ahora.strftime('%d/%m')} · {hora_texto(ahora)}"


class HorarioService:
    def __init__(self, horario_repository=None):
        if horario_repository is None:
            from repositories.horario_repository import HorarioRepository
            horario_repository = HorarioRepository()
        self._repo = horario_repository

    def franjas_semana(self):
        """{dia_iso: [Franja]} solo con las franjas activas."""
        semana = {}
        for _id, dia, apertura, cierre, activo in self._repo.listar():
            if activo:
                semana.setdefault(dia, []).append(Franja(apertura, cierre))
        return semana

    def ahora(self):
        return self._repo.ahora()

    def estado_actual(self):
        """(abierto, texto, ahora) con el reloj de la base."""
        ahora = self.ahora()
        abierto, texto = estado_apertura(self.franjas_semana(), ahora)
        return abierto, texto, ahora
