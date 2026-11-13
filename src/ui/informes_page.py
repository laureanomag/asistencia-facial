"""Informes (la dueña): ingresos y rechazos por fechas y por socio, y estado
de membresía y cupos. Se exportan a Excel o PDF."""
import os
from datetime import date

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QComboBox, QDateEdit, QFileDialog, QFrame, QHBoxLayout, QLineEdit, QPushButton, QStackedWidget,
    QVBoxLayout, QWidget,
)

from services.exportar import exportar_excel, exportar_pdf, nombre_archivo
from services.persona_service import DatosInvalidos
from ui import tema
from ui.componentes import CampoFormulario, con_rol, etiqueta
from ui.tablas import crear_tabla, llenar

INGRESOS, MEMBRESIAS = "ingresos", "membresias"


def elegir_ruta(parent, sugerido, filtro):
    carpeta = os.path.join(os.path.expanduser("~"), "Documents")
    ruta, _ = QFileDialog.getSaveFileName(parent, "Guardar informe", os.path.join(carpeta, sugerido), filtro)
    return ruta or None


def _fecha(campo):
    valor = campo.date()
    return date(valor.year(), valor.month(), valor.day())


class InformesPage(QWidget):
    def __init__(self, sesion, servicio=None, elegir=None, hoy=date.today):
        super().__init__()
        if servicio is None:
            from services.informe_service import InformeService
            servicio = InformeService()
        self.sesion, self.servicio = sesion, servicio
        self._elegir = elegir or elegir_ruta
        self._hoy = hoy
        self.informe = None

        self.tipo = QComboBox()
        self.tipo.addItem("Ingresos y rechazos", INGRESOS)
        self.tipo.addItem("Estado de membresías y cupos", MEMBRESIAS)
        self.tipo.currentIndexChanged.connect(self._tipo_elegido)
        hoy_qt = QDate(hoy().year, hoy().month, hoy().day)
        self.desde, self.hasta = QDateEdit(hoy_qt.addDays(-6)), QDateEdit(hoy_qt)
        for campo in (self.desde, self.hasta):
            campo.setCalendarPopup(True)
            campo.setDisplayFormat("dd/MM/yyyy")
        self.dni = QLineEdit()
        self.dni.setPlaceholderText("Todos los socios")
        self.dni.returnPressed.connect(self.ver)
        self.campos = {"desde": CampoFormulario("Desde", self.desde),
                       "hasta": CampoFormulario("Hasta", self.hasta),
                       "dni": CampoFormulario("DNI del socio (opcional)", self.dni)}
        filtros = QWidget()
        fila_f = QHBoxLayout(filtros)
        fila_f.setContentsMargins(0, 0, 0, 0)
        for campo in self.campos.values():
            fila_f.addWidget(campo, 1)
        self.filtros = filtros
        ver = con_rol(QPushButton("Ver informe"), "primario")
        ver.clicked.connect(self.ver)
        self.boton_excel = QPushButton("Exportar a Excel")
        self.boton_excel.clicked.connect(lambda: self.exportar("xlsx"))
        self.boton_pdf = QPushButton("Exportar a PDF")
        self.boton_pdf.clicked.connect(lambda: self.exportar("pdf"))
        for boton in (self.boton_excel, self.boton_pdf):
            boton.setEnabled(False)

        arriba = QHBoxLayout()
        arriba.addWidget(CampoFormulario("Informe", self.tipo), 1)
        arriba.addWidget(filtros, 3)
        botones = QHBoxLayout()
        botones.addWidget(ver)
        botones.addStretch()
        botones.addWidget(self.boton_excel)
        botones.addWidget(self.boton_pdf)
        self.subtitulo = etiqueta("", "titulo-panel")
        self.resumen = etiqueta("", "secundario")
        self.resumen.setWordWrap(True)
        self.mensaje = etiqueta("", "ok")
        self.mensaje.setWordWrap(True)
        self.mensaje.hide()
        self.vacio = etiqueta("Elegí el informe y tocá Ver informe.", "secundario")
        self.tablas = QStackedWidget()
        self.tabla = None

        caja = con_rol(QFrame(), "panel")
        columna = QVBoxLayout(caja)
        columna.setContentsMargins(24, 20, 24, 20)
        columna.setSpacing(12)
        columna.addLayout(arriba)
        columna.addLayout(botones)
        columna.addWidget(self.mensaje)
        columna.addWidget(self.subtitulo)
        columna.addWidget(self.resumen)
        columna.addWidget(self.vacio)
        columna.addWidget(self.tablas, 1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(caja)

    def _tipo_elegido(self, *_):
        self.filtros.setVisible(self.tipo.currentData() == INGRESOS)
        self.informe = None
        for boton in (self.boton_excel, self.boton_pdf):
            boton.setEnabled(False)

    def ver(self):
        self.mensaje.hide()
        for campo in self.campos.values():
            campo.limpiar_error()
        try:
            if self.tipo.currentData() == INGRESOS:
                desde, hasta = _fecha(self.desde), _fecha(self.hasta)
                if hasta < desde:
                    self.campos["hasta"].mostrar_error("No puede ser anterior a Desde.")
                    return
                informe = self.servicio.ingresos(self.sesion, desde, hasta, self.dni.text())
            else:
                informe = self.servicio.membresias(self.sesion, self._hoy())
        except DatosInvalidos as error:
            self.campos["dni"].mostrar_error(str(error))
            return
        except Exception as error:
            self._avisar(f"No se pudo armar el informe. {error}", "error")
            return
        self.mostrar(informe)

    def mostrar(self, informe):
        self.informe = informe
        self.subtitulo.setText(informe.subtitulo)
        self.resumen.setText("\n".join(informe.resumen))
        if self.tabla is not None:
            self.tablas.removeWidget(self.tabla)
            self.tabla.deleteLater()
        self.tabla = crear_tabla(informe.encabezados, estirar=2 if informe.encabezados[0] == "Fecha" else 0)
        llenar(self.tabla, informe.filas)
        self.tablas.addWidget(self.tabla)
        self.vacio.setText("No hay datos para los filtros elegidos.")
        self.vacio.setVisible(not informe.filas)
        self.tablas.setVisible(bool(informe.filas))
        for boton in (self.boton_excel, self.boton_pdf):
            boton.setEnabled(True)

    def exportar(self, extension):
        if self.informe is None:
            return
        filtro = "Excel (*.xlsx)" if extension == "xlsx" else "PDF (*.pdf)"
        ruta = self._elegir(self, nombre_archivo(self.informe.titulo, extension), filtro)
        if not ruta:
            return
        if not ruta.lower().endswith(f".{extension}"):
            ruta += f".{extension}"
        try:
            (exportar_excel if extension == "xlsx" else exportar_pdf)(self.informe, ruta)
        except PermissionError:
            self._avisar("No se pudo guardar: el archivo está abierto en otro programa. Cerralo y probá de nuevo.",
                         "error")
            return
        except Exception as error:
            self._avisar(f"No se pudo exportar. {error}", "error")
            return
        self._avisar(f"Informe guardado en {ruta}", "ok")

    def _avisar(self, texto, rol):
        self.mensaje.setText(texto)
        self.mensaje.setProperty("rol", rol)
        tema.refrescar_estilo(self.mensaje)
        self.mensaje.show()
