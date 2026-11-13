"""Pantalla Control de acceso y modal de confirmación (Qt offscreen, sin
cámara real, sin proceso de reconocimiento y sin base de datos)."""
import os
from datetime import datetime, time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from ui import tema  # noqa: E402

PROPUESTA_ANA = {
    "estado": "PROPUESTA", "token": "t1", "cierre_s": 60, "mensaje": "¿Confirmás tu entrada al gimnasio?",
    "evaluacion": {
        "nombre": "Juan Pérez", "dni": "30.111.222", "rol_texto": "Socio", "modo": "socio",
        "opciones": [{"clave": "entrenar", "boton": "Entrar", "habilitada": True, "motivo": None}],
        "sugerida": "entrenar",
        "tarjetas": [["Plan", "3 veces por semana", None], ["Esta semana", "2 de 3 días", None],
                     ["Vence", "05/12 · en 23 días", None], ["Estado contable", "Al día", "verde"]],
        "advertencias": [], "lineas": [],
    },
}

EMPLEADO = {
    "nombre": "Sofía Romero", "dni": "27.555.888", "rol_texto": "Entrenador", "modo": "empleado",
    "opciones": [{"clave": "fichar", "boton": "Llegué", "habilitada": True, "motivo": None}],
    "sugerida": "fichar",
    "tarjetas": [["Rol", "Entrenador", None], ["Turno de hoy", "14:00–22:00", None],
                 ["Hora", "14:05", None], ["Estado", "Llegaste 5 min tarde", "ambar"]],
    "advertencias": [], "lineas": [],
}

AMBOS = {
    "nombre": "Sofía Romero", "dni": "27.555.888", "rol_texto": "Socio y entrenador", "modo": "ambos",
    "opciones": [{"clave": "fichar", "boton": "Trabajar", "habilitada": True, "motivo": None},
                 {"clave": "entrenar", "boton": "Entrenar", "habilitada": True, "motivo": None}],
    "sugerida": "fichar", "tarjetas": [], "advertencias": [],
    "lineas": [["Empleado · Turno 14:00–22:00 · En horario", "verde"],
               ["Socio · Pase libre · Vigente (vence 05/12)", "verde"]],
}


@pytest.fixture(scope="module")
def app():
    aplicacion = QApplication.instance() or QApplication([])
    tema.aplicar_tema(aplicacion)
    return aplicacion


class Reloj:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


class Worker:
    def __init__(self):
        self.enviados = []
        self.detenido = False

    def iniciar(self):
        pass

    def enviar(self, mensaje):
        self.enviados.append(mensaje)

    def detener(self):
        self.detenido = True

    def comandos(self):
        return [m["cmd"] for m in self.enviados]


class Camara:
    def __init__(self, abre=True):
        self.abre, self.abierta = abre, False

    def open(self):
        self.abierta = self.abre
        return self.abre

    def read_frame(self):
        return np.zeros((480, 640, 3), np.uint8) if self.abierta else None

    def close(self):
        self.abierta = False


class Detector:
    def __init__(self):
        self.caras = [(200, 120, 200, 200)]

    def detectar(self, _frame):
        return list(self.caras)

    def filtrar(self, caras):
        return caras

    def recortar(self, frame, rect):
        x, y, w, h = rect
        return frame[y:y + h, x:x + w]


class Horario:
    def franjas_semana(self):
        from datetime import time
        from services.reglas_ingreso import Franja
        semana = {d: [Franja(time(7, 30), time(23, 0))] for d in range(1, 6)}
        semana[6] = [Franja(time(10, 0), time(14, 0))]
        return semana


class Fichajes:
    def __init__(self):
        self.filas = [(1, "Sofía", "Romero", datetime(2026, 11, 12, 14, 5), None, 3, time(14, 0))]

    def ultimos(self, limite=4):
        return self.filas


class Accesos:
    def __init__(self):
        self.consultas = 0
        self.socios_hoy = 2
        self.filas = [(1, datetime(2026, 11, 12, 18, 41), "permitido", None, "Juan", "Pérez",
                       "3 veces por semana")]

    def socios_que_entrenaron_hoy(self):
        return self.socios_hoy

    def ultimos(self, limite=5):
        self.consultas += 1
        return self.filas


@pytest.fixture
def pagina(app):
    from ui.control_acceso_page import ControlAccesoPage
    reloj = Reloj()
    elecciones = []
    p = ControlAccesoPage(worker=Worker(), camara=Camara(), detector=Detector(), accesos=Accesos(), fichajes=Fichajes(),
                          abrir_modal=lambda ev, s: elecciones.pop(0) if elecciones else None,
                          reloj=reloj, horario=Horario())
    p.resize(1000, 700)
    p.show()
    app.processEvents()
    p.reloj, p.elecciones = reloj, elecciones
    yield p
    p.liberar()


def _listo(p):
    p.on_respuesta({"estado": "MODELO_LISTO", "mensaje": ""})


def test_inicio_precarga_y_lee_ultimos(pagina, app):
    assert pagina.worker.comandos() == ["precargar"]           # una sola carga
    assert pagina.accesos.consultas >= 1
    pagina.hide()
    pagina.show()                                             # volver a la pantalla no recarga nada
    app.processEvents()
    assert pagina.worker.comandos() == ["precargar"]
    assert pagina.camara_panel.chip_estado.text() == "Cargando reconocimiento…"
    _listo(pagina)
    assert pagina.camara_panel.chip_estado.text() == "Reconocimiento en curso"


def test_envia_un_rostro_cada_dos_segundos(pagina):
    _listo(pagina)
    pagina.actualizar()
    pagina.actualizar()                                       # esperando respuesta: no reenvía
    assert pagina.worker.comandos().count("reconocer") == 1
    pagina.on_respuesta({"estado": "CONFIRMANDO", "mensaje": "Verificando identidad"})
    assert pagina.camara_panel.chip_estado.text() == "Verificando identidad…"
    pagina.actualizar()                                       # todavía no pasaron 2 s
    pagina.reloj.t += 2.0
    pagina.actualizar()
    assert pagina.worker.comandos().count("reconocer") == 2


def test_sin_rostro_o_con_dos_rostros_no_envia(pagina):
    _listo(pagina)
    pagina.detector.caras = []
    pagina.actualizar()
    pagina.detector.caras = [(10, 10, 100, 100), (300, 10, 100, 100)]
    pagina.actualizar()
    assert "reconocer" not in pagina.worker.comandos()


def test_propuesta_ok_confirma_y_pausa(pagina):
    _listo(pagina)
    pagina.elecciones.append("entrenar")
    pagina.on_respuesta(PROPUESTA_ANA)
    assert pagina.worker.enviados[-1] == {"cmd": "confirmar", "token": "t1", "opcion": "entrenar"}
    assert pagina.pausado
    pagina.reloj.t += 5
    pagina.actualizar()                                       # en pausa: no reconoce
    assert "reconocer" not in pagina.worker.comandos()
    consultas = pagina.accesos.consultas
    pagina.on_respuesta({"estado": "CONFIRMADO", "mensaje": "Ingreso registrado a las 18:42.",
                         "nombre": "Juan Pérez", "opcion": "entrenar", "tono": "verde"})
    aviso = pagina.camara_panel.aviso
    assert not pagina.pausado and aviso.isVisible()
    assert (aviso.titulo.text(), aviso.property("tono")) == ("Entrada al gimnasio · Juan Pérez", "verde")
    assert pagina.accesos.consultas == consultas + 1         # se actualizan los últimos ingresos


def test_propuesta_cancelada_no_confirma(pagina):
    _listo(pagina)
    pagina.on_respuesta(PROPUESTA_ANA)                        # el modal devuelve None
    assert pagina.worker.enviados[-1] == {"cmd": "cancelar", "token": "t1"}
    pagina.on_respuesta({"estado": "CANCELADO", "mensaje": "Cancelado. No se guardó nada."})
    assert not pagina.pausado
    assert pagina.camara_panel.aviso.titulo.text() == "Cancelado"


def test_rechazo_muestra_motivo_y_reintento(pagina):
    _listo(pagina)
    pagina.on_respuesta({"estado": "RECHAZADO", "nombre": "Lucas Díaz", "motivo": "limite_semanal",
                         "etiqueta": "Límite semanal", "reintento_s": 10,
                         "mensaje": "Ya entrenó 3 días esta semana: es el límite del plan "
                                    "3 veces por semana. Puede volver el lunes."})
    panel = pagina.camara_panel
    assert panel.aviso.titulo.text() == "Ingreso rechazado · Lucas Díaz"
    assert panel.chip_estado.text() == "Reintento en 10 s" and panel.property("tono") == "rojo"
    pagina.reloj.t += 3.2
    pagina.actualizar()
    assert panel.chip_estado.text() == "Reintento en 7 s"
    pagina.reloj.t += 2
    pagina.actualizar()                                       # pasaron los 5 s del aviso
    assert not panel.aviso.isVisible() and panel.property("tono") == "dorado"


def test_rechazo_de_un_rostro_desconocido(pagina):
    pagina.on_respuesta({"estado": "RECHAZADO", "nombre": None, "motivo": "no_reconocido",
                         "etiqueta": "No reconocido", "reintento_s": 10,
                         "mensaje": "No pudimos reconocerte. Acercate a recepción."})
    assert pagina.camara_panel.aviso.titulo.text() == "Ingreso rechazado · No reconocido"


def test_camara_no_disponible(app):
    from ui.control_acceso_page import ControlAccesoPage
    p = ControlAccesoPage(worker=Worker(), camara=Camara(abre=False), detector=Detector(),
                          accesos=Accesos(), fichajes=Fichajes(), abrir_modal=lambda ev, s: None, horario=Horario())
    p.show()
    app.processEvents()
    assert p.camara_panel.chip_estado.text() == "Cámara no disponible"
    assert p.camara_panel.video.text() == "No se pudo acceder a la cámara."
    p.liberar()
    assert p.worker.detenido


def test_ultimos_ingresos_y_mensajes(pagina):
    from ui.control_acceso_page import describir_ingreso
    momento = datetime(2026, 11, 12, 18, 30)
    assert describir_ingreso((1, momento, "permitido", None, "Juan", "Pérez", "Pase libre")) == (
        "Juan Pérez", "18:30 · Pase libre", "Permitido", "verde")
    assert describir_ingreso((2, momento, "rechazado", "limite_semanal", "Lucas", "Díaz",
                              "3 veces por semana")) == (
        "Lucas Díaz", "18:30 · 3 veces por semana", "Límite semanal", "rojo")
    assert describir_ingreso((3, momento, "rechazado", "no_reconocido", None, None, None)) == (
        "No reconocido", "18:30 · —", "Rechazado", "rojo")
    assert pagina.ultimos.socios.filas.count() == 1


def test_fichajes_del_personal(pagina):
    from ui.control_acceso_page import describir_fichaje
    llegada = datetime(2026, 11, 12, 14, 5)
    salida = datetime(2026, 11, 12, 22, 1)
    assert describir_fichaje((1, "Sofía", "Romero", llegada, None, 3, time(14, 0))) == (
        "Sofía Romero", "Llegada 14:05 · Salida en curso", "5 min tarde", "ambar")
    assert describir_fichaje((2, "Sofía", "Romero", llegada, salida, 3, time(14, 30))) == (
        "Sofía Romero", "Llegada 14:05 · Salida 22:01", "En horario", "verde")
    assert describir_fichaje((3, "Sofía", "Romero", llegada, salida, None, None))[2:] == (
        "Fuera de turno", "ambar")
    personal = pagina.ultimos.personal
    assert personal.filas.count() == 1 and not personal.vacio.isVisible()


def test_listas_sin_base(pagina):
    def falla(_limite):
        raise ConnectionError("sin base")
    pagina.fichajes.ultimos = falla
    pagina.refrescar_ultimos()
    assert pagina.ultimos.personal.vacio.text() == "No se pudieron consultar los fichajes."
    assert pagina.ultimos.socios.filas.count() == 1             # la otra lista sigue funcionando


def test_marco_del_rostro():
    from ui.control_acceso_page import COLOR_MARCO, dibujar_marco
    frame = np.zeros((200, 200, 3), np.uint8)
    dibujar_marco(frame, (50, 50, 100, 100), COLOR_MARCO["dorado"])
    assert tuple(frame[50, 55]) == COLOR_MARCO["dorado"] and tuple(frame[100, 100]) == (0, 0, 0)


# --- Modal ---

def _modal(evaluacion):
    from ui.modal_confirmacion import ModalConfirmacion
    return ModalConfirmacion(evaluacion)


def _textos_visibles(m):
    from PySide6.QtWidgets import QLabel, QPushButton
    return " ".join(w.text() for tipo in (QLabel, QPushButton) for w in m.findChildren(tipo))


def test_modal_del_socio(app):
    m = _modal(PROPUESTA_ANA["evaluacion"])
    assert (m.titulo.text(), m.encabezado.text()) == ("¡Hola, Juan!", "¿Confirmás tu entrada al gimnasio?")
    assert m.cuenta.text() == "Se cancela solo en 60 s"
    texto = _textos_visibles(m)
    assert "Esta semana" in texto and "2 de 3 días" in texto
    assert [b.text() for b in m.botones_opcion.values()] == ["Entrar"]
    assert m.botones_opcion["entrenar"].property("rol") == "primario"
    m.botones_opcion["entrenar"].click()
    assert m.opcion == "entrenar"


def test_modal_del_empleado(app):
    m = _modal(EMPLEADO)
    assert m.titulo.text() == "Asistencia laboral"
    assert m.detalle.text() == "DNI 27.555.888 · Entrenador"
    texto = _textos_visibles(m)
    assert "Turno de hoy" in texto and "Llegaste 5 min tarde" in texto
    assert "Plan" not in texto and "Estado contable" not in texto
    assert [b.text() for b in m.botones_opcion.values()] == ["Llegué"]
    m.botones_opcion["fichar"].click()
    assert m.opcion == "fichar"


def test_modal_socio_y_empleado(app):
    m = _modal(AMBOS)
    assert (m.titulo.text(), m.encabezado.text()) == ("Hola, Sofía", "¿Qué vas a hacer?")
    assert [l.texto.text() for l in m.lineas] == [
        "Empleado · Turno 14:00–22:00 · En horario", "Socio · Pase libre · Vigente (vence 05/12)"]
    assert [b.text() for b in m.botones_opcion.values()] == ["Trabajar", "Entrenar"]
    assert m.botones_opcion["fichar"].property("rol") == "primario"        # la sugerida, en dorado
    assert m.botones_opcion["entrenar"].property("rol") != "primario"
    assert not m.motivo.isVisible() and m.motivo.text() == ""
    m.botones_opcion["entrenar"].click()
    assert m.opcion == "entrenar"


def test_entrenar_deshabilitado_muestra_el_motivo(app):
    ev = dict(AMBOS, opciones=[
        {"clave": "fichar", "boton": "Trabajar", "habilitada": True, "motivo": None},
        {"clave": "entrenar", "boton": "Entrenar", "habilitada": False,
         "motivo": "Su membresía venció el 10/11/2026. Renovala en el mostrador."}])
    m = _modal(ev)
    assert not m.botones_opcion["entrenar"].isEnabled()
    assert m.motivo.text() == "Entrenar no disponible: Su membresía venció el 10/11/2026. Renovala en el mostrador."


def test_el_modal_no_dice_registrar_ni_operacion(app):
    for ev in (PROPUESTA_ANA["evaluacion"], EMPLEADO, AMBOS):
        texto = _textos_visibles(_modal(ev)).lower()
        assert "registr" not in texto and "operación" not in texto


def test_botones_pasan_a_dos_filas_si_no_entran(app):
    m = _modal(AMBOS)
    fila = m.botones
    assert fila.dos_filas is False
    for boton in (m.boton_cancelar, *m.botones_opcion.values()):        # nunca cortan su texto
        assert boton.minimumSizeHint().width() >= boton.fontMetrics().horizontalAdvance(boton.text())
    fila.acomodar(fila.ancho_necesario() - 1)
    assert fila.dos_filas is True
    posicion = {fila.grilla.getItemPosition(fila.grilla.indexOf(b))[:2]: b.text()
                for b in (m.boton_cancelar, *m.botones_opcion.values())}
    assert posicion == {(0, 0): "Trabajar", (0, 1): "Entrenar", (1, 0): "Cancelar"}
    fila.acomodar(fila.ancho_necesario())
    assert fila.dos_filas is False


def test_modal_se_cierra_solo_como_cancelar(app):
    m = _modal(PROPUESTA_ANA["evaluacion"])
    for _ in range(59):
        m._tic()
    assert m.cuenta.text() == "Se cancela solo en 1 s" and m.result() == 0
    m._tic()
    assert m.opcion is None and not m._reloj.isActive()


def test_modal_cancelar(app):
    m = _modal(PROPUESTA_ANA["evaluacion"])
    m.boton_cancelar.click()
    assert m.opcion is None


def test_modal_con_advertencias(app):
    from ui.modal_confirmacion import tono_advertencia
    assert [tono_advertencia(t) for t in ("Debe $8.000,00", "Vence en 3 días", "Hoy figura con permiso.",
                                          "Le quedan 2 accesos después de este")] == [
        "rojo", "ambar", "ambar", "neutro"]
    m = _modal(dict(EMPLEADO, advertencias=["Hoy figura con permiso."]))
    assert "Hoy figura con permiso." in _textos_visibles(m)


def test_franja_con_socios_de_hoy_y_horario(pagina):
    franja = pagina.franja
    assert franja.titulo.text() == "Hoy entrenaron 2 socios"
    assert franja.subtitulo.text() == "Horario: Lun a Vie 7:30–23 · Sáb 10–14"
    assert franja.height() == franja.ALTO
    pagina.accesos.socios_hoy = 3
    _listo(pagina)
    pagina.on_respuesta({"estado": "CONFIRMADO", "mensaje": "Ingreso registrado a las 18:42.",
                         "nombre": "Juan Pérez", "opcion": "entrenar", "tono": "verde"})
    assert franja.titulo.text() == "Hoy entrenaron 3 socios"     # se actualiza con cada ingreso
    pagina.accesos.socios_hoy = 1
    pagina.refrescar_franja()
    assert franja.titulo.text() == "Hoy entrenó 1 socio"


def test_franja_sin_base(pagina):
    def falla():
        raise ConnectionError("sin base")
    pagina.accesos.socios_que_entrenaron_hoy = falla
    pagina.horario.franjas_semana = falla
    pagina.refrescar_franja()
    assert pagina.franja.titulo.text() == "Hoy entrenaron —"
    assert pagina.franja.subtitulo.text() == "Horario no disponible"


def test_aviso_se_oculta_a_los_cinco_segundos(pagina):
    pagina.on_respuesta({"estado": "RECHAZADO", "nombre": "Ana Ruiz", "motivo": "limite_diario",
                         "etiqueta": "Ya ingresó hoy", "reintento_s": 10, "mensaje": "Ya ingresó hoy."})
    assert pagina.camara_panel.aviso.isVisible()
    pagina.reloj.t += 4.9
    pagina.actualizar()
    assert pagina.camara_panel.aviso.isVisible()
    pagina.reloj.t += 0.2
    pagina.actualizar()
    assert not pagina.camara_panel.aviso.isVisible()
