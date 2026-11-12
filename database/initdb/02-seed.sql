-- =====================================================================
--  ZEBRAGYM - Datos iniciales (ejecutar después de zebragym.sql)
-- =====================================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- solo para generar el hash de la cuenta inicial

-- Horario habitual: lunes a viernes de 7:30 a 23, sábados a la mañana, domingos cerrado
INSERT INTO horario_atencion (dia_semana, hora_apertura, hora_cierre) VALUES
    (1, '07:30', '23:00'),
    (2, '07:30', '23:00'),
    (3, '07:30', '23:00'),
    (4, '07:30', '23:00'),
    (5, '07:30', '23:00'),
    (6, '10:00', '14:00');

-- Pases de ZebraGym. PRECIOS EN 0: cargar los valores reales antes de vender.
INSERT INTO plan (nombre, vigencia, entrenamientos_mensuales, max_dias_semanales, max_ingresos_diarios, precio) VALUES
    ('Pase por día',       INTERVAL '1 day',   NULL, NULL, 1,    0),
    ('3 veces por semana', INTERVAL '1 month', NULL, 3,    NULL, 0),
    ('Pase libre',         INTERVAL '1 month', NULL, NULL, NULL, 0);

-- Cuenta técnica inicial (sin persona). Obliga a cambiar la contraseña al primer ingreso.
INSERT INTO usuario (nombre_usuario, contrasenia_hash, debe_cambiar_contrasenia)
VALUES ('admin', crypt('admin123', gen_salt('bf', 12)), TRUE);

INSERT INTO usuario_rol (usuario_id, rol)
SELECT id, 'administrador' FROM usuario WHERE nombre_usuario = 'admin';
