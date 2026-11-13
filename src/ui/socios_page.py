"""Socios: alta con datos, contacto de emergencia y las 3 fotos (entran con
la cara) y lista con búsqueda por DNI o nombre. Si el DNI ya existe (por
ejemplo, un entrenador) se reutiliza la persona. La baja y la reactivación
las hace la dueña desde Estado del socio."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLineEdit, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from services.persona_service import DatosInvalidos, SocioYaRegistrado
from ui import tema
from ui.componentes import CampoFormulario, EtiquetaEstado, con_rol, etiqueta
from ui.estados import dni_con_puntos, estado_membresia
from ui.tablas import crear_tabla, llenar


class SociosPage(QWidget):
    COLUMNAS = ("Nombre", "DNI", "Membresía")

    def __init__(self, sesion, servicio=None, fotos=None):
        super().__init__()
        if servicio is None:
            from services.persona_service import PersonaService
            servicio = PersonaService()
        if fotos is None:
            from ui.fotos_referencia import FotosReferencia
            fotos = FotosReferencia()
        self.sesion, self.servicio, self.fotos = sesion, servicio, fotos
        self._existente = None

        # --- Formulario ---
        self.dni = QLineEdit()
        self.dni.setPlaceholderText("Solo números, 7 u 8 dígitos")
        self.dni.editingFinished.connect(self.buscar_dni)
        self.nombre, self.apellido, self.celular = QLineEdit(), QLineEdit(), QLineEdit()
        self.emergencia_nombre, self.emergencia_telefono = QLineEdit(), QLineEdit()
        self.campos = {
            "dni": CampoFormulario("DNI", self.dni),
            "nombre": CampoFormulario("Nombre", self.nombre),
            "apellido": CampoFormulario("Apellido", self.apellido),
            "celular": CampoFormulario("Celular (opcional)", self.celular),
            "contacto_emergencia_nombre": CampoFormulario("Contacto de emergencia (opcional)",
                                                          self.emergencia_nombre),
            "contacto_emergencia_telefono": CampoFormulario("Teléfono de emergencia",
                                                            self.emergencia_telefono),
            "fotos": CampoFormulario("Fotos de referencia", self.fotos,
                                     "Entra con la cara: el frente tiene que tener un rostro detectable."),
        }
        self.aviso_persona = etiqueta("", "secundario")
        self.aviso_persona.setWordWrap(True)
        self.aviso_persona.hide()
        self.resultado = etiqueta("", "ok")
        self.resultado.setWordWrap(True)
        self.resultado.hide()

        self.registrar_boton = con_rol(QPushButton("Registrar socio"), "primario")
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
        grilla.addWidget(self.campos["celular"], 2, 0, arriba)
        grilla.addWidget(self.campos["contacto_emergencia_nombre"], 3, 0, arriba)
        grilla.addWidget(self.campos["contacto_emergencia_telefono"], 3, 1, arriba)
        grilla.addWidget(self.campos["fotos"], 4, 0, 1, 2)
        grilla.setColumnStretch(0, 1)
        grilla.setColumnStretch(1, 1)

        formulario = con_rol(QFrame(), "panel")
        columna = QVBoxLayout(formulario)
        columna.setContentsMargins(24, 20, 24, 20)
        columna.setSpacing(14)
        columna.addWidget(etiqueta("Nuevo socio", "titulo-panel"))
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
        self.busqueda = QLineEdit()
        self.busqueda.setPlaceholderText("DNI o nombre")
        self.busqueda.returnPressed.connect(self.cargar_lista)
        self.busqueda.textChanged.connect(lambda texto: self.cargar_lista() if not texto else None)
        buscar = QPushButton("Buscar")
        buscar.clicked.connect(self.cargar_lista)
        fila_busqueda = QHBoxLayout()
        fila_busqueda.addWidget(self.busqueda, 1)
        fila_busqueda.addWidget(buscar)
        self.tabla = crear_tabla(self.COLUMNAS)
        self.lista_vacia = etiqueta("Todavía no hay socios registrados.", "secundario")
        self.lista_vacia.setWordWrap(True)
        self.error_lista = etiqueta("", "error")
        self.error_lista.setWordWrap(True)
        self.error_lista.hide()
        lista = con_rol(QFrame(), "panel")
        columna_l = QVBoxLayout(lista)
        columna_l.setContentsMargins(20, 20, 20, 20)
        columna_l.setSpacing(12)
        columna_l.addWidget(etiqueta("Socios", "titulo-panel"))
        columna_l.addLayout(fila_busqueda)
        columna_l.addWidget(self.error_lista)
        columna_l.addWidget(self.lista_vacia)
        columna_l.addWidget(self.tabla, 1)
        lista.setMinimumWidth(320)
        lista.setMaximumWidth(400)

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
                "celular": self.celular.text().strip(),
                "contacto_emergencia_nombre": self.emergencia_nombre.text().strip(),
                "contacto_emergencia_telefono": self.emergencia_telefono.text().strip()}

    def mostrar_errores(self, errores):
        for campo in self.campos.values():
            campo.limpiar_error()
        for nombre, mensaje in errores.items():
            self.campos.get(nombre, self.campos["dni"]).mostrar_error(mensaje)

    def buscar_dni(self):
        self._existente = None
        self.aviso_persona.hide()
        for campo in (self.nombre, self.apellido):
            campo.setReadOnly(False)
        if not self.dni.text().strip():
            return
        try:
            existente = self.servicio.buscar_persona(self.sesion, self.dni.text())
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
        errores = self.servicio.validar_socio(self._datos(), {}, existente)
        if "dni" in errores:
            self.campos["dni"].mostrar_error(errores["dni"])
            return
        fotos = (f"Ya tiene {existente['fotos']} fotos: cargá nuevas solo para reemplazarlas."
                 if existente["fotos"] else "No tiene fotos: cargá las 3.")
        self.aviso_persona.setText(f"Persona registrada (por ejemplo, del personal): se reutilizan "
                                   f"sus datos. {fotos}")
        self.aviso_persona.show()

    def registrar(self):
        self.resultado.hide()
        datos, fotos = self._datos(), self.fotos.fotos()
        errores = self.servicio.validar_socio(datos, fotos, self._existente)
        if not errores and fotos.get("frente") is not None and hasattr(self.fotos, "frente_detectable") \
                and self.fotos.frente_detectable() is False:
            errores["fotos"] = "En la foto de frente no se detecta un rostro: tomala de nuevo."
        self.mostrar_errores(errores)
        if errores:
            return
        try:
            self.servicio.registrar_socio(self.sesion, datos, fotos, datos["contacto_emergencia_telefono"],
                                          datos["contacto_emergencia_nombre"] or None)
        except (DatosInvalidos, SocioYaRegistrado) as error:
            self.campos["dni"].mostrar_error(str(error))
            return
        except Exception as error:
            self._mostrar_resultado(f"No se pudo registrar el socio. {error}", "error")
            return
        nombre = f"{datos['nombre'].strip()} {datos['apellido'].strip()}"
        self.limpiar()
        self._mostrar_resultado(f"Se registró a {nombre}. Para que pueda entrar, cobrale un plan en "
                                "Cobros y renovaciones.", "ok")
        self.cargar_lista()

    def _mostrar_resultado(self, texto, rol):
        self.resultado.setText(texto)
        self.resultado.setProperty("rol", rol)
        tema.refrescar_estilo(self.resultado)
        self.resultado.show()

    def limpiar(self):
        self._existente = None
        for campo in (self.dni, self.nombre, self.apellido, self.celular, self.emergencia_nombre,
                      self.emergencia_telefono):
            campo.clear()
            campo.setReadOnly(False)
        self.fotos.limpiar()
        self.aviso_persona.hide()
        self.resultado.hide()
        self.mostrar_errores({})

    # --- Lista ---

    def cargar_lista(self):
        try:
            filas = self.servicio.listar_socios(self.sesion, self.busqueda.text())
        except Exception as error:
            self.error_lista.setText(f"No se pudo consultar los socios. {error}")
            self.error_lista.show()
            return
        self.error_lista.hide()
        buscando = bool(self.busqueda.text().strip())
        self.lista_vacia.setText("No hay socios que coincidan con la búsqueda." if buscando
                                 else "Todavía no hay socios registrados.")
        self.lista_vacia.setVisible(not filas)
        self.tabla.setVisible(bool(filas))
        llenar(self.tabla, [
            [f"{nombre} {apellido}", dni_con_puntos(dni), EtiquetaEstado(*estado_membresia(situacion, activo))]
            for (_sid, _pid, dni, nombre, apellido, _cel, activo, _plan, situacion, _contable, _vence, _saldo)
            in filas])
