# Casos especiales

Este documento describe cómo resuelve ZebraGym los casos que no son el ingreso
normal. Para cada caso indica qué ve la persona en pantalla, qué queda guardado
en la base y dónde está la regla en el código.

## Intentos repetidos

- **Misma persona:** después de cualquier decisión (confirmar, cancelar o
  rechazo), la cámara ignora a esa persona durante **10 s**. El chip muestra
  "Reintento en N s". Así un socio que se queda frente a la cámara no se
  registra dos veces.
- **Confirmación de identidad:** para abrir el modal hacen falta **2
  reconocimientos seguidos** de la misma persona dentro de 8 s.
- **Doble confirmación:** cada propuesta tiene un código de un solo uso. Un
  segundo clic vuelve a evaluar las reglas y, por ejemplo, rechaza con "Ya
  ingresó hoy" si el plan permite 1 ingreso por día.
- **Rostro no reconocido:** se guarda un rechazo `no_reconocido` recién al
  **tercer intento seguido**. Después, durante 10 s no se vuelve a guardar.
- **Código:**
  - `services/acceso_service.py`: `Antirrebote`, `GestorPropuestas` y `ContadorNoReconocidos`.
  - `services/recognition_logic.py`.

## Gimnasio cerrado

- **Socio:** fuera de las franjas activas de `horario_atencion` se le rechaza
  la entrada con el motivo `gimnasio_cerrado`. El mensaje dice el horario del
  día, por ejemplo "Horario de hoy: 07:30 a 23:00 hs".
- **Día sin franjas activas:** es un día cerrado. Por ejemplo, el domingo en el seed.
- **Empleados:** pueden fichar aunque el gimnasio esté cerrado.
- **Socio que también es empleado:** "Entrenar" aparece deshabilitado con el
  motivo, y "Trabajar" sigue disponible.
- **Configuración:** las franjas se agregan sin superponerse y se activan o
  desactivan. Nunca se borran.

## Socio sin membresía

| Situación | Motivo guardado | Mensaje |
|---|---|---|
| Nunca compró un plan | `sin_membresia` | "No tiene una membresía. Pasá por el mostrador para contratar un plan." |
| La última venció | `membresia_vencida` | "Su membresía venció el dd/mm/aaaa. Renovala en el mostrador." |
| Compró un plan que empieza más adelante | `membresia_no_vigente` | "Su membresía empieza el dd/mm/aaaa." |
| Usó todo el cupo del plan | `cupo_agotado` | "Ya usó los N accesos de su plan." |
| Dado de baja | `socio_inactivo` | "El socio está dado de baja. Consultá en el mostrador." |

Cada rechazo queda en la tabla `acceso` y aparece en Informes.

## Renovación anticipada

Si el socio renueva antes de que venza su plan, el plan nuevo **empieza el día
en que vence el actual**, así que no pierde días.

- **Ejemplo:** tiene un Pase libre del 20/10 al 20/11 y renueva el 13/11. El
  nuevo va del 20/11 al 20/12.
- **Mientras tanto:** Estado del socio sigue mostrando el plan vigente hasta
  que empieza el nuevo.
- **En pantalla:** Cobros y renovaciones lo avisa con "Renovación anticipada:
  empieza cuando vence el plan actual".
- **Código:** `services/cobro_service.py`, `fecha_inicio_nueva`.

## Cambio de plan

Funciona igual que la renovación anticipada: el plan nuevo empieza cuando
vence el actual.

- **Condiciones copiadas:** cada membresía copia el precio y los límites del
  plan en el momento de la venta. Si la dueña cambia un plan en Configuración,
  las membresías ya vendidas no cambian.
- **Pendiente:** cambiar de plan en el acto, cancelando el actual, no está
  disponible en la interfaz. Si hace falta, se agrega como una función aparte.

## Meses de 28 a 31 días

El vencimiento lo calcula PostgreSQL como `fecha_inicio + plan.vigencia`. La
mensualidad dura exactamente un mes calendario:

| Inicio | Vencimiento |
|---|---|
| 20/10 | 20/11 |
| 31/01 | 28/02 (29/02 en año bisiesto) |
| 31/03 | 30/04 |

- **Último día:** el plan es válido hasta el día **anterior** al vencimiento.
  El día del vencimiento ya hay que renovar.
- **Código:** `MembresiaRepository.crear` y `calcular_vencimiento`.

## Pago parcial

- **En Cobros:** se puede cobrar menos que el precio. La membresía se crea
  igual y el resto queda como **saldo**.
- **Entrada al gimnasio:** el socio con saldo **puede entrar**. El modal de la
  cámara muestra "Estado contable: Debe $X" en rojo.
- **Dónde se ve el saldo:**
  - En Cobros y renovaciones, en "Saldo pendiente", donde además se cobra.
  - En Estado del socio.
  - En el informe de membresías.
- **Validaciones:** el monto no puede ser $0 ni superar el precio o el saldo.

## Socio que también es empleado

La persona es una sola, con un DNI y unas fotos, aunque tenga ficha de socio y
cuenta de empleado. Al reconocerla, el modal pregunta "¿Qué vas a hacer?" y
muestra una línea por condición:

- "Empleado · Turno 14:00–22:00 · En horario / Fuera de turno / Sin turno hoy"
- "Socio · {plan} · Vigente (vence dd/mm) / Vencida / Sin membresía"

Los botones son **Cancelar · Trabajar · Entrenar**:

- **Botón en dorado:** es la opción más probable. Es **Trabajar** si está en su
  turno, a menos de 30 min del inicio o con la llegada ya marcada (en ese caso
  el botón dice "Me voy"). Si no, es **Entrenar**.
- **Entrenar deshabilitado:** si no puede entrenar (membresía vencida,
  gimnasio cerrado, límite del plan), el botón aparece deshabilitado y debajo
  se explica el motivo. En ese caso no se guarda un rechazo, porque vino a trabajar.
- **Trabajar deshabilitado:** si acaba de marcar la llegada, Trabajar queda
  deshabilitado con "Ya marcaste tu llegada a las HH:MM".
- **Cuenta desactivada:** solo ve el modal de socio y puede seguir entrenando.
- **Socio dado de baja:** solo ve el modal de asistencia laboral.

## Fichaje fuera de turno

- **Turno:** la llegada se vincula a la jornada del día si llega **hasta 30 min
  antes** del inicio o dentro del turno.
  - Antes del inicio figura "En horario".
  - Después del inicio figura "Llegaste N min tarde".
- **Fuera de turno:** sin jornada ese día, fuera del horario o con licencia, se
  ficha igual, pero queda sin jornada (`jornada_id` NULL). En el modal y en
  "Fichajes del personal" figura como **"Fuera de turno"**.
- **Licencia o permiso:** si el día figura con licencia o permiso, el modal lo avisa.
- **Salida:** se propone recién 10 min después de la llegada, para que el
  reconocimiento siguiente no cierre una entrada recién marcada. Al salir se
  muestra "Trabajaste H h MM min".
- **Entrada abierta de otro día:** al reconocerlo se propone cerrarla y se
  avisa la fecha.
- **Código:** `services/reglas_ingreso.py`, `evaluar_fichaje`.
