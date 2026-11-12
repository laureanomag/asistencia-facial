from dataclasses import dataclass

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QButtonGroup, QFrame, QHBoxLayout, QLabel, QPushButton, QStackedWidget, QVBoxLayout, QWidget,
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


SECCIONES = (
    Seccion("acceso", "Control de acceso", "camara", auth.ACCESO_OPERAR_CAMARA,
            "Control de acceso", "Mirá a la cámara para ingresar", 7),
    Seccion("socios", "Socios", "socios", auth.SOCIO_REGISTRAR,
            "Socios", "Registro de socios: datos personales, 3 fotos y contacto de emergencia", 8),
    Seccion("cobros", "Cobros y\nrenovaciones", "cobros", auth.PAGO_REGISTRAR,
            "Cobros y renovaciones", "Alta y renovación de membresías con su pago", 9),
    Seccion("estado", "Estado del socio", "estado", auth.MEMBRESIA_CONSULTAR,
            "Estado del socio", "Plan, vencimiento, ingresos de la semana y pagos", 10),
    Seccion("fichajes", "Fichajes", "fichajes", auth.JORNADA_GESTIONAR,
            "Fichajes", "Entradas y salidas del personal, por empleado y por fecha", 13),
    Seccion("jornadas", "Jornadas", "jornadas", auth.JORNADA_GESTIONAR,
            "Jornadas", "Turnos de los entrenadores y sus cambios", 12),
    Seccion("informes", "Informes", "informes", auth.REPORTE_CONSULTAR,
            "Informes", "Ingresos y rechazos por socio", 14),
    Seccion("configuracion", "Configuración", "configuracion", auth.CONFIGURACION_GESTIONAR,
            "Configuración", "Planes, precios y horario de atención", 11),
)


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
        fila.setContentsMargins(14, 8, 10, 8)
        fila.setSpacing(14)
        fila.addWidget(self._icono)
        fila.addWidget(self._texto, 1)
        self.setMinimumHeight(58 if "\n" in texto else 44)
        self.toggled.connect(self._pintar)
        self._pintar(False)

    def texto(self):
        return self._texto.text().replace("\n", " ")

    def _pintar(self, activo):
        self._icono.setPixmap(self._icono_activo if activo else self._icono_normal)
        self._texto.setProperty("activo", activo)
        tema.refrescar_estilo(self._texto)


def secciones_permitidas(sesion):
    return [s for s in SECCIONES if sesion.puede(s.permiso)]


def texto_roles(roles):
    return " · ".join(NOMBRES_ROL[r] for r in auth.ROLES if r in roles)


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

    def __init__(self, sesion, horario_service=None, paginas=None):
        super().__init__()
        self.setObjectName("Ventana")
        self.sesion = sesion
        if horario_service is None:
            from services.horario_service import HorarioService
            horario_service = HorarioService()
        self._horario = horario_service
        self.setWindowTitle(f"{tema.NOMBRE_GIMNASIO} — {sesion.nombre_mostrado}")
        self.resize(1280, 800)

        self.secciones = secciones_permitidas(sesion)
        paginas = paginas or {}

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
        tarjeta = con_rol(QFrame(), "tarjeta-usuario")
        textos = QVBoxLayout()
        textos.setSpacing(0)
        nombre = QLabel(self.sesion.nombre_mostrado)
        nombre.setStyleSheet("font-weight: 700;")
        textos.addWidget(nombre)
        textos.addWidget(etiqueta(texto_roles(self.sesion.roles), "secundario"))
        fila = QHBoxLayout(tarjeta)
        fila.setContentsMargins(12, 12, 12, 12)
        fila.setSpacing(12)
        fila.addWidget(Avatar(self.sesion.nombre_mostrado))
        fila.addLayout(textos)
        fila.addStretch()
        return tarjeta

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
