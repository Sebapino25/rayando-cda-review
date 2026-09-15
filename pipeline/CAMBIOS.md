# Cambios aplicados — eliminar las notificaciones por mail del disparador automático (15/09)

`auto_procesar.ps1` mandaba mails de aviso/error vía Resend, pero la cuenta
está en modo sandbox: con más de un destinatario (`to` con 3 direcciones),
Resend devolvía `403 validation_error` y ni siquiera le llegaba al dueño de
la cuenta (confirmado varias veces en
`pipeline\logs_auto\auto_procesar_errores.log`, la última el 15/09 tras la
limpieza automática de la cola). En vez de verificar un dominio propio en
Resend para arreglarlo, se decidió sacar el mail directamente — no es
necesario, el equipo revisa la app a mano.

- **`pipeline/auto_procesar.ps1`**: se eliminó `Enviar-Alerta`, la
  dependencia de `RESEND_API_KEY` (incluido el `throw` que abortaba todo el
  script si faltaba) y `Get-DotEnvValue` (que solo se usaba para leerla).
  Cada paso (procesamiento de grabación nueva, corrección de video,
  corrección de subtítulos, limpieza de cola, ritmo del disparador) ahora
  escribe el mismo mensaje informativo directo en
  `pipeline\logs_auto\loop.log` (éxito) o `auto_procesar_errores.log`
  (fallo), vía dos helpers nuevos `Log-Evento` / `Log-Error`. No cambia
  ninguna otra lógica (ritmo adaptativo, reintentos, restauración ante
  fallo de corrección de video, etc.).
- **`pipeline/.env.example`**: se sacó la variable `RESEND_API_KEY`.
- **`pipeline/README.md`**: se actualizó la sección "Disparador automático"
  para reflejar que ya no hay notificaciones por mail, solo logs en
  `pipeline\logs_auto\`.

No toca `supabase/functions/_shared/email.ts` (usado por las Edge
Functions, ej. `publicar-clip`) — es un sistema de alertas separado que
solo manda al dueño del proyecto y nunca dio el error 403.

**Pendiente de Seba:** ninguno — el cambio es local y no requiere deploy
(no toca Supabase ni la app; solo corre la próxima vez que Task Scheduler
dispare `auto_procesar.ps1`).
