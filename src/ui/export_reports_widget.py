from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QFileDialog, QHeaderView, QLabel, QMessageBox,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from services import report_exporters as exp
from services.report_service import JornadaAjenaError, ReportService


class ExportReportsWidget(QWidget):
    """
    Cuarta opción del Menú Lateral: Exportar Informes.
    Lista (desde PostgreSQL, en cada ingreso) las Jornadas del usuario
    autenticado y exporta la planilla de cada una a Excel o PDF.
    """

    COLUMNAS = ["Fecha", "Cátedra", "Horario", "Excel", "PDF"]

    def __init__(self, usuario_id, nombre_usuario):
        super().__init__()
        self.usuario_id = usuario_id
        self.nombre_usuario = nombre_usuario
        self.service = ReportService()
        self._jornadas = []

        titulo = QLabel("Exportar Informes")
        titulo.setStyleSheet("font-weight: bold; font-size: 16px;")

        self.vacio_label = QLabel("No hay Jornadas registradas.")

        self.tabla = QTableWidget(0, len(self.COLUMNAS))
        self.tabla.setHorizontalHeaderLabels(self.COLUMNAS)
        self.tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        layout = QVBoxLayout()
        layout.addWidget(titulo)
        layout.addWidget(self.vacio_label)
        layout.addWidget(self.tabla)
        self.setLayout(layout)

    def showEvent(self, event):
        super().showEvent(event)
        self.cargar_jornadas()  # refresca siempre desde PostgreSQL

    def cargar_jornadas(self):
        try:
            self._jornadas = self.service.listar_jornadas(self.usuario_id)
        except Exception as error:
            QMessageBox.critical(self, "Error", f"No se pudieron consultar las Jornadas:\n{error}")
            return

        self.tabla.setRowCount(len(self._jornadas))
        self.vacio_label.setVisible(not self._jornadas)
        self.tabla.setVisible(bool(self._jornadas))

        for fila, (jornada_id, fecha, catedra, h_ent, h_sal) in enumerate(self._jornadas):
            valores = [
                fecha.strftime("%d/%m/%Y"),
                catedra,
                f"{exp.hora_texto(h_ent)} - {exp.hora_texto(h_sal)}",
            ]
            for col, valor in enumerate(valores):
                item = QTableWidgetItem(valor)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.tabla.setItem(fila, col, item)

            for col, (texto, extension) in ((3, ("Excel", "xlsx")), (4, ("PDF", "pdf"))):
                boton = QPushButton(texto)
                boton.clicked.connect(
                    lambda _c=False, j=jornada_id, f=fecha, c=catedra, e=extension:
                        self.exportar(j, f, c, e)
                )
                self.tabla.setCellWidget(fila, col, boton)

    def exportar(self, jornada_id, fecha, catedra, extension):
        filtro = "Excel (*.xlsx)" if extension == "xlsx" else "PDF (*.pdf)"
        sugerido = str(Path.home() / exp.nombre_sugerido(fecha, catedra, extension))

        ruta, _ = QFileDialog.getSaveFileName(self, "Guardar como", sugerido, filtro)
        if not ruta:
            return  # canceló: no se genera nada ni se muestra error
        if not ruta.lower().endswith(f".{extension}"):
            ruta += f".{extension}"

        try:
            datos = self.service.preparar(jornada_id, self.usuario_id, self.nombre_usuario)
            if extension == "xlsx":
                exp.generar_excel(ruta, datos)
            else:
                exp.generar_pdf(ruta, datos)
        except JornadaAjenaError as error:
            QMessageBox.critical(self, "No se pudo exportar", str(error))
            return
        except PermissionError as error:
            QMessageBox.critical(self, "No se pudo exportar", f"{error}\n\n"
                                 "Si el archivo está abierto en otro programa, ciérrelo e intente de nuevo.")
            return
        except Exception as error:
            QMessageBox.critical(self, "No se pudo exportar", f"Error al generar el informe:\n{error}")
            return

        QMessageBox.information(self, "Informe generado",
                                f"El archivo fue creado correctamente:\n{ruta}")
