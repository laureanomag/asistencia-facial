-- =============================================================================
-- ESQUEMA DE BASE DE DATOS: ZEBRA GYM - SISTEMA DE CONTROL DE ACCESO
-- Contexto B: Gimnasio (IES N°7 Populorum Progressio)
-- =============================================================================

-- 1. Tabla de Usuarios Administrativos / Recepción
CREATE TABLE IF NOT EXISTS "usuario" (
    "id" SERIAL PRIMARY KEY,
    "nombre_usuario" VARCHAR(100) UNIQUE NOT NULL,
    "correo_electronico" VARCHAR(255) UNIQUE NULL,
    "contrasenia" VARCHAR(255) NOT NULL,
    "rol" VARCHAR(50) NOT NULL DEFAULT 'recepcionista'
);

-- 2. Tabla de Personas (Socios y Profesores)
CREATE TABLE IF NOT EXISTS "persona" (
    "id" SERIAL PRIMARY KEY,
    "tipo" VARCHAR(20) NOT NULL CHECK ("tipo" IN ('socio', 'profesor')),
    "nombre" VARCHAR(100) NOT NULL,
    "apellido" VARCHAR(100) NOT NULL,
    "dni" VARCHAR(20) UNIQUE NOT NULL,
    "correo_electronico" VARCHAR(255) NULL,
    "telefono" VARCHAR(50) NULL,
    "fecha_nacimiento" DATE NULL,
    "fecha_alta" DATE NOT NULL DEFAULT CURRENT_DATE,
    "activo" BOOLEAN NOT NULL DEFAULT TRUE
);

-- 3. Tabla de Fotos de Referencia (DeepFace / FaceNet512)
CREATE TABLE IF NOT EXISTS "foto_persona" (
    "id" SERIAL PRIMARY KEY,
    "persona_id" INTEGER NOT NULL REFERENCES "persona"("id") ON DELETE CASCADE,
    "angulo" VARCHAR(50) NOT NULL CHECK ("angulo" IN ('frente', 'perfil_derecho', 'perfil_izquierdo')),
    "imagen" BYTEA NOT NULL
);

-- 4. Catálogo de Planes de Membresía / Pases
CREATE TABLE IF NOT EXISTS "plan" (
    "id" SERIAL PRIMARY KEY,
    "codigo" VARCHAR(50) UNIQUE NOT NULL,
    "nombre" VARCHAR(100) NOT NULL,
    "descripcion" TEXT NULL,
    "cupo_mensual" INTEGER NULL,            -- 8, 12, 20 o NULL si es ilimitado
    "max_ingresos_por_dia" INTEGER NULL,    -- 1 para 'todos_los_dias', NULL para 'pase_libre'
    "precio" NUMERIC(10, 2) NOT NULL DEFAULT 0.00,
    "activo" BOOLEAN NOT NULL DEFAULT TRUE
);

-- 5. Membresías / Cuotas de Socios
CREATE TABLE IF NOT EXISTS "membresia" (
    "id" SERIAL PRIMARY KEY,
    "socio_id" INTEGER NOT NULL REFERENCES "persona"("id") ON DELETE RESTRICT,
    "plan_id" INTEGER NOT NULL REFERENCES "plan"("id") ON DELETE RESTRICT,
    "fecha_pago" DATE NOT NULL DEFAULT CURRENT_DATE,
    "fecha_inicio" DATE NOT NULL DEFAULT CURRENT_DATE,
    "fecha_vencimiento" DATE NOT NULL,
    "cupos_totales" INTEGER NULL,
    "monto_abonado" NUMERIC(10, 2) NOT NULL DEFAULT 0.00,
    "estado" VARCHAR(20) NOT NULL DEFAULT 'activa' CHECK ("estado" IN ('activa', 'vencida', 'agotada', 'cancelada'))
);

-- 6. Ingresos de Socios
CREATE TABLE IF NOT EXISTS "ingreso_socio" (
    "id" SERIAL PRIMARY KEY,
    "socio_id" INTEGER NOT NULL REFERENCES "persona"("id") ON DELETE RESTRICT,
    "membresia_id" INTEGER NOT NULL REFERENCES "membresia"("id") ON DELETE RESTRICT,
    "fecha_hora" TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);

-- 7. Turnos de Profesores (Turnos semanales y rotativos de sábados)
CREATE TABLE IF NOT EXISTS "turno_profesor" (
    "id" SERIAL PRIMARY KEY,
    "profesor_id" INTEGER NOT NULL REFERENCES "persona"("id") ON DELETE RESTRICT,
    "dia_semana" INTEGER NULL CHECK ("dia_semana" BETWEEN 0 AND 6),
    "fecha_especifica" DATE NULL,
    "horario_inicio" TIME WITHOUT TIME ZONE NOT NULL,
    "horario_fin" TIME WITHOUT TIME ZONE NOT NULL,
    "es_rotativo" BOOLEAN NOT NULL DEFAULT FALSE,
    "observaciones" TEXT NULL
);

-- 8. Asistencia Laboral de Profesores (Entrada y Salida)
CREATE TABLE IF NOT EXISTS "asistencia_profesor" (
    "id" SERIAL PRIMARY KEY,
    "profesor_id" INTEGER NOT NULL REFERENCES "persona"("id") ON DELETE RESTRICT,
    "turno_id" INTEGER NULL REFERENCES "turno_profesor"("id") ON DELETE SET NULL,
    "entrada" TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
    "salida" TIMESTAMP WITHOUT TIME ZONE NULL,
    "es_cambio_turno" BOOLEAN NOT NULL DEFAULT FALSE,
    "observaciones" TEXT NULL
);

-- 9. Horarios de Atención del Gimnasio
CREATE TABLE IF NOT EXISTS "horario_atencion" (
    "id" SERIAL PRIMARY KEY,
    "dia_semana" INTEGER NOT NULL UNIQUE CHECK ("dia_semana" BETWEEN 0 AND 6),
    "nombre_dia" VARCHAR(20) NOT NULL,
    "abierto" BOOLEAN NOT NULL DEFAULT TRUE,
    "horario_apertura" TIME WITHOUT TIME ZONE NULL,
    "horario_cierre" TIME WITHOUT TIME ZONE NULL
);

-- 10. Feriados (Nacionales y Provinciales de Jujuy)
CREATE TABLE IF NOT EXISTS "feriado" (
    "id" SERIAL PRIMARY KEY,
    "fecha" DATE NOT NULL UNIQUE,
    "descripcion" VARCHAR(255) NOT NULL,
    "es_nacional" BOOLEAN NOT NULL,
    "abre_gimnasio" BOOLEAN NOT NULL
);

-- 11. Auditoría de Accesos Denegados
CREATE TABLE IF NOT EXISTS "rechazo_acceso" (
    "id" SERIAL PRIMARY KEY,
    "persona_id" INTEGER NULL REFERENCES "persona"("id") ON DELETE SET NULL,
    "tipo_persona" VARCHAR(20) NULL,
    "motivo" VARCHAR(100) NOT NULL,
    "detalle" TEXT NULL,
    "fecha_hora" TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);

-- =============================================================================
-- DATOS INICIALES Y CONFIGURACIÓN PREDETERMINADA
-- =============================================================================

-- Usuario administrador por defecto
INSERT INTO "usuario" ("nombre_usuario", "correo_electronico", "contrasenia", "rol")
VALUES ('admin', 'admin@zebragym.com', 'admin123', 'admin')
ON CONFLICT ("nombre_usuario") DO NOTHING;

-- Planes obligatorios del Trabajo Final + Pase Diario de Zebra Gym
INSERT INTO "plan" ("codigo", "nombre", "descripcion", "cupo_mensual", "max_ingresos_por_dia", "precio")
VALUES
    ('pase_diario', 'Pase Diario', 'Acceso individual para entrenar por el día', 1, 1, 3000.00),
    ('2_veces_semana', '2 veces por semana', '8 entrenamientos durante el mes de vigencia', 8, NULL, 18000.00),
    ('3_veces_semana', '3 veces por semana', '12 entrenamientos durante el mes de vigencia', 12, NULL, 22000.00),
    ('5_veces_semana', '5 veces por semana', '20 entrenamientos durante el mes de vigencia', 20, NULL, 26000.00),
    ('todos_los_dias', 'Todos los días', 'Puede ingresar todos los días, pero como máximo una vez por día', NULL, 1, 28000.00),
    ('pase_libre', 'Pase Libre', 'Puede ingresar todos los días y varias veces durante un mismo día', NULL, NULL, 32000.00)
ON CONFLICT ("codigo") DO NOTHING;

-- Horarios habituales de Zebra Gym Jujuy
-- 0=Lunes, 1=Martes, 2=Miércoles, 3=Jueves, 4=Viernes, 5=Sábado, 6=Domingo
INSERT INTO "horario_atencion" ("dia_semana", "nombre_dia", "abierto", "horario_apertura", "horario_cierre")
VALUES
    (0, 'Lunes', TRUE, '07:30:00', '23:00:00'),
    (1, 'Martes', TRUE, '07:30:00', '23:00:00'),
    (2, 'Miércoles', TRUE, '07:30:00', '23:00:00'),
    (3, 'Jueves', TRUE, '07:30:00', '23:00:00'),
    (4, 'Viernes', TRUE, '07:30:00', '23:00:00'),
    (5, 'Sábado', TRUE, '10:00:00', '14:00:00'),
    (6, 'Domingo', FALSE, NULL, NULL)
ON CONFLICT ("dia_semana") DO NOTHING;

-- Feriados de Jujuy y Nacionales de muestra
-- Nacionales: abre_gimnasio = FALSE | Provinciales de Jujuy: abre_gimnasio = TRUE
INSERT INTO "feriado" ("fecha", "descripcion", "es_nacional", "abre_gimnasio")
VALUES
    ('2026-01-01', 'Año Nuevo', TRUE, FALSE),
    ('2026-03-24', 'Día Nacional de la Memoria por la Verdad y la Justicia', TRUE, FALSE),
    ('2026-04-02', 'Día del Veterano y de los Caídos en la Guerra de Malvinas', TRUE, FALSE),
    ('2026-04-19', 'Fundación de San Salvador de Jujuy', FALSE, TRUE),
    ('2026-05-01', 'Día Internacional de los Trabajadores', TRUE, FALSE),
    ('2026-05-25', 'Día de la Revolución de Mayo', TRUE, FALSE),
    ('2026-06-20', 'Paso a la Inmortalidad del Gral. Manuel Belgrano', TRUE, FALSE),
    ('2026-07-09', 'Día de la Independencia Argentina', TRUE, FALSE),
    ('2026-08-23', 'Éxodo Jujeño', FALSE, TRUE),
    ('2026-11-18', 'Autonomía Política de Jujuy', FALSE, TRUE),
    ('2026-12-08', 'Inmaculada Concepción de María', TRUE, FALSE),
    ('2026-12-25', 'Navidad', TRUE, FALSE)
ON CONFLICT ("fecha") DO NOTHING;
