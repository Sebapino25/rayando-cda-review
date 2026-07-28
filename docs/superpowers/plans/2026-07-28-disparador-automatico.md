# Disparador automático semanal — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que el pipeline (`transcribir.py` + `procesar_programa.py`) se dispare solo cuando aparece una grabación nueva, sobreviviendo a reinicios de la PC, con notificaciones enriquecidas (equipo avisado al terminar bien, tail del log si falla) y sin el punto de fallo silencioso encontrado hoy (`$ErrorActionPreference = "Stop"` ya corregido en una sesión previa a este plan).

**Architecture:** Una tarea de Task Scheduler ("RayandoCDA_AutoProcesar") con trigger "al iniciar sesión" arranca `auto_procesar_loop.ps1` (ya probado, corre desde 2026-07-27), que cada 5 min corre `auto_procesar.ps1`. Se modifican las notificaciones de ese script (destinatarios distintos para éxito/fallo, tail de log en fallo) y se endurece el fallback a CPU de `transcribir.py` para que un fallo ahí deje un mensaje claro. Un script nuevo (`registrar_tarea_programada.ps1`) registra la tarea de forma idempotente y repetible.

**Tech Stack:** PowerShell 5.1 (Windows Task Scheduler vía `Register-ScheduledTask`), Python 3.12, API de Resend para email.

## Global Constraints

- Trigger de Task Scheduler: `AtLogOn` del usuario actual, sin guardar contraseña (no usar `-User`/`-Password` con credenciales).
- Un solo proceso del loop corriendo a la vez — matar cualquier loop manual antes de que la tarea registrada levante el suyo.
- Mail de éxito ("procesamiento automático completo") va a: `seba.pino.v@gmail.com`, `Cristian.fajardoc@gmail.com`, `arriagada.rene@gmail.com`. Cuerpo incluye el link `https://sebapino25.github.io/rayando-cda-review/`.
- Mail de fallo va solo a `seba.pino.v@gmail.com`, con las últimas 30 líneas del log de esa corrida incluidas en el cuerpo.
- No se toca la lógica de detección/procesamiento en sí (`procesar_programa.py`, la detección de candidatos en `auto_procesar.ps1`).
- No se implementa un watchdog separado para "Task Scheduler no disparó en absoluto" — fuera de alcance.
- `$ErrorActionPreference` en `auto_procesar.ps1` debe seguir siendo `"Continue"` (ya corregido, no revertir).

---

### Task 1: Notificaciones enriquecidas en `auto_procesar.ps1`

**Files:**
- Modify: `pipeline/auto_procesar.ps1`

**Interfaces:**
- Produces: función `Enviar-Alerta($asunto, $cuerpo, $destinatarios = @($AlertEmail))` (nuevo tercer parámetro opcional; los llamadores existentes sin ese parámetro siguen mandando solo a `$AlertEmail`, comportamiento actual sin cambios salvo donde se pase explícitamente). Función nueva `Obtener-TailLog($logFile, $lineas = 30)` que devuelve un string con las últimas N líneas del archivo (o `"(no se encontró el log)"` si no existe).

- [ ] **Step 1: Agregar las variables de destinatarios y URL de la app**

En `pipeline/auto_procesar.ps1`, después de la línea `$AlertEmail = "seba.pino.v@gmail.com"`, agregar:

```powershell
$TeamEmails = @($AlertEmail, "Cristian.fajardoc@gmail.com", "arriagada.rene@gmail.com")
$AppUrl = "https://sebapino25.github.io/rayando-cda-review/"
```

- [ ] **Step 2: Modificar `Enviar-Alerta` para aceptar destinatarios, y agregar `Obtener-TailLog`**

Reemplazar la función `Enviar-Alerta` actual por:

```powershell
function Enviar-Alerta($asunto, $cuerpo, $destinatarios = @($AlertEmail)) {
    try {
        $body = @{
            from    = "Rayando el CDA <onboarding@resend.dev>"
            to      = @($destinatarios)
            subject = $asunto
            text    = $cuerpo
        } | ConvertTo-Json
        Invoke-RestMethod -Uri "https://api.resend.com/emails" -Method Post `
            -Headers @{ Authorization = "Bearer $ResendApiKey"; "Content-Type" = "application/json" } `
            -Body $body | Out-Null
    } catch {
        Add-Content -Path (Join-Path $LogsDir "auto_procesar_errores.log") -Value "$(Get-Date -Format o) No se pudo enviar alerta ('$asunto'): $_"
    }
}

function Obtener-TailLog($logFile, $lineas = 30) {
    if (-not (Test-Path $logFile)) { return "(no se encontró el log)" }
    return (Get-Content -Path $logFile -Tail $lineas -Encoding UTF8) -join "`n"
}
```

- [ ] **Step 3: Actualizar los dos call sites**

Reemplazar:

```powershell
        Enviar-Alerta "Rayando el CDA: procesamiento automático completo" "Se procesó $($rec.Name) automáticamente. Entrá a la app para revisar y aprobar los clips. Log: $logFile"
    } catch {
        Enviar-Alerta "Rayando el CDA: falló el procesamiento automático" "Falló procesando $($rec.Name): $_`n`nRevisar el log en $logFile y correr los pasos a mano si hace falta (ver pipeline/README.md)."
    } finally {
```

por:

```powershell
        Enviar-Alerta "Rayando el CDA: procesamiento automático completo" "Se procesó $($rec.Name) automáticamente. Entrá a la app para revisar y aprobar los clips: $AppUrl`n`nLog: $logFile" $TeamEmails
    } catch {
        $tail = Obtener-TailLog $logFile
        Enviar-Alerta "Rayando el CDA: falló el procesamiento automático" "Falló procesando $($rec.Name): $_`n`nÚltimas líneas del log ($logFile):`n$tail`n`nRevisar el log completo y correr los pasos a mano si hace falta (ver pipeline/README.md)."
    } finally {
```

- [ ] **Step 4: Probar el envío y el formato, sin mandarle nada al equipo todavía**

Correr esto en PowerShell (usa las mismas funciones ya editadas, pero fuerza el destinatario a vos mismo para no mandarle un mail de prueba a Cristian/René):

```powershell
$ResendApiKey = (Get-Content (Join-Path $PSScriptRoot ".env") | Where-Object { $_ -match "^\s*RESEND_API_KEY\s*=" } | Select-Object -First 1) -replace "^\s*RESEND_API_KEY\s*=", "" -replace '"', ''
$AlertEmail = "seba.pino.v@gmail.com"
$AppUrl = "https://sebapino25.github.io/rayando-cda-review/"
$logFileTest = "$env:TEMP\test_tail.log"
"linea 1`nlinea 2`nlinea 3" | Set-Content $logFileTest

function Obtener-TailLog($logFile, $lineas = 30) {
    if (-not (Test-Path $logFile)) { return "(no se encontró el log)" }
    return (Get-Content -Path $logFile -Tail $lineas -Encoding UTF8) -join "`n"
}

$tail = Obtener-TailLog $logFileTest
$cuerpoExito = "Se procesó video-de-prueba.mkv automáticamente. Entrá a la app para revisar y aprobar los clips: $AppUrl`n`nLog: $logFileTest"
$cuerpoFallo = "Falló procesando video-de-prueba.mkv: excepción de prueba`n`nÚltimas líneas del log ($logFileTest):`n$tail`n`nRevisar el log completo."

foreach ($cuerpo in @($cuerpoExito, $cuerpoFallo)) {
    $body = @{ from = "Rayando el CDA <onboarding@resend.dev>"; to = @($AlertEmail); subject = "PRUEBA formato mail"; text = $cuerpo } | ConvertTo-Json
    Invoke-RestMethod -Uri "https://api.resend.com/emails" -Method Post -Headers @{ Authorization = "Bearer $ResendApiKey"; "Content-Type" = "application/json" } -Body $body | Out-Null
}
Write-Host "2 mails de prueba mandados a $AlertEmail — revisar que el link y el tail del log se vean bien."
```

Expected: llegan 2 mails a `seba.pino.v@gmail.com` ("PRUEBA formato mail"), uno con el link de la app legible y uno con las 3 líneas de prueba bajo "Últimas líneas del log". Confirmar visualmente antes de seguir.

- [ ] **Step 5: Commit**

```bash
git add pipeline/auto_procesar.ps1
git commit -m "auto_procesar.ps1: avisar al equipo cuando termina bien, incluir tail del log en el mail de fallo"
```

---

### Task 2: Endurecer el fallback a CPU en `transcribir.py`

**Files:**
- Modify: `pipeline/transcribir.py:84-100` (función `load_model_and_start`)
- Create: `pipeline/test_transcribir_cpu_fallback.py`

**Interfaces:**
- Consumes: `transcribir.WhisperModel` (referencia al símbolo importado en el módulo, no la clase real — se monkeypatchea en el test).
- Produces: `load_model_and_start(video_path, model_size)` sigue devolviendo `(first, iterator, info)` en el camino feliz; si GPU y CPU fallan, sigue lanzando la excepción original de CPU (comportamiento sin cambios), pero ahora imprime `"Falló también en CPU (...)."` por stdout antes de relanzarla.

Este repo no usa pytest — los scripts de prueba existentes (`test_instagram_publish.py`) son scripts standalone que se corren con `python archivo.py` y usan `assert` simple. Seguimos ese mismo patrón acá en vez de sumar pytest como dependencia nueva.

- [ ] **Step 1: Escribir el test standalone (que hoy falla)**

Crear `pipeline/test_transcribir_cpu_fallback.py`:

```python
"""Prueba AISLADA de que load_model_and_start() deja un mensaje claro si
tanto GPU como CPU fallan al cargar el modelo. No requiere GPU real ni
modelo de Whisper descargado: reemplaza WhisperModel por una función que
siempre lanza una excepción.

Uso:
    python test_transcribir_cpu_fallback.py
"""
from __future__ import annotations

import contextlib
import io
from pathlib import Path
from unittest.mock import patch

import transcribir


def fake_whisper_model(model_size, device, compute_type):
    raise RuntimeError(f"fake fail on {device}")


def main() -> None:
    buf = io.StringIO()
    excepcion_capturada = None

    with patch.object(transcribir, "WhisperModel", fake_whisper_model):
        with contextlib.redirect_stdout(buf):
            try:
                transcribir.load_model_and_start(Path("video-inexistente.mkv"), "medium")
            except RuntimeError as e:
                excepcion_capturada = e

    salida = buf.getvalue()
    print(salida)

    assert excepcion_capturada is not None, "Se esperaba que la excepción de CPU se relance"
    assert "fake fail on cpu" in str(excepcion_capturada), (
        f"La excepción relanzada debería ser la de CPU, fue: {excepcion_capturada}"
    )
    assert "No se pudo usar GPU" in salida, "Falta el mensaje de fallback GPU->CPU"
    assert "Falló también en CPU" in salida, (
        "Falta el mensaje claro de que el fallback a CPU también falló"
    )

    print("OK: el fallback a CPU deja un mensaje claro y relanza la excepción original.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Correr el test y confirmar que falla**

Run: `cd pipeline && python test_transcribir_cpu_fallback.py`
Expected: `AssertionError: Falta el mensaje claro de que el fallback a CPU también falló` (porque el código actual no imprime ese mensaje).

- [ ] **Step 3: Implementar el manejo de errores en `load_model_and_start`**

En `pipeline/transcribir.py`, reemplazar la función completa (líneas 84-100):

```python
def load_model_and_start(video_path: Path, model_size: str):
    try:
        model = WhisperModel(
            model_size, device="cuda", compute_type=config.WHISPER_COMPUTE_TYPE_GPU
        )
        first, iterator, info = _start_transcription(model, video_path)
        print(f"Modelo '{model_size}' corriendo en GPU (CUDA, {config.WHISPER_COMPUTE_TYPE_GPU}).")
        return first, iterator, info
    except Exception as e:
        print(f"No se pudo usar GPU ({e}).")
        print(f"Cargando modelo '{model_size}' en CPU ({config.WHISPER_COMPUTE_TYPE_CPU})...")
        try:
            model = WhisperModel(
                model_size, device="cpu", compute_type=config.WHISPER_COMPUTE_TYPE_CPU
            )
            first, iterator, info = _start_transcription(model, video_path)
            print("Modelo corriendo en CPU.")
            return first, iterator, info
        except Exception as e2:
            print(f"Falló también en CPU ({e2}).")
            raise
```

- [ ] **Step 4: Correr el test y confirmar que pasa**

Run: `cd pipeline && python test_transcribir_cpu_fallback.py`
Expected: termina con `OK: el fallback a CPU deja un mensaje claro y relanza la excepción original.` y código de salida 0.

- [ ] **Step 5: Confirmar que el camino feliz (GPU) sigue andando**

Run: `cd pipeline && python transcribir.py --help`
Expected: muestra el usage sin errores de import (confirma que la edición no rompió la sintaxis del archivo). No hace falta correr una transcripción real de nuevo — ya se verificó hoy a mano con la grabación real.

- [ ] **Step 6: Commit**

```bash
git add pipeline/transcribir.py pipeline/test_transcribir_cpu_fallback.py
git commit -m "transcribir.py: mensaje claro si el fallback a CPU también falla al cargar el modelo"
```

---

### Task 3: Script de registro idempotente de la tarea de Task Scheduler

**Files:**
- Create: `pipeline/registrar_tarea_programada.ps1`

**Interfaces:**
- Consumes: `pipeline/auto_procesar_loop.ps1` (ruta fija, ya existe).
- Produces: tarea de Task Scheduler `RayandoCDA_AutoProcesar` registrada y arrancada; ningún otro task del plan depende de esto directamente, es el punto de entrada operativo.

- [ ] **Step 1: Escribir el script de registro**

Crear `pipeline/registrar_tarea_programada.ps1`:

```powershell
# Registra (o re-registra) la tarea de Task Scheduler "RayandoCDA_AutoProcesar":
# arranca auto_procesar_loop.ps1 al iniciar sesión de este usuario, sin pedir
# ni guardar contraseña. Idempotente: si la tarea ya existe, la borra y la
# vuelve a crear. Además mata cualquier loop que haya quedado corriendo a
# mano, para no terminar con dos loops en paralelo.
#
# Uso (una sola vez, o de nuevo si hace falta re-registrar):
#   powershell -ExecutionPolicy Bypass -File registrar_tarea_programada.ps1

$ErrorActionPreference = "Stop"

$TaskName = "RayandoCDA_AutoProcesar"
$LoopScript = "C:\Users\sebap\rayando-cda\pipeline\auto_procesar_loop.ps1"

Write-Host "Buscando loops manuales corriendo para matarlos..."
Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" |
    Where-Object { $_.CommandLine -and $_.CommandLine -like "*auto_procesar_loop.ps1*" } |
    ForEach-Object {
        Write-Host "  Matando loop manual previo (PID $($_.ProcessId))..."
        Stop-Process -Id $_.ProcessId -Force
    }

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Write-Host "Ya existe la tarea '$TaskName', la borro para re-registrarla..."
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$LoopScript`""
$trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
# ExecutionTimeLimit = 0 (sin límite): el loop corre indefinidamente hasta
# que se cierre sesión. El límite por defecto de Task Scheduler es 3 días —
# sin esto, mataría el loop en silencio a los 3 días, el mismo tipo de fallo
# silencioso que ya se vio hoy con RepetitionDuration en triggers repetitivos.
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings `
    -Description "Arranca el loop de procesamiento automático de Rayando el CDA al iniciar sesión (ver pipeline/README.md)." | Out-Null

Write-Host "Tarea '$TaskName' registrada. Arrancándola ahora (sin esperar al próximo login)..."
Start-ScheduledTask -TaskName $TaskName
Start-Sleep -Seconds 3

Get-ScheduledTaskInfo -TaskName $TaskName | Format-List TaskName, LastRunTime, LastTaskResult, NextRunTime
```

- [ ] **Step 2: Correr el script**

Run: `powershell -ExecutionPolicy Bypass -File pipeline\registrar_tarea_programada.ps1`
Expected: imprime que mató el loop manual previo (PID de esta sesión), registra la tarea, y el `Get-ScheduledTaskInfo` final muestra `LastTaskResult : 0`.

- [ ] **Step 3: Verificar que la tarea quedó bien configurada**

Run: `Get-ScheduledTask -TaskName RayandoCDA_AutoProcesar | Select-Object TaskName, State`
Expected: `State` es `Ready` (no `Disabled` ni `Running` colgado).

- [ ] **Step 4: Verificar que hay exactamente un loop corriendo**

Run: `Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" | Where-Object { $_.CommandLine -like "*auto_procesar_loop.ps1*" } | Measure-Object | Select-Object -ExpandProperty Count`
Expected: `1`.

- [ ] **Step 5: Verificar que el loop nuevo efectivamente arrancó**

Run: `Get-Content pipeline\logs_auto\loop.log -Tail 3`
Expected: última línea es `Loop de respaldo iniciado (PID ...)` con un timestamp de los últimos segundos y un PID distinto al que tenía el loop manual de antes.

- [ ] **Step 6: Commit**

```bash
git add pipeline/registrar_tarea_programada.ps1
git commit -m "Agregar script de registro idempotente de la tarea de Task Scheduler"
```

---

### Task 4: Commitear los scripts existentes y documentar en el README

**Files:**
- Create (commit por primera vez, ya existían sin trackear): `pipeline/auto_procesar_loop.ps1`
- Modify: `pipeline/README.md`

**Interfaces:** Ninguna — tarea de documentación, no cambia comportamiento de código.

- [ ] **Step 1: Agregar sección al README**

En `pipeline/README.md`, después de la sección "## Publicación (YouTube no listado + Supabase)" (antes de "## Diccionario de nombres propios..."), agregar:

```markdown
## Disparador automático (Task Scheduler)

Una tarea de Windows Task Scheduler llamada `RayandoCDA_AutoProcesar`
arranca `auto_procesar_loop.ps1` al iniciar sesión, que cada 5 minutos
corre `auto_procesar.ps1`: si hay una grabación nueva en `grabaciones\`
(sin transcripción todavía y sin cambios en los últimos 5 min, para no
agarrar un archivo que OBS todavía está escribiendo), corre
`transcribir.py` + `procesar_programa.py` sola.

**Notificaciones por mail (vía Resend):**
- Al terminar bien: aviso a todo el equipo (`seba.pino.v@gmail.com`,
  `Cristian.fajardoc@gmail.com`, `arriagada.rene@gmail.com`) con el link a
  la app para revisar los clips nuevos.
- Si falla: aviso solo a `seba.pino.v@gmail.com`, con las últimas líneas
  del log de esa corrida incluidas en el mail. El log completo queda en
  `pipeline\logs_auto\<nombre-grabación>.log`.

**Para registrar la tarea (primera vez en una PC nueva, o para
re-registrarla si hace falta):**

```powershell
powershell -ExecutionPolicy Bypass -File pipeline\registrar_tarea_programada.ps1
```

Es idempotente — mata cualquier loop manual que haya quedado corriendo y
vuelve a crear la tarea desde cero. Corre solo mientras la sesión de
Windows esté iniciada (no requiere guardar la contraseña de la cuenta).

**Para revisar el estado:**

```powershell
Get-ScheduledTask -TaskName RayandoCDA_AutoProcesar | Select-Object TaskName, State
Get-ScheduledTaskInfo -TaskName RayandoCDA_AutoProcesar
Get-Content pipeline\logs_auto\loop.log -Tail 10
```
```

- [ ] **Step 2: Commitear todo junto**

```bash
git add pipeline/auto_procesar_loop.ps1 pipeline/README.md
git commit -m "Commitear el loop de respaldo y documentar el disparador automático en el README"
```

- [ ] **Step 3: Verificación final de todo el subsistema**

Run: `git log --oneline -6 -- pipeline/`
Expected: se ven los 4 commits de este plan (notificaciones, fallback CPU, script de registro, README) más los del incidente de hoy.

Run: `git status`
Expected: working tree limpio (nada sin commitear relacionado a este subsistema).
