"""Empleados (solo administrador): alta de entrenadores y recepcionistas con
sus 3 fotos (fichan con la cara) y lista con activación o desactivación."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLineEdit,
    QMessageBox, QPushButton, QScrollArea, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from services.empleado_service import ROL_POR_DEFECTO, ROLES_EMPLEADO, ErroresFormulario
from services.persona_service import DatosInvalidos
from ui import tema
from ui.componentes import CampoFormulario, EtiquetaEstado, con_rol, etiqueta
from ui.fotos_referencia import FotosReferencia


def confirmar(parent, titulo, texto):
    return QMessageBox.question(parent, titulo, texto) == QMessageBox.StandardButton.Yes


class EmpleadosPage(QWidget):
    COLUMNAS = ("Nombre", "Usuario", "Rol", "Estado", "")

    def __init__(self, sesion, servicio=None, fotos=None, confirmar_accion=None):
        super().__init__()
        if servicio is None:
            from services.empleado_service import EmpleadoService
            servicio = EmpleadoService()
        self.sesion, self.servicio = sesion, servicio
        self._confirmar = confirmar_accion or confirmar
        self._existente = None

        # --- Formulario ---
        self.dni = QLineEdit()
        self.dni.setPlaceholderText("Solo números, 7 u 8 dígitos")
        self.dni.editingFinished.connect(self.buscar_dni)
        self.nombre, self.apellido = QLineEdit(), QLineEdit()
        self.usuario = QLineEdit()
        self.contrasenia = QLineEdit()
        self.contrasenia.setEchoMode(QLineEdit.EchoMode.Password)
        self.rol = QComboBox()
        for clave, texto in ROLES_EMPLEADO.items():     # Entrenador primero: queda elegido
            self.rol.addItem(texto, clave)
        self.fotos = fotos or FotosReferencia()

        self.campos = {
            "dni": CampoFormulario("DNI", self.dni),
            "nombre": CampoFormulario("Nombre", self.nombre),
            "apellido": CampoFormulario("Apellido", self.apellido),
            "usuario": CampoFormulario("Usuario", self.usuario),
            "contrasenia": CampoFormulario("Contraseña inicial", self.contrasenia,
                                           "Mínimo 8 caracteres. Se cambia en el primer ingreso."),
            "rol": CampoFormulario("Rol", self.rol),
            "fotos": CampoFormulario("Fotos de referencia", self.fotos,
                                     "Fichan con la cara: el frente tiene que tener un rostro detectable."),
        }
        self.aviso_persona = etiqueta("", "secundario")
        self.aviso_persona.setWordWrap(True)
        self.aviso_persona.hide()
        self.resultado = etiqueta("", "ok")
        self.resultado.setWordWrap(True)
        self.resultado.hide()

        self.registrar_boton = con_rol(QPushButton("Registrar empleado"), "primario")
        self.registrar_boton.clicked.connect(self.registrar)
        limpiar = QPushButton("Limpiar")
        limpiar.clicked.connect(self.limpiar)
        botones = QHBoxLayout()
        botones.addStretch()
        botones.addWidget(limpiar)
        botones.addWidget(self.registrar_boton)

        grilla = QGridLayout()
        grilla.setHorizontalSpacing(16)
        grilla.setVerticalSpacing(14)
        arriba = Qt.AlignmentFlag.AlignTop
        grilla.addWidget(self.campos["dni"], 0, 0, arriba)
        grilla.addWidget(self.aviso_persona, 0, 1, Qt.AlignmentFlag.AlignBottom)
        grilla.addWidget(self.campos["nombre"], 1, 0, arriba)
        grilla.addWidget(self.campos["apellido"], 1, 1, arriba)
        grilla.addWidget(self.campos["fotos"], 2, 0, 1, 2)
        grilla.addWidget(self.campos["usuario"], 3, 0, arriba)
        grilla.addWidget(self.campos["contrasenia"], 3, 1, arriba)
        grilla.addWidget(self.campos["rol"], 4, 0, arriba)
        grilla.setColumnStretch(0, 1)
        grilla.setColumnStretch(1, 1)

        formulario = con_rol(QFrame(), "panel")
        columna = QVBoxLayout(formulario)
        columna.setContentsMargins(24, 20, 24, 20)
        columna.setSpacing(14)
        columna.addWidget(etiqueta("Nuevo empleado", "titulo-panel"))
        columna.addLayout(grilla)
        columna.addWidget(self.resultado)
        columna.addLayout(botones)
        columna.addStretch()
        desplazable = QScrollArea()
        desplazable.setWidgetResizable(True)
        desplazable.setFrameShape(QFrame.Shape.NoFrame)
        desplazable.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        desplazable.setWidget(formulario)

        # --- Lista ---
        self.tabla = QTableWidget(0, len(self.COLUMNAS))
        self.tabla.setHorizontalHeaderLabels(self.COLUMNAS)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.tabla.setShowGrid(False)
        self.tabla.verticalHeader().setDefaultSectionSize(52)
        cabecera = self.tabla.horizontalHeader()
        cabecera.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for columna_tabla in range(1, len(self.COLUMNAS)):
            cabecera.setSectionResizeMode(columna_tabla, QHeaderView.ResizeMode.ResizeToContents)
        self.lista_vacia = etiqueta("Todavía no hay empleados registrados.", "secundario")
        self.error_lista = etiqueta("", "error")
        self.error_lista.setWordWrap(True)
        self.error_lista.hide()
        lista = con_rol(QFrame(), "panel")
        columna_l = QVBoxLayout(lista)
        columna_l.setContentsMargins(20, 20, 20, 20)
        columna_l.setSpacing(12)
        columna_l.addWidget(etiqueta("Personal", "titulo-panel"))
        columna_l.addWidget(self.error_lista)
        columna_l.addWidget(self.lista_vacia)
        columna_l.addWidget(self.tabla, 1)
        columna_l.addStretch(0)
        self._columna_lista = columna_l
        lista.setFixedWidth(330)

        fila = QHBoxLayout(self)
        fila.setContentsMargins(0, 0, 0, 0)
        fila.setSpacing(20)
        fila.addWidget(desplazable, 1)
        fila.addWidget(lista)

    def showEvent(self, evento):
        super().showEvent(evento)
        self.cargar_lista()

    # --- Formulario ---

    def _datos(self):
        return {"dni": self.dni.text(), "nombre": self.nombre.text(), "apellido": self.apellido.text(),
                "usuario": self.usuario.text(), "contrasenia": self.contrasenia.text(),
                "rol": self.rol.currentData()}

    def limpiar_errores(self):
        for campo in self.campos.values():
            campo.limpiar_error()

    def mostrar_errores(self, errores):
        self.limpiar_errores()
        for nombre, mensaje in errores.items():
            self.campos.get(nombre, self.campos["dni"]).mostrar_error(mensaje)

    def buscar_dni(self):
        """Si el DNI ya existe (p. ej., un socio), se reutiliza la persona."""
        self._existente = None
        self.aviso_persona.hide()
        for campo in (self.nombre, self.apellido):
            campo.setReadOnly(False)
        if not self.dni.text().strip():
            return
        try:
            existente = self.servicio.buscar_por_dni(self.sesion, self.dni.text())
        except DatosInvalidos as error:
            self.campos["dni"].mostrar_error(str(error))
            return
        except Exception as error:
            self.campos["dni"].mostrar_error(f"No se pudo consultar la base de datos. {error}")
            return
        self.campos["dni"].limpiar_error()
        if existente is None:
            return
        self._existente = existente
        self.nombre.setText(existente["nombre"])
        self.apellido.setText(existente["apellido"])
        for campo in (self.nombre, self.apellido):
            campo.setReadOnly(True)
        if existente["tiene_cuenta"]:
            self.campos["dni"].mostrar_error("Esa persona ya tiene una cuenta de usuario.")
            return
        fotos = (f"Ya tiene {existente['fotos']} fotos: cargá nuevas solo para reemplazarlas."
                 if existente["fotos"] else "No tiene fotos: cargá las 3.")
        self.aviso_persona.setText(f"Persona registrada: se reutilizan sus datos. {fotos}")
        self.aviso_persona.show()

    def registrar(self):
        self.resultado.hide()
        datos = self._datos()
        errores = self.servicio.validar(datos, self.fotos.fotos(), self._existente)
        if errores:
            self.mostrar_errores(errores)
            return
        try:
            self.servicio.registrar(self.sesion, datos, self.fotos.fotos())
        except ErroresFormulario as error:
            self.mostrar_errores(error.errores)
            return
        except Exception as error:
            self._mostrar_resultado(f"No se pudo registrar el empleado. {error}", "error")
            return
        nombre = f"{datos['nombre'].strip()} {datos['apellido'].strip()}"
        rol = ROLES_EMPLEADO[datos["rol"]].lower()
        self.limpiar()
        self._mostrar_resultado(f"Se registró a {nombre} como {rol}. En el primer ingreso va a "
                                "tener que cambiar la contraseña.", "ok")
        self.cargar_lista()

    def _mostrar_resultado(self, texto, rol):
        self.resultado.setText(texto)
        self.resultado.setProperty("rol", rol)
        tema.refrescar_estilo(self.resultado)
        self.resultado.show()

    def limpiar(self):
        self._existente = None
        for campo in (self.dni, self.nombre, self.apellido, self.usuario, self.contrasenia):
            campo.clear()
            campo.setReadOnly(False)
        self.rol.setCurrentIndex(self.rol.findData(ROL_POR_DEFECTO))
        self.fotos.limpiar()
        self.aviso_persona.hide()
        self.resultado.hide()
        self.limpiar_errores()

    # --- Lista ---

    def cargar_lista(self):
        try:
            filas = self.servicio.listar(self.sesion)
        except Exception as error:
            self.error_lista.setText(f"No se pudo consultar el personal. {error}")
            self.error_lista.show()
            return
        self.error_lista.hide()
        self.lista_vacia.setVisible(not filas)
        self.tabla.setVisible(bool(filas))
        # Sin filas, el espacio libre queda abajo (no se centra el aviso).
        indice_tabla = self._columna_lista.indexOf(self.tabla)
        self._columna_lista.setStretch(indice_tabla, 1 if filas else 0)
        self._columna_lista.setStretch(indice_tabla + 1, 0 if filas else 1)
        self.tabla.setRowCount(len(filas))
        for fila, (usuario_id, nombre, apellido, _dni, usuario, activo, roles, _acceso) in enumerate(filas):
            self.tabla.setItem(fila, 0, QTableWidgetItem(f"{nombre} {apellido}"))
            self.tabla.setItem(fila, 1, QTableWidgetItem(usuario))
            self.tabla.setItem(fila, 2, QTableWidgetItem(
                ", ".join(ROLES_EMPLEADO.get(r, r.capitalize()) for r in roles)))
            self.tabla.setCellWidget(fila, 3, self._celda(EtiquetaEstado(
                "Activo" if activo else "Inactivo", "verde" if activo else "neutro")))
            boton = QPushButton("Desactivar" if activo else "Reactivar")
            boton.setMinimumHeight(34)
            boton.setStyleSheet("font-size: 13px;")
            boton.clicked.connect(lambda _c=False, u=usuario_id, a=activo, n=f"{nombre} {apellido}":
                                  self.cambiar_estado(u, not a, n))
            self.tabla.setCellWidget(fila, 4, self._celda(boton))

    @staticmethod
    def _celda(widget):
        contenedor = QWidget()
        fila = QHBoxLayout(contenedor)
        fila.setContentsMargins(6, 0, 6, 0)
        fila.addWidget(widget)
        return contenedor

    def cambiar_estado(self, usuario_id, activo, nombre):
        accion = "reactivar" if activo else "desactivar"
        detalle = ("Va a poder volver a ingresar y fichar." if activo
                   else "No va a poder ingresar al sistema ni fichar. Sus datos y fotos se conservan.")
        if not self._confirmar(self, f"{accion.capitalize()} cuenta", f"¿Querés {accion} la cuenta de {nombre}? {detalle}"):
            return
        try:
            self.servicio.cambiar_estado(self.sesion, usuario_id, activo)
        except Exception as error:
            self.error_lista.setText(f"No se pudo {accion} la cuenta. {error}")
            self.error_lista.show()
            return
        self.cargar_lista()
