-- Ajustes de base de datos para los incrementos 5 y 6.
-- Se puede ejecutar más de una vez: no repite ni borra nada.

-- El DER del profe tiene alumno.nombre pero no apellido ni dni; el formulario
-- de registro y los informes (incremento 6) los usan.
ALTER TABLE alumno ADD COLUMN IF NOT EXISTS apellido VARCHAR;
ALTER TABLE alumno ADD COLUMN IF NOT EXISTS dni VARCHAR;

-- Los requisitos del incremento 5 exigen cátedra en jornada.
ALTER TABLE jornada ADD COLUMN IF NOT EXISTS catedra VARCHAR NOT NULL DEFAULT '';

-- Aporte propio: el alumno llegó después de la tolerancia de entrada.
ALTER TABLE asistencia ADD COLUMN IF NOT EXISTS tardanza BOOLEAN NOT NULL DEFAULT FALSE;

-- Una única fila de asistencia por combinación jornada_id + alumno_id.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_asistencia_jornada_alumno'
    ) THEN
        ALTER TABLE asistencia
            ADD CONSTRAINT uq_asistencia_jornada_alumno UNIQUE (jornada_id, alumno_id);
    END IF;
END $$;

-- Verificación: deben aparecer las 5 columnas.
SELECT table_name, column_name FROM information_schema.columns
WHERE (table_name = 'alumno'     AND column_name IN ('apellido', 'dni'))
   OR (table_name = 'jornada'    AND column_name = 'catedra')
   OR (table_name = 'asistencia' AND column_name = 'tardanza')
ORDER BY table_name, column_name;
