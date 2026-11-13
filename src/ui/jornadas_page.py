"""Jornadas (solo la dueña): carga de turnos del personal por rango de
fechas y días de la semana, y cambios de horario o de estado (licencia,
permiso) que quedan registrados en jornada_cambio."""
from datetime import date, time, timedelta

from PySide6.QtCore import QTime, Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDateEdit, QFrame, QHBoxLayout, QLineEdit, QPushButton, QScrollArea, QTimeEdit,
    QVBoxLayout, QWidget,
)

from services.fichajes_service import ESTADOS_JORNADA, ErroresJornada, fechas_entre, validar_jornada
from services.horario_service import DIAS_CORTOS
from services.reglas_ingreso import fecha_texto, hora_texto
from ui import tema
from ui.componentes import CampoFormulario, EtiquetaEstado, con_rol, etiqueta
from ui.fichajes_page import a_fecha, a_qdate
from ui.tablas import crear_tabla, llenar


def _hora(campo):
    valor = campo.time()
    return time(valor.hour(), valor.minute())


def _editor_hora(hora, minuto):
    campo = QTimeEdit(QTime(hora, minuto))
    campo.setDisplayFormat("HH:mm")
    return campo


class JornadasPage(QWidget):
    def __init__(self, sesion, servicio=None, hoy=date.today):
        super().__init__()
        if servicio is None:
            from services.fichajes_service import FichajesService
            servicio = FichajesService()
        self.sesion, self.servicio = sesion, servicio
        self._hoy = hoy
        self._jornadas = []
        self.elegida = None

        # --- Cargar turnos ---
        self.empleado = QComboBox()
        lunes = hoy() - timedelta(days=hoy().weekday())
        self.desde, self.hasta = QDateEdit(a_qdate(hoy())), QDateEdit(a_qdate(lunes + timedelta(days=6)))
        for campo in (self.desde, self.hasta):
            campo.setCalendarPopup(True)
            campo.setDisplayFormat("dd/MM/yyyy")
        self.dias = {}
        fila_dias = QWidget()
        fila_d = QHBoxLayout(fila_dias)
        fila_d.setContentsMargins(0, 0, 0, 0)
        for numero, nombre in DIAS_CORTOS.items():
            caja = QCheckBox(nombre)
            caja.setChecked(numero <= 5)
            self.dias[numero] = caja
            fila_d.addWidget(caja)
        fila_d.addStretch()
        self.entrada, self.salida = _editor_hora(14, 0), _editor_hora(22, 0)
        self.estado = QComboBox()
        for clave, texto in ESTADOS_JORNADA.items():
            self.estado.addItem(texto, clave)
        self.campos = {"empleado": CampoFormulario("Empleado", self.empleado),
                       "desde": CampoFormulario("Desde", self.desde),
                       "hasta": CampoFormulario("Hasta", self.hasta),
                       "fechas": CampoFormulario("Días", fila_dias),
                       "entrada": CampoFormulario("Entrada", self.entrada),
                       "salida": CampoFormulario("Salida", self.salida),
                       "estado": CampoFormulario("Tipo", self.estado)}
        cargar = con_rol(QPushButton("Cargar turnos"), "primario")
        cargar.clicked.connect(self.cargar_turnos)
        self.mensaje = etiqueta("", "ok")
        self.mensaje.setWordWrap(True)
        self.mensaje.hide()
        fila1, fila2 = QHBoxLayout(), QHBoxLayout()
        for clave in ("empleado", "desde", "hasta"):
            fila1.addWidget(self.campos[clave], 1)
        for clave in ("entrada", "salida", "estado"):
            fila2.addWidget(self.campos[clave], 1)
        alta = con_rol(QFrame(), "panel")
        columna_a = QVBoxLayout(alta)
        columna_a.setContentsMargins(24, 20, 24, 20)
        columna_a.setSpacing(12)
        columna_a.addWidget(etiqueta("Cargar turnos", "titulo-panel"))
        columna_a.addLayout(fila1)
        columna_a.addWidget(self.campos["fechas"])
        columna_a.addLayout(fila2)
        pie = QHBoxLayout()
        pie.addWidget(self.mensaje, 1)
        pie.addWidget(cargar)
        columna_a.addLayout(pie)

        # --- Turnos de la semana y cambios ---
        self.tabla = crear_tabla(("Fecha", "Empleado", "Turno", "Tipo"), estirar=1, seleccion=True)
        self.tabla.itemSelectionChanged.connect(self._elegida)
        self.tabla.setMinimumHeight(200)
        self.vacio = etiqueta("No hay turnos cargados en esas fechas.", "secundario")
        self.cambio_entrada, self.cambio_salida = _editor_hora(14, 0), _editor_hora(22, 0)
        self.cambio_estado = QComboBox()
        for clave, texto in ESTADOS_JORNADA.items():
            self.cambio_estado.addItem(texto, clave)
        self.motivo = QLineEdit()
        self.motivo.setPlaceholderText("Por ejemplo: cambio de turno del sábado")
        self.campos_cambio = {"entrada": CampoFormulario("Entrada", self.cambio_entrada),
                              "salida": CampoFormulario("Salida", self.cambio_salida),
                              "estado": CampoFormulario("Tipo", self.cambio_estado),
                              "motivo": CampoFormulario("Motivo (opcional)", self.motivo)}
        guardar = QPushButton("Guardar cambio")
        guardar.clicked.connect(self.cambiar_turno)
        self.titulo_cambio = etiqueta("Elegí un turno de la lista para cambiarlo.", "secundario")
        fila3 = QHBoxLayout()
        for campo in self.campos_cambio.values():
            fila3.addWidget(campo, 1)
        fila3.addWidget(guardar)
        lista = con_rol(QFrame(), "panel")
        columna_l = QVBoxLayout(lista)
        columna_l.setContentsMargins(24, 20, 24, 20)
        columna_l.setSpacing(12)
        columna_l.addWidget(etiqueta("Turnos cargados", "titulo-panel"))
        columna_l.addWidget(self.vacio)
        columna_l.addWidget(self.tabla, 1)
        columna_l.addWidget(self.titulo_cambio)
        columna_l.addLayout(fila3)

        contenido = QWidget()
        columna = QVBoxLayout(contenido)
        columna.setContentsMargins(0, 0, 0, 0)
        columna.setSpacing(16)
        columna.addWidget(alta)
        columna.addWidget(lista, 1)
        desplazable = QScrollArea()
        desplazable.setWidgetResizable(True)
        desplazable.setFrameShape(QFrame.Shape.NoFrame)
        desplazable.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        desplazable.setWidget(contenido)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(desplazable)
        self._personal_cargado = False

    def showEvent(self, evento):
        super().showEvent(evento)
        if not self._personal_cargado:
            self.cargar_personal()
        self.cargar_lista()

    def cargar_personal(self):
        self.empleado.clear()
        self.empleado.addItem("Elegí el empleado", None)
        try:
            for usuario_id, nombre in self.servicio.personal(self.sesion):
                self.empleado.addItem(nombre, usuario_id)
        except Exception as error:
            self._avisar(f"No se pudo consultar el personal. {error}", "error")
            return
        self._personal_cargado = True

    def _fechas(self):
        dias = {n for n, caja in self.dias.items() if caja.isChecked()}
        return fechas_entre(a_fecha(self.desde), a_fecha(self.hasta), dias)

    def cargar_turnos(self):
        self.mensaje.hide()
        fechas = self._fechas()
        datos = (self.empleado.currentData(), fechas, _hora(self.entrada), _hora(self.salida),
                 self.estado.currentData())
        errores = validar_jornada(*datos[2:], fechas, [])
        if datos[0] is None:
            errores["empleado"] = "Elegí el empleado."
        if not errores:
            try:
                cantidad = self.servicio.cargar_turnos(self.sesion, *datos)
            except ErroresJornada as error:
                errores = error.errores
            except Exception as error:
                self._avisar(f"No se pudieron cargar los turnos. {error}", "error")
                return
        for nombre, campo in self.campos.items():
            campo.mostrar_error(errores[nombre]) if nombre in errores else campo.limpiar_error()
        if errores:
            return
        self._avisar(f"Se cargaron {cantidad} turnos de {self.empleado.currentText()}." if cantidad != 1
                     else f"Se cargó 1 turno de {self.empleado.currentText()}.", "ok")
        self.cargar_lista()

    def cargar_lista(self):
        desde, hasta = a_fecha(self.desde), a_fecha(self.hasta)
        try:
            self._jornadas = list(self.servicio.jornadas(self.sesion, min(desde, hasta), max(desde, hasta)))
        except Exception as error:
            self._avisar(f"No se pudieron consultar los turnos. {error}", "error")
            return
        self.tabla.blockSignals(True)
        llenar(self.tabla, [[f"{DIAS_CORTOS[j[4].isoweekday()]} {fecha_texto(j[4])}", f"{j[2]} {j[3]}",
                             f"{hora_texto(j[5])}–{hora_texto(j[6])}",
                             EtiquetaEstado(ESTADOS_JORNADA.get(j[7], j[7]), "verde" if j[7] == "jornada" else "neutro")]
                            for j in self._jornadas])
        self.tabla.blockSignals(False)
        self.vacio.setVisible(not self._jornadas)
        self.tabla.setVisible(bool(self._jornadas))
        self.elegida = None

    def _elegida(self):
        filas = self.tabla.selectionModel().selectedRows()
        if not filas:
            return
        jornada = self._jornadas[filas[0].row()]
        self.elegida = jornada[0]
        self.titulo_cambio.setText(f"Cambiar el turno de {jornada[2]} {jornada[3]} del {fecha_texto(jornada[4])}:")
        self.cambio_entrada.setTime(QTime(jornada[5].hour, jornada[5].minute))
        self.cambio_salida.setTime(QTime(jornada[6].hour, jornada[6].minute))
        self.cambio_estado.setCurrentIndex(self.cambio_estado.findData(jornada[7]))

    def cambiar_turno(self):
        if self.elegida is None:
            self._avisar("Elegí un turno de la lista.", "error")
            return
        try:
            self.servicio.cambiar_turno(self.sesion, self.elegida, _hora(self.cambio_entrada),
                                        _hora(self.cambio_salida), self.cambio_estado.currentData(),
                                        self.motivo.text().strip())
        except ErroresJornada as error:
            for nombre, campo in self.campos_cambio.items():
                campo.mostrar_error(error.errores[nombre]) if nombre in error.errores else campo.limpiar_error()
            return
        except Exception as error:
            self._avisar(f"No se pudo cambiar el turno. {error}", "error")
            return
        for campo in self.campos_cambio.values():
            campo.limpiar_error()
        self.motivo.clear()
        self._avisar("Turno cambiado. El horario anterior queda en el historial.", "ok")
        self.cargar_lista()

    def _avisar(self, texto, rol):
        self.mensaje.setText(texto)
        self.mensaje.setProperty("rol", rol)
        tema.refrescar_estilo(self.mensaje)
        self.mensaje.show()
