"""Panel del administrador: indicadores del gimnasio calculados desde la base.

Se actualiza al abrir la sección, con el botón "Actualizar" y solo cada 15 s
mientras está a la vista. Si los datos no cambiaron no se vuelve a dibujar
nada, y cuando cambian se repinta todo de una vez: sin parpadeo."""
from datetime import datetime

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from services.reglas_ingreso import ETIQUETAS_MOTIVO, es_dia_completo, fecha_texto, hora_texto, pesos
from ui import iconos, tema
from ui.componentes import EtiquetaEstado, con_rol, etiqueta
from ui.graficos import BarrasHorizontales, BarrasVerticales

HORA_DESDE, HORA_HASTA = 6, 23
NOMBRES_ROL = {"entrenador": "Entrenador", "recepcionista": "Recepcionista", "administrador": "Administrador"}


def texto_ausencia(nombre, apellido, usuario, estado, desde, hasta):
    """'Sofía Romero · Licencia' o 'Luis Gómez · Permiso de 14:00 a 16:00'."""
    quien = f"{nombre or usuario} {apellido or ''}".strip()
    if estado == "licencia_vacaciones":
        return f"{quien} · Licencia"
    if es_dia_completo(desde, hasta):
        return f"{quien} · Permiso"
    return f"{quien} · Permiso de {hora_texto(desde)} a {hora_texto(hasta)}"


class Indicador(QFrame):
    """Tarjeta con un número grande: TÍTULO / valor / detalle."""

    def __init__(self, titulo):
        super().__init__()
        con_rol(self, "panel")
        self.titulo = etiqueta(titulo.upper(), "dato-panel")
        self.titulo.setWordWrap(True)
        self.valor = etiqueta("—", "numero-panel")
        self.detalle = etiqueta("", "secundario")
        self.detalle.setWordWrap(True)
        columna = QVBoxLayout(self)
        columna.setContentsMargins(20, 18, 20, 18)
        columna.setSpacing(6)
        columna.addWidget(self.titulo)
        columna.addWidget(self.valor)
        columna.addWidget(self.detalle)
        columna.addStretch()

    def mostrar(self, valor, detalle=""):
        self.valor.setText(str(valor))
        self.detalle.setText(detalle)


class Lista(QFrame):
    """Panel con título, etiqueta de estado (cantidad) y una lista de filas."""

    MAXIMO = 8

    def __init__(self, titulo, tono, vacio):
        super().__init__()
        con_rol(self, "panel")
        self._vacio = vacio
        self.estado = EtiquetaEstado("0", tono)
        encabezado = QHBoxLayout()
        nombre = etiqueta(titulo, "titulo-panel")
        nombre.setWordWrap(True)
        encabezado.addWidget(nombre, 1)
        encabezado.addWidget(self.estado, 0, Qt.AlignmentFlag.AlignTop)
        self.filas = QVBoxLayout()
        self.filas.setSpacing(0)
        columna = QVBoxLayout(self)
        columna.setContentsMargins(20, 18, 20, 18)
        columna.addLayout(encabezado)
        columna.addSpacing(8)
        columna.addLayout(self.filas)
        columna.addStretch()

    def mostrar(self, filas, texto_estado):
        """filas: [(principal, secundario)]."""
        while self.filas.count():
            item = self.filas.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.estado.setText(texto_estado)
        if not filas:
            vacio = etiqueta(self._vacio, "secundario")
            vacio.setWordWrap(True)
            self.filas.addWidget(vacio)
        for principal, secundario in filas[:self.MAXIMO]:
            fila = con_rol(QFrame(), "fila-ingreso")
            interior = QVBoxLayout(fila)
            interior.setContentsMargins(0, 8, 0, 8)
            interior.setSpacing(2)
            nombre = QLabel(principal)
            nombre.setStyleSheet("font-size: 14px; font-weight: 700;")
            nombre.setWordWrap(True)
            detalle = etiqueta(secundario, "secundario")
            detalle.setWordWrap(True)
            interior.addWidget(nombre)
            interior.addWidget(detalle)
            self.filas.addWidget(fila)
        if len(filas) > self.MAXIMO:
            self.filas.addWidget(etiqueta(f"y {len(filas) - self.MAXIMO} más…", "secundario"))


class Grafico(QFrame):
    def __init__(self, titulo, grafico):
        super().__init__()
        con_rol(self, "panel")
        self.grafico = grafico
        columna = QVBoxLayout(self)
        columna.setContentsMargins(20, 18, 20, 18)
        nombre = etiqueta(titulo, "titulo-panel")
        nombre.setWordWrap(True)
        columna.addWidget(nombre)
        columna.addSpacing(10)
        alto_fijo = grafico.sizePolicy().verticalPolicy() == grafico.sizePolicy().Policy.Fixed
        columna.addWidget(grafico, 0 if alto_fijo else 1)
        if alto_fijo:
            columna.addStretch(1)


def texto_vence(dias):
    return "vence mañana" if dias == 1 else f"vence en {dias} días"


def filas_por_vencer(por_vencer):
    return [(f"{n} {a}", f"{plan} · {texto_vence(dias)} ({fecha_texto(vence)})")
            for n, a, plan, vence, dias in por_vencer]


def filas_deben(deben):
    filas = []
    for n, a, saldo, estado in deben:
        partes = []
        if saldo and saldo > 0:
            partes.append(f"Debe {pesos(saldo)}")
        if estado == "vencida":
            partes.append("Membresía vencida")
        filas.append((f"{n} {a}", " · ".join(partes) or "Debe"))
    return filas


def serie_por_hora(por_hora):
    """(etiquetas, valores, tooltips) de HORA_DESDE a HORA_HASTA, ampliado si
    hay ingresos fuera de ese rango."""
    desde = min([HORA_DESDE] + list(por_hora))
    hasta = max([HORA_HASTA] + list(por_hora))
    horas = range(desde, hasta + 1)
    valores = [por_hora.get(h, 0) for h in horas]
    tooltips = [f"{h:02d} a {h + 1:02d} h · {v} {'ingreso' if v == 1 else 'ingresos'}"
                for h, v in zip(horas, valores)]
    return [f"{h}" for h in horas], valores, tooltips


class PanelPage(QWidget):
    INTERVALO_MS = 15_000

    def __init__(self, sesion, servicio=None, reloj=datetime.now):
        super().__init__()
        if servicio is None:
            from services.panel_service import PanelService
            servicio = PanelService()
        self.sesion, self.servicio = sesion, servicio
        self._reloj = reloj
        self._datos = None            # últimos datos mostrados (para no repintar si no cambian)

        self.boton_actualizar = QPushButton("Actualizar")
        self.boton_actualizar.setIcon(iconos.icono_menu("actualizar", tema.TEXTO, tema.TEXTO))
        self.boton_actualizar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.boton_actualizar.setMinimumHeight(38)
        self.boton_actualizar.setToolTip("Volver a consultar los indicadores ahora")
        self.boton_actualizar.clicked.connect(self.actualizar_ahora)
        self.actualizado = etiqueta("", "secundario")

        self.error = etiqueta("", "error")
        self.error.setWordWrap(True)
        self.error.hide()
        self.hoy = Indicador("Ingresos de hoy")
        self.vigentes = Indicador("Socios con membresía vigente")
        self.recaudacion = Indicador("Recaudación del mes")
        self.trabajando = Indicador("Empleados trabajando")
        self.por_vencer = Lista("Por vencer (5 días o menos)", "ambar", "Ninguna membresía vence en los próximos 5 días.")
        self.deben = Lista("Socios que deben", "rojo", "Ningún socio tiene deuda ni membresía vencida.")
        self.rechazos = BarrasHorizontales(tema.ROJO, "Hoy no hubo rechazos.")
        self.por_hora = BarrasVerticales(tema.DORADO, "Todavía no hay ingresos en los últimos 30 días.")
        self.por_plan = BarrasHorizontales(tema.DORADO, "No hay planes activos.")
        self.titulo_rechazos = etiqueta("Rechazos de hoy", "titulo-panel")
        self.total_rechazos = EtiquetaEstado("0", "rojo")

        rechazos = con_rol(QFrame(), "panel")
        self.titulo_rechazos.setWordWrap(True)
        encabezado = QHBoxLayout()
        encabezado.addWidget(self.titulo_rechazos, 1)
        encabezado.addStretch()
        encabezado.addWidget(self.total_rechazos)
        columna_r = QVBoxLayout(rechazos)
        columna_r.setContentsMargins(20, 18, 20, 18)
        columna_r.addLayout(encabezado)
        columna_r.addSpacing(10)
        columna_r.addWidget(self.rechazos)
        columna_r.addStretch()

        grilla = QGridLayout()
        grilla.setSpacing(16)
        for columna, tarjeta in enumerate((self.hoy, self.vigentes, self.recaudacion, self.trabajando)):
            grilla.addWidget(tarjeta, 0, columna)
        grilla.addWidget(self.por_vencer, 1, 0, 1, 2)
        grilla.addWidget(self.deben, 1, 2)
        grilla.addWidget(rechazos, 1, 3)
        grilla.addWidget(Grafico("Ingresos por hora · últimos 30 días", self.por_hora), 2, 0, 1, 3)
        grilla.addWidget(Grafico("Socios por plan (membresía vigente)", self.por_plan), 2, 3)
        for columna in range(4):
            grilla.setColumnStretch(columna, 1)

        contenido = QWidget()
        columna = QVBoxLayout(contenido)
        columna.setContentsMargins(0, 0, 4, 0)
        columna.setSpacing(16)
        barra = QHBoxLayout()
        barra.addWidget(self.error, 1)
        barra.addStretch()
        barra.addWidget(self.boton_actualizar, 0, Qt.AlignmentFlag.AlignTop)
        columna.addLayout(barra)
        columna.addLayout(grilla)
        columna.addWidget(self.actualizado, 0, Qt.AlignmentFlag.AlignRight)
        columna.addStretch()
        self.contenido = contenido
        desplazable = QScrollArea()
        desplazable.setWidgetResizable(True)
        desplazable.setFrameShape(QFrame.Shape.NoFrame)
        desplazable.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        desplazable.setWidget(contenido)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(desplazable)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.actualizar)

    def showEvent(self, evento):
        super().showEvent(evento)
        self.actualizar()
        self.timer.start(self.INTERVALO_MS)

    def hideEvent(self, evento):
        self.timer.stop()
        super().hideEvent(evento)

    def liberar(self):
        self.timer.stop()

    def actualizar_ahora(self):
        """Botón Actualizar: consulta ya y reinicia la cuenta de 15 s."""
        self.actualizar()
        if self.isVisible():
            self.timer.start(self.INTERVALO_MS)

    def actualizar(self):
        try:
            datos = self.servicio.indicadores(self.sesion)
        except Exception as error:
            self.error.setText(f"No se pudieron consultar los indicadores. {error}")
            self.error.show()
            return
        self.error.hide()
        if datos != self._datos:
            self.contenido.setUpdatesEnabled(False)      # se repinta todo junto
            try:
                self.mostrar(datos)
            finally:
                self.contenido.setUpdatesEnabled(True)
            self._datos = datos
        self.actualizado.setText(f"Actualizado a las {self._reloj():%H:%M:%S}")

    def mostrar(self, d):
        self.hoy.mostrar(d.ingresos_hoy, f"{d.ingresos_semana} en la semana (desde el lunes)")
        self.vigentes.mostrar(d.socios_vigentes, "Socios activos con un plan en vigencia")
        self.recaudacion.mostrar(pesos(d.recaudacion_mes), "Pagos registrados en el mes")
        nombres = [f"{n or u} {a or ''}".strip() + f" · desde las {hora_texto(e)}"
                   for n, a, u, e, _roles in d.empleados_trabajando]
        nombres += [texto_ausencia(*fila) for fila in d.ausencias_hoy]
        self.trabajando.mostrar(len(d.empleados_trabajando), "\n".join(nombres) or "Nadie fichó entrada")
        self.por_vencer.mostrar(filas_por_vencer(d.por_vencer), str(len(d.por_vencer)))
        self.deben.mostrar(filas_deben(d.deben), str(len(d.deben)))
        self.total_rechazos.setText(str(d.total_rechazos_hoy))
        self.rechazos.mostrar([(ETIQUETAS_MOTIVO.get(m, m), c) for m, c in d.rechazos_hoy])
        self.por_hora.mostrar(*serie_por_hora(d.ingresos_por_hora))
        self.por_plan.mostrar(d.socios_por_plan)
