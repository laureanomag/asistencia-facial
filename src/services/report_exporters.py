"""Generación de planillas de asistencia: Excel (openpyxl) y PDF (ReportLab).
Módulo sin acceso a base de datos: recibe los datos ya armados."""
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from xml.sax.saxutils import escape

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

SIN_REGISTRAR = "Sin registrar"
MENSAJE_VACIO = "No se registraron asistencias para esta Jornada."
ENCABEZADOS = ["#", "Apellido", "Nombre", "DNI", "Libreta", "Entrada", "Salida"]


@dataclass
class FilaAlumno:
    apellido: str
    nombre: str
    dni: str
    libreta: str
    entrada: object   # datetime / time
    salida: object    # datetime / time / None
    tardanza: bool = False


@dataclass
class DatosInforme:
    fecha: object
    catedra: str
    horario_entrada: object
    horario_salida: object
    usuario: str
    alumnos: list = field(default_factory=list)


def hora_texto(valor):
    return valor.strftime("%H:%M") if valor is not None else ""


def contador_texto(cantidad):
    if cantidad == 1:
        return "Se registró 1 alumno presente en total."
    return f"Se registraron {cantidad} alumnos presentes en total."


def _clave_orden(texto):
    sin_acentos = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return sin_acentos.casefold()


def ordenar_alumnos(alumnos):
    return sorted(alumnos, key=lambda a: (_clave_orden(a.apellido), _clave_orden(a.nombre)))


def nombre_sugerido(fecha, catedra, extension):
    base = unicodedata.normalize("NFKD", catedra).encode("ascii", "ignore").decode().lower()
    base = re.sub(r"[^a-z0-9]+", "-", base).strip("-") or "jornada"
    return f"asistencia_{fecha.strftime('%Y-%m-%d')}_{base}.{extension}"


def _filas_tabla(datos):
    filas = []
    for i, a in enumerate(ordenar_alumnos(datos.alumnos), start=1):
        salida = hora_texto(a.salida) if a.salida is not None else SIN_REGISTRAR
        entrada = hora_texto(a.entrada)
        if a.tardanza:
            entrada += " (Tardanza)"
        filas.append([i, a.apellido, a.nombre, str(a.dni), str(a.libreta or ""),
                      entrada, salida])
    return filas


def _datos_jornada(datos):
    return [
        ("Fecha", datos.fecha.strftime("%d/%m/%Y")),
        ("Cátedra", datos.catedra),
        ("Horario de entrada", hora_texto(datos.horario_entrada)),
        ("Horario de salida", hora_texto(datos.horario_salida)),
        ("Usuario", datos.usuario),
    ]


def generar_excel(ruta, datos):
    wb = Workbook()
    ws = wb.active
    ws.title = "Asistencia"
    ultima_col = len(ENCABEZADOS)

    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=ultima_col)
    ws["A1"] = "PLANILLA DE ASISTENCIA"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A1"].alignment = Alignment(horizontal="center")

    fila = 3
    for etiqueta, valor in _datos_jornada(datos):
        ws.cell(fila, 1, f"{etiqueta}:").font = Font(bold=True)
        ws.merge_cells(start_row=fila, start_column=2, end_row=fila, end_column=ultima_col)
        ws.cell(fila, 2, valor)
        fila += 1
    # la etiqueta cabe mejor combinando A:B no es necesario: se ajusta el ancho abajo

    fila += 1
    alumnos = _filas_tabla(datos)
    borde = Border(*(Side(style="thin"),) * 4)

    if alumnos:
        for col, titulo in enumerate(ENCABEZADOS, start=1):
            c = ws.cell(fila, col, titulo)
            c.font = Font(bold=True, color="FFFFFF")
            c.fill = PatternFill("solid", fgColor="305496")
            c.alignment = Alignment(horizontal="center")
            c.border = borde
        for datos_fila in alumnos:
            fila += 1
            for col, valor in enumerate(datos_fila, start=1):
                c = ws.cell(fila, col, valor)
                c.border = borde
                if col in (1, 6, 7):
                    c.alignment = Alignment(horizontal="center")
    else:
        ws.merge_cells(start_row=fila, start_column=1, end_row=fila, end_column=ultima_col)
        ws.cell(fila, 1, MENSAJE_VACIO).font = Font(italic=True)

    fila += 2
    ws.merge_cells(start_row=fila, start_column=1, end_row=fila, end_column=ultima_col)
    ws.cell(fila, 1, contador_texto(len(alumnos))).font = Font(bold=True)

    for letra, ancho in zip("ABCDEFG", [20, 22, 22, 14, 14, 20, 16]):
        ws.column_dimensions[letra].width = ancho

    wb.save(ruta)


def generar_pdf(ruta, datos):
    estilos = getSampleStyleSheet()
    normal = estilos["Normal"]
    doc = SimpleDocTemplate(
        ruta, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm,
        topMargin=2 * cm, bottomMargin=2 * cm, title="Planilla de asistencia",
    )

    elementos = [Paragraph("PLANILLA DE ASISTENCIA", estilos["Title"])]
    for etiqueta, valor in _datos_jornada(datos):
        elementos.append(Paragraph(f"<b>{etiqueta}:</b> {escape(str(valor))}", normal))
    elementos.append(Spacer(1, 0.6 * cm))

    alumnos = _filas_tabla(datos)
    if alumnos:
        tabla = Table(
            [ENCABEZADOS] + alumnos,
            colWidths=[1.0 * cm, 3.3 * cm, 2.8 * cm, 2.2 * cm, 2.0 * cm, 3.1 * cm, 2.6 * cm],
            repeatRows=1,
        )
        tabla.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#305496")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("ALIGN", (0, 0), (0, -1), "CENTER"),
            ("ALIGN", (5, 0), (6, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F2F2")]),
        ]))
        elementos.append(tabla)
    else:
        elementos.append(Paragraph(f"<i>{MENSAJE_VACIO}</i>", normal))

    elementos.append(Spacer(1, 0.6 * cm))
    elementos.append(Paragraph(f"<b>{contador_texto(len(alumnos))}</b>", normal))
    doc.build(elementos)
