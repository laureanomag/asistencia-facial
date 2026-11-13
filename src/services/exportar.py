"""Exportación de informes de ZebraGym a Excel (openpyxl) y PDF (ReportLab).
Sin acceso a la base: recibe un Informe ya armado."""
from dataclasses import dataclass, field
from xml.sax.saxutils import escape

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

DORADO = "F0B820"
MENSAJE_VACIO = "No hay datos para los filtros elegidos."


@dataclass
class Informe:
    titulo: str
    subtitulo: str
    encabezados: list
    filas: list = field(default_factory=list)       # listas de textos
    resumen: list = field(default_factory=list)     # líneas de texto


def nombre_archivo(titulo, extension):
    """'Ingresos y rechazos' -> 'ingresos_y_rechazos.xlsx'."""
    import unicodedata
    base = unicodedata.normalize("NFKD", titulo).encode("ascii", "ignore").decode()
    base = "_".join(p for p in "".join(c if c.isalnum() else " " for c in base.lower()).split())
    return f"{base or 'informe'}.{extension}"


def exportar_excel(informe, ruta):
    libro = Workbook()
    hoja = libro.active
    hoja.title = informe.titulo[:31]
    hoja.append([informe.titulo])
    hoja["A1"].font = Font(bold=True, size=14)
    hoja.append([informe.subtitulo])
    for linea in informe.resumen:
        hoja.append([linea])
    hoja.append([])
    hoja.append(list(informe.encabezados))
    fila_encabezado = hoja.max_row
    for celda in hoja[fila_encabezado]:
        celda.font = Font(bold=True)
        celda.fill = PatternFill("solid", fgColor=DORADO)
        celda.alignment = Alignment(horizontal="center")
    if informe.filas:
        for fila in informe.filas:
            hoja.append(["" if v is None else v for v in fila])
    else:
        hoja.append([MENSAJE_VACIO])
    for indice, encabezado in enumerate(informe.encabezados, start=1):
        largo = max([len(str(encabezado))] + [len(str(f[indice - 1])) for f in informe.filas if f[indice - 1]])
        hoja.column_dimensions[hoja.cell(fila_encabezado, indice).column_letter].width = min(45, largo + 3)
    hoja.freeze_panes = hoja.cell(fila_encabezado + 1, 1)
    libro.save(ruta)
    return ruta


def exportar_pdf(informe, ruta):
    estilos = getSampleStyleSheet()
    documento = SimpleDocTemplate(str(ruta), pagesize=landscape(A4), leftMargin=1.5 * cm,
                                  rightMargin=1.5 * cm, topMargin=1.5 * cm, bottomMargin=1.5 * cm,
                                  title=informe.titulo)
    partes = [Paragraph(f"ZebraGym · {escape(informe.titulo)}", estilos["Title"]),
              Paragraph(escape(informe.subtitulo), estilos["Normal"])]
    for linea in informe.resumen:
        partes.append(Paragraph(escape(linea), estilos["Normal"]))
    partes.append(Spacer(1, 0.4 * cm))
    if informe.filas:
        celda = estilos["BodyText"]
        celda.fontSize = 8
        celda.leading = 10
        datos = [[Paragraph(f"<b>{escape(str(e))}</b>", celda) for e in informe.encabezados]]
        datos += [[Paragraph(escape("" if v is None else str(v)), celda) for v in fila] for fila in informe.filas]
        tabla = Table(datos, repeatRows=1)
        tabla.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(f"#{DORADO}")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F4F4F4")]),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CCCCCC")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        partes.append(tabla)
    else:
        partes.append(Paragraph(MENSAJE_VACIO, estilos["Normal"]))
    documento.build(partes)
    return ruta
