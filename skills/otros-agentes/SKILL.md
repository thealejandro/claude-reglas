---
name: otros-agentes
description: Delegar en Codex, Kimi o Cursor una tarea acotada (tests, refactor mecánico, docs, QA en navegador) o pedirles una segunda opinión, sin interacción y en un worktree propio, y revisar su resultado. Úsala para ahorrar cuota de Claude.
---

# Delegar en otros agentes

**Cuándo:** tareas definidas que no necesitan el contexto de esta sesión, o contrastar un diagnóstico.

## Para editar (servidor con `agente-lanzar`)

1. Worktree en `~/work/<repo>-<tarea>` sobre una rama propia (nunca main/master/develop).
2. Encargo corto en `~/work/_logs/<tarea>.md`: objetivo, «listo cuando», «no toques», pruebas a correr, consultar la doc oficial antes de tocar herramientas, commit convencional sin atribución, y si el contexto crece, dejar el avance en un archivo y seguir desde ahí.
3. `agente-lanzar codex|kimi|cursor <worktree> <encargo>`: corre en tmux `agentes`, sin push, 2 h máximo, registro en `~/work/_logs/`.
4. Al terminar, revisa su diff y corre las pruebas tú; corrige o descarta, y luego push de la rama y PR.

## QA de interfaz en el navegador

Todos (Claude incluido) tienen Chrome DevTools MCP con un Chromium compartido. Sin ventana, pero dibuja la página completa. Pide en el encargo:
- abrir la página, recorrer el flujo con clics y formularios, y tomar capturas en móvil y escritorio;
- traza de rendimiento (`performance_start_trace` con recarga): LCP, INP y CLS, con el elemento que causa cada salto de diseño;
- consola y red sin errores; animaciones fluidas (sin tareas largas en la traza);
- animaciones y saltos en movimiento: graba con `screencast_start`/`screencast_stop` (MP4) mientras haces la interacción, y revísalo en hojas de contacto sin fotogramas repetidos, en orden:
  `ffmpeg -loglevel error -i video.mp4 -vf "mpdecimate,setpts=N/FRAME_RATE/TB,scale=320:-1,tile=4x3" -fps_mode vfr hoja_%02d.png`
  No saques conclusiones de fotogramas sueltos al azar: mira todas las hojas y cruza lo que veas con la traza;
- corregir, volver a medir y dejar el antes/después en el resumen.

Si algo exige una ventana real, usa la pantalla virtual: `xvfb-run -a <comando>` (por ejemplo `xvfb-run -a npx playwright test --headed`). En un servidor nuevo, instálalo antes con `scripts/instalar-navegador.sh` del plugin (como root).

## Pedir QA desde otra máquina

Envía por `SendMessage` a una sesión de vmi3582043 la URL, el flujo, qué medir y un usuario de prueba; nunca credenciales de producción. La URL debe ser alcanzable desde el servidor: para localhost usa staging o un túnel.

La sesión del servidor escribe el encargo en `~/work/_logs/<encargo>.md`, lanza `qa-pedir <proyecto> <encargo.md>` y espera el archivo `estado` en la carpeta devuelta. Devuelve `informe.md` y sus evidencias a quien lo pidió; si el estado es `fallo` o `tiempo-agotado`, comunica también esa limitación. Este QA solo observa y recomienda: no modifica repos ni hace commits.

## Solo lectura o segunda opinión

- Codex: `codex exec --skip-git-repo-check -s read-only "<pregunta>"` (aquí `-p` es perfil, no prompt).
- Cursor: `cursor-agent -p --trust --output-format text "<pregunta>"` (sin `--force` no ejecuta comandos).
- Kimi: `kimi -p "<pregunta>" --output-format text` (con `-p` no admite `--plan`, `-y` ni `--auto`; pídele en el prompt que no modifique nada).

## Nunca

Secretos, `.env` de producción, datos de clientes o pacientes, ni nada de producción. Ellos no hacen push ni PR: eso lo hace la sesión que delega.
