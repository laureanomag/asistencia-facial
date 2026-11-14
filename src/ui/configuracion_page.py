"""Configuración (solo la dueña): planes con precio y límites, y el horario
de atención: un renglón por día con "Abierto", apertura y cierre."""
from datetime import time
from decimal import Decimal

from PySide6.QtCore import QTime, Qt
from PySide6.QtWidgets import (
    QCheckBox, QFrame, QGridLayout, QHBoxLayout, QLineEdit, QPushButton, QScrollArea, QTimeEdit,
    QVBoxLayout, QWidget,
)

from services.configuracion_service import ErroresConfiguracion, aviso_cupo, validar_horario, validar_plan
from services.horario_service import DIAS
from services.reglas_ingreso import pesos
from ui import tema
from ui.componentes import CampoFormulario, EtiquetaEstado, con_rol, etiqueta

VIGENCIAS = {"1 day": "1 día", "1 mon": "1 mes", "7 days": "1 semana"}


def _texto(valor):
    return "" if valor is None else str(valor)


class EditorPlan(QFrame):
    """Un plan: precio, cupo, días por semana, ingresos por día y si se vende."""

    def __init__(self, plan, guardar):
        super().__init__()
        con_rol(self, "tarjeta-dato")
        self.plan_id, self.nombre, self.vigencia = plan[0], plan[1], plan[2]
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
        for campo in (self.cupo, self.dias_semana):
            campo.textChanged.connect(self.revisar_cupo)
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
        self.revisar_cupo()

    def revisar_cupo(self, *_):
        """Aviso en ámbar si "Accesos en la vigencia" no alcanza para todos los días permitidos."""
        _errores, valores = validar_plan(self.datos())
        aviso = aviso_cupo(valores["cupo"], valores["dias_semana"], self.vigencia)
        campo = self.campos["cupo"]
        if aviso:
            campo.mostrar_aviso(aviso)
        elif campo.mensaje.property("rol") == "advertencia":
            campo.limpiar_error()
        return aviso

    def datos(self):
        return {"precio": self.precio.text(), "cupo": self.cupo.text(), "dias_semana": self.dias_semana.text(),
                "ingresos_dia": self.ingresos_dia.text(), "activo": self.activo.isChecked()}

    def mostrar_errores(self, errores):
        for nombre, campo in self.campos.items():
            campo.mostrar_error(errores[nombre]) if nombre in errores else campo.limpiar_error()
        if "cupo" not in errores:
            self.revisar_cupo()

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


class DiaHorario:
    """Renglón de un día: casilla Abierto y horas de apertura y cierre
    (deshabilitadas si el día está cerrado). El error va debajo del cierre."""

    def __init__(self, dia):
        self.dia = dia
        self.nombre = etiqueta(DIAS[dia].capitalize(), "etiqueta")
        self.abierto = QCheckBox("Abierto")
        self.apertura, self.cierre = QTimeEdit(), QTimeEdit()
        for campo in (self.apertura, self.cierre):
            campo.setDisplayFormat("HH:mm")
        self.campo_cierre = CampoFormulario("", self.cierre)
        self.campo_cierre.etiqueta.hide()
        self.abierto.toggled.connect(self._habilitar)

    def _habilitar(self, abierto):
        self.apertura.setEnabled(abierto)
        self.cierre.setEnabled(abierto)
        if not abierto:
            self.campo_cierre.limpiar_error()

    def mostrar(self, abierto, apertura, cierre):
        self.abierto.setChecked(abierto)
        self.apertura.setTime(QTime(apertura.hour, apertura.minute))
        self.cierre.setTime(QTime(cierre.hour, cierre.minute))
        self._habilitar(abierto)

    def valores(self):
        def hora(campo):
            return time(campo.time().hour(), campo.time().minute())
        return self.abierto.isChecked(), hora(self.apertura), hora(self.cierre)


class ConfiguracionPage(QWidget):
    def __init__(self, sesion, servicio=None):
        super().__init__()
        if servicio is None:
            from services.configuracion_service import ConfiguracionService
            servicio = ConfiguracionService()
        self.sesion, self.servicio = sesion, servicio
        self.editores = []

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
        self.dias = {dia: DiaHorario(dia) for dia in DIAS}
        grilla = QGridLayout()
        grilla.setHorizontalSpacing(16)
        grilla.setVerticalSpacing(8)
        for columna, titulo in enumerate(("Día", "", "Abre", "Cierra")):
            grilla.addWidget(etiqueta(titulo, "dato-titulo"), 0, columna)
        arriba = Qt.AlignmentFlag.AlignTop
        for fila, renglon in enumerate(self.dias.values(), start=1):
            grilla.addWidget(renglon.nombre, fila, 0, Qt.AlignmentFlag.AlignVCenter)
            grilla.addWidget(renglon.abierto, fila, 1, Qt.AlignmentFlag.AlignVCenter)
            grilla.addWidget(renglon.apertura, fila, 2, arriba)
            grilla.addWidget(renglon.campo_cierre, fila, 3, arriba)
        grilla.setColumnStretch(2, 1)
        grilla.setColumnStretch(3, 1)
        guardar = con_rol(QPushButton("Guardar cambios"), "primario")
        guardar.clicked.connect(self.guardar_horario)
        self.mensaje_horario = etiqueta("", "ok")
        self.mensaje_horario.setWordWrap(True)
        self.mensaje_horario.hide()
        pie = QHBoxLayout()
        pie.addWidget(self.mensaje_horario, 1)
        pie.addWidget(guardar)
        horario = con_rol(QFrame(), "panel")
        columna_h = QVBoxLayout(horario)
        columna_h.setContentsMargins(24, 20, 24, 20)
        columna_h.setSpacing(12)
        columna_h.addWidget(etiqueta("Horario de atención", "titulo-panel"))
        columna_h.addWidget(etiqueta("Días y horarios en que el gimnasio está abierto.", "secundario"))
        columna_h.addLayout(grilla)
        columna_h.addLayout(pie)

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
        self.cargar_horario()

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

    def cargar_horario(self):
        try:
            semana = self.servicio.horario(self.sesion)
        except Exception as error:
            self._avisar_horario(f"No se pudo consultar el horario. {error}", "error")
            return
        for dia, renglon in self.dias.items():
            renglon.mostrar(*semana[dia])

    def guardar_horario(self):
        self.mensaje_horario.hide()
        semana = {dia: renglon.valores() for dia, renglon in self.dias.items()}
        errores = validar_horario(semana)
        if not errores:
            try:
                self.servicio.guardar_horario(self.sesion, semana)
            except ErroresConfiguracion as error:
                errores = error.errores
            except Exception as error:
                self._avisar_horario(f"No se pudo guardar el horario. {error}", "error")
                return
        for dia, renglon in self.dias.items():
            if dia in errores:
                renglon.campo_cierre.mostrar_error(errores[dia])
            else:
                renglon.campo_cierre.limpiar_error()
        if errores:
            return
        self._avisar_horario("Se guardó el horario de atención.", "ok")
        self.cargar_horario()

    def _avisar_horario(self, texto, rol):
        self.mensaje_horario.setText(texto)
        self.mensaje_horario.setProperty("rol", rol)
        tema.refrescar_estilo(self.mensaje_horario)
        self.mensaje_horario.show()
