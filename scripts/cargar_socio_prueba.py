"""Carga (o actualiza) un socio de prueba con sus 3 fotos y un "Pase por día"
vigente hoy, para probar el control de acceso con la cámara real.

Uso (desde la carpeta del proyecto):
    .venv\\Scripts\\python.exe scripts\\cargar_socio_prueba.py
    .venv\\Scripts\\python.exe scripts\\cargar_socio_prueba.py --nombre Ana --apellido Pérez --dni 30111222
    .venv\\Scripts\\python.exe scripts\\cargar_socio_prueba.py --fotos frente.jpg izquierda.jpg derecha.jpg

Sin --fotos abre la misma ventana de captura del proyecto original y guía
las 3 tomas (frente, perfil izquierdo y perfil derecho). Cada foto se revisa
con el detector de las referencias: el frente es obligatorio; si un perfil no
tiene rostro detectable se elige Repetir o Usar igual.
Si el DNI ya existe, reutiliza la persona y el socio (no los duplica): solo
reemplaza las fotos si se toman o se pasan de nuevo, y agrega un "Pase por
día" para hoy si no tiene una membresía vigente. Las fotos se guardan solo
en la base de datos, nunca en disco."""
import argparse
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))
os.chdir(RAIZ)  # para leer el .env del proyecto

PLAN_PRUEBA = "Pase por día"


def capturar_fotos():
    """Toma guiada de las 3 fotos con la misma ventana de captura del proyecto
    original (Qt, con el tema de ZebraGym). Devuelve {angulo: bytes} o None."""
    from PySide6.QtWidgets import QApplication
    from ui.captura_fotos import capturar_guiado, confirmar_fotos
    from ui.tema import aplicar_tema
    app = QApplication.instance() or QApplication([])
    aplicar_tema(app)
    fotos = capturar_guiado()
    if fotos is None:
        print("Captura cancelada: no se guardó nada.")
        return None
    if not confirmar_fotos(fotos):
        print("No se confirmaron las fotos: no se guardó nada.")
        return None
    print("Fotos confirmadas.")
    return fotos


def leer_fotos(rutas, detectable=None):
    """Lee las 3 fotos de archivos y las revisa con el mismo detector que la
    carga de referencias. La de frente es obligatoria; los perfiles avisan."""
    from ui.captura_fotos import ANGULOS, FRENTE_SIN_ROSTRO, MENSAJE_FRENTE, OK, revisar_foto
    fotos = {}
    for (angulo, nombre, _indicacion), ruta in zip(ANGULOS, rutas):
        datos = Path(ruta).read_bytes()
        resultado = revisar_foto(angulo, datos, detectable)
        if resultado == FRENTE_SIN_ROSTRO:
            raise SystemExit(MENSAJE_FRENTE)
        if resultado != OK:
            print(f"Aviso: la foto de {nombre.lower()} ({ruta}) no tiene un rostro detectable; "
                  "se guarda igual pero no se va a usar para reconocer.")
        fotos[angulo] = datos
    return fotos


def sesion_de_carga(conn, usuario=None):
    """Sesión de un entrenador activo (los entrenadores atienden el mostrador y
    registran socios; la dueña no). Con `usuario` usa esa cuenta; si no, el
    primer entrenador activo."""
    from repositories.user_repository import UserRepository
    from services.auth_service import ENTRENADOR, Sesion
    repo = UserRepository()
    entrenadores = [f for f in repo.listar_personal(conn=conn) if f[5] and ENTRENADOR in f[6]]
    if usuario:
        entrenadores = [f for f in entrenadores if f[4].lower() == usuario.lower()]
        if not entrenadores:
            raise SystemExit(f"No hay un entrenador activo con el usuario '{usuario}'.")
    if not entrenadores:
        raise SystemExit("No hay ninguna cuenta de entrenador activa. Creala en Empleados "
                         "(por ejemplo, 'profe') y volvé a ejecutar el script.")
    uid, nombre, apellido, _dni, nombre_usuario, _activo, roles, _ultimo = entrenadores[0]
    persona_id = repo.buscar_para_login(nombre_usuario, conn=conn)[1]
    return Sesion(uid, persona_id, nombre_usuario, f"{nombre} {apellido}", frozenset(roles))


def cargar(datos, fotos, telefono, transaccion=None, usuario=None):
    """Registra o actualiza al socio de prueba y le asegura un Pase por día
    vigente hoy. Devuelve un dict con lo que hizo."""
    from config.database import usar_conexion
    from repositories.horario_repository import HorarioRepository
    from repositories.membresia_repository import MembresiaRepository
    from repositories.person_repository import PersonRepository
    from repositories.socio_repository import SocioRepository
    from services.persona_service import PersonaService, normalizar_dni

    transaccion = transaccion or usar_conexion
    personas, socios, membresias = PersonRepository(), SocioRepository(), MembresiaRepository()
    dni = normalizar_dni(datos["dni"])
    resumen = {"dni": dni}
    with transaccion() as conn:
        sesion = sesion_de_carga(conn, usuario)
        resumen["registrado_por"] = sesion.nombre_usuario
        persona = personas.obtener_por_dni(dni, conn=conn)
        socio = socios.obtener_por_persona(persona[0], conn=conn) if persona else None
        if socio is None:
            servicio = PersonaService(personas, socios, transaccion=lambda: _misma(conn))
            r = servicio.registrar_socio(sesion, datos, fotos or {}, telefono)
            persona_id, socio_id = r.persona_id, r.socio_id
            resumen["socio"] = "creado" if not r.persona_reutilizada else "creado (persona existente)"
        else:
            persona_id, socio_id = persona[0], socio[0]
            if not socio[5]:
                socios.reactivar(socio_id, conn=conn)
            if fotos:
                personas.guardar_fotos(persona_id, fotos, conn=conn)
            resumen["socio"] = "existente"
        resumen["fotos"] = personas.contar_fotos(persona_id, conn=conn)

        estado = socios.obtener_estado(socio_id, conn=conn)
        if estado and estado["estado_membresia"] == "vigente" and estado["accesos_hoy"] == 0:
            resumen["membresia"] = f"vigente ({estado['plan']}, vence {estado['fecha_vencimiento']:%d/%m/%Y})"
        else:
            plan = next(p for p in membresias.listar_planes(conn=conn) if p[1] == PLAN_PRUEBA)
            hoy = HorarioRepository().ahora(conn=conn).date()
            _m, vence, _precio = membresias.crear(socio_id, plan[0], hoy, sesion.usuario_id, conn=conn)
            resumen["membresia"] = f"nueva: {PLAN_PRUEBA} del {hoy:%d/%m/%Y} (vence {vence:%d/%m/%Y})"
        fila = personas.obtener_por_id(persona_id, conn=conn)
        resumen.update(persona_id=persona_id, socio_id=socio_id, nombre=f"{fila[2]} {fila[3]}")
    return resumen


class _misma:
    """Hace que PersonaService use la transacción en curso."""

    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self.conn

    def __exit__(self, *exc):
        return False


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--nombre", default="Socio")
    parser.add_argument("--apellido", default="de Prueba")
    parser.add_argument("--dni", default="99000001")
    parser.add_argument("--telefono", default="388 000-0000", help="contacto de emergencia")
    parser.add_argument("--fotos", nargs=3, metavar=("FRENTE", "IZQUIERDA", "DERECHA"))
    parser.add_argument("--usuario", help="entrenador que registra al socio (por defecto, el primero activo)")
    parser.add_argument("--sin-fotos", action="store_true",
                        help="si el socio ya existe, no toma fotos nuevas")
    args = parser.parse_args()

    if args.fotos:
        fotos = leer_fotos(args.fotos)
    elif args.sin_fotos:
        fotos = None
    else:
        print("Se abre la cámara para las 3 fotos de referencia.")
        fotos = capturar_fotos()
        if fotos is None:
            return 1
    resumen = cargar({"dni": args.dni, "nombre": args.nombre, "apellido": args.apellido},
                     fotos, args.telefono, usuario=args.usuario)
    print(f"Socio {resumen['socio']}: {resumen['nombre']}, DNI {resumen['dni']} "
          f"(persona {resumen['persona_id']}, socio {resumen['socio_id']})")
    print(f"Fotos de referencia: {resumen['fotos']}")
    print(f"Membresía: {resumen['membresia']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
