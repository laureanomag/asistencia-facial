"""Estado del socio: buscar por DNI o nombre y ver su membresía actual
(plan, vigencia, accesos usados y restantes, días de la semana, saldo),
el historial de membresías, los pagos y los últimos ingresos.
La dueña también da de baja o reactiva al socio."""
from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLineEdit, QMessageBox, QPushButton, QScrollArea, QVBoxLayout,
    QWidget,
)

from services.cobro_service import METODOS
from services.reglas_ingreso import ETIQUETAS_MOTIVO, fecha_texto, hora_texto, pesos
from ui import tema
from ui.componentes import EtiquetaEstado, con_rol, etiqueta
from ui.estados import dni_con_puntos, estado_contable, estado_membresia
from ui.tablas import crear_tabla, llenar

# 'cancelada' es como queda la membresía anterior al vender un plan nuevo.
ESTADO_MEMBRESIA_GUARDADO = {"activa": "Activa", "suspendida": "Suspendida", "cancelada": "Cerrada"}


def confirmar(parent, titulo, texto):
    return QMessageBox.question(parent, titulo, texto) == QMessageBox.StandardButton.Yes


def datos_membresia(estado):
    """[(título, valor)] de la membresía actual para las tarjetas."""
    if not estado or not estado.get("membresia_id"):
        return []
    incluidos = estado.get("accesos_incluidos")
    accesos = (f"{estado['accesos_usados']} de {incluidos} (quedan {max(0, estado['accesos_restantes'])})"
               if incluidos else f"{estado['accesos_usados']} (sin cupo)")
    maximo = estado.get("max_dias_semanales")
    semana = f"{estado['dias_entrenados_semana']} de {maximo} días" if maximo \
        else f"{estado['dias_entrenados_semana']} días (sin límite)"
    diarios = estado.get("max_ingresos_diarios")
    hoy = f"{estado['accesos_hoy']} de {diarios}" if diarios else f"{estado['accesos_hoy']} (sin límite)"
    dias = estado.get("dias_para_vencer")
    vence = fecha_texto(estado["fecha_vencimiento"])
    if dias is not None and dias > 0:
        vence += " · mañana" if dias == 1 else f" · en {dias} días"
    ultimo = estado.get("ultimo_pago")
    return [("Plan", estado["plan"]), ("Desde", fecha_texto(estado["fecha_inicio"])), ("Vence", vence),
            ("Accesos usados", accesos), ("Esta semana", semana), ("Hoy", hoy),
            ("Precio", pesos(estado["precio"])), ("Pagado", pesos(estado["pagado"])),
            ("Saldo", pesos(max(Decimal(estado["saldo"]), Decimal(0)))),
            ("Último pago", fecha_texto(ultimo) if ultimo else "—")]


class EstadoSocioPage(QWidget):
    def __init__(self, sesion, servicio=None, confirmar_accion=None):
        super().__init__()
        if servicio is None:
            from services.estado_socio_service import EstadoSocioService
            servicio = EstadoSocioService()
        self.sesion, self.servicio = sesion, servicio
        self._confirmar = confirmar_accion or confirmar
        self.ficha_actual = None
        self._resultados = []

        # --- Búsqueda ---
        self.busqueda = QLineEdit()
        self.busqueda.setPlaceholderText("DNI, nombre o apellido")
        self.busqueda.returnPressed.connect(self.buscar)
        buscar = con_rol(QPushButton("Buscar"), "primario")
        buscar.clicked.connect(self.buscar)
        fila_b = QHBoxLayout()
        fila_b.addWidget(self.busqueda, 1)
        fila_b.addWidget(buscar)
        self.lista = crear_tabla(("Socio", "DNI"), seleccion=True)
        self.lista.itemSelectionChanged.connect(self._elegido)
        self.aviso_lista = etiqueta("Buscá a un socio para ver su estado.", "secundario")
        self.aviso_lista.setWordWrap(True)
        izquierda = con_rol(QFrame(), "panel")
        columna_i = QVBoxLayout(izquierda)
        columna_i.setContentsMargins(20, 20, 20, 20)
        columna_i.setSpacing(12)
        columna_i.addWidget(etiqueta("Buscar socio", "titulo-panel"))
        columna_i.addLayout(fila_b)
        columna_i.addWidget(self.aviso_lista)
        columna_i.addWidget(self.lista, 1)
        izquierda.setMinimumWidth(300)
        izquierda.setMaximumWidth(380)

        # --- Ficha ---
        self.nombre = etiqueta("", "titulo-panel")
        self.nombre.setWordWrap(True)
        self.detalle = etiqueta("", "secundario")
        self.detalle.setWordWrap(True)
        self.chips = QHBoxLayout()
        self.chips.setSpacing(8)
        self.boton_estado = QPushButton()
        self.boton_estado.clicked.connect(self.cambiar_estado)
        encabezado = QHBoxLayout()
        textos = QVBoxLayout()
        textos.addWidget(self.nombre)
        textos.addWidget(self.detalle)
        textos.addLayout(self.chips)
        encabezado.addLayout(textos, 1)
        encabezado.addWidget(self.boton_estado, 0, Qt.AlignmentFlag.AlignTop)
        self.resultado = etiqueta("", "ok")
        self.resultado.setWordWrap(True)
        self.resultado.hide()
        self.datos = QGridLayout()
        self.datos.setHorizontalSpacing(12)
        self.datos.setVerticalSpacing(12)
        self.sin_membresia = etiqueta("", "secundario")
        self.sin_membresia.setWordWrap(True)
        self.membresias = crear_tabla(("Plan", "Desde", "Vence", "Precio", "Pagado", "Estado"))
        self.pagos = crear_tabla(("Fecha", "Plan", "Monto", "Medio"), estirar=1)
        self.accesos = crear_tabla(("Fecha", "Resultado"), estirar=1)
        for tabla in (self.membresias, self.pagos, self.accesos):
            tabla.setMinimumHeight(200)

        ficha = QWidget()
        columna_f = QVBoxLayout(ficha)
        columna_f.setContentsMargins(0, 0, 0, 0)
        columna_f.setSpacing(16)
        cabecera = con_rol(QFrame(), "panel")
        columna_c = QVBoxLayout(cabecera)
        columna_c.setContentsMargins(24, 20, 24, 20)
        columna_c.setSpacing(14)
        columna_c.addLayout(encabezado)
        columna_c.addWidget(self.resultado)
        columna_c.addWidget(self.sin_membresia)
        columna_c.addLayout(self.datos)
        columna_f.addWidget(cabecera)
        for titulo, tabla in (("Membresías", self.membresias), ("Pagos", self.pagos),
                              ("Últimos ingresos", self.accesos)):
            caja = con_rol(QFrame(), "panel")
            columna_t = QVBoxLayout(caja)
            columna_t.setContentsMargins(20, 18, 20, 18)
            columna_t.addWidget(etiqueta(titulo, "titulo-panel"))
            columna_t.addWidget(tabla)
            columna_f.addWidget(caja)
        columna_f.addStretch()
        self.ficha = ficha
        desplazable = QScrollArea()
        desplazable.setWidgetResizable(True)
        desplazable.setFrameShape(QFrame.Shape.NoFrame)
        desplazable.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        desplazable.setWidget(ficha)

        fila = QHBoxLayout(self)
        fila.setContentsMargins(0, 0, 0, 0)
        fila.setSpacing(20)
        fila.addWidget(izquierda, 1)
        fila.addWidget(desplazable, 2)
        self.ficha.hide()

    def showEvent(self, evento):
        super().showEvent(evento)
        if self.ficha_actual is not None:
            self.mostrar(self.ficha_actual["socio_id"])

    # --- Búsqueda ---

    def buscar(self):
        try:
            self._resultados = list(self.servicio.buscar(self.sesion, self.busqueda.text()))
        except Exception as error:
            self.aviso_lista.setText(f"No se pudo consultar los socios. {error}")
            self.aviso_lista.show()
            return
        self.aviso_lista.setText("No hay socios que coincidan con la búsqueda.")
        self.aviso_lista.setVisible(not self._resultados)
        self.lista.blockSignals(True)
        llenar(self.lista, [[f"{f[3]} {f[4]}", dni_con_puntos(f[2])] for f in self._resultados])
        self.lista.blockSignals(False)
        if len(self._resultados) == 1:
            self.lista.selectRow(0)

    def _elegido(self):
        filas = self.lista.selectionModel().selectedRows()
        if filas:
            self.mostrar(self._resultados[filas[0].row()][0])

    # --- Ficha ---

    def mostrar(self, socio_id):
        try:
            ficha = self.servicio.ficha(self.sesion, socio_id)
        except Exception as error:
            self.aviso_lista.setText(f"No se pudo consultar el socio. {error}")
            self.aviso_lista.show()
            return
        self.ficha_actual = ficha
        self.ficha.setVisible(ficha is not None)
        if ficha is None:
            return
        self.nombre.setText(ficha["nombre"])
        contacto = " ".join(p for p in (ficha["contacto_nombre"], ficha["contacto_telefono"]) if p)
        partes = [f"DNI {dni_con_puntos(ficha['dni'])}", f"Socio desde el {fecha_texto(ficha['fecha_alta'])}"]
        if ficha["celular"]:
            partes.append(f"Celular {ficha['celular']}")
        partes.append(f"Emergencias: {contacto}")
        if not ficha["activo"] and ficha["fecha_baja"]:
            partes.append(f"Baja el {fecha_texto(ficha['fecha_baja'])}")
        self.detalle.setText(" · ".join(partes))

        while self.chips.count():
            item = self.chips.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        estado = ficha["estado"] or {}
        self.chips.addWidget(EtiquetaEstado(*estado_membresia(estado.get("estado_membresia"), ficha["activo"])))
        if ficha["activo"]:
            self.chips.addWidget(EtiquetaEstado(*estado_contable(estado.get("estado_contable"))))
        self.chips.addStretch()

        puede = self.servicio.puede_dar_de_baja(self.sesion)
        self.boton_estado.setVisible(puede)
        self.boton_estado.setText("Dar de baja" if ficha["activo"] else "Reactivar")

        while self.datos.count():
            item = self.datos.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        datos = datos_membresia(estado) if ficha["activo"] else []
        for indice, (titulo, valor) in enumerate(datos):
            self.datos.addWidget(self._tarjeta(titulo, valor), indice // 4, indice % 4)
        self.sin_membresia.setVisible(not datos)
        self.sin_membresia.setText("Dado de baja: no puede entrar." if not ficha["activo"]
                                   else "Todavía no tiene ningún plan. Se cobra en Cobros y renovaciones.")

        llenar(self.membresias, [[m[1], fecha_texto(m[2]), fecha_texto(m[3]), pesos(m[4]), pesos(m[6]),
                                  ESTADO_MEMBRESIA_GUARDADO.get(m[5], m[5])] for m in ficha["membresias"]])
        llenar(self.pagos, [[f"{fecha_texto(f)} {hora_texto(f)}", plan, pesos(monto), METODOS.get(metodo, metodo)]
                            for f, monto, metodo, plan, _mid in ficha["pagos"]])
        llenar(self.accesos, [[f"{fecha_texto(f)} {hora_texto(f)}",
                               "Permitido" if resultado == "permitido" else ETIQUETAS_MOTIVO.get(motivo, "Rechazado")]
                              for f, resultado, motivo in ficha["accesos"]])

    @staticmethod
    def _tarjeta(titulo, valor):
        tarjeta = con_rol(QFrame(), "tarjeta-dato")
        interior = QVBoxLayout(tarjeta)
        interior.setContentsMargins(12, 10, 12, 10)
        interior.setSpacing(2)
        interior.addWidget(etiqueta(titulo, "dato-titulo"))
        interior.addWidget(etiqueta(valor, "dato-valor"))
        return tarjeta

    def cambiar_estado(self):
        ficha = self.ficha_actual
        if ficha is None:
            return
        if ficha["activo"]:
            pregunta = (f"¿Dar de baja a {ficha['nombre']}? No va a poder entrar. Sus datos, fotos, "
                        "membresías y pagos se conservan.")
            titulo, accion = "Dar de baja", self.servicio.dar_baja
        else:
            pregunta = f"¿Reactivar a {ficha['nombre']}? Va a poder volver a entrar si tiene un plan vigente."
            titulo, accion = "Reactivar", self.servicio.reactivar
        if not self._confirmar(self, titulo, pregunta):
            return
        try:
            accion(self.sesion, ficha["socio_id"])
        except Exception as error:
            self._mostrar_resultado(f"No se pudo {titulo.lower()}. {error}", "error")
            return
        self.mostrar(ficha["socio_id"])
        self._mostrar_resultado("Socio dado de baja." if ficha["activo"] else "Socio reactivado.", "ok")

    def _mostrar_resultado(self, texto, rol):
        self.resultado.setText(texto)
        self.resultado.setProperty("rol", rol)
        tema.refrescar_estilo(self.resultado)
        self.resultado.show()
