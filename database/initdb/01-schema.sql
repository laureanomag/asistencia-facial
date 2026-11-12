-- =====================================================================
--  ZEBRAGYM - Esquema oficial (PostgreSQL 16)
--  14 tablas + 1 vista. Orden de creación = orden de carga (sin ciclos).
--
--  Requisitos del gimnasio que cubre:
--   - Horario: lunes a viernes 7 a 23 h, sábados 10 a 14 h, domingos cerrado.
--   - Pases de ZebraGym: por día, 3 x semana y pase libre (mensualidad).
--     Cada plan puede tener, si hace falta: límite diario, límite semanal y
--     cupo de accesos en la vigencia.
--   - La mensualidad dura exactamente un mes desde el pago (20/10 -> 20/11).
--   - Entrenadores con turnos por fecha (rotativos los sábados), cambios de
--     horario con historial, y registro de entrada y salida (fichaje).
--   - Por socio: plan, vigencia, accesos usados y restantes, último pago,
--     días entrenados en la semana y estado contable (vista v_socio_estado).
-- =====================================================================


-- ---------------------------------------------------------------------
-- NIVEL 1: tablas que no dependen de ninguna otra
-- ---------------------------------------------------------------------

-- Datos personales: una sola fila por persona, sea socio, empleado o ambos
CREATE TABLE persona (
    id                  SERIAL PRIMARY KEY,
    dni                 VARCHAR(8)   NOT NULL UNIQUE,
    nombre              VARCHAR(100) NOT NULL,
    apellido            VARCHAR(100) NOT NULL,
    celular             VARCHAR(30),
    correo_electronico  VARCHAR(150),
    fecha_nacimiento    DATE,
    domicilio           VARCHAR(200),
    creado_en           TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_persona_dni CHECK (dni ~ '^[0-9]{7,8}$')
);

-- Planes de membresía
CREATE TABLE plan (
    id                        SERIAL PRIMARY KEY,
    nombre                    VARCHAR(50)   NOT NULL UNIQUE,
    vigencia                  INTERVAL      NOT NULL,     -- '1 month' (vence el mismo día del mes siguiente) o '1 day'
    entrenamientos_mensuales  INT,                        -- cupo de accesos en toda la vigencia; NULL = sin cupo
    max_dias_semanales        INT,                        -- 3 = pase 3 x semana; NULL = sin límite semanal
    max_ingresos_diarios      INT,                        -- 1 = un ingreso por día; NULL = sin límite diario
    precio                    DECIMAL(12,2) NOT NULL,     -- precio vigente; margen para aumentos
    activo                    BOOLEAN       NOT NULL DEFAULT TRUE,
    CONSTRAINT chk_plan_vigencia       CHECK (vigencia > INTERVAL '0'),
    CONSTRAINT chk_plan_entrenamientos CHECK (entrenamientos_mensuales > 0),
    CONSTRAINT chk_plan_dias_semana    CHECK (max_dias_semanales BETWEEN 1 AND 7),
    CONSTRAINT chk_plan_ingresos       CHECK (max_ingresos_diarios > 0),
    CONSTRAINT chk_plan_precio         CHECK (precio >= 0)
);

-- Horario semanal habitual (un día sin filas = cerrado)
CREATE TABLE horario_atencion (
    id             SERIAL PRIMARY KEY,
    dia_semana     SMALLINT NOT NULL,                   -- ISO: 1 = lunes ... 7 = domingo
    hora_apertura  TIME     NOT NULL,
    hora_cierre    TIME     NOT NULL,
    activo         BOOLEAN  NOT NULL DEFAULT TRUE,
    CONSTRAINT chk_horario_dia   CHECK (dia_semana BETWEEN 1 AND 7),
    CONSTRAINT chk_horario_horas CHECK (hora_cierre > hora_apertura),
    CONSTRAINT uq_horario_franja UNIQUE (dia_semana, hora_apertura)
);

-- ---------------------------------------------------------------------
-- NIVEL 2
-- ---------------------------------------------------------------------

-- Perfil facial de la persona (sirve para que el socio entre y para que el entrenador fiche)
CREATE TABLE foto_persona (
    id          SERIAL PRIMARY KEY,
    persona_id  INT         NOT NULL REFERENCES persona (id) ON DELETE CASCADE,
    angulo      VARCHAR(30) NOT NULL,
    imagen      BYTEA       NOT NULL,                    -- dato biométrico: restringir acceso
    creado_en   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_foto_angulo CHECK (angulo IN ('frente', 'perfil_izquierdo', 'perfil_derecho')),
    CONSTRAINT uq_foto_persona_angulo UNIQUE (persona_id, angulo)    -- máximo 3 fotos por persona
);

-- Cuenta para entrar al sistema (empleados)
CREATE TABLE usuario (
    id                        SERIAL PRIMARY KEY,
    persona_id                INT          UNIQUE REFERENCES persona (id) ON DELETE RESTRICT,  -- NULL solo para la cuenta técnica inicial
    nombre_usuario            VARCHAR(50)  NOT NULL,
    contrasenia_hash          VARCHAR(255) NOT NULL,     -- hash bcrypt, nunca la clave en texto
    activo                    BOOLEAN      NOT NULL DEFAULT TRUE,
    debe_cambiar_contrasenia  BOOLEAN      NOT NULL DEFAULT FALSE,
    ultimo_acceso             TIMESTAMPTZ,
    creado_en                 TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX uq_usuario_nombre ON usuario (LOWER(nombre_usuario));


-- ---------------------------------------------------------------------
-- NIVEL 3
-- ---------------------------------------------------------------------

-- Una cuenta puede tener varios roles (ej.: administrador y entrenador).
-- Los roles son una lista fija, controlada con CHECK.
CREATE TABLE usuario_rol (
    usuario_id               INT         NOT NULL REFERENCES usuario (id) ON DELETE CASCADE,
    rol                      VARCHAR(30) NOT NULL,
    asignado_por_usuario_id  INT         REFERENCES usuario (id)          ON DELETE RESTRICT,
    asignado_en              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (usuario_id, rol),
    CONSTRAINT chk_usuario_rol CHECK (rol IN ('administrador', 'recepcionista', 'entrenador'))
);

CREATE TABLE socio (
    id                            SERIAL PRIMARY KEY,
    persona_id                    INT          NOT NULL UNIQUE REFERENCES persona (id) ON DELETE RESTRICT,
    contacto_emergencia_nombre    VARCHAR(100),
    contacto_emergencia_telefono  VARCHAR(30)  NOT NULL,
    fecha_alta                    DATE         NOT NULL DEFAULT CURRENT_DATE,
    activo                        BOOLEAN      NOT NULL DEFAULT TRUE,
    fecha_baja                    DATE,
    registrado_por_usuario_id     INT REFERENCES usuario (id) ON DELETE RESTRICT,
    creado_en                     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_socio_baja CHECK (activo = (fecha_baja IS NULL))   -- dado de baja <=> tiene fecha de baja
);

-- Turno de trabajo de un empleado en una fecha (permite sábados rotativos)
CREATE TABLE jornada (
    id               SERIAL PRIMARY KEY,
    usuario_id       INT         NOT NULL REFERENCES usuario (id) ON DELETE RESTRICT,
    fecha            DATE        NOT NULL,
    horario_entrada  TIME        NOT NULL,
    horario_salida   TIME        NOT NULL,
    -- jornada             = turno normal de trabajo
    -- licencia_vacaciones = no trabaja por licencia o vacaciones
    -- permiso             = pidió el día (u horas) por un asunto personal
    estado           VARCHAR(30) NOT NULL DEFAULT 'jornada',
    CONSTRAINT chk_jornada_horas  CHECK (horario_salida > horario_entrada),
    CONSTRAINT chk_jornada_estado CHECK (estado IN ('jornada', 'licencia_vacaciones', 'permiso')),
    CONSTRAINT uq_jornada_turno   UNIQUE (usuario_id, fecha, horario_entrada),
    CONSTRAINT uq_jornada_usuario UNIQUE (id, usuario_id)          -- para la FK compuesta de fichaje
);


-- ---------------------------------------------------------------------
-- NIVEL 4
-- ---------------------------------------------------------------------

-- Cada período de membresía (alta o renovación). Copia las condiciones del plan al momento de la venta.
-- Vigente desde fecha_inicio (día del pago) hasta el día ANTERIOR a fecha_vencimiento.
-- Ej.: inicio 2026-10-20, vencimiento 2026-11-20 -> el 20/11 ya debe renovarse.
CREATE TABLE membresia (
    id                         SERIAL PRIMARY KEY,
    socio_id                   INT           NOT NULL REFERENCES socio (id) ON DELETE RESTRICT,
    plan_id                    INT           NOT NULL REFERENCES plan  (id) ON DELETE RESTRICT,
    fecha_inicio               DATE          NOT NULL,
    fecha_vencimiento          DATE          NOT NULL,   -- = fecha_inicio + plan.vigencia (lo calcula la app)
    precio                     DECIMAL(12,2) NOT NULL,
    entrenamientos_mensuales   INT,
    max_dias_semanales         INT,
    max_ingresos_diarios       INT,
    -- solo estados que decide una persona; "vencida", "agotada" y "no vigente" se calculan en v_socio_estado
    estado                     VARCHAR(30)   NOT NULL DEFAULT 'activa',
    registrado_por_usuario_id  INT REFERENCES usuario (id) ON DELETE RESTRICT,
    creado_en                  TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_membresia_fechas   CHECK (fecha_vencimiento > fecha_inicio),
    CONSTRAINT chk_membresia_precio   CHECK (precio >= 0),
    CONSTRAINT chk_membresia_dias     CHECK (max_dias_semanales BETWEEN 1 AND 7),
    CONSTRAINT chk_membresia_entrenam CHECK (entrenamientos_mensuales > 0),
    CONSTRAINT chk_membresia_ingresos CHECK (max_ingresos_diarios > 0),
    CONSTRAINT chk_membresia_estado   CHECK (estado IN ('activa', 'suspendida', 'cancelada')),
    CONSTRAINT uq_membresia_socio     UNIQUE (id, socio_id)       -- para la FK compuesta de acceso
);

-- Rutina armada por un entrenador para un socio
CREATE TABLE plan_entrenamiento (
    id                     SERIAL PRIMARY KEY,
    socio_id               INT          NOT NULL REFERENCES socio (id)   ON DELETE RESTRICT,
    entrenador_usuario_id  INT          REFERENCES usuario (id)          ON DELETE RESTRICT,
    objetivo               VARCHAR(150),
    descripcion            TEXT         NOT NULL,
    fecha_inicio           DATE         NOT NULL,
    fecha_fin              DATE,
    creado_en              TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_plan_entrenamiento_fechas CHECK (fecha_fin IS NULL OR fecha_fin >= fecha_inicio)
);

-- Historial de cambios de un turno (ej.: el entrenador cambia su horario del sábado)
CREATE TABLE jornada_cambio (
    id                       SERIAL PRIMARY KEY,
    jornada_id               INT          NOT NULL REFERENCES jornada (id) ON DELETE RESTRICT,
    fecha_anterior           DATE         NOT NULL,
    entrada_anterior         TIME         NOT NULL,
    salida_anterior          TIME         NOT NULL,
    estado_anterior          VARCHAR(30)  NOT NULL,
    fecha_nueva              DATE         NOT NULL,
    entrada_nueva            TIME         NOT NULL,
    salida_nueva             TIME         NOT NULL,
    estado_nuevo             VARCHAR(30)  NOT NULL,
    motivo                   VARCHAR(255),
    cambiado_por_usuario_id  INT REFERENCES usuario (id) ON DELETE RESTRICT,
    cambiado_en              TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_jornada_cambio_estados CHECK (
        estado_anterior IN ('jornada', 'licencia_vacaciones', 'permiso')
    AND estado_nuevo    IN ('jornada', 'licencia_vacaciones', 'permiso')
    )
);

-- Entrada y salida real del empleado
CREATE TABLE fichaje (
    id          SERIAL PRIMARY KEY,
    usuario_id  INT         NOT NULL REFERENCES usuario (id) ON DELETE RESTRICT,
    jornada_id  INT         REFERENCES jornada (id)          ON DELETE RESTRICT,  -- NULL = fuera de turno
    entrada     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    salida      TIMESTAMPTZ,                                                     -- NULL = todavía no salió
    CONSTRAINT chk_fichaje_horas CHECK (salida IS NULL OR salida > entrada)
);
-- Un empleado no puede tener dos entradas abiertas a la vez
CREATE UNIQUE INDEX uq_fichaje_abierto ON fichaje (usuario_id) WHERE salida IS NULL;


-- ---------------------------------------------------------------------
-- NIVEL 5
-- ---------------------------------------------------------------------

CREATE TABLE pago (
    id                         SERIAL PRIMARY KEY,
    membresia_id               INT           NOT NULL REFERENCES membresia (id) ON DELETE RESTRICT,
    monto                      DECIMAL(12,2) NOT NULL,
    metodo                     VARCHAR(30)   NOT NULL,
    fecha_pago                 TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    registrado_por_usuario_id  INT REFERENCES usuario (id) ON DELETE RESTRICT,
    CONSTRAINT chk_pago_monto  CHECK (monto > 0),
    CONSTRAINT chk_pago_metodo CHECK (metodo IN ('efectivo', 'debito', 'credito', 'transferencia', 'mercado_pago'))
);

-- Cada intento de ingreso de un socio (permitido o rechazado)
CREATE TABLE acceso (
    id                SERIAL PRIMARY KEY,
    socio_id          INT          REFERENCES socio (id)     ON DELETE RESTRICT,  -- NULL = rostro no reconocido
    membresia_id      INT          REFERENCES membresia (id) ON DELETE RESTRICT,
    fecha_hora        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    resultado         VARCHAR(30)  NOT NULL,
    motivo_rechazo    VARCHAR(30),
    distancia_facial  DECIMAL(6,4),
    CONSTRAINT chk_acceso_resultado CHECK (resultado IN ('permitido', 'rechazado')),
    -- un ingreso permitido siempre tiene socio y membresía; uno rechazado siempre tiene motivo
    CONSTRAINT chk_acceso_coherencia CHECK (
        (resultado = 'permitido' AND socio_id IS NOT NULL AND membresia_id IS NOT NULL AND motivo_rechazo IS NULL)
     OR (resultado = 'rechazado' AND motivo_rechazo IS NOT NULL)
    ),
    CONSTRAINT chk_acceso_motivo CHECK (motivo_rechazo IN (
        'no_reconocido',          -- la persona no pudo ser identificada
        'no_es_socio',            -- se reconoció a alguien sin ficha de socio
        'socio_inactivo',         -- el socio está dado de baja
        'sin_membresia',          -- nunca tuvo membresía
        'membresia_vencida',      -- la última membresía ya venció
        'membresia_no_vigente',   -- la membresía todavía no empezó
        'cupo_agotado',           -- usó todos los accesos del plan
        'limite_diario',          -- ya usó los ingresos permitidos hoy
        'limite_semanal',         -- ya entrenó los días permitidos esta semana
        'gimnasio_cerrado'))      -- fuera del horario de atención (horario_atencion)
);


-- ---------------------------------------------------------------------
-- REGLAS DE COHERENCIA (FK compuestas)
-- ---------------------------------------------------------------------

-- El acceso y su membresía deben ser del mismo socio
ALTER TABLE acceso
    ADD CONSTRAINT fk_acceso_membresia_mismo_socio
    FOREIGN KEY (membresia_id, socio_id) REFERENCES membresia (id, socio_id);

-- El fichaje y su jornada deben ser del mismo empleado
ALTER TABLE fichaje
    ADD CONSTRAINT fk_fichaje_jornada_mismo_usuario
    FOREIGN KEY (jornada_id, usuario_id) REFERENCES jornada (id, usuario_id);


-- ---------------------------------------------------------------------
-- ÍNDICES
-- ---------------------------------------------------------------------

CREATE INDEX idx_usuario_rol_rol           ON usuario_rol (rol);
CREATE INDEX idx_plan_entrenamiento_socio  ON plan_entrenamiento (socio_id);
CREATE INDEX idx_membresia_socio           ON membresia (socio_id, fecha_inicio);
CREATE INDEX idx_membresia_plan            ON membresia (plan_id);
CREATE INDEX idx_pago_membresia            ON pago (membresia_id);
CREATE INDEX idx_jornada_fecha             ON jornada (fecha);
CREATE INDEX idx_jornada_cambio_jornada    ON jornada_cambio (jornada_id);
CREATE INDEX idx_fichaje_usuario           ON fichaje (usuario_id, entrada);
CREATE INDEX idx_fichaje_jornada           ON fichaje (jornada_id);
CREATE INDEX idx_acceso_socio_fecha        ON acceso (socio_id, fecha_hora);
CREATE INDEX idx_acceso_membresia          ON acceso (membresia_id);


-- ---------------------------------------------------------------------
-- VISTA: estado de cada socio activo
-- Se calcula en el momento: nunca queda desactualizada.
--   Membresía actual = la vigente hoy; si no hay, la más reciente (sin contar canceladas).
--   estado_membresia: vigente | agotada | no_vigente | vencida | sin_membresia
--   estado_contable:
--     sin_pase   -> nunca compró una membresía
--     debe       -> pagó menos que el precio, o la membresía ya venció
--     por_vencer -> vence dentro de 5 días o menos
--     al_dia     -> pagada y vigente
-- ---------------------------------------------------------------------

CREATE VIEW v_socio_estado AS
WITH hoy AS (
    SELECT (NOW() AT TIME ZONE 'America/Argentina/Buenos_Aires')::date AS d
),
actual AS (
    SELECT DISTINCT ON (m.socio_id) m.*
    FROM membresia m, hoy
    WHERE m.estado <> 'cancelada'
    ORDER BY m.socio_id,
             (m.fecha_inicio <= hoy.d AND hoy.d < m.fecha_vencimiento) DESC,   -- primero la vigente
             m.fecha_inicio DESC, m.id DESC
),
pagos AS (
    SELECT membresia_id, SUM(monto) AS total, MAX(fecha_pago) AS ultimo
    FROM pago
    GROUP BY membresia_id
),
usados AS (                                   -- accesos permitidos consumidos por cada membresía
    SELECT membresia_id,
           COUNT(*) AS accesos,
           COUNT(*) FILTER (WHERE (fecha_hora AT TIME ZONE 'America/Argentina/Buenos_Aires')::date
                                  = (SELECT d FROM hoy)) AS accesos_hoy
    FROM acceso
    WHERE resultado = 'permitido'
    GROUP BY membresia_id
),
dias_semana AS (                              -- días distintos con ingreso permitido desde el lunes
    SELECT a.socio_id,
           COUNT(DISTINCT (a.fecha_hora AT TIME ZONE 'America/Argentina/Buenos_Aires')::date) AS dias
    FROM acceso a, hoy
    WHERE a.resultado = 'permitido'
      AND (a.fecha_hora AT TIME ZONE 'America/Argentina/Buenos_Aires')::date >= DATE_TRUNC('week', hoy.d)::date
    GROUP BY a.socio_id
)
SELECT
    s.id                                              AS socio_id,
    p.dni,
    p.nombre,
    p.apellido,
    s.contacto_emergencia_telefono,
    u.id                                              AS membresia_id,
    pl.nombre                                         AS plan,
    u.fecha_inicio,
    u.fecha_vencimiento,
    u.fecha_vencimiento - hoy.d                       AS dias_para_vencer,
    u.entrenamientos_mensuales                        AS accesos_incluidos,
    COALESCE(us.accesos, 0)                           AS accesos_usados,
    u.entrenamientos_mensuales - COALESCE(us.accesos, 0) AS accesos_restantes,
    COALESCE(us.accesos_hoy, 0)                       AS accesos_hoy,
    u.max_ingresos_diarios,
    COALESCE(ds.dias, 0)                              AS dias_entrenados_semana,
    u.max_dias_semanales,
    pg.ultimo                                         AS ultimo_pago,
    u.precio,
    COALESCE(pg.total, 0)                             AS pagado,
    u.precio - COALESCE(pg.total, 0)                  AS saldo,
    CASE
        WHEN u.id IS NULL                                        THEN 'sin_membresia'
        WHEN hoy.d >= u.fecha_vencimiento                        THEN 'vencida'
        WHEN hoy.d <  u.fecha_inicio                             THEN 'no_vigente'
        WHEN u.entrenamientos_mensuales IS NOT NULL
         AND COALESCE(us.accesos, 0) >= u.entrenamientos_mensuales THEN 'agotada'
        ELSE 'vigente'
    END                                               AS estado_membresia,
    CASE
        WHEN u.id IS NULL                              THEN 'sin_pase'
        WHEN u.precio - COALESCE(pg.total, 0) > 0      THEN 'debe'
        WHEN hoy.d >= u.fecha_vencimiento              THEN 'debe'
        WHEN u.fecha_vencimiento - hoy.d <= 5          THEN 'por_vencer'
        ELSE 'al_dia'
    END                                               AS estado_contable
FROM socio s
JOIN persona p        ON p.id = s.persona_id
CROSS JOIN hoy
LEFT JOIN actual u    ON u.socio_id = s.id
LEFT JOIN plan pl     ON pl.id = u.plan_id
LEFT JOIN pagos pg    ON pg.membresia_id = u.id
LEFT JOIN usados us   ON us.membresia_id = u.id
LEFT JOIN dias_semana ds ON ds.socio_id = s.id
WHERE s.activo;
