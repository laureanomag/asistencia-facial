"""Tablas de solo lectura con el estilo de ZebraGym (listas de Socios,
Estado del socio, Configuración e Informes)."""
from PySide6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QHeaderView, QTableWidget, QTableWidgetItem, QWidget,
)


def crear_tabla(columnas, estirar=0, alto_fila=46, seleccion=False):
    tabla = QTableWidget(0, len(columnas))
    tabla.setHorizontalHeaderLabels(columnas)
    tabla.verticalHeader().setVisible(False)
    tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    if seleccion:
        tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        tabla.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    else:
        tabla.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
    tabla.setShowGrid(False)
    tabla.setWordWrap(False)
    tabla.verticalHeader().setDefaultSectionSize(alto_fila)
    cabecera = tabla.horizontalHeader()
    for columna in range(len(columnas)):
        modo = (QHeaderView.ResizeMode.Stretch if columna == estirar
                else QHeaderView.ResizeMode.ResizeToContents)
        cabecera.setSectionResizeMode(columna, modo)
    return tabla


def celda(widget):
    contenedor = QWidget()
    fila = QHBoxLayout(contenedor)
    fila.setContentsMargins(6, 0, 6, 0)
    fila.addWidget(widget)
    return contenedor


def llenar(tabla, filas):
    """filas: listas de valores; un QWidget se pone como widget de la celda."""
    tabla.setRowCount(len(filas))
    for numero, valores in enumerate(filas):
        for columna, valor in enumerate(valores):
            if isinstance(valor, QWidget):
                tabla.setCellWidget(numero, columna, celda(valor))
            else:
                tabla.setItem(numero, columna, QTableWidgetItem("" if valor is None else str(valor)))


def textos(tabla):
    """Contenido de texto de la tabla (para pruebas)."""
    return [[tabla.item(f, c).text() if tabla.item(f, c) else None
             for c in range(tabla.columnCount())] for f in range(tabla.rowCount())]
