CREATE TABLE "alumno"(
    "id" SERIAL NOT NULL,
    "nombre" VARCHAR(255) NOT NULL,
    "contrasena" VARCHAR(255) NOT NULL,
    "carrera" VARCHAR(255) NOT NULL,
    "celular" VARCHAR(255) NOT NULL,
    "correo_electronico" VARCHAR(255) NOT NULL,
    "fecha_nacimiento" DATE NOT NULL,
    "anio_ingreso" INTEGER NOT NULL,
    "domicilio" VARCHAR(255) NOT NULL,
    "libreta" VARCHAR(255) NOT NULL
);
ALTER TABLE
    "alumno" ADD PRIMARY KEY("id");
ALTER TABLE
    "alumno" ADD CONSTRAINT "alumno_nombre_unique" UNIQUE("nombre");
CREATE TABLE "foto_alumno"(
    "id" SERIAL NOT NULL,
    "alumno_id" INTEGER NOT NULL,
    "angulo" VARCHAR(255) CHECK
        (
            "angulo" IN(
                'frente',
                'perfil_derecho',
                'perfil_izquierdo'
            )
        ) NOT NULL,
        "imagen" bytea NOT NULL
);
ALTER TABLE
    "foto_alumno" ADD PRIMARY KEY("id");
CREATE TABLE "usuario"(
    "id" SERIAL NOT NULL,
    "nombre_usuario" VARCHAR(255) NOT NULL,
    "correo_electronico" VARCHAR(255) NULL,
    "dni" VARCHAR(255) NULL,
    "cuil" VARCHAR(255) NULL,
    "contrasenia" VARCHAR(255) NOT NULL
);
ALTER TABLE
    "usuario" ADD PRIMARY KEY("id");
ALTER TABLE
    "usuario" ADD CONSTRAINT "usuario_nombre_usuario_unique" UNIQUE("nombre_usuario");
ALTER TABLE
    "usuario" ADD CONSTRAINT "usuario_correo_electronico_unique" UNIQUE("correo_electronico");
ALTER TABLE
    "usuario" ADD CONSTRAINT "usuario_dni_unique" UNIQUE("dni");
ALTER TABLE
    "usuario" ADD CONSTRAINT "usuario_cuil_unique" UNIQUE("cuil");
CREATE TABLE "asistencia"(
    "id" SERIAL NOT NULL,
    "alumno_id" INTEGER NOT NULL,
    "entrada" TIMESTAMP(0) WITHOUT TIME ZONE NOT NULL,
    "salida" TIMESTAMP(0) WITHOUT TIME ZONE NULL,
    "jornada_id" BIGINT NOT NULL
);
ALTER TABLE
    "asistencia" ADD PRIMARY KEY("id");
CREATE TABLE "jornada"(
    "id" SERIAL NOT NULL,
    "fecha" DATE NOT NULL,
    "horario_salida" TIME(0) WITHOUT TIME ZONE NOT NULL,
    "horario_entrada" TIME(0) WITHOUT TIME ZONE NOT NULL,
    "usuario_id" BIGINT NOT NULL
);
ALTER TABLE
    "jornada" ADD PRIMARY KEY("id");
ALTER TABLE
    "asistencia" ADD CONSTRAINT "asistencia_jornada_id_foreign" FOREIGN KEY("jornada_id") REFERENCES "jornada"("id");
ALTER TABLE
    "foto_alumno" ADD CONSTRAINT "foto_alumno_alumno_id_foreign" FOREIGN KEY("alumno_id") REFERENCES "alumno"("id");
ALTER TABLE
    "jornada" ADD CONSTRAINT "jornada_usuario_id_foreign" FOREIGN KEY("usuario_id") REFERENCES "usuario"("id");
ALTER TABLE
    "asistencia" ADD CONSTRAINT "asistencia_alumno_id_foreign" FOREIGN KEY("alumno_id") REFERENCES "alumno"("id");