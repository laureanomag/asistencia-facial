"""Fichajes: por empleado y fecha, turno, llegada, salida, tardanza, horas
trabajadas y estado (Ausente, Fichaje incompleto, Fuera de turno...).
El entrenador ve solo los suyos; la dueña elige el empleado."""
from datetime import date, timedelta

from PySide6.QtCore import QDate
from PySide6.QtWidgets import QComboBox, QDateEdit, QFrame, QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from services.reglas_ingreso import fecha_texto
from ui.componentes import CampoFormulario, EtiquetaEstado, con_rol, etiqueta
from ui.tablas import crear_tabla, llenar


def a_qdate(valor):
    return QDate(valor.year, valor.month, valor.day)


def a_fecha(campo):
    valor = campo.date()
    return date(valor.year(), valor.month(), valor.day())


class FichajesPage(QWidget):
    COLUMNAS = ("Fecha", "Empleado", "Turno", "Llegada", "Salida", "Tardanza", "Trabajado", "Estado")

    def __init__(self, sesion, servicio=None, hoy=date.today):
        super().__init__()
        if servicio is None:
            from services.fichajes_service import FichajesService
            servicio = FichajesService()
        self.sesion, self.servicio = sesion, servicio
        inicio_semana = hoy() - timedelta(days=hoy().weekday())
        self.empleado = QComboBox()
        self.desde, self.hasta = QDateEdit(a_qdate(inicio_semana)), QDateEdit(a_qdate(hoy()))
        for campo in (self.desde, self.hasta):
            campo.setCalendarPopup(True)
            campo.setDisplayFormat("dd/MM/yyyy")
        self.campos = {"empleado": CampoFormulario("Empleado", self.empleado),
                       "desde": CampoFormulario("Desde", self.desde),
                       "hasta": CampoFormulario("Hasta", self.hasta)}
        ver = con_rol(QPushButton("Ver fichajes"), "primario")
        ver.clicked.connect(self.cargar)
        filtros = QHBoxLayout()
        for campo in self.campos.values():
            filtros.addWidget(campo, 1)
        self.resumen = etiqueta("", "secundario")
        self.resumen.setWordWrap(True)
        self.mensaje = etiqueta("", "error")
        self.mensaje.setWordWrap(True)
        self.mensaje.hide()
        self.vacio = etiqueta("No hay turnos ni fichajes en esas fechas.", "secundario")
        self.tabla = crear_tabla(self.COLUMNAS, estirar=1)

        caja = con_rol(QFrame(), "panel")
        columna = QVBoxLayout(caja)
        columna.setContentsMargins(24, 20, 24, 20)
        columna.setSpacing(12)
        columna.addLayout(filtros)
        botones = QHBoxLayout()
        botones.addWidget(ver)
        botones.addStretch()
        columna.addLayout(botones)
        columna.addWidget(self.mensaje)
        columna.addWidget(self.resumen)
        columna.addWidget(self.vacio)
        columna.addWidget(self.tabla, 1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(caja)
        self._personal_cargado = False

    def showEvent(self, evento):
        super().showEvent(evento)
        if not self._personal_cargado:
            self.cargar_personal()
        self.cargar()

    def cargar_personal(self):
        self.empleado.clear()
        try:
            personal = self.servicio.personal(self.sesion)
        except Exception as error:
            self._error(f"No se pudo consultar el personal. {error}")
            return
        if self.servicio.ve_a_todos(self.sesion):
            self.empleado.addItem("Todo el personal", None)
        for usuario_id, nombre in personal:
            self.empleado.addItem(nombre, usuario_id)
        self.campos["empleado"].setVisible(self.servicio.ve_a_todos(self.sesion))
        self._personal_cargado = True

    def cargar(self):
        self.mensaje.hide()
        self.campos["hasta"].limpiar_error()
        desde, hasta = a_fecha(self.desde), a_fecha(self.hasta)
        if hasta < desde:
            self.campos["hasta"].mostrar_error("No puede ser anterior a Desde.")
            return
        try:
            filas = self.servicio.fichajes(self.sesion, desde, hasta, self.empleado.currentData())
        except Exception as error:
            self._error(f"No se pudieron consultar los fichajes. {error}")
            return
        llenar(self.tabla, [[fecha_texto(f.fecha), f.empleado, f.turno, f.llegada, f.salida, f.tardanza,
                             f.trabajado, EtiquetaEstado(f.estado, f.tono)] for f in filas])
        self.vacio.setVisible(not filas)
        self.tabla.setVisible(bool(filas))
        cuenta = {}
        for fila in filas:
            cuenta[fila.estado] = cuenta.get(fila.estado, 0) + 1
        self.resumen.setText(" · ".join(f"{estado}: {n}" for estado, n in sorted(cuenta.items())))

    def _error(self, texto):
        self.mensaje.setText(texto)
        self.mensaje.show()
