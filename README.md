# ZebraGym · Control de acceso por reconocimiento facial

Aplicación de escritorio (Python 3.12 + PySide6 + PostgreSQL 16) para el
gimnasio ZebraGym:

- Los **socios** entran mirando a la cámara.
- Los **entrenadores** marcan su llegada y su salida con la cara.
- La **dueña** controla todo desde el Panel y los Informes.

![Control de acceso](docs/capturas/03_control_acceso.png)

## Quién usa qué

| Rol | Menú |
|---|---|
| Dueña (administrador) | Panel, Informes, Estado del socio, Empleados, Jornadas, Fichajes, Configuración |
| Entrenador | Control de acceso, Socios, Cobros y renovaciones, Estado del socio, Fichajes |
| Recepcionista (rol opcional, para el futuro) | Igual que el entrenador, sin planes de entrenamiento |

Los socios no tienen usuario: se identifican solo con la cara.

## 1. Levantar la base de datos

Requisitos:
- Docker Desktop.
- El archivo `.env` con las credenciales.

```powershell
copy .env.example .env        # completar los valores reales; .env no se sube a GitHub
docker compose up -d
docker compose ps             # el servicio db tiene que figurar como "healthy"
```

La primera vez que se crea el volumen, PostgreSQL ejecuta solo los dos scripts
de `database/initdb/`, que son la única fuente de verdad del esquema:

- **`01-schema.sql`**: 14 tablas y la vista `v_socio_estado`.
- **`02-seed.sql`**:
  - El horario: lunes a viernes de 7:30 a 23 y sábados de 10 a 14.
  - Los 3 planes, con precio $0.
  - La cuenta `admin`.

La base queda en `localhost:5433`, en la base `asistencia_gimnasio`.

## 2. Instalar y ejecutar la aplicación

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python src/main.py
```

La primera vez que se abre Control de acceso, el modelo de reconocimiento tarda
unos 30 s en cargarse. Mientras tanto la cámara muestra "Cargando reconocimiento…".

## 3. Usuarios de prueba y primeros pasos

1. Ingresá con **`admin` / `admin123`**. La app pide cambiar la contraseña.
2. En **Configuración**, cargá el precio de cada plan. Un plan en $0 no se puede vender.
3. En **Empleados**, creá un entrenador. Por ejemplo, el usuario `profe` con
   rol Entrenador (es el que aparece elegido) y sus 3 fotos. En el primer
   ingreso tiene que cambiar la contraseña.
4. Cerrá sesión desde la tarjeta de abajo a la izquierda y ingresá como `profe`.
5. En **Socios**, registrá un socio con sus 3 fotos. Después, en
   **Cobros y renovaciones**, vendele un plan.
6. En **Control de acceso**, el socio mira a la cámara, confirma con
   **Entrar** y se registra su ingreso.

También podés cargar un socio de prueba con un "Pase por día" vigente hoy. El
script registra el socio a nombre de un entrenador activo:

```powershell
.\.venv\Scripts\python.exe scripts\cargar_socio_prueba.py --nombre Ana --apellido Pérez --dni 30111222
```

## 4. Pruebas automáticas

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Las pruebas de base de datos se ejecutan solo si está definida
`ZEBRAGYM_TEST_DSN`. Usan un esquema temporal (`zg_prueba`) dentro de una
transacción que se descarta al final, así que nunca modifican los datos reales.

```powershell
$env:ZEBRAGYM_TEST_DSN = "postgresql://admin:admin123@localhost:5433/asistencia_gimnasio"
.\.venv\Scripts\python.exe -m pytest -q
```

## Capturas

Las capturas están en [`docs/capturas/`](docs/capturas) y usan datos de muestra.

| | |
|---|---|
| ![Login](docs/capturas/01_login.png) | ![Panel](docs/capturas/02_panel.png) |
| ![Socio](docs/capturas/04_modal_socio.png) | ![Empleado](docs/capturas/05_modal_empleado.png) |
| ![Socio y empleado](docs/capturas/06_modal_socio_y_empleado.png) | ![Entrenar deshabilitado](docs/capturas/07_modal_entrenar_deshabilitado.png) |
| ![Socios](docs/capturas/08_socios.png) | ![Cobros](docs/capturas/09_cobros.png) |
| ![Estado del socio](docs/capturas/10_estado_socio.png) | ![Configuración](docs/capturas/11_configuracion.png) |
| ![Informes](docs/capturas/12_informes.png) | ![Menú de la cuenta](docs/capturas/13_menu_cuenta.png) |
| ![Jornadas](docs/capturas/14_jornadas.png) | ![Fichajes](docs/capturas/15_fichajes.png) |

Las reglas de los casos especiales, como el pago parcial, la renovación
anticipada o el fichaje fuera de turno, están en
[`docs/casos_especiales.md`](docs/casos_especiales.md).

## Estructura

```
asistencia-facial/
├── compose.yaml, .env.example, requirements.txt
├── database/initdb/        01-schema.sql y 02-seed.sql (fuente de verdad)
├── docs/                   capturas, diseño y casos especiales
├── scripts/                cargar_socio_prueba.py
├── src/
│   ├── main.py
│   ├── config/             conexión a PostgreSQL
│   ├── hardware/           cámara
│   ├── repositories/       consultas SQL por tabla
│   ├── services/           reglas de negocio, permisos y reconocimiento facial
│   └── ui/                 pantallas (PySide6); estilos solo en tema.py
└── tests/
```
