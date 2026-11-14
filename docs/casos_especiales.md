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
- **Configuración:** una tabla con los 7 días, cada uno con "Abierto", apertura
  y cierre. Al guardar, un día abierto queda con una sola franja activa con
  esas horas (se actualiza la existente o se crea) y un día cerrado desactiva
  sus franjas. Nunca se borra nada.

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

La membresía **comienza el día en que se registra el pago** (trabajo final,
punto 6.3), aunque el plan anterior todavía no haya vencido.

- **Ejemplo:** tiene un Pase libre del 20/10 al 20/11 y renueva el 13/11. El
  nuevo va del 13/11 al 13/12 y reemplaza al anterior desde ese día.
- **En pantalla:** Cobros y renovaciones muestra "Empieza hoy, dd/mm/aaaa, y
  vence el …" y, si tenía un plan vigente, "Reemplaza al plan actual desde hoy".
- **Estado del socio:** muestra el plan nuevo desde el día del pago. Si dos
  membresías están vigentes a la vez, `v_socio_estado` toma la que empezó más
  tarde.
- **Código:** `services/cobro_service.py`, `CobroService.vender`.

## Cambio de plan

Funciona igual que la renovación anticipada: el plan nuevo **empieza el día del
pago** y reemplaza al actual desde ese día.

- **Ejemplo:** tiene un Pase libre vigente y el 13/11 paga "3 veces por
  semana". Desde el 13/11 entra con los límites del plan nuevo.
- **Condiciones copiadas:** cada membresía copia el precio y los límites del
  plan en el momento de la venta. Si la dueña cambia un plan en Configuración,
  las membresías ya vendidas no cambian.
- **El plan anterior queda cerrado:** siempre que se vende un plan nuevo, las
  membresías anteriores del socio pasan a `cancelada` (el único estado cerrado
  del esquema). En Estado del socio figuran como "Cerrada".
- **Descuento solo en un caso:** si el socio tiene un Pase por día que empezó
  hoy y ese mismo día cambia a un plan mensual, se descuenta lo que pagó por el
  pase. Ejemplo: Pase por día $3.000 y "3 veces por semana" $40.000, se cobran
  $37.000 y la recaudación suma $40.000. El descuento queda en el precio de la
  membresía nueva. En cualquier otro caso (renovación, plan vencido, pase de
  otro día, de un pase a otro pase) se cobra el precio completo.

## Plan "3 veces por semana"

Es estricto: hasta 3 días distintos por semana (de lunes a domingo) y 1 ingreso
por día. Lo controlan "Días por semana" e "Ingresos por día" del plan.

- El cuarto día de la misma semana se rechaza con "Límite semanal". El lunes
  siguiente vuelve a entrar.
- Un segundo ingreso el mismo día se rechaza con "Ya ingresó hoy".
- Las semanas en que no vino no se compensan.
- "Accesos en la vigencia" (cupo total) va vacío, sin límite. Si se carga,
  Configuración avisa cuando es menor que días por semana × 5 (un mes puede
  tocar 5 semanas, porque empieza y termina a mitad de semana): con 3 días por
  semana, al menos 15. Es un aviso y no impide guardar.
- Cada membresía copia los límites del plan al venderse: cambiar el plan no
  cambia las membresías ya vendidas.

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

## Licencia o permiso del personal

La dueña los aprueba en **Jornadas**, con "Dar licencia" o "Dar permiso". No
hay tablas nuevas: se usan `jornada.estado` (`licencia_vacaciones` o `permiso`)
y `jornada_cambio`, que guarda el motivo, quién lo aprobó y cuándo.

- **Licencia:** se elige un rango de fechas. En cada día, los turnos cargados
  pasan a licencia; un día sin turno se crea como licencia de día completo.
- **Permiso:** se elige un día y, si hace falta, un rango de horas. Sin horas es
  de día completo (de 00:00 a 23:59). Con los turnos de ese día:

  | Turno | Permiso | Resultado |
  |---|---|---|
  | 14 a 22 | 14 a 16 (cubre el inicio) | Turno de 16 a 22 y permiso de 14 a 16 |
  | 14 a 22 | 20 a 23 (cubre el final) | Turno de 14 a 20 y permiso de 20 a 23 |
  | 14 a 22 | 13 a 23 o día completo (cubre todo) | El turno pasa a `permiso` con el horario del permiso |
  | 14 a 22 | 17 a 18 (en el medio) | El turno no cambia y el permiso tiene su fila |

  Cada turno corrido o acortado queda en `jornada_cambio` con el motivo
  "Permiso de HH:MM a HH:MM", quién lo aprobó y cuándo. Ningún horario lleva segundos.
- **Cámara:** desde que se aprueba, el empleado no puede marcar la llegada:
  - Licencia: "Hoy tenés licencia: no corresponde marcar llegada."
  - Permiso que cubre la hora actual: "Tenés permiso de HH:MM a HH:MM: no
    corresponde marcar llegada." (si es de día completo: "Hoy tenés permiso…").
  - Fuera del permiso por horas, puede marcar la llegada; la tardanza se cuenta
    desde que termina el permiso.
  - Si también es socio con membresía vigente, solo se le ofrece **Entrar**
    para entrenar.
  - Si ya había marcado la llegada antes de la aprobación, esa llegada es
    válida y puede marcar la salida.
- **Fichajes, Informes ("Asistencia del personal") y Panel:** esos días figuran
  como **"Licencia"** o **"Permiso"**, nunca como "Ausente", y no cuentan como tardanza.
- **Anular:** anula todo lo que se aprobó junto (todos los días de una
  licencia, o el permiso y los turnos que corrió) y queda en el historial
  con el motivo "Anulación". Cada turno vuelve a su horario y a `jornada`;
  en el ejemplo, el turno corrido vuelve de 16 a 22 a 14 a 22.
- **Anular en un día sin turno (y la fila propia de un permiso):** la fila que
  se creó con la licencia o el permiso no se borra (el historial la necesita y la base no permite borrar
  una jornada con cambios). Pasa a `jornada`, pero se reconoce por su
  historial (su alta tiene el mismo estado antes y después, y lo último que le
  pasó fue anularla) y no cuenta como turno: no aparece en Jornadas, Fichajes,
  Informes ni en la cámara, y nunca figura como "Ausente". Si su hora de
  entrada la necesita un turno que vuelve a su horario (la base no admite dos
  jornadas del mismo empleado que empiecen a la misma hora), queda guardada en
  el primer minuto libre del día. Si después se carga un turno o se da una
  licencia o un permiso ese día, se reutiliza esa fila.
- **Código:**
  - `services/reglas_ingreso.py`: `bloqueo_llegada` e `inicio_efectivo`.
  - `services/fichajes_service.py`: `dar_licencia`, `dar_permiso`, `anular` y `_minuto_libre`.
  - `repositories/jornada_repository.py`: `SIN_ANULADAS`.
