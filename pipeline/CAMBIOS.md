# Cambios aplicados — OpenCV opcional, pedidos de corte relativos y portadas por agencia (01/10)

**Incidente del 30/09:** Smart App Control de Windows (modo activo) empezó a
bloquear `Python312\Lib\site-packages\cv2\cv2.pyd` (sin firma digital) y
`import cv2` fallaba con "Una directiva de Control de aplicaciones bloqueó
este archivo". Como `portadas.py` lo importaba al cargar, caían
`reprocesar_video.py` y `reprocesar_subtitulos.py` (las correcciones del
programa del 28/09 quedaron sin procesar). Diagnóstico: eventos 3077/3033 en
el registro `Microsoft-Windows-CodeIntegrity/Operational`. **No se apagó
Smart App Control** (no se puede reactivar sin reinstalar Windows).

- **`pipeline/portadas.py`** (commit `b7a5a5c`): OpenCV es opcional. Si no
  carga, la nitidez se calcula con numpy (`_laplacian_var`) y se omite la
  detección de rostros/ojos (el score queda solo por nitidez). Imprime un
  aviso, no falla. Test: `test_portadas_sin_opencv.py`.
- **Pedidos de corte relativos** (mismo commit): `interpretar_correccion`
  nunca recibía el inicio/fin actual del clip, así que "empezá 15 segundos
  antes" siempre daba `confianza=false`. Ahora `reprocesar_video.buscar_pendientes`
  trae `timestamp_inicio/fin` y se los pasa ("Rango actual del clip") junto con
  una instrucción en el prompt. Test nuevo en `test_interpretar_correccion.py`.
- **Botón "Pedir portada a la agencia"** (commit `e5def12`): columna nueva
  `rayando_cda.clips.portada_agencia_solicitada_en` (migración aplicada el
  01/10, documentada en `supabase_migration_clips.sql`) + botón en
  `ClipCard.jsx`. La agencia hace la portada en el proyecto `El_Proyecto`
  (`tools/audiovisual/portada_clip.py`, ver `docs/proceso-portadas-clip.md`
  allá) y deja la imagen en `portada_url`. No pisa portadas subidas a mano
  (`/portadas/custom/`).

**Operación:** la tarea `RayandoCDA_AutoProcesar` solo corre en su ventana
semanal (martes → miércoles ~11:00). Correcciones hechas después no se
procesan hasta el martes siguiente: se pueden forzar con
`Start-ScheduledTask -TaskName RayandoCDA_AutoProcesar`. Si un pedido de
corrección fue rechazado por la IA, no se reintenta hasta que cambie su
texto; para forzarlo sin cambiarlo, borrar su entrada en
`logs_auto\correccion_video_fallos.log`.

---

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
