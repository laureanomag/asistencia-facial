"""Jornadas (solo la dueña): carga de turnos del personal por rango de
fechas y días de la semana, cambios de horario, y licencias y permisos
("Dar licencia", "Dar permiso", "Anular"). Todo queda en jornada_cambio con
el motivo, quién lo aprobó y cuándo."""
from datetime import date, time, timedelta

from PySide6.QtCore import QTime, Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDateEdit, QDialog, QFrame, QHBoxLayout, QLineEdit, QMessageBox, QPushButton,
    QScrollArea, QTimeEdit, QVBoxLayout, QWidget,
)

from services.fichajes_service import (
    ESTADOS_JORNADA, ErroresJornada, fechas_entre, texto_horario, validar_jornada,
)
from services.horario_service import DIAS_CORTOS
from services.reglas_ingreso import fecha_texto, hora_texto
from ui import tema
from ui.componentes import CampoFormulario, EtiquetaEstado, con_rol, etiqueta
from ui.fichajes_page import a_fecha, a_qdate
from ui.tablas import crear_tabla, llenar


def _hora(campo):
    valor = campo.time()
    return time(valor.hour(), valor.minute())


def _editor_hora(hora, minuto):
    campo = QTimeEdit(QTime(hora, minuto))
    campo.setDisplayFormat("HH:mm")
    return campo


def _editor_fecha(valor):
    campo = QDateEdit(a_qdate(valor))
    campo.setCalendarPopup(True)
    campo.setDisplayFormat("dd/MM/yyyy")
    return campo


class DialogoAusencia(QDialog):
    """Dar licencia (rango de fechas) o dar permiso (un día, con horas opcionales)."""

    def __init__(self, tipo, personal, hoy, parent=None):
        super().__init__(parent)
        self.tipo = tipo
        self.datos = None
        licencia = tipo == "licencia"
        self.setWindowTitle("Dar licencia" if licencia else "Dar permiso")
        self.empleado = QComboBox()
        self.empleado.addItem("Elegí el empleado", None)
        for usuario_id, nombre in personal:
            self.empleado.addItem(nombre, usuario_id)
        self.desde, self.hasta = _editor_fecha(hoy), _editor_fecha(hoy)
        self.solo_horas = QCheckBox("Solo algunas horas")
        self.hora_desde, self.hora_hasta = _editor_hora(14, 0), _editor_hora(16, 0)
        self.motivo = QLineEdit()
        self.motivo.setPlaceholderText("Por ejemplo: vacaciones, trámite, turno médico")
        self.campos = {"empleado": CampoFormulario("Empleado", self.empleado),
                       "desde": CampoFormulario("Desde" if licencia else "Día", self.desde),
                       "hasta": CampoFormulario("Hasta", self.hasta),
                       "hora_desde": CampoFormulario("De", self.hora_desde),
                       "hora_hasta": CampoFormulario("A", self.hora_hasta),
                       "motivo": CampoFormulario("Motivo", self.motivo)}
        self.solo_horas.toggled.connect(self._horas)
        aprobar = con_rol(QPushButton("Aprobar licencia" if licencia else "Aprobar permiso"), "primario")
        aprobar.clicked.connect(self.aprobar)
        cancelar = QPushButton("Cancelar")
        cancelar.clicked.connect(self.reject)
        fechas = QHBoxLayout()
        fechas.addWidget(self.campos["desde"], 1)
        fechas.addWidget(self.campos["hasta"], 1)
        horas = QHBoxLayout()
        horas.addWidget(self.campos["hora_desde"], 1)
        horas.addWidget(self.campos["hora_hasta"], 1)
        botones = QHBoxLayout()
        botones.addStretch()
        botones.addWidget(cancelar)
        botones.addWidget(aprobar)
        columna = QVBoxLayout(self)
        columna.setContentsMargins(24, 22, 24, 22)
        columna.setSpacing(12)
        columna.addWidget(etiqueta(self.windowTitle(), "titulo-panel"))
        ayuda = etiqueta("Desde que lo aprobás, no puede marcar la llegada esos días u horas. "
                         "Si ya la había marcado, puede marcar la salida.", "secundario")
        ayuda.setWordWrap(True)
        columna.addWidget(ayuda)
        columna.addWidget(self.campos["empleado"])
        columna.addLayout(fechas)
        columna.addWidget(self.solo_horas)
        columna.addLayout(horas)
        columna.addWidget(self.campos["motivo"])
        columna.addLayout(botones)
        self.campos["hasta"].setVisible(licencia)
        self.solo_horas.setVisible(not licencia)
        for clave in ("hora_desde", "hora_hasta"):
            self.campos[clave].setVisible(not licencia)
        self._horas(False)

    def _horas(self, activas):
        self.hora_desde.setEnabled(activas)
        self.hora_hasta.setEnabled(activas)

    def aprobar(self):
        errores = {}
        if self.empleado.currentData() is None:
            errores["empleado"] = "Elegí el empleado."
        desde, hasta = a_fecha(self.desde), a_fecha(self.hasta)
        if self.tipo == "licencia" and hasta < desde:
            errores["hasta"] = "No puede ser anterior a Desde."
        horas = None
        if self.tipo == "permiso" and self.solo_horas.isChecked():
            horas = (_hora(self.hora_desde), _hora(self.hora_hasta))
            if horas[1] <= horas[0]:
                errores["hora_hasta"] = "Tiene que ser posterior a la hora inicial."
        for nombre, campo in self.campos.items():
            campo.mostrar_error(errores[nombre]) if nombre in errores else campo.limpiar_error()
        if errores:
            return
        self.datos = {"tipo": self.tipo, "usuario_id": self.empleado.currentData(),
                      "empleado": self.empleado.currentText(), "desde": desde,
                      "hasta": hasta if self.tipo == "licencia" else desde, "horas": horas,
                      "motivo": self.motivo.text().strip()}
        self.accept()


def pedir_ausencia(parent, tipo, personal, hoy):
    dialogo = DialogoAusencia(tipo, personal, hoy, parent)
    return dialogo.datos if dialogo.exec() == QDialog.DialogCode.Accepted else None


def confirmar(parent, titulo, texto):
    return QMessageBox.question(parent, titulo, texto) == QMessageBox.StandardButton.Yes


class JornadasPage(QWidget):
    def __init__(self, sesion, servicio=None, hoy=date.today, pedir=None, confirmar_accion=None):
        super().__init__()
        self._pedir = pedir or pedir_ausencia
        self._confirmar = confirmar_accion or confirmar
        self._personal = []
        self._ausencias = []
        if servicio is None:
            from services.fichajes_service import FichajesService
            servicio = FichajesService()
        self.sesion, self.servicio = sesion, servicio
        self._hoy = hoy
        self._jornadas = []
        self.elegida = None

        # --- Cargar turnos ---
        self.empleado = QComboBox()
        lunes = hoy() - timedelta(days=hoy().weekday())
        self.desde, self.hasta = QDateEdit(a_qdate(hoy())), QDateEdit(a_qdate(lunes + timedelta(days=6)))
        for campo in (self.desde, self.hasta):
            campo.setCalendarPopup(True)
            campo.setDisplayFormat("dd/MM/yyyy")
        self.dias = {}
        fila_dias = QWidget()
        fila_d = QHBoxLayout(fila_dias)
        fila_d.setContentsMargins(0, 0, 0, 0)
        for numero, nombre in DIAS_CORTOS.items():
            caja = QCheckBox(nombre)
            caja.setChecked(numero <= 5)
            self.dias[numero] = caja
            fila_d.addWidget(caja)
        fila_d.addStretch()
        self.entrada, self.salida = _editor_hora(14, 0), _editor_hora(22, 0)
        self.estado = QComboBox()
        for clave, texto in ESTADOS_JORNADA.items():
            self.estado.addItem(texto, clave)
        self.campos = {"empleado": CampoFormulario("Empleado", self.empleado),
                       "desde": CampoFormulario("Desde", self.desde),
                       "hasta": CampoFormulario("Hasta", self.hasta),
                       "fechas": CampoFormulario("Días", fila_dias),
                       "entrada": CampoFormulario("Entrada", self.entrada),
                       "salida": CampoFormulario("Salida", self.salida),
                       "estado": CampoFormulario("Tipo", self.estado)}
        cargar = con_rol(QPushButton("Cargar turnos"), "primario")
        cargar.clicked.connect(self.cargar_turnos)
        self.mensaje = etiqueta("", "ok")
        self.mensaje.setWordWrap(True)
        self.mensaje.hide()
        fila1, fila2 = QHBoxLayout(), QHBoxLayout()
        for clave in ("empleado", "desde", "hasta"):
            fila1.addWidget(self.campos[clave], 1)
        for clave in ("entrada", "salida", "estado"):
            fila2.addWidget(self.campos[clave], 1)
        alta = con_rol(QFrame(), "panel")
        columna_a = QVBoxLayout(alta)
        columna_a.setContentsMargins(24, 20, 24, 20)
        columna_a.setSpacing(12)
        columna_a.addWidget(etiqueta("Cargar turnos", "titulo-panel"))
        columna_a.addLayout(fila1)
        columna_a.addWidget(self.campos["fechas"])
        columna_a.addLayout(fila2)
        pie = QHBoxLayout()
        pie.addWidget(self.mensaje, 1)
        pie.addWidget(cargar)
        columna_a.addLayout(pie)

        # --- Turnos de la semana y cambios ---
        self.tabla = crear_tabla(("Fecha", "Empleado", "Turno", "Tipo"), estirar=1, seleccion=True)
        self.tabla.itemSelectionChanged.connect(self._elegida)
        self.tabla.setMinimumHeight(200)
        self.vacio = etiqueta("No hay turnos cargados en esas fechas.", "secundario")
        self.cambio_entrada, self.cambio_salida = _editor_hora(14, 0), _editor_hora(22, 0)
        self.cambio_estado = QComboBox()
        for clave, texto in ESTADOS_JORNADA.items():
            self.cambio_estado.addItem(texto, clave)
        self.motivo = QLineEdit()
        self.motivo.setPlaceholderText("Por ejemplo: cambio de turno del sábado")
        self.campos_cambio = {"entrada": CampoFormulario("Entrada", self.cambio_entrada),
                              "salida": CampoFormulario("Salida", self.cambio_salida),
                              "estado": CampoFormulario("Tipo", self.cambio_estado),
                              "motivo": CampoFormulario("Motivo (opcional)", self.motivo)}
        guardar = QPushButton("Guardar cambio")
        guardar.clicked.connect(self.cambiar_turno)
        self.titulo_cambio = etiqueta("Elegí un turno de la lista para cambiarlo.", "secundario")
        fila3 = QHBoxLayout()
        for campo in self.campos_cambio.values():
            fila3.addWidget(campo, 1)
        fila3.addWidget(guardar)
        lista = con_rol(QFrame(), "panel")
        columna_l = QVBoxLayout(lista)
        columna_l.setContentsMargins(24, 20, 24, 20)
        columna_l.setSpacing(12)
        columna_l.addWidget(etiqueta("Turnos cargados", "titulo-panel"))
        columna_l.addWidget(self.vacio)
        columna_l.addWidget(self.tabla, 1)
        columna_l.addWidget(self.titulo_cambio)
        columna_l.addLayout(fila3)

        # --- Licencias y permisos ---
        dar_licencia = con_rol(QPushButton("Dar licencia"), "primario")
        dar_licencia.clicked.connect(lambda: self.dar_ausencia("licencia"))
        dar_permiso = con_rol(QPushButton("Dar permiso"), "primario")
        dar_permiso.clicked.connect(lambda: self.dar_ausencia("permiso"))
        self.mensaje_ausencias = etiqueta("", "ok")
        self.mensaje_ausencias.setWordWrap(True)
        self.mensaje_ausencias.hide()
        self.tabla_ausencias = crear_tabla(("Empleado", "Tipo", "Fechas", "Horario", "Aprobó", "Aprobado el",
                                            "Motivo", ""), estirar=6)
        self.tabla_ausencias.setMinimumHeight(180)
        self.sin_ausencias = etiqueta("No hay licencias ni permisos cargados.", "secundario")
        encabezado = QHBoxLayout()
        encabezado.addWidget(etiqueta("Licencias y permisos", "titulo-panel"))
        encabezado.addStretch()
        encabezado.addWidget(dar_licencia)
        encabezado.addWidget(dar_permiso)
        ausencias = con_rol(QFrame(), "panel")
        columna_au = QVBoxLayout(ausencias)
        columna_au.setContentsMargins(24, 20, 24, 20)
        columna_au.setSpacing(12)
        columna_au.addLayout(encabezado)
        columna_au.addWidget(self.mensaje_ausencias)
        columna_au.addWidget(self.sin_ausencias)
        columna_au.addWidget(self.tabla_ausencias)

        contenido = QWidget()
        columna = QVBoxLayout(contenido)
        columna.setContentsMargins(0, 0, 0, 0)
        columna.setSpacing(16)
        columna.addWidget(alta)
        columna.addWidget(ausencias)
        columna.addWidget(lista, 1)
        desplazable = QScrollArea()
        desplazable.setWidgetResizable(True)
        desplazable.setFrameShape(QFrame.Shape.NoFrame)
        desplazable.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        desplazable.setWidget(contenido)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(desplazable)
        self._personal_cargado = False

    def showEvent(self, evento):
        super().showEvent(evento)
        if not self._personal_cargado:
            self.cargar_personal()
        self.cargar_lista()
        self.cargar_ausencias()

    def cargar_personal(self):
        self.empleado.clear()
        self.empleado.addItem("Elegí el empleado", None)
        try:
            self._personal = list(self.servicio.personal(self.sesion))
            for usuario_id, nombre in self._personal:
                self.empleado.addItem(nombre, usuario_id)
        except Exception as error:
            self._avisar(f"No se pudo consultar el personal. {error}", "error")
            return
        self._personal_cargado = True

    def _fechas(self):
        dias = {n for n, caja in self.dias.items() if caja.isChecked()}
        return fechas_entre(a_fecha(self.desde), a_fecha(self.hasta), dias)

    def cargar_turnos(self):
        self.mensaje.hide()
        fechas = self._fechas()
        datos = (self.empleado.currentData(), fechas, _hora(self.entrada), _hora(self.salida),
                 self.estado.currentData())
        errores = validar_jornada(*datos[2:], fechas, [])
        if datos[0] is None:
            errores["empleado"] = "Elegí el empleado."
        if not errores:
            try:
                cantidad = self.servicio.cargar_turnos(self.sesion, *datos)
            except ErroresJornada as error:
                errores = error.errores
            except Exception as error:
                self._avisar(f"No se pudieron cargar los turnos. {error}", "error")
                return
        for nombre, campo in self.campos.items():
            campo.mostrar_error(errores[nombre]) if nombre in errores else campo.limpiar_error()
        if errores:
            return
        self._avisar(f"Se cargaron {cantidad} turnos de {self.empleado.currentText()}." if cantidad != 1
                     else f"Se cargó 1 turno de {self.empleado.currentText()}.", "ok")
        self.cargar_lista()

    def cargar_lista(self):
        desde, hasta = a_fecha(self.desde), a_fecha(self.hasta)
        try:
            self._jornadas = list(self.servicio.jornadas(self.sesion, min(desde, hasta), max(desde, hasta)))
        except Exception as error:
            self._avisar(f"No se pudieron consultar los turnos. {error}", "error")
            return
        self.tabla.blockSignals(True)
        llenar(self.tabla, [[f"{DIAS_CORTOS[j[4].isoweekday()]} {fecha_texto(j[4])}", f"{j[2]} {j[3]}",
                             texto_horario(j[5], j[6]),
                             EtiquetaEstado(ESTADOS_JORNADA.get(j[7], j[7]), "verde" if j[7] == "jornada" else "neutro")]
                            for j in self._jornadas])
        self.tabla.blockSignals(False)
        self.vacio.setVisible(not self._jornadas)
        self.tabla.setVisible(bool(self._jornadas))
        self.elegida = None

    def _elegida(self):
        filas = self.tabla.selectionModel().selectedRows()
        if not filas:
            return
        jornada = self._jornadas[filas[0].row()]
        self.elegida = jornada[0]
        self.titulo_cambio.setText(f"Cambiar el turno de {jornada[2]} {jornada[3]} del {fecha_texto(jornada[4])}:")
        self.cambio_entrada.setTime(QTime(jornada[5].hour, jornada[5].minute))
        self.cambio_salida.setTime(QTime(jornada[6].hour, jornada[6].minute))
        self.cambio_estado.setCurrentIndex(self.cambio_estado.findData(jornada[7]))

    def cambiar_turno(self):
        if self.elegida is None:
            self._avisar("Elegí un turno de la lista.", "error")
            return
        try:
            self.servicio.cambiar_turno(self.sesion, self.elegida, _hora(self.cambio_entrada),
                                        _hora(self.cambio_salida), self.cambio_estado.currentData(),
                                        self.motivo.text().strip())
        except ErroresJornada as error:
            for nombre, campo in self.campos_cambio.items():
                campo.mostrar_error(error.errores[nombre]) if nombre in error.errores else campo.limpiar_error()
            return
        except Exception as error:
            self._avisar(f"No se pudo cambiar el turno. {error}", "error")
            return
        for campo in self.campos_cambio.values():
            campo.limpiar_error()
        self.motivo.clear()
        self._avisar("Turno cambiado. El horario anterior queda en el historial.", "ok")
        self.cargar_lista()

    # --- Licencias y permisos ---

    def cargar_ausencias(self):
        hoy = self._hoy()
        try:
            self._ausencias = list(self.servicio.ausencias(self.sesion, hoy - timedelta(days=60),
                                                           hoy + timedelta(days=366)))
        except Exception as error:
            self._avisar_ausencias(f"No se pudieron consultar las licencias y permisos. {error}", "error")
            return
        filas = []
        for lote in self._ausencias:
            fechas = fecha_texto(lote["desde"]) if lote["desde"] == lote["hasta"] else \
                f"{fecha_texto(lote['desde'])} al {fecha_texto(lote['hasta'])}"
            aprobado = (f"{fecha_texto(lote['aprobado_en'])} {hora_texto(lote['aprobado_en'])}"
                        if lote["aprobado_en"] else "—")
            boton = QPushButton("Anular")
            boton.setMinimumHeight(34)
            boton.clicked.connect(lambda _c=False, l=lote: self.anular(l))
            filas.append([lote["empleado"], lote["tipo"], fechas, lote["horario"], lote["aprobado_por"],
                          aprobado, lote["motivo"] or "—", boton])
        llenar(self.tabla_ausencias, filas)
        self.sin_ausencias.setVisible(not filas)
        self.tabla_ausencias.setVisible(bool(filas))

    def dar_ausencia(self, tipo):
        self.mensaje_ausencias.hide()
        datos = self._pedir(self, tipo, self._personal, self._hoy())
        if not datos:
            return
        try:
            if tipo == "licencia":
                dias = self.servicio.dar_licencia(self.sesion, datos["usuario_id"], datos["desde"],
                                                  datos["hasta"], datos["motivo"])
                texto = (f"Licencia aprobada para {datos['empleado']}: "
                         + ("1 día." if dias == 1 else f"{dias} días."))
            else:
                horas = datos["horas"] or (None, None)
                self.servicio.dar_permiso(self.sesion, datos["usuario_id"], datos["desde"], *horas,
                                          motivo=datos["motivo"])
                cuando = (f"de {hora_texto(horas[0])} a {hora_texto(horas[1])}" if datos["horas"]
                          else "todo el día")
                texto = f"Permiso aprobado para {datos['empleado']} el {fecha_texto(datos['desde'])}, {cuando}."
        except ErroresJornada as error:
            self._avisar_ausencias(" ".join(error.errores.values()), "error")
            return
        except Exception as error:
            self._avisar_ausencias(f"No se pudo aprobar. {error}", "error")
            return
        self._avisar_ausencias(texto, "ok")
        self.cargar_ausencias()
        self.cargar_lista()

    def anular(self, lote):
        tipo = lote["tipo"].lower()
        if not self._confirmar(self, f"Anular {tipo}",
                               f"¿Anular la {tipo} de {lote['empleado']}? Vuelve a tener sus turnos "
                               "y queda registrado en el historial."):
            return
        try:
            self.servicio.anular(self.sesion, lote["jornada_id"])
        except Exception as error:
            self._avisar_ausencias(f"No se pudo anular. {error}", "error")
            return
        self._avisar_ausencias(f"Se anuló la {tipo} de {lote['empleado']}.", "ok")
        self.cargar_ausencias()
        self.cargar_lista()

    def _avisar_ausencias(self, texto, rol):
        self.mensaje_ausencias.setText(texto)
        self.mensaje_ausencias.setProperty("rol", rol)
        tema.refrescar_estilo(self.mensaje_ausencias)
        self.mensaje_ausencias.show()

    def _avisar(self, texto, rol):
        self.mensaje.setText(texto)
        self.mensaje.setProperty("rol", rol)
        tema.refrescar_estilo(self.mensaje)
        self.mensaje.show()
