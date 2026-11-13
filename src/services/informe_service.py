"""Informes de la dueña (reporte.consultar):
- Ingresos y rechazos por fechas y, opcionalmente, por socio (tabla acceso).
- Estado de membresía y cupos de todos los socios activos (v_socio_estado).
Cada informe se puede exportar a Excel o PDF (services/exportar.py)."""
from collections import Counter

from config.database import usar_conexion
from services.auth_service import REPORTE_CONSULTAR, autorizar
from services.exportar import Informe
from services.persona_service import DatosInvalidos, normalizar_dni
from services.reglas_ingreso import ETIQUETAS_MOTIVO, fecha_texto, hora_texto, pesos

MEMBRESIA = {"vigente": "Vigente", "agotada": "Cupo agotado", "no_vigente": "Todavía no vigente",
             "vencida": "Vencida", "sin_membresia": "Sin membresía"}
CONTABLE = {"al_dia": "Al día", "por_vencer": "Por vencer", "debe": "Debe", "sin_pase": "Sin pase"}


def _dni(dni):
    try:
        return f"{int(dni):,}".replace(",", ".")
    except (TypeError, ValueError):
        return dni or ""


class InformeService:
    def __init__(self, personas=None, socios=None, accesos=None, transaccion=usar_conexion):
        if personas is None:
            from repositories.person_repository import PersonRepository
            personas = PersonRepository()
        if socios is None:
            from repositories.socio_repository import SocioRepository
            socios = SocioRepository()
        if accesos is None:
            from repositories.acceso_repository import AccesoRepository
            accesos = AccesoRepository()
        self._personas, self._socios, self._accesos = personas, socios, accesos
        self._transaccion = transaccion

    def ingresos(self, sesion, desde, hasta, dni=None):
        """Informe de ingresos permitidos y rechazados entre dos fechas (incluidas)."""
        autorizar(sesion, REPORTE_CONSULTAR)
        if hasta < desde:
            raise DatosInvalidos("La fecha final no puede ser anterior a la inicial.")
        socio_id, quien = None, "todos los socios"
        with self._transaccion() as conn:
            if (dni or "").strip():
                persona = self._personas.obtener_por_dni(normalizar_dni(dni), conn=conn)
                socio = self._socios.obtener_por_persona(persona[0], conn=conn) if persona else None
                if socio is None:
                    raise DatosInvalidos("No hay ningún socio con ese DNI.")
                socio_id, quien = socio[0], f"{persona[2]} {persona[3]}"
            filas = self._accesos.informe(desde, hasta, socio_id, conn=conn)
        datos = []
        for momento, resultado, motivo, dni_s, nombre, apellido, plan, _distancia in filas:
            socio = f"{nombre} {apellido}" if nombre else "Sin identificar"
            datos.append([fecha_texto(momento), hora_texto(momento), socio, _dni(dni_s), plan or "—",
                          "Permitido" if resultado == "permitido" else "Rechazado",
                          ETIQUETAS_MOTIVO.get(motivo, "") if motivo else ""])
        permitidos = sum(1 for f in filas if f[1] == "permitido")
        rechazos = Counter(f[2] for f in filas if f[1] != "permitido")
        resumen = [f"Permitidos: {permitidos} · Rechazados: {sum(rechazos.values())}"]
        if rechazos:
            resumen.append("Rechazos por motivo: " + ", ".join(
                f"{ETIQUETAS_MOTIVO.get(m, m)} {n}" for m, n in rechazos.most_common()))
        return Informe("Ingresos y rechazos",
                       f"Del {fecha_texto(desde)} al {fecha_texto(hasta)} · {quien}",
                       ["Fecha", "Hora", "Socio", "DNI", "Plan", "Resultado", "Motivo"], datos, resumen)

    def membresias(self, sesion, hoy):
        """Estado de membresía y cupos de los socios activos."""
        autorizar(sesion, REPORTE_CONSULTAR)
        estados = self._socios.listar_estados()
        datos = []
        for e in estados:
            incluidos = e["accesos_incluidos"]
            cupo = f"{e['accesos_usados']} de {incluidos}" if incluidos else f"{e['accesos_usados']} (sin cupo)"
            maximo = e["max_dias_semanales"]
            semana = f"{e['dias_entrenados_semana']} de {maximo}" if maximo else str(e["dias_entrenados_semana"])
            datos.append([f"{e['nombre']} {e['apellido']}", _dni(e["dni"]), e["plan"] or "—",
                          fecha_texto(e["fecha_vencimiento"]) if e["fecha_vencimiento"] else "—",
                          cupo, semana, MEMBRESIA.get(e["estado_membresia"], e["estado_membresia"]),
                          CONTABLE.get(e["estado_contable"], e["estado_contable"]),
                          pesos(max(e["saldo"], 0)) if e["saldo"] is not None else "—"])
        conteo = Counter(MEMBRESIA.get(e["estado_membresia"]) for e in estados)
        resumen = [f"Socios activos: {len(estados)}"]
        if conteo:
            resumen.append(" · ".join(f"{texto}: {n}" for texto, n in conteo.most_common()))
        deuda = sum(max(e["saldo"] or 0, 0) for e in estados)
        if deuda:
            resumen.append(f"Saldo pendiente total: {pesos(deuda)}")
        return Informe("Estado de membresías y cupos", f"Al {fecha_texto(hoy)}",
                       ["Socio", "DNI", "Plan", "Vence", "Accesos usados", "Días esta semana",
                        "Membresía", "Estado contable", "Saldo"], datos, resumen)
