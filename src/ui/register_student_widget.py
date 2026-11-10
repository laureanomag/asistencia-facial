from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QLabel, QLineEdit, QDateEdit, QSpinBox, QPushButton,
    QVBoxLayout, QHBoxLayout, QFormLayout, QWidget, QMessageBox, QScrollArea
)

from repositories.student_repository import StudentRepository
from ui.image_slot_widget import ImageSlotWidget


class RegisterStudentWidget(QWidget):
    """
    Tercera opción del Menú Lateral: Registrar Alumno.
    """

    def __init__(self):
        super().__init__()
        self.repo = StudentRepository()

        titulo = QLabel("Registrar Alumno")
        titulo.setStyleSheet("font-weight: bold; font-size: 16px;")

        self.nombre_edit = QLineEdit()
        self.apellido_edit = QLineEdit()
        self.dni_edit = QLineEdit()
        self.carrera_edit = QLineEdit()
        self.celular_edit = QLineEdit()
        self.correo_edit = QLineEdit()

        self.fecha_nacimiento_edit = QDateEdit()
        self.fecha_nacimiento_edit.setCalendarPopup(True)
        self.fecha_nacimiento_edit.setDisplayFormat("dd/MM/yyyy")
        self.fecha_nacimiento_edit.setDate(QDate.currentDate().addYears(-18))

        anio_actual = QDate.currentDate().year()
        self.anio_ingreso_spin = QSpinBox()
        self.anio_ingreso_spin.setRange(2000, anio_actual + 1)
        self.anio_ingreso_spin.setValue(anio_actual)

        self.domicilio_edit = QLineEdit()
        self.libreta_edit = QLineEdit()

        datos_form = QFormLayout()
        datos_form.addRow("Nombre", self.nombre_edit)
        datos_form.addRow("Apellido", self.apellido_edit)
        datos_form.addRow("DNI", self.dni_edit)
        datos_form.addRow("Carrera", self.carrera_edit)
        datos_form.addRow("Celular", self.celular_edit)
        datos_form.addRow("Correo Electrónico", self.correo_edit)
        datos_form.addRow("Fecha de Nacimiento", self.fecha_nacimiento_edit)
        datos_form.addRow("Año de ingreso", self.anio_ingreso_spin)
        datos_form.addRow("Domicilio", self.domicilio_edit)
        datos_form.addRow("Número de libreta", self.libreta_edit)

        self.slot_frontal = ImageSlotWidget("Ángulo Frontal")
        self.slot_izquierdo = ImageSlotWidget("Ángulo Izquierdo")
        self.slot_derecho = ImageSlotWidget("Ángulo Derecho")

        fotos_layout = QHBoxLayout()
        fotos_layout.addWidget(self.slot_frontal)
        fotos_layout.addWidget(self.slot_izquierdo)
        fotos_layout.addWidget(self.slot_derecho)

        self.registrar_button = QPushButton("Registrar")
        self.registrar_button.clicked.connect(self.registrar_alumno)

        contenido = QWidget()
        contenido_layout = QVBoxLayout()
        contenido_layout.addWidget(titulo)
        contenido_layout.addLayout(datos_form)
        contenido_layout.addLayout(fotos_layout)
        contenido_layout.addWidget(self.registrar_button)
        contenido.setLayout(contenido_layout)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(contenido)

        layout = QVBoxLayout()
        layout.addWidget(scroll)
        self.setLayout(layout)

    def registrar_alumno(self):
        campos_texto = {
            "nombre": self.nombre_edit.text().strip(),
            "apellido": self.apellido_edit.text().strip(),
            "dni": self.dni_edit.text().strip(),
            "carrera": self.carrera_edit.text().strip(),
            "celular": self.celular_edit.text().strip(),
            "correo_electronico": self.correo_edit.text().strip(),
            "domicilio": self.domicilio_edit.text().strip(),
            "libreta": self.libreta_edit.text().strip(),
        }

        campos_incompletos = any(valor == "" for valor in campos_texto.values())
        imagenes_incompletas = not (
            self.slot_frontal.has_image()
            and self.slot_izquierdo.has_image()
            and self.slot_derecho.has_image()
        )

        if campos_incompletos or imagenes_incompletas:
            QMessageBox.critical(
                self,
                "Datos incompletos",
                "Existen campos obligatorios sin completar.",
            )
            return

        datos = {
            **campos_texto,
            "fecha_nacimiento": self.fecha_nacimiento_edit.date().toString("yyyy-MM-dd"),
            "anio_ingreso": self.anio_ingreso_spin.value(),
        }

        fotos = {
            "frente": self.slot_frontal.get_image_bytes(),
            "perfil_izquierdo": self.slot_izquierdo.get_image_bytes(),
            "perfil_derecho": self.slot_derecho.get_image_bytes(),
        }

        try:
            self.repo.registrar_alumno_completo(datos, fotos)
        except Exception as error:
            QMessageBox.critical(
                self,
                "Error al registrar",
                f"No se pudo registrar el alumno.\n\n{error}",
            )
            return

        QMessageBox.information(
            self, "Éxito", "El alumno fue registrado exitosamente."
        )
        self._limpiar_formulario()

    def _limpiar_formulario(self):
        self.nombre_edit.clear()
        self.apellido_edit.clear()
        self.dni_edit.clear()
        self.carrera_edit.clear()
        self.celular_edit.clear()
        self.correo_edit.clear()
        self.fecha_nacimiento_edit.setDate(QDate.currentDate().addYears(-18))
        self.anio_ingreso_spin.setValue(QDate.currentDate().year())
        self.domicilio_edit.clear()
        self.libreta_edit.clear()

        self.slot_frontal.eliminar_foto()
        self.slot_izquierdo.eliminar_foto()
        self.slot_derecho.eliminar_foto()
