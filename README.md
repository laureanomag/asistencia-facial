# asistencia-facial

Sistema de Asistencia por Reconocimiento Facial — IES N°7 Populorum Progressio.

## Incremento #2: Inicio de sesión

Este incremento agrega una aplicación de escritorio en Python (PySide6) que
valida credenciales contra la tabla `usuario` de PostgreSQL.

### Requisitos previos

- Docker y la base de datos del Incremento #1 en funcionamiento (`compose.yaml`,
  `database/initdb/01-schema.sql`).
- La tabla `usuario` debe tener al menos un registro cargado.
- Python 3.12.

### 1. Entorno virtual

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

Si PowerShell no permite activar el entorno:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

### 2. Instalar dependencias

```powershell
python -m pip install -r requirements.txt
python -c "import PySide6, cv2, deepface, tensorflow, keras, psycopg; print('OK')"
```

### 3. Variables de entorno

Copiar `.env.example` a `.env` y completar los valores reales. **No subir `.env` a GitHub.**

```powershell
copy .env.example .env
```

### 4. Usuario de prueba

Si todavía no hay ningún usuario cargado, ejecutar desde DBeaver (o similar):

```sql
INSERT INTO usuario
    (nombre_usuario, correo_electronico, dni, cuil, contrasenia)
VALUES
    ('admin', 'admin@ies7.edu.ar', '00000000', NULL, 'admin123')
ON CONFLICT (nombre_usuario) DO NOTHING;
```

### 5. Levantar la base y ejecutar la app

```powershell
docker compose ps
python src/main.py
```

Debería abrirse la ventana **"Inicio de sesión"**. Al validar credenciales
correctas se abre la ventana **"Bienvenido"**; si son incorrectas o faltan
campos, se muestra un mensaje de error.

## Estructura

```
asistencia-facial/
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
├── src/
│   ├── main.py
│   ├── config/
│   │   └── database.py
│   ├── repositories/
│   │   └── user_repository.py
│   └── ui/
│       ├── login_window.py
│       └── welcome_window.py
└── tests/
```

## Qué NO se evalúa en este incremento

Registro de alumnos, captura de fotos con webcam, reconocimiento facial con
DeepFace, registro de entrada/salida, exportación a `.xlsx`, diseño visual
definitivo.
