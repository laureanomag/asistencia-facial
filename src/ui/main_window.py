from dataclasses import dataclass

from PySide6.QtCore import QPoint, QTimer, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QButtonGroup, QDialog, QFrame, QHBoxLayout, QLabel, QMenu, QMessageBox, QPushButton,
    QStackedWidget, QVBoxLayout, QWidget,
)

from services import auth_service as auth
from services.horario_service import fecha_hora_titulo
from ui import iconos, tema
from ui.componentes import (
    Avatar, EncabezadoPagina, IndicadorApertura, Marca, con_rol, etiqueta, panel,
)

NOMBRES_ROL = {
    auth.ADMINISTRADOR: "Administrador",
    auth.RECEPCIONISTA: "Recepcionista",
    auth.ENTRENADOR: "Entrenador",
}


@dataclass(frozen=True)
class Seccion:
    clave: str
    menu: str
    icono: str
    permiso: str
    titulo: str
    subtitulo: str
    commit: int            # commit de la etapa 2 que completa la pantalla


SECCIONES = {s.clave: s for s in (
    Seccion("panel", "Panel", "panel", auth.REPORTE_CONSULTAR,
            "Panel", "Indicadores del día, la semana y el mes", 8),
    Seccion("acceso", "Control de acceso", "camara", auth.ACCESO_OPERAR_CAMARA,
            "Control de acceso", "Mirá a la cámara para ingresar", 7),
    Seccion("socios", "Socios", "socios", auth.SOCIO_REGISTRAR,
            "Socios", "Registro de socios: datos personales, 3 fotos y contacto de emergencia", 10),
    Seccion("cobros", "Cobros y\nrenovaciones", "cobros", auth.PAGO_REGISTRAR,
            "Cobros y renovaciones", "Alta y renovación de membresías con su pago", 11),
    Seccion("estado", "Estado del socio", "estado", auth.MEMBRESIA_CONSULTAR,
            "Estado del socio", "Plan, vencimiento, ingresos de la semana y pagos", 12),
    Seccion("empleados", "Empleados", "empleados", auth.USUARIO_ADMINISTRAR,
            "Empleados", "Cuentas del personal: entrenadores y recepcionistas", 9),
    Seccion("jornadas", "Jornadas", "jornadas", auth.JORNADA_GESTIONAR,
            "Jornadas", "Turnos de los entrenadores y sus cambios", 14),
    Seccion("fichajes", "Fichajes", "fichajes", auth.FICHAJE_CONSULTAR_PROPIO,
            "Fichajes", "Entradas y salidas del personal, por empleado y por fecha", 15),
    Seccion("informes", "Informes", "informes", auth.REPORTE_CONSULTAR,
            "Informes", "Ingresos y rechazos por socio", 16),
    Seccion("configuracion", "Configuración", "configuracion", auth.CONFIGURACION_GESTIONAR,
            "Configuración", "Planes, precios y horario de atención", 13),
)}

# Orden del menú. La dueña (administrador) no opera la cámara: su pantalla de
# inicio es el Panel. El personal (recepción y entrenadores) empieza en el
# Control de acceso. Cada opción se muestra solo si la cuenta tiene el permiso.
MENU_ADMINISTRADOR = ("panel", "informes", "estado", "empleados", "jornadas", "fichajes",
                      "configuracion")
MENU_PERSONAL = ("acceso", "socios", "cobros", "estado", "fichajes")


class BotonMenu(QPushButton):
    """Opción del menú lateral: ícono + texto (puede ocupar dos líneas).
    Al marcarse toma el fondo dorado y el ícono y el texto pasan a negro."""

    def __init__(self, texto, icono):
        super().__init__()
        con_rol(self, "menu")
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._icono_normal = iconos.pixmap(icono, "#E6E6E6")
        self._icono_activo = iconos.pixmap(icono, tema.FONDO)
        self._icono = QLabel()
        self._icono.setFixedSize(20, 20)
        self._texto = etiqueta(texto, "texto-menu")
        self._texto.setWordWrap(True)
        for hijo in (self._icono, self._texto):
            hijo.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        fila = QHBoxLayout(self)
        fila.setContentsMargins(14, 6, 10, 6)
        fila.setSpacing(14)
        fila.addWidget(self._icono)
        fila.addWidget(self._texto, 1)
        self.setMinimumHeight(62 if "\n" in texto else 44)
        self.toggled.connect(self._pintar)
        self._pintar(False)

    def texto(self):
        return self._texto.text().replace("\n", " ")

    def _pintar(self, activo):
        self._icono.setPixmap(self._icono_activo if activo else self._icono_normal)
        self._texto.setProperty("activo", activo)
        tema.refrescar_estilo(self._texto)


def secciones_permitidas(sesion):
    if sesion.tiene_rol(auth.ADMINISTRADOR):
        orden = MENU_ADMINISTRADOR
        if sesion.roles - {auth.ADMINISTRADOR}:      # además trabaja en recepción o entrena
            orden += tuple(c for c in MENU_PERSONAL if c not in MENU_ADMINISTRADOR)
    else:
        orden = MENU_PERSONAL
    return [SECCIONES[c] for c in orden if sesion.puede(SECCIONES[c].permiso)]


def texto_roles(roles):
    return " · ".join(NOMBRES_ROL[r] for r in auth.ROLES if r in roles)


class TarjetaUsuario(QFrame):
    """Avatar, nombre y rol abajo a la izquierda. Al hacer clic abre el menú
    de la cuenta (Cambiar contraseña / Cerrar sesión)."""

    clicked = Signal()

    def __init__(self, sesion):
        super().__init__()
        con_rol(self, "tarjeta-usuario")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setToolTip("Opciones de la cuenta")
        textos = QVBoxLayout()
        textos.setSpacing(0)
        self.nombre = QLabel(sesion.nombre_mostrado)
        self.nombre.setStyleSheet("font-weight: 700; background: transparent;")
        self.nombre.setWordWrap(True)         # nombres largos en dos líneas, sin cortarse
        self.rol = etiqueta(texto_roles(sesion.roles), "secundario")
        self.rol.setStyleSheet("background: transparent;")
        textos.addWidget(self.nombre)
        textos.addWidget(self.rol)
        flecha = QLabel()
        flecha.setPixmap(iconos.pixmap("opciones", tema.TEXTO_SECUNDARIO, 16))
        flecha.setStyleSheet("background: transparent;")
        fila = QHBoxLayout(self)
        fila.setContentsMargins(12, 12, 12, 12)
        fila.setSpacing(12)
        fila.addWidget(Avatar(sesion.nombre_mostrado))
        fila.addLayout(textos, 1)
        fila.addWidget(flecha)

    def mouseReleaseEvent(self, evento):
        if evento.button() == Qt.MouseButton.LeftButton and self.rect().contains(evento.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(evento)

    def keyPressEvent(self, evento):
        if evento.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.clicked.emit()
            return
        super().keyPressEvent(evento)


def confirmar_cierre(ventana, nombre):
    caja = QMessageBox(QMessageBox.Icon.Question, "Cerrar sesión",
                       f"¿Cerrar la sesión de {nombre}?", parent=ventana)
    caja.setInformativeText("Se detiene la cámara y se vuelve a la pantalla de ingreso.")
    cerrar = caja.addButton("Cerrar sesión", QMessageBox.ButtonRole.AcceptRole)
    cancelar = caja.addButton("Cancelar", QMessageBox.ButtonRole.RejectRole)
    caja.setDefaultButton(cancelar)
    caja.exec()
    return caja.clickedButton() is cerrar


class PaginaPendiente(QWidget):
    """Lugar de una pantalla que se completa en un commit posterior."""

    def __init__(self, seccion):
        super().__init__()
        caja = panel()
        interior = QVBoxLayout(caja)
        interior.setContentsMargins(28, 24, 28, 24)
        interior.addWidget(etiqueta(seccion.menu, "titulo-panel"))
        interior.addWidget(etiqueta(
            f"Esta pantalla se completa en el commit {seccion.commit} de la etapa 2.", "secundario"))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(caja)
        layout.addStretch()


class MainWindow(QWidget):
    """Ventana principal: menú lateral según los permisos de la cuenta,
    encabezado con el estado del gimnasio y el área de cada pantalla."""

    INTERVALO_RELOJ_MS = 30_000
    sesion_cerrada = Signal()

    def __init__(self, sesion, horario_service=None, paginas=None, fabricas=None,
                 auth_service=None, confirmar=None):
        super().__init__()
        self.setObjectName("Ventana")
        self.sesion = sesion
        self._auth = auth_service
        self._confirmar = confirmar or confirmar_cierre
        self._finalizada = False
        if horario_service is None:
            from services.horario_service import HorarioService
            horario_service = HorarioService()
        self._horario = horario_service
        self.setWindowTitle(f"{tema.NOMBRE_GIMNASIO} — {sesion.nombre_mostrado}")
        self.resize(1280, 800)

        self.secciones = secciones_permitidas(sesion)
        claves = [s.clave for s in self.secciones]
        paginas = dict(paginas or {})
        fabricas = FABRICAS if fabricas is None else fabricas
        for clave, fabrica in fabricas.items():
            if clave in claves and clave not in paginas:
                try:
                    pagina = fabrica(self)
                except Exception as error:          # sin base, sin cámara, etc.
                    pagina = PaginaConError(SECCIONES[clave], error)
                if pagina is not None:
                    paginas[clave] = pagina
        self.paginas = paginas

        self.indicador = IndicadorApertura()
        self.encabezado = EncabezadoPagina("", "", self.indicador)
        self.stack = QStackedWidget()
        for seccion in self.secciones:
            self.stack.addWidget(paginas.get(seccion.clave) or PaginaPendiente(seccion))
        if not self.secciones:
            self.stack.addWidget(etiqueta("Su cuenta no tiene opciones disponibles.", "subtitulo"))

        contenido = QVBoxLayout()
        contenido.setContentsMargins(32, 28, 32, 28)
        contenido.setSpacing(24)
        contenido.addWidget(self.encabezado)
        contenido.addWidget(self.stack, 1)

        raiz = QHBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)
        raiz.addWidget(self._crear_menu())
        raiz.addLayout(contenido, 1)

        self._reloj = QTimer(self)
        self._reloj.timeout.connect(self.actualizar_encabezado)
        self._reloj.start(self.INTERVALO_RELOJ_MS)
        self.seleccionar(0)

    def _crear_menu(self):
        lateral = QFrame()
        lateral.setObjectName("Sidebar")
        lateral.setFixedWidth(240)
        columna = QVBoxLayout(lateral)
        columna.setContentsMargins(16, 24, 16, 24)
        columna.setSpacing(4)

        marca = Marca()
        marca.setContentsMargins(8, 0, 0, 0)
        marca.setFixedHeight(56)
        columna.addWidget(marca)
        columna.addSpacing(20)

        self.botones = QButtonGroup(self)
        self.botones.setExclusive(True)
        for indice, seccion in enumerate(self.secciones):
            boton = BotonMenu(seccion.menu, seccion.icono)
            boton.clicked.connect(lambda _c=False, i=indice: self.seleccionar(i))
            self.botones.addButton(boton, indice)
            columna.addWidget(boton)
        columna.addStretch()
        columna.addWidget(self._crear_tarjeta_usuario())
        return lateral

    def _crear_tarjeta_usuario(self):
        self.tarjeta_usuario = TarjetaUsuario(self.sesion)
        self.menu_cuenta = QMenu(self)
        self.accion_contrasenia = self.menu_cuenta.addAction(
            QIcon(iconos.pixmap("llave", tema.TEXTO, 18)), "Cambiar contraseña")
        self.menu_cuenta.addSeparator()
        self.accion_cerrar = self.menu_cuenta.addAction(
            QIcon(iconos.pixmap("salir", tema.ROJO, 18)), "Cerrar sesión")
        self.accion_contrasenia.triggered.connect(self.cambiar_contrasenia)
        self.accion_cerrar.triggered.connect(self.cerrar_sesion)
        self.tarjeta_usuario.clicked.connect(self.abrir_menu_cuenta)
        return self.tarjeta_usuario

    def abrir_menu_cuenta(self):
        """El menú se abre hacia arriba, alineado con la tarjeta."""
        tarjeta = self.tarjeta_usuario
        self.menu_cuenta.setMinimumWidth(tarjeta.width())
        alto = self.menu_cuenta.sizeHint().height()
        self.menu_cuenta.popup(tarjeta.mapToGlobal(QPoint(0, -alto - 6)))

    def _servicio_auth(self):
        if self._auth is None:
            from services.auth_service import AuthService
            self._auth = AuthService()
        return self._auth

    def cambiar_contrasenia(self):
        from ui.cambiar_contrasenia_dialog import CambiarContraseniaDialog
        dialogo = CambiarContraseniaDialog(self._servicio_auth(), self.sesion, parent=self)
        if dialogo.exec() == QDialog.DialogCode.Accepted:
            self.sesion = dialogo.sesion
            QMessageBox.information(self, "Cambiar contraseña", "La contraseña se cambió correctamente.")

    def cerrar_sesion(self):
        """Pide confirmación, libera cámara y reconocimiento y avisa con
        sesion_cerrada (la aplicación vuelve al login sin cerrarse)."""
        if not self._confirmar(self, self.sesion.nombre_mostrado):
            return False
        self.finalizar()
        self.sesion_cerrada.emit()
        return True

    def finalizar(self):
        """Detiene relojes, suelta la webcam, cancela un modal abierto y
        termina el proceso de reconocimiento. Se puede llamar más de una vez."""
        if self._finalizada:
            return
        self._finalizada = True
        self._reloj.stop()
        for pagina in self.paginas.values():
            if hasattr(pagina, "liberar"):
                try:
                    pagina.liberar()
                except Exception as error:      # que una pantalla no impida salir
                    print(f"[Cerrar sesión] No se pudo liberar {type(pagina).__name__}: {error}")

    def ir_a(self, clave):
        claves = [s.clave for s in self.secciones]
        if clave in claves:
            self.seleccionar(claves.index(clave))

    def closeEvent(self, evento):
        self.finalizar()
        super().closeEvent(evento)

    def seleccionar(self, indice):
        if not self.secciones:
            self.encabezado.titulo.setText(tema.NOMBRE_GIMNASIO)
            self.actualizar_encabezado()
            return
        self.botones.button(indice).setChecked(True)
        self.stack.setCurrentIndex(indice)
        self.encabezado.titulo.setText(self.secciones[indice].titulo)
        self.actualizar_encabezado()

    def seccion_actual(self):
        return self.secciones[self.stack.currentIndex()] if self.secciones else None

    def actualizar_encabezado(self):
        """Indicador de apertura y subtítulo con el reloj de la base."""
        seccion = self.seccion_actual()
        try:
            abierto, texto, ahora = self._horario.estado_actual()
        except Exception:
            self.indicador.mostrar(False, "Sin conexión con la base de datos")
            if seccion:
                self.encabezado.subtitulo.setText(seccion.subtitulo)
            return
        self.indicador.mostrar(abierto, texto)
        if seccion is None:
            return
        if seccion.clave == "acceso":
            self.encabezado.subtitulo.setText(f"{fecha_hora_titulo(ahora)} · {seccion.subtitulo}")
        else:
            self.encabezado.subtitulo.setText(seccion.subtitulo)


class PaginaConError(QWidget):
    """Se muestra si una pantalla no se pudo abrir (por ejemplo, sin base de
    datos): el resto de la aplicación sigue funcionando."""

    def __init__(self, seccion, error):
        super().__init__()
        caja = panel()
        interior = QVBoxLayout(caja)
        interior.setContentsMargins(28, 24, 28, 24)
        interior.addWidget(etiqueta(f"No se pudo abrir {seccion.menu.replace(chr(10), ' ')}", "titulo-panel"))
        detalle = etiqueta(f"{error}", "secundario")
        detalle.setWordWrap(True)
        interior.addWidget(detalle)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(caja)
        layout.addStretch()


def _crear_control_acceso(ventana):
    from ui.control_acceso_page import ControlAccesoPage
    return ControlAccesoPage()


def _por_modulo(modulo, clase):
    """Fábrica que importa la pantalla recién al crearla. Si el módulo todavía
    no existe en este commit, la sección queda como PaginaPendiente."""
    def fabrica(ventana):
        import importlib
        try:
            tipo = getattr(importlib.import_module(modulo), clase)
        except ModuleNotFoundError:
            return None
        return tipo(ventana.sesion)
    return fabrica


# Pantallas implementadas; el resto muestra PaginaPendiente.
FABRICAS = {
    "acceso": _crear_control_acceso,
    "panel": _por_modulo("ui.panel_page", "PanelPage"),
    "empleados": _por_modulo("ui.empleados_page", "EmpleadosPage"),
    "socios": _por_modulo("ui.socios_page", "SociosPage"),
    "cobros": _por_modulo("ui.cobros_page", "CobrosPage"),
    "estado": _por_modulo("ui.estado_socio_page", "EstadoSocioPage"),
    "configuracion": _por_modulo("ui.configuracion_page", "ConfiguracionPage"),
    "informes": _por_modulo("ui.informes_page", "InformesPage"),
    "jornadas": _por_modulo("ui.jornadas_page", "JornadasPage"),
    "fichajes": _por_modulo("ui.fichajes_page", "FichajesPage"),
}
