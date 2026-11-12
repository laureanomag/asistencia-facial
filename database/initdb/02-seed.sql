-- =====================================================================
--  ZEBRAGYM - Datos iniciales (ejecutar después de zebragym.sql)
-- =====================================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- solo para generar el hash de la cuenta inicial

-- Roles del sistema
INSERT INTO rol (codigo, nombre) VALUES
    ('administrador', 'Administrador'),
    ('recepcionista', 'Recepcionista'),
    ('entrenador',    'Entrenador');

-- Horario habitual: lunes a viernes de corrido, sábados a la mañana, domingos cerrado
INSERT INTO horario_atencion (dia_semana, hora_apertura, hora_cierre) VALUES
    (1, '07:00', '23:00'),
    (2, '07:00', '23:00'),
    (3, '07:00', '23:00'),
    (4, '07:00', '23:00'),
    (5, '07:00', '23:00'),
    (6, '10:00', '14:00');

-- Pases de ZebraGym. PRECIOS EN 0: cargar los valores reales antes de vender.
INSERT INTO plan (nombre, vigencia, entrenamientos_mensuales, max_dias_semanales, max_ingresos_diarios, precio) VALUES
    ('Pase por día',       INTERVAL '1 day',   NULL, NULL, 1,    0),
    ('3 veces por semana', INTERVAL '1 month', NULL, 3,    NULL, 0),
    ('Pase libre',         INTERVAL '1 month', NULL, NULL, NULL, 0);

-- Cuenta técnica inicial (sin persona). Obliga a cambiar la contraseña al primer ingreso.
INSERT INTO usuario (nombre_usuario, contrasenia_hash, debe_cambiar_contrasenia)
VALUES ('admin', crypt('admin123', gen_salt('bf', 12)), TRUE);

INSERT INTO usuario_rol (usuario_id, rol_id)
SELECT u.id, r.id FROM usuario u, rol r
WHERE u.nombre_usuario = 'admin' AND r.codigo = 'administrador';

-- Feriados: cargarlos desde el sistema a medida que se publican. Ejemplos:
-- INSERT INTO dia_especial (fecha, tipo, descripcion, abre)
--     VALUES ('2026-12-25', 'feriado_nacional', 'Navidad', FALSE);
-- INSERT INTO dia_especial (fecha, tipo, descripcion, abre, hora_apertura, hora_cierre)
--     VALUES ('2026-XX-XX', 'feriado_provincial', '...', TRUE, '09:00', '13:00');
