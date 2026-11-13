"""Configuración (solo la dueña): planes con precio y límites, y franjas del
horario de atención (se agregan y se activan o desactivan)."""
from datetime import time
from decimal import Decimal

from PySide6.QtCore import QTime, Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLineEdit, QPushButton, QScrollArea,
    QTimeEdit, QVBoxLayout, QWidget,
)

from services.configuracion_service import ErroresConfiguracion, validar_franja, validar_plan
from services.horario_service import DIAS
from services.reglas_ingreso import pesos
from ui import tema
from ui.componentes import CampoFormulario, EtiquetaEstado, con_rol, etiqueta
from ui.tablas import crear_tabla, llenar

VIGENCIAS = {"1 day": "1 día", "1 mon": "1 mes", "7 days": "1 semana"}


def _texto(valor):
    return "" if valor is None else str(valor)


class EditorPlan(QFrame):
    """Un plan: precio, cupo, días por semana, ingresos por día y si se vende."""

    def __init__(self, plan, guardar):
        super().__init__()
        con_rol(self, "tarjeta-dato")
        self.plan_id, self.nombre = plan[0], plan[1]
        self._guardar = guardar
        self.precio = QLineEdit(pesos(plan[6]).replace("$", ""))
        self.cupo = QLineEdit(_texto(plan[3]))
        self.dias_semana = QLineEdit(_texto(plan[4]))
        self.ingresos_dia = QLineEdit(_texto(plan[5]))
        for campo in (self.cupo, self.dias_semana, self.ingresos_dia):
            campo.setPlaceholderText("Sin límite")
        self.activo = QCheckBox("Se vende")
        self.activo.setChecked(bool(plan[7]))
        self.campos = {
            "precio": CampoFormulario("Precio", self.precio),
            "cupo": CampoFormulario("Accesos en la vigencia", self.cupo),
            "dias_semana": CampoFormulario("Días por semana", self.dias_semana),
            "ingresos_dia": CampoFormulario("Ingresos por día", self.ingresos_dia),
        }
        self.boton = con_rol(QPushButton("Guardar"), "primario")
        self.boton.clicked.connect(self.guardar)
        self.mensaje = etiqueta("", "ok")
        self.mensaje.setWordWrap(True)
        self.mensaje.hide()
        titulo = QHBoxLayout()
        titulo.addWidget(etiqueta(plan[1], "titulo-panel"))
        titulo.addWidget(etiqueta(f"Vigencia: {VIGENCIAS.get(plan[2], plan[2])}", "secundario"))
        titulo.addStretch()
        if Decimal(plan[6]) <= 0:
            titulo.addWidget(EtiquetaEstado("Sin precio: no se vende", "ambar"))
        grilla = QGridLayout()
        grilla.setHorizontalSpacing(12)
        for columna, campo in enumerate(self.campos.values()):
            grilla.addWidget(campo, 0, columna)
            grilla.setColumnStretch(columna, 1)
        pie = QHBoxLayout()
        pie.addWidget(self.activo)
        pie.addWidget(self.mensaje, 1)
        pie.addWidget(self.boton)
        columna_p = QVBoxLayout(self)
        columna_p.setContentsMargins(16, 14, 16, 14)
        columna_p.setSpacing(10)
        columna_p.addLayout(titulo)
        columna_p.addLayout(grilla)
        columna_p.addLayout(pie)

    def datos(self):
        return {"precio": self.precio.text(), "cupo": self.cupo.text(), "dias_semana": self.dias_semana.text(),
                "ingresos_dia": self.ingresos_dia.text(), "activo": self.activo.isChecked()}

    def mostrar_errores(self, errores):
        for nombre, campo in self.campos.items():
            campo.mostrar_error(errores[nombre]) if nombre in errores else campo.limpiar_error()

    def guardar(self):
        self.mensaje.hide()
        errores, _ = validar_plan(self.datos())
        self.mostrar_errores(errores)
        if errores:
            return
        self._guardar(self)

    def avisar(self, texto, rol):
        self.mensaje.setText(texto)
        self.mensaje.setProperty("rol", rol)
        tema.refrescar_estilo(self.mensaje)
        self.mensaje.show()


class ConfiguracionPage(QWidget):
    def __init__(self, sesion, servicio=None):
        super().__init__()
        if servicio is None:
            from services.configuracion_service import ConfiguracionService
            servicio = ConfiguracionService()
        self.sesion, self.servicio = sesion, servicio
        self.editores = []
        self._franjas = []

        # --- Planes ---
        self.lista_planes = QVBoxLayout()
        self.lista_planes.setSpacing(12)
        self.error_planes = etiqueta("", "error")
        self.error_planes.setWordWrap(True)
        self.error_planes.hide()
        planes = con_rol(QFrame(), "panel")
        columna_p = QVBoxLayout(planes)
        columna_p.setContentsMargins(24, 20, 24, 20)
        columna_p.setSpacing(12)
        columna_p.addWidget(etiqueta("Planes y precios", "titulo-panel"))
        ayuda = etiqueta("Un plan sin precio no se puede vender. Los cambios valen para las ventas nuevas: "
                         "las membresías ya vendidas conservan su precio y sus límites.", "secundario")
        ayuda.setWordWrap(True)
        columna_p.addWidget(ayuda)
        columna_p.addWidget(self.error_planes)
        columna_p.addLayout(self.lista_planes)

        # --- Horario ---
        self.dia = QComboBox()
        for numero, nombre in DIAS.items():
            self.dia.addItem(nombre.capitalize(), numero)
        self.apertura, self.cierre = QTimeEdit(QTime(7, 30)), QTimeEdit(QTime(23, 0))
        for campo in (self.apertura, self.cierre):
            campo.setDisplayFormat("HH:mm")
        self.campos_franja = {"dia": CampoFormulario("Día", self.dia),
                              "apertura": CampoFormulario("Abre", self.apertura),
                              "cierre": CampoFormulario("Cierra", self.cierre)}
        agregar = con_rol(QPushButton("Agregar franja"), "primario")
        agregar.clicked.connect(self.agregar_franja)
        self.mensaje_horario = etiqueta("", "ok")
        self.mensaje_horario.setWordWrap(True)
        self.mensaje_horario.hide()
        fila_franja = QHBoxLayout()
        for campo in self.campos_franja.values():
            fila_franja.addWidget(campo, 1)
        fila_franja.addWidget(agregar, 0, Qt.AlignmentFlag.AlignBottom)
        self.tabla_franjas = crear_tabla(("Día", "Abre", "Cierra", "Estado", ""))
        self.tabla_franjas.setMinimumHeight(330)
        horario = con_rol(QFrame(), "panel")
        columna_h = QVBoxLayout(horario)
        columna_h.setContentsMargins(24, 20, 24, 20)
        columna_h.setSpacing(12)
        columna_h.addWidget(etiqueta("Horario de atención", "titulo-panel"))
        ayuda_h = etiqueta("Un día sin franjas activas es un día cerrado. Las franjas no se borran: "
                           "se desactivan.", "secundario")
        ayuda_h.setWordWrap(True)
        columna_h.addWidget(ayuda_h)
        columna_h.addLayout(fila_franja)
        columna_h.addWidget(self.mensaje_horario)
        columna_h.addWidget(self.tabla_franjas)

        contenido = QWidget()
        columna = QVBoxLayout(contenido)
        columna.setContentsMargins(0, 0, 0, 0)
        columna.setSpacing(16)
        columna.addWidget(planes)
        columna.addWidget(horario)
        columna.addStretch()
        desplazable = QScrollArea()
        desplazable.setWidgetResizable(True)
        desplazable.setFrameShape(QFrame.Shape.NoFrame)
        desplazable.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        desplazable.setWidget(contenido)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(desplazable)

    def showEvent(self, evento):
        super().showEvent(evento)
        self.cargar()

    def cargar(self):
        self.cargar_planes()
        self.cargar_franjas()

    # --- Planes ---

    def cargar_planes(self):
        try:
            planes = self.servicio.planes(self.sesion)
        except Exception as error:
            self.error_planes.setText(f"No se pudieron consultar los planes. {error}")
            self.error_planes.show()
            return
        self.error_planes.hide()
        for editor in self.editores:
            self.lista_planes.removeWidget(editor)
            editor.deleteLater()
        self.editores = [EditorPlan(plan, self.guardar_plan) for plan in planes]
        for editor in self.editores:
            self.lista_planes.addWidget(editor)

    def guardar_plan(self, editor):
        try:
            self.servicio.guardar_plan(self.sesion, editor.plan_id, editor.datos())
        except ErroresConfiguracion as error:
            editor.mostrar_errores(error.errores)
            return
        except Exception as error:
            editor.avisar(f"No se pudo guardar. {error}", "error")
            return
        editor.avisar(f"Se guardó {editor.nombre}.", "ok")

    # --- Horario ---

    def cargar_franjas(self):
        try:
            self._franjas = list(self.servicio.franjas(self.sesion))
        except Exception as error:
            self._avisar_horario(f"No se pudo consultar el horario. {error}", "error")
            return
        filas = []
        for franja_id, dia, apertura, cierre, activa in self._franjas:
            boton = QPushButton("Desactivar" if activa else "Activar")
            boton.setMinimumHeight(34)
            boton.clicked.connect(lambda _c=False, f=franja_id, a=activa: self.cambiar_activa(f, not a))
            filas.append([DIAS[dia].capitalize(), apertura.strftime("%H:%M"), cierre.strftime("%H:%M"),
                          EtiquetaEstado("Activa" if activa else "Desactivada", "verde" if activa else "neutro"),
                          boton])
        llenar(self.tabla_franjas, filas)

    def _hora(self, campo):
        valor = campo.time()
        return time(valor.hour(), valor.minute())

    def agregar_franja(self):
        self.mensaje_horario.hide()
        dia, apertura, cierre = self.dia.currentData(), self._hora(self.apertura), self._hora(self.cierre)
        errores = validar_franja(dia, apertura, cierre, self._franjas)
        if not errores:
            try:
                self.servicio.agregar_franja(self.sesion, dia, apertura, cierre)
            except ErroresConfiguracion as error:
                errores = error.errores
            except Exception as error:
                self._avisar_horario(f"No se pudo agregar la franja. {error}", "error")
                return
        for nombre, campo in self.campos_franja.items():
            campo.mostrar_error(errores[nombre]) if nombre in errores else campo.limpiar_error()
        if errores:
            return
        self.cargar_franjas()
        self._avisar_horario(f"Se agregó {DIAS[dia]} de {apertura:%H:%M} a {cierre:%H:%M}.", "ok")

    def cambiar_activa(self, franja_id, activa):
        try:
            self.servicio.cambiar_activa(self.sesion, franja_id, activa)
        except ErroresConfiguracion as error:
            self._avisar_horario(" ".join(error.errores.values()), "error")
            return
        except Exception as error:
            self._avisar_horario(f"No se pudo cambiar la franja. {error}", "error")
            return
        self.cargar_franjas()
        self._avisar_horario("Franja activada." if activa else "Franja desactivada: ese horario queda cerrado.",
                             "ok")

    def _avisar_horario(self, texto, rol):
        self.mensaje_horario.setText(texto)
        self.mensaje_horario.setProperty("rol", rol)
        tema.refrescar_estilo(self.mensaje_horario)
        self.mensaje_horario.show()
