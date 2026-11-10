from datetime import date

from PySide6.QtCore import QDate, QTime, Signal
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QTimeEdit,
    QVBoxLayout, QWidget,
)

from repositories.jornada_repository import JornadaRepository
from repositories.attendance_repository import AttendanceRepository
from services.jornada_service import JornadaService


class JornadaWidget(QWidget):
    """
    Segunda opción del Menú Lateral: Configuración de la Jornada (persistida).

    Estados:
      - Sin Jornada: campos editables y botón Guardar Jornada (INSERT).
      - Guardada: campos bloqueados, Editar Jornada y Terminar Jornada;
        se conserva jornada_id en memoria.
      - Edición: mismo jornada_id, campos editables, Guardar Jornada (UPDATE).

    Terminar Jornada sólo olvida el jornada_id y limpia el formulario: no
    elimina ni modifica el registro en PostgreSQL.

    Emite estado_cambiado(bool) cuando cambia camara_habilitada(), para que la
    pantalla de asistencia cierre la cámara automáticamente.
    """

    estado_cambiado = Signal(bool)

    def __init__(self, usuario_id):
        super().__init__()
        self.usuario_id = usuario_id
        self.repo = JornadaRepository()
        self.servicio = JornadaService(self.repo, AttendanceRepository())
        self.jornada_id = None
        self.modo_edicion = False
        self._ultimo_estado = False

        titulo = QLabel("Configuración de la Jornada")
        titulo.setStyleSheet("font-weight: bold; font-size: 16px;")

        self.fecha_valor = QLabel(QDate.currentDate().toString("dd/MM/yyyy"))

        self.entrada_edit = self._crear_time_edit()
        self.salida_edit = self._crear_time_edit()

        self.catedra_edit = QLineEdit()
        self.catedra_edit.setPlaceholderText("Nombre de la cátedra")
        self.catedra_edit.textChanged.connect(self._actualizar_interfaz)

        self.guardar_button = QPushButton("Guardar Jornada")
        self.editar_button = QPushButton("Editar Jornada")
        self.terminar_button = QPushButton("Terminar Jornada")
        self.guardar_button.clicked.connect(self.guardar_jornada)
        self.editar_button.clicked.connect(self.editar_jornada)
        self.terminar_button.clicked.connect(self.terminar_jornada)

        fila_fecha = QHBoxLayout()
        fila_fecha.addWidget(QLabel("Fecha"))
        fila_fecha.addWidget(self.fecha_valor)
        fila_fecha.addStretch()

        fila_entrada = QHBoxLayout()
        fila_entrada.addWidget(QLabel("Horario de entrada"))
        fila_entrada.addWidget(self.entrada_edit)
        fila_entrada.addStretch()

        fila_salida = QHBoxLayout()
        fila_salida.addWidget(QLabel("Horario de salida"))
        fila_salida.addWidget(self.salida_edit)
        fila_salida.addStretch()

        fila_catedra = QHBoxLayout()
        fila_catedra.addWidget(QLabel("Cátedra"))
        fila_catedra.addWidget(self.catedra_edit)

        fila_botones = QHBoxLayout()
        fila_botones.addWidget(self.guardar_button)
        fila_botones.addWidget(self.editar_button)
        fila_botones.addWidget(self.terminar_button)
        fila_botones.addStretch()

        layout = QVBoxLayout()
        layout.addWidget(titulo)
        layout.addLayout(fila_fecha)
        layout.addLayout(fila_entrada)
        layout.addLayout(fila_salida)
        layout.addLayout(fila_catedra)
        layout.addLayout(fila_botones)
        layout.addStretch()
        self.setLayout(layout)

        self._actualizar_interfaz()

    def _crear_time_edit(self):
        editor = QTimeEdit()
        editor.setDisplayFormat("HH:mm")
        editor.setMinimumTime(QTime(0, 0))
        editor.setSpecialValueText("--:--")
        editor.setTime(QTime(0, 0))  # "--:--" hasta que el usuario lo cambie
        editor.timeChanged.connect(self._actualizar_interfaz)
        return editor

    # --- Estado ---

    @staticmethod
    def _hora_cargada(editor):
        return editor.time() != editor.minimumTime()

    def _datos_validos(self):
        return (
            self._hora_cargada(self.entrada_edit)
            and self._hora_cargada(self.salida_edit)
            and self.salida_edit.time() > self.entrada_edit.time()
            and self.catedra_edit.text().strip() != ""
        )

    def camara_habilitada(self):
        """La cámara sólo puede abrirse con una Jornada guardada y fuera de edición."""
        return self.jornada_id is not None and not self.modo_edicion

    def horario_entrada(self):
        return self.entrada_edit.time().toPython()

    def horario_salida(self):
        return self.salida_edit.time().toPython()

    def _actualizar_interfaz(self, *_args):
        guardada = self.jornada_id is not None
        editable = (not guardada) or self.modo_edicion

        for control in (self.entrada_edit, self.salida_edit, self.catedra_edit):
            control.setEnabled(editable)

        self.guardar_button.setVisible(editable)
        self.guardar_button.setEnabled(editable and self._datos_validos())
        self.editar_button.setVisible(guardada and not self.modo_edicion)
        self.terminar_button.setVisible(guardada)

        habilitada = self.camara_habilitada()
        if habilitada != self._ultimo_estado:
            self._ultimo_estado = habilitada
            self.estado_cambiado.emit(habilitada)

    # --- Acciones ---

    def guardar_jornada(self):
        if not self._datos_validos():
            return
        if self._persistir():
            self.modo_edicion = False
            self._actualizar_interfaz()

    def guardar_cambios_pendientes(self):
        """Si hay una Jornada en edición, registra en PostgreSQL lo que se
        modificó aunque no se haya apretado Guardar Jornada (al terminarla,
        al cambiar de opción del menú o al cerrar la aplicación).
        Devuelve False si los datos no son válidos o no se pudieron guardar."""
        if self.jornada_id is None or not self.modo_edicion:
            return True
        if not self._datos_validos():
            QMessageBox.warning(
                self, "Cambios sin guardar",
                "Los cambios de la Jornada no se guardaron: complete ambos horarios "
                "(la salida posterior a la entrada) y la cátedra.")
            return False
        if not self._persistir():
            return False
        self.modo_edicion = False
        self._actualizar_interfaz()
        return True

    def _persistir(self):
        entrada = self.entrada_edit.time().toPython()
        salida = self.salida_edit.time().toPython()
        catedra = self.catedra_edit.text().strip()

        try:
            if self.jornada_id is None:
                hoy = date.today()
                self.jornada_id = self.repo.crear(self.usuario_id, hoy, entrada, salida, catedra)
                self.fecha_valor.setText(hoy.strftime("%d/%m/%Y"))
            else:
                self.servicio.actualizar(self.jornada_id, self.usuario_id, entrada, salida, catedra)
        except Exception as error:
            QMessageBox.critical(self, "Error al guardar", f"No se pudo guardar la Jornada:\n{error}")
            return False
        return True

    def editar_jornada(self):
        self.modo_edicion = True
        self._actualizar_interfaz()  # emite False: la cámara se cierra

    def hideEvent(self, event):
        # Al pasar a otra opción del menú no se pierden los cambios en edición.
        self.guardar_cambios_pendientes()
        super().hideEvent(event)

    def terminar_jornada(self):
        # Primero se registran los cambios hechos en edición; si no son
        # válidos, la Jornada sigue abierta para corregirlos.
        if not self.guardar_cambios_pendientes():
            return
        self.jornada_id = None
        self.modo_edicion = False
        self.entrada_edit.setTime(QTime(0, 0))
        self.salida_edit.setTime(QTime(0, 0))
        self.catedra_edit.clear()
        self.fecha_valor.setText(QDate.currentDate().toString("dd/MM/yyyy"))
        self._actualizar_interfaz()
