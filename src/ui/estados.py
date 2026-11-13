"""Textos y tonos de los estados de v_socio_estado para chips y tablas."""

MEMBRESIA = {
    "vigente": ("Vigente", "verde"),
    "agotada": ("Cupo agotado", "rojo"),
    "no_vigente": ("Todavía no vigente", "ambar"),
    "vencida": ("Vencida", "rojo"),
    "sin_membresia": ("Sin membresía", "neutro"),
}
CONTABLE = {
    "al_dia": ("Al día", "verde"),
    "por_vencer": ("Por vencer", "ambar"),
    "debe": ("Debe", "rojo"),
    "sin_pase": ("Sin pase", "neutro"),
}
BAJA = ("Dado de baja", "neutro")


def estado_membresia(codigo, activo=True):
    if not activo:
        return BAJA
    return MEMBRESIA.get(codigo or "sin_membresia", MEMBRESIA["sin_membresia"])


def estado_contable(codigo, activo=True):
    if not activo:
        return BAJA
    return CONTABLE.get(codigo or "sin_pase", CONTABLE["sin_pase"])


def dni_con_puntos(dni):
    try:
        return f"{int(dni):,}".replace(",", ".")
    except (TypeError, ValueError):
        return dni or ""
