"""Licencias y permisos del personal: Jornadas, cámara, Fichajes, Informes y Panel."""
import os
from datetime import date, datetime, time, timedelta

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from apoyo_db import HOY_AR, membresia, persona, requiere_base, socio, usuario, valor  # noqa: E402
from services.acceso_service import AVISO, ENTRENAR, FICHAR, PROPUESTA, AccesoService  # noqa: E402
from services.auth_service import ADMINISTRADOR, Sesion  # noqa: E402
from services.fichajes_service import ErroresJornada, FichajesService  # noqa: E402
from ui import tema  # noqa: E402

LICENCIA = "Hoy tenés licencia: no corresponde marcar llegada."


@pytest.fixture(scope="module")
def app():
    aplicacion = QApplication.instance() or QApplication([])
    tema.aplicar_tema(aplicacion)
    return aplicacion


# --- Contra la base ---

@pytest.fixture
def entorno(db):
    """Gimnasio abierto todo el día, la dueña y el entrenador 'profe' con turno de 14 a 22."""
    for dia in range(1, 8):
        db.execute("INSERT INTO horario_atencion (dia_semana, hora_apertura, hora_cierre) "
                   "VALUES (%s, '00:00', '23:59')", (dia,))
    hoy = valor(db, f"SELECT {HOY_AR}")
    pid = persona(db, "27555888", "Sofía", "Romero")
    profe = usuario(db, pid, "profe")
    duenia = Sesion(valor(db, "SELECT id FROM usuario WHERE nombre_usuario = 'admin'"), None, "admin",
                    "Administrador", frozenset({ADMINISTRADOR}))
    servicio = FichajesService()
    servicio.cargar_turnos(duenia, profe, [hoy, hoy + timedelta(days=1)], time(14, 0), time(22, 0))
    return {"db": db, "hoy": hoy, "pid": pid, "profe": profe, "duenia": duenia, "servicio": servicio}


def _camara(hoy, hora, minuto=0):
    momento = datetime.combine(hoy, time(hora, minuto))
    return AccesoService(reloj=lambda conn: momento)


def _jornadas(e):
    return [(f[4], f[5], f[6], f[7]) for f in e["servicio"].jornadas(e["duenia"], e["hoy"], e["hoy"] + timedelta(days=3),
                                                                      e["profe"])]


@requiere_base
def test_licencia_de_varios_dias(entorno):
    e = entorno
    hoy = e["hoy"]
    dias = e["servicio"].dar_licencia(e["duenia"], e["profe"], hoy, hoy + timedelta(days=2), "Vacaciones")
    assert dias == 3
    # Los dos días con turno pasan a licencia; el tercero, sin turno, se crea de día completo.
    assert _jornadas(e) == [(hoy, time(14, 0), time(22, 0), "licencia_vacaciones"),
                            (hoy + timedelta(days=1), time(14, 0), time(22, 0), "licencia_vacaciones"),
                            (hoy + timedelta(days=2), time(0, 0), time(23, 59, 59), "licencia_vacaciones")]
    cambio = e["db"].execute("SELECT estado_anterior, estado_nuevo, motivo, cambiado_por_usuario_id, cambiado_en "
                             "FROM jornada_cambio ORDER BY id LIMIT 1").fetchone()
    assert cambio[:4] == ("jornada", "licencia_vacaciones", "Vacaciones", e["duenia"].usuario_id)
    assert cambio[4] is not None                                       # cuándo se aprobó

    ev = _camara(hoy, 14, 5).evaluar(e["pid"])
    assert (ev.estado, ev.mensaje) == (AVISO, LICENCIA)
    assert valor(e["db"], "SELECT COUNT(*) FROM fichaje") == 0

    filas = e["servicio"].fichajes(e["duenia"], hoy, hoy + timedelta(days=2))
    assert [f.estado for f in filas] == ["Licencia", "Licencia", "Licencia"]
    lote = e["servicio"].ausencias(e["duenia"], hoy, hoy + timedelta(days=5))
    assert [(l["tipo"], l["desde"], l["hasta"], l["motivo"]) for l in lote] == [
        ("Licencia", hoy, hoy + timedelta(days=2), "Vacaciones")]


@requiere_base
def test_permiso_de_dia_completo(entorno):
    e = entorno
    e["servicio"].dar_permiso(e["duenia"], e["profe"], e["hoy"], motivo="Trámite")
    for hora in (9, 14, 21):                                            # antes y durante el turno
        ev = _camara(e["hoy"], hora).evaluar(e["pid"])
        assert (ev.estado, ev.mensaje) == (AVISO, "Hoy tenés permiso: no corresponde marcar llegada.")
    estados = [f.estado for f in e["servicio"].fichajes(e["duenia"], e["hoy"], e["hoy"])]
    assert estados == ["Permiso", "Permiso"] and "Ausente" not in estados


@requiere_base
def test_permiso_por_horas_bloquea_adentro_y_permite_afuera(entorno):
    e = entorno
    e["servicio"].dar_permiso(e["duenia"], e["profe"], e["hoy"], time(14, 0), time(16, 0), "Turno médico")
    # El turno también empieza a las 14: el permiso queda un segundo después (no se ve en pantalla).
    assert (e["hoy"], time(14, 0, 1), time(16, 0), "permiso") in _jornadas(e)
    adentro = _camara(e["hoy"], 15, 0).evaluar(e["pid"])
    assert (adentro.estado, adentro.mensaje) == (
        AVISO, "Tenés permiso de 14:00 a 16:00: no corresponde marcar llegada.")
    afuera = _camara(e["hoy"], 16, 10)
    ev = afuera.evaluar(e["pid"])
    assert ev.estado == PROPUESTA and ev.tarjetas[3] == ("Estado", "Llegaste 10 min tarde", "ambar")
    assert afuera.confirmar(ev, FICHAR).registrado


@requiere_base
def test_entrenador_que_tambien_es_socio_solo_entrena(entorno):
    e = entorno
    membresia(e["db"], socio(e["db"], e["pid"]))
    e["servicio"].dar_licencia(e["duenia"], e["profe"], e["hoy"], e["hoy"])
    acceso = _camara(e["hoy"], 15)
    ev = acceso.evaluar(e["pid"])
    assert ev.estado == PROPUESTA and ev.modo == "socio"
    assert [(o.clave, o.boton) for o in ev.opciones] == [(ENTRENAR, "Entrar")]
    assert LICENCIA in ev.advertencias
    with pytest.raises(ValueError):
        acceso.confirmar(ev, FICHAR)
    assert acceso.confirmar(ev, ENTRENAR).registrado


@requiere_base
def test_salida_permitida_si_la_llegada_era_anterior(entorno):
    e = entorno
    # Marcó la llegada a las 14:00 y después la dueña le aprobó la licencia.
    e["db"].execute("INSERT INTO fichaje (usuario_id, entrada) VALUES (%s, NOW() - INTERVAL '3 hours')",
                    (e["profe"],))
    e["servicio"].dar_licencia(e["duenia"], e["profe"], e["hoy"], e["hoy"])
    acceso = _camara(e["hoy"], 23, 59)
    ev = acceso.evaluar(e["pid"])
    assert ev.estado == PROPUESTA and [o.boton for o in ev.opciones] == ["Me voy"]
    assert acceso.confirmar(ev, FICHAR).mensaje.startswith("Salida marcada a las")
    assert valor(e["db"], "SELECT COUNT(*) FROM fichaje WHERE salida IS NULL") == 0


@requiere_base
def test_anulacion_de_una_licencia(entorno):
    e = entorno
    hoy = e["hoy"]
    e["servicio"].dar_licencia(e["duenia"], e["profe"], hoy, hoy + timedelta(days=2), "Vacaciones")
    filas_antes = valor(e["db"], "SELECT COUNT(*) FROM jornada")
    (lote,) = e["servicio"].ausencias(e["duenia"], hoy, hoy + timedelta(days=5))
    assert e["servicio"].anular(e["duenia"], lote["jornada_id"], "Se suspendieron") == 3
    # Los turnos vuelven a 'jornada'; el día sin turno deja de contar (no se borra nada).
    assert _jornadas(e) == [(hoy, time(14, 0), time(22, 0), "jornada"),
                            (hoy + timedelta(days=1), time(14, 0), time(22, 0), "jornada")]
    assert valor(e["db"], "SELECT COUNT(*) FROM jornada") == filas_antes
    assert valor(e["db"], "SELECT COUNT(*) FROM jornada_cambio WHERE motivo = 'Anulación: Se suspendieron'") == 3
    assert e["servicio"].ausencias(e["duenia"], hoy, hoy + timedelta(days=5)) == []
    ev = _camara(hoy, 14, 5).evaluar(e["pid"])
    assert ev.estado == PROPUESTA and [o.boton for o in ev.opciones] == ["Llegué"]
    # El día que había quedado anulado se puede volver a usar: una nueva licencia reutiliza la fila.
    e["servicio"].dar_licencia(e["duenia"], e["profe"], hoy + timedelta(days=2), hoy + timedelta(days=2))
    assert valor(e["db"], "SELECT COUNT(*) FROM jornada") == filas_antes
    e["servicio"].cargar_turnos(e["duenia"], e["profe"], [hoy + timedelta(days=3)], time(0, 0), time(8, 0))


@requiere_base
def test_validaciones_de_licencia_y_permiso(entorno):
    e = entorno
    with pytest.raises(ErroresJornada):
        e["servicio"].dar_licencia(e["duenia"], e["profe"], e["hoy"], e["hoy"] - timedelta(days=1))
    with pytest.raises(ErroresJornada):
        e["servicio"].dar_permiso(e["duenia"], e["profe"], e["hoy"], time(16, 0), time(15, 0))
    with pytest.raises(ErroresJornada):
        e["servicio"].dar_licencia(e["duenia"], None, e["hoy"], e["hoy"])


@requiere_base
def test_informe_de_personal_y_panel(entorno):
    from repositories.panel_repository import PanelRepository
    from services.informe_service import InformeService
    e = entorno
    e["servicio"].dar_licencia(e["duenia"], e["profe"], e["hoy"], e["hoy"])
    informe = InformeService().personal(e["duenia"], e["hoy"], e["hoy"])
    assert [f[7] for f in informe.filas] == ["Licencia"] and informe.titulo == "Asistencia del personal"
    assert PanelRepository().ausencias_hoy()[0][:4] == ("Sofía", "Romero", "profe", "licencia_vacaciones")


# --- Pantallas ---

class ServicioFalso:
    def __init__(self):
        self.licencias, self.permisos, self.anuladas = [], [], []

    def personal(self, sesion):
        return [(7, "Sofía Romero")]

    def jornadas(self, sesion, desde, hasta, usuario_id=None):
        return []

    def ausencias(self, sesion, desde, hasta, usuario_id=None):
        return [{"jornada_id": 5, "empleado": "Sofía Romero", "tipo": "Licencia", "desde": date(2026, 11, 16),
                 "hasta": date(2026, 11, 20), "horario": "Día completo", "aprobado_por": "Administrador",
                 "aprobado_en": datetime(2026, 11, 13, 10, 0), "motivo": "Vacaciones"}]

    def dar_licencia(self, sesion, usuario_id, desde, hasta, motivo=""):
        self.licencias.append((usuario_id, desde, hasta, motivo))
        return (hasta - desde).days + 1

    def dar_permiso(self, sesion, usuario_id, fecha, desde=None, hasta=None, motivo=""):
        self.permisos.append((usuario_id, fecha, desde, hasta, motivo))
        return True

    def anular(self, sesion, jornada_id, motivo=""):
        self.anuladas.append(jornada_id)
        return 5


def test_pantalla_dar_licencia_permiso_y_anular(app):
    from ui.jornadas_page import JornadasPage
    from ui.tablas import textos
    pedidos = []

    def pedir(_parent, tipo, personal, hoy):
        pedidos.append((tipo, personal))
        if tipo == "licencia":
            return {"tipo": tipo, "usuario_id": 7, "empleado": "Sofía Romero", "desde": date(2026, 11, 16),
                    "hasta": date(2026, 11, 20), "horas": None, "motivo": "Vacaciones"}
        return {"tipo": tipo, "usuario_id": 7, "empleado": "Sofía Romero", "desde": date(2026, 11, 13),
                "hasta": date(2026, 11, 13), "horas": (time(14, 0), time(16, 0)), "motivo": ""}
    pagina = JornadasPage(DUENIA_FALSA, ServicioFalso(), hoy=lambda: date(2026, 11, 13), pedir=pedir,
                          confirmar_accion=lambda *_: True)
    pagina.resize(1300, 900)
    pagina.show()
    app.processEvents()
    assert textos(pagina.tabla_ausencias)[0][:7] == [
        "Sofía Romero", "Licencia", "16/11/2026 al 20/11/2026", "Día completo", "Administrador",
        "13/11/2026 10:00", "Vacaciones"]
    pagina.dar_ausencia("licencia")
    assert pagina.servicio.licencias == [(7, date(2026, 11, 16), date(2026, 11, 20), "Vacaciones")]
    assert pagina.mensaje_ausencias.text() == "Licencia aprobada para Sofía Romero: 5 días."
    pagina.dar_ausencia("permiso")
    assert pagina.servicio.permisos == [(7, date(2026, 11, 13), time(14, 0), time(16, 0), "")]
    assert pagina.mensaje_ausencias.text() == "Permiso aprobado para Sofía Romero el 13/11/2026, de 14:00 a 16:00."
    assert pedidos[0] == ("licencia", [(7, "Sofía Romero")])
    pagina.anular(pagina._ausencias[0])
    assert pagina.servicio.anuladas == [5]


def test_dialogo_de_permiso_valida_las_horas(app):
    from PySide6.QtCore import QTime
    from ui.jornadas_page import DialogoAusencia
    dialogo = DialogoAusencia("permiso", [(7, "Sofía Romero")], date(2026, 11, 13))
    assert not dialogo.hora_desde.isEnabled()
    dialogo.aprobar()
    assert dialogo.campos["empleado"].mensaje.text() == "Elegí el empleado." and dialogo.datos is None
    dialogo.empleado.setCurrentIndex(1)
    dialogo.solo_horas.setChecked(True)
    dialogo.hora_hasta.setTime(QTime(13, 0))
    dialogo.aprobar()
    assert dialogo.campos["hora_hasta"].mensaje.text() == "Tiene que ser posterior a la hora inicial."
    dialogo.hora_hasta.setTime(QTime(16, 0))
    dialogo.aprobar()
    assert dialogo.datos["horas"] == (time(14, 0), time(16, 0)) and dialogo.datos["hasta"] == date(2026, 11, 13)
    licencia = DialogoAusencia("licencia", [(7, "Sofía Romero")], date(2026, 11, 13))
    licencia.empleado.setCurrentIndex(1)
    licencia.hasta.setDate(licencia.desde.date().addDays(-1))
    licencia.aprobar()
    assert licencia.campos["hasta"].mensaje.text() == "No puede ser anterior a Desde."


DUENIA_FALSA = Sesion(1, None, "admin", "Administrador", frozenset({ADMINISTRADOR}))
