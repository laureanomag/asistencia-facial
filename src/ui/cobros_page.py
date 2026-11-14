"""Cobros y renovaciones: buscar al socio por DNI, venderle o renovarle un
plan (con pago total o parcial) y cobrar el saldo pendiente."""
from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QFrame, QGridLayout, QHBoxLayout, QLineEdit, QPushButton, QScrollArea, QVBoxLayout,
    QWidget,
)

from services.cobro_service import METODOS, ReglaDeCobro, descuento_por_cambio, validar_cobro
from services.persona_service import DatosInvalidos
from services.reglas_ingreso import fecha_texto, hora_texto, pesos
from ui import tema
from ui.componentes import CampoFormulario, EtiquetaEstado, con_rol, etiqueta
from ui.estados import estado_contable, estado_membresia
from ui.tablas import crear_tabla, llenar


def _combo_metodos():
    combo = QComboBox()
    combo.addItem("Elegí cómo paga", None)
    for clave, texto in METODOS.items():
        combo.addItem(texto, clave)
    return combo


def _monto_texto(valor):
    return pesos(valor).replace("$", "")


class CobrosPage(QWidget):
    def __init__(self, sesion, servicio=None):
        super().__init__()
        if servicio is None:
            from services.cobro_service import CobroService
            servicio = CobroService()
        self.sesion, self.servicio = sesion, servicio
        self.socio = None
        self._planes = []

        # --- Buscar socio ---
        self.dni = QLineEdit()
        self.dni.setPlaceholderText("DNI del socio")
        self.dni.returnPressed.connect(self.buscar)
        buscar = con_rol(QPushButton("Buscar"), "primario")
        buscar.clicked.connect(self.buscar)
        fila_dni = QHBoxLayout()
        fila_dni.addWidget(self.dni, 1)
        fila_dni.addWidget(buscar)
        self.campo_dni = CampoFormulario("Socio", QWidget())
        self.campo_dni.campo.setLayout(fila_dni)
        self.campo_dni.campo.layout().setContentsMargins(0, 0, 0, 0)
        self.ficha = etiqueta("", "titulo-panel")
        self.ficha.setWordWrap(True)
        self.detalle = etiqueta("", "secundario")
        self.detalle.setWordWrap(True)
        self.chips = QHBoxLayout()
        self.chips.setSpacing(8)

        # --- Vender o renovar ---
        self.plan = QComboBox()
        self.plan.currentIndexChanged.connect(self._plan_elegido)
        self.monto = QLineEdit()
        self.monto.setPlaceholderText("Monto que paga hoy")
        self.metodo = _combo_metodos()
        self.campos = {"plan": CampoFormulario("Plan", self.plan),
                       "monto": CampoFormulario("Monto", self.monto,
                                                "Puede pagar una parte: el resto queda como saldo."),
                       "metodo": CampoFormulario("Medio de pago", self.metodo)}
        self.periodo = etiqueta("", "secundario")
        self.periodo.setWordWrap(True)
        self.cobrar_boton = con_rol(QPushButton("Cobrar"), "primario")
        self.cobrar_boton.clicked.connect(self.cobrar)
        venta = con_rol(QFrame(), "panel")
        grilla = QGridLayout(venta)
        grilla.setContentsMargins(24, 20, 24, 20)
        grilla.setHorizontalSpacing(16)
        grilla.setVerticalSpacing(12)
        grilla.addWidget(etiqueta("Vender o renovar un plan", "titulo-panel"), 0, 0, 1, 2)
        grilla.addWidget(self.campos["plan"], 1, 0, 1, 2)
        grilla.addWidget(self.periodo, 2, 0, 1, 2)
        grilla.addWidget(self.campos["monto"], 3, 0)
        grilla.addWidget(self.campos["metodo"], 3, 1)
        grilla.addWidget(self.cobrar_boton, 4, 1)
        grilla.setColumnStretch(0, 1)
        grilla.setColumnStretch(1, 1)
        self.venta = venta

        # --- Saldo pendiente ---
        self.saldo_texto = etiqueta("", "secundario")
        self.saldo_texto.setWordWrap(True)
        self.saldo_monto = QLineEdit()
        self.saldo_metodo = _combo_metodos()
        self.campos_saldo = {"monto": CampoFormulario("Monto", self.saldo_monto),
                             "metodo": CampoFormulario("Medio de pago", self.saldo_metodo)}
        self.cobrar_saldo_boton = QPushButton("Cobrar saldo")
        self.cobrar_saldo_boton.clicked.connect(self.cobrar_saldo)
        saldo = con_rol(QFrame(), "panel")
        grilla_s = QGridLayout(saldo)
        grilla_s.setContentsMargins(24, 20, 24, 20)
        grilla_s.setHorizontalSpacing(16)
        grilla_s.setVerticalSpacing(12)
        grilla_s.addWidget(etiqueta("Saldo pendiente", "titulo-panel"), 0, 0, 1, 2)
        grilla_s.addWidget(self.saldo_texto, 1, 0, 1, 2)
        grilla_s.addWidget(self.campos_saldo["monto"], 2, 0)
        grilla_s.addWidget(self.campos_saldo["metodo"], 2, 1)
        grilla_s.addWidget(self.cobrar_saldo_boton, 3, 1)
        grilla_s.setColumnStretch(0, 1)
        grilla_s.setColumnStretch(1, 1)
        self.saldo = saldo

        self.resultado = etiqueta("", "ok")
        self.resultado.setWordWrap(True)
        self.resultado.hide()
        self.pagos = crear_tabla(("Fecha", "Plan", "Monto", "Medio"), estirar=1)
        self.pagos.setMinimumHeight(220)

        ficha = con_rol(QFrame(), "panel")
        columna_f = QVBoxLayout(ficha)
        columna_f.setContentsMargins(24, 20, 24, 20)
        columna_f.setSpacing(10)
        columna_f.addWidget(self.campo_dni)
        columna_f.addWidget(self.ficha)
        columna_f.addWidget(self.detalle)
        columna_f.addLayout(self.chips)
        historial = con_rol(QFrame(), "panel")
        columna_h = QVBoxLayout(historial)
        columna_h.setContentsMargins(20, 20, 20, 20)
        columna_h.addWidget(etiqueta("Últimos pagos", "titulo-panel"))
        columna_h.addWidget(self.pagos, 1)
        self.historial = historial

        contenido = QWidget()
        columna = QVBoxLayout(contenido)
        columna.setContentsMargins(0, 0, 0, 0)
        columna.setSpacing(16)
        columna.addWidget(ficha)
        columna.addWidget(self.resultado)
        columna.addWidget(venta)
        columna.addWidget(saldo)
        columna.addWidget(historial)
        columna.addStretch()
        desplazable = QScrollArea()
        desplazable.setWidgetResizable(True)
        desplazable.setFrameShape(QFrame.Shape.NoFrame)
        desplazable.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        desplazable.setWidget(contenido)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(desplazable)
        self._mostrar_socio(None)

    # --- Búsqueda ---

    def buscar(self):
        self.resultado.hide()
        self.campo_dni.limpiar_error()
        try:
            socio = self.servicio.buscar_socio(self.sesion, self.dni.text())
        except DatosInvalidos as error:
            self.campo_dni.mostrar_error(str(error))
            return self._mostrar_socio(None)
        except Exception as error:
            self.campo_dni.mostrar_error(f"No se pudo consultar la base de datos. {error}")
            return self._mostrar_socio(None)
        if socio is None:
            self.campo_dni.mostrar_error("No hay ningún socio con ese DNI. Registralo en Socios.")
        elif not socio["activo"]:
            self.campo_dni.mostrar_error("El socio está dado de baja: la dueña puede reactivarlo "
                                         "en Estado del socio.")
        self._mostrar_socio(socio)

    def _mostrar_socio(self, socio):
        self.socio = socio
        while self.chips.count():
            item = self.chips.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        activo = bool(socio and socio["activo"])
        self.ficha.setVisible(socio is not None)
        self.detalle.setVisible(socio is not None)
        for panel in (self.venta, self.historial):
            panel.setVisible(activo)
        self.saldo.hide()
        if socio is None:
            return
        estado = socio["estado"] or {}
        self.ficha.setText(socio["nombre"])
        if estado.get("plan"):
            self.detalle.setText(f"{estado['plan']} · vence el {fecha_texto(estado['fecha_vencimiento'])}")
        else:
            self.detalle.setText("Todavía no tiene ningún plan.")
        self.chips.addWidget(EtiquetaEstado(*estado_membresia(estado.get("estado_membresia"), socio["activo"])))
        self.chips.addWidget(EtiquetaEstado(*estado_contable(estado.get("estado_contable"), socio["activo"])))
        self.chips.addStretch()
        if not activo:
            return
        self._cargar_planes()
        llenar(self.pagos, [[f"{fecha_texto(f)} {hora_texto(f)}", plan, pesos(monto), METODOS.get(metodo, metodo)]
                            for f, monto, metodo, plan, _mid in socio["pagos"]])
        deuda = next(((m[0], m[1], Decimal(m[4]) - Decimal(m[6])) for m in socio["membresias"]
                      if m[5] != "cancelada" and Decimal(m[4]) - Decimal(m[6]) > 0), None)
        self._deuda = deuda
        if deuda:
            self.saldo_texto.setText(f"Debe {pesos(deuda[2])} de {deuda[1]}.")
            self.saldo_monto.setText(_monto_texto(deuda[2]))
            self.saldo.show()

    def _cargar_planes(self):
        try:
            self._planes = list(self.servicio.planes(self.sesion))
        except Exception as error:
            self.campos["plan"].mostrar_error(f"No se pudieron consultar los planes. {error}")
            self._planes = []
        self.plan.blockSignals(True)
        self.plan.clear()
        self.plan.addItem("Elegí un plan", None)
        for plan in self._planes:
            precio = Decimal(plan[6])
            self.plan.addItem(f"{plan[1]} · {pesos(precio) if precio > 0 else 'sin precio'}", plan[0])
        actual = (self.socio["estado"] or {}).get("plan")
        indice = next((i + 1 for i, p in enumerate(self._planes) if p[1] == actual and Decimal(p[6]) > 0), 0)
        self.plan.setCurrentIndex(indice)
        self.plan.blockSignals(False)
        self._plan_elegido()

    def _plan_actual(self):
        return next((p for p in self._planes if p[0] == self.plan.currentData()), None)

    def _a_cobrar(self, plan):
        """(precio a cobrar, descuento) del plan elegido para este socio."""
        descuento = descuento_por_cambio(self.socio["membresias"], plan, self.socio["inicio_nueva"])
        return Decimal(plan[6]) - descuento, descuento

    def _plan_elegido(self, *_):
        plan = self._plan_actual()
        self.campos["plan"].limpiar_error()
        self.periodo.setText("")
        if plan is None or self.socio is None:
            return
        if Decimal(plan[6]) <= 0:
            errores, _ = validar_cobro(plan, "1", "efectivo")
            self.campos["plan"].mostrar_error(errores["plan"])
            self.cobrar_boton.setEnabled(False)
            return
        self.cobrar_boton.setEnabled(True)
        a_cobrar, descuento = self._a_cobrar(plan)
        self.monto.setText(_monto_texto(a_cobrar))
        inicio = self.socio["inicio_nueva"]
        try:
            vence = self.servicio.vencimiento(plan[0], inicio)
        except Exception:
            vence = None
        texto = f"Empieza hoy, {fecha_texto(inicio)}"
        if vence:
            texto += f", y vence el {fecha_texto(vence)} (ese día ya tiene que renovar)"
        if (self.socio["estado"] or {}).get("estado_membresia") in ("vigente", "agotada", "no_vigente"):
            texto += ". Reemplaza al plan actual desde hoy"
        texto += "."
        if descuento:
            texto += (f" Precio {pesos(plan[6])} − Pase por día de hoy {pesos(descuento)} = "
                      f"{pesos(a_cobrar)}.")
        self.periodo.setText(texto)

    # --- Cobros ---

    def cobrar(self):
        self.resultado.hide()
        plan = self._plan_actual()
        maximo = self._a_cobrar(plan)[0] if plan is not None and self.socio is not None else None
        errores, monto = validar_cobro(plan, self.monto.text(), self.metodo.currentData(), maximo=maximo)
        for nombre, campo in self.campos.items():
            campo.mostrar_error(errores[nombre]) if nombre in errores else campo.limpiar_error()
        if errores or self.socio is None:
            return
        try:
            venta = self.servicio.vender(self.sesion, self.socio["socio_id"], plan[0], monto,
                                         self.metodo.currentData())
        except ReglaDeCobro as error:
            return self._mostrar_resultado(str(error), "error")
        except Exception as error:
            return self._mostrar_resultado(f"No se pudo cobrar. {error}", "error")
        texto = (f"Listo: {venta.plan} del {fecha_texto(venta.fecha_inicio)} al "
                 f"{fecha_texto(venta.fecha_vencimiento)}. Pagó {pesos(venta.pagado)}.")
        if venta.descuento:
            texto += f" Se descontaron {pesos(venta.descuento)} del Pase por día de hoy, que quedó cerrado."
        if venta.saldo > 0:
            texto += f" Queda debiendo {pesos(venta.saldo)}."
        self._refrescar(texto)

    def cobrar_saldo(self):
        self.resultado.hide()
        if self.socio is None or not self._deuda:
            return
        membresia_id, plan, saldo = self._deuda
        errores, monto = validar_cobro((None, plan, None, None, None, None, saldo, True),
                                       self.saldo_monto.text(), self.saldo_metodo.currentData(), maximo=saldo)
        for nombre, campo in self.campos_saldo.items():
            campo.mostrar_error(errores[nombre]) if nombre in errores else campo.limpiar_error()
        if errores:
            return
        try:
            resta = self.servicio.pagar_saldo(self.sesion, self.socio["socio_id"], membresia_id, monto,
                                              self.saldo_metodo.currentData())
        except ReglaDeCobro as error:
            return self._mostrar_resultado(str(error), "error")
        except Exception as error:
            return self._mostrar_resultado(f"No se pudo cobrar el saldo. {error}", "error")
        self._refrescar(f"Pagó {pesos(monto)}. " + (f"Todavía debe {pesos(resta)}." if resta > 0
                                                    else "La membresía quedó paga."))

    def _refrescar(self, texto):
        self.metodo.setCurrentIndex(0)
        self.saldo_metodo.setCurrentIndex(0)
        try:
            self._mostrar_socio(self.servicio.buscar_socio(self.sesion, self.dni.text()))
        except Exception:
            pass
        self._mostrar_resultado(texto, "ok")

    def _mostrar_resultado(self, texto, rol):
        self.resultado.setText(texto)
        self.resultado.setProperty("rol", rol)
        tema.refrescar_estilo(self.resultado)
        self.resultado.show()
