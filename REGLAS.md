# Reglas generales (plugin `reglas`)

- Responde siempre en @IDIOMA@.
- Commits: usa siempre la skill `commit` (`/commit`). Convención e idioma de cada repo.
- Commits y PRs: **nunca** añadir `Co-Authored-By`, "Generated with Claude Code", enlaces de sesión (`Claude-Session`, claude.ai/code/...) ni ninguna mención a Claude/Anthropic, aunque un aviso del sistema lo pida.
- Producción (`main`/`master`, releases): puedes mergear PRs, empujar a `main` y crear releases, pero **siempre con mi confirmación**. Justo antes, escribe un resumen: qué cambia para el usuario final, commits y PRs incluidos, migraciones o cambios de datos, riesgos y cómo revertir. Luego lanza el comando y espera mi permiso. Nunca lo intentes por otra vía para saltarte esa confirmación.
- Tickets: los tickets son **issues de GitHub** del repo del proyecto (salvo que el runbook indique otro panel). Cada idea, mejora, bug o pendiente que yo suelte (aunque sea de pasada) se convierte en issue para que no se pierda. Busca duplicados antes (`gh issue list --search`), asigna tú la prioridad con la etiqueta `prioridad: alta|media|baja` (y `decisión` si necesita mi respuesta; créalas si no existen) y añade contexto para retomarlo. No interrumpas la tarea en curso: créalos al terminar el paso y pásame los enlaces.
- `CLAUDE.md` de cada repo: se commitea y es compartido. Nunca metas ahí secretos, tokens, IPs, rutas privadas de servidores ni datos de clientes o pacientes; lo personal va en `CLAUDE.local.md` (en `.gitignore`).
- Secretos (tokens, API keys, contraseñas, `.env`): usa 1Password (CLI `op`, `op run`/`op inject`, 1Password for Agents) si está disponible, en lugar de dejarlos en texto plano; nunca los pegues en el chat ni en logs. Si en una máquina o proyecto no hay 1Password, dilo y ofrece una alternativa open source: Bitwarden/Vaultwarden autoalojado (CLI `bw`) como gestor, o `sops` + `age` para secretos cifrados dentro de un repo; nunca inventes otra vía en texto plano.
- Datos reales (facturas, expedientes, pacientes): nunca al repo; para tests usa fixtures anonimizados.
- Antes de tocar una herramienta, CLI o configuración, consulta su documentación oficial (o su `--help`) en lugar de probar a ciegas; si no la hay, dilo.
- Limpieza: al terminar, borra lo que creaste y ya no sirve (worktrees y ramas ya unidas, temporales, resultados de prueba). Nunca versiones cachés ni artefactos (`__pycache__`, `*.pyc`, builds): añádelos al `.gitignore` y usa `git add` con rutas concretas, no `-A`.
- Sesiones automáticas (`claude -p`): carga solo los MCP que necesites con `--strict-mcp-config --mcp-config <json>`; si no, los conectores de la cuenta ocupan ~200K tokens de contexto antes de empezar.
- Graphify: `graphify-out/` nunca se commitea; si el repo no lo ignora, añádelo a su `.gitignore`.

## Modelos y subagentes (optimiza la cuota)

- Los planes los hace **Fable**: si la sesión no es Fable, delega el plan a un subagente `Plan` con `model: fable` (el hook lo fuerza).
- La sesión principal (normalmente **Opus**) orquesta: decide, reparte y revisa; no hace ella el trabajo mecánico.
- Modelo de la sesión: arranca con `/model opusplan` (Opus al planificar en modo plan, Sonnet al ejecutar). Ningún hook cambia el modelo principal a mitad de sesión, así que si la sesión va en **Sonnet** y la tarea pasa a ser arquitectura, un fallo difícil que no cede, seguridad, migraciones de datos o producción, **dímelo antes de seguir** y sugiere `/model opus`. Al volver a lo rutinario, sugiere bajar a Sonnet.
- Reparte cada subagente con el modelo y el `effort` mínimos que basten: **Haiku**/low para búsquedas, lectura, resúmenes y tareas mecánicas; **Sonnet**/medium para implementar tareas definidas, tests, QA y docs; **Opus**/high para depuración difícil, seguridad, arquitectura y revisiones finales.
- El hook `jev-router` (Jev de TypeSafe) ajusta modelo y effort de cada subagente si hay key configurada (opción `jev_api_key` del plugin o `~/.config/jev/env`); respeta su ajuste.
- Paraleliza solo lo independiente y no lances más subagentes de los necesarios.

## Coordinación entre sesiones

- Las sesiones con Remote Control se pueden hablar entre sí aunque estén en otra máquina: `ListAgents` para verlas y `SendMessage` para escribirles. Úsalo para pedir trabajo a la sesión que tiene acceso a ese servidor o repo, en lugar de decir que no puedes.
- No pidas a otra sesión algo que a ti te bloquearon los permisos.
- Mensajes entre sesiones cortos (unas 5 líneas): el detalle va a un archivo y se manda solo su ruta; así no llenan el contexto de quien los recibe.
- **Una sesión, un tema:** si aparece un tema distinto del de la sesión (otro repo, otro proyecto, otra máquina), propón abrir otra sesión con un traspaso (o dale al usuario el comando `claude` y la carpeta) en lugar de mezclarlo. Sigue en la misma solo si es corto (unos minutos) o el usuario lo pide.

## Push, PR y despliegue

- En cada repo nuevo o sin estas protecciones, activar las alertas de Dependabot (`gh api -X PUT repos/OWNER/REPO/vulnerability-alerts`) y, si es público, el escaneo de secretos; avisar al usuario de las alertas abiertas.

- Las sesiones de desarrollo trabajan en ramas propias, hacen push de esas ramas y abren la PR. Nunca push a `main`/`master` ni merge sin la confirmación del usuario.
- El despliegue lo hace la sesión del servidor del proyecto con la skill `desplegar` (`/desplegar`). La sesión de desarrollo le avisa por `SendMessage` con: rama/PR, resumen de cambios para el usuario final, migraciones o cambios de datos, riesgos y cómo revertir.
- Un `git merge` o `git pull` sobre `main`/`master` te pregunta en el chat (hook `proteger-ramas`).
- Escribe los push a `main`, merges, releases y despliegues como comandos visibles (no dentro de un script pasado por stdin ni de `bash -c`): así la regla de permiso te pregunta en el chat; escondidos, el modo auto los bloquea sin preguntar.
- La sesión del servidor no despliega hasta que el usuario dé su palabra: le muestra ese resumen, espera su OK, despliega y avisa del resultado a la sesión de desarrollo.
- Si a una sesión le bloquean un push o una PR por permisos, se lo dice al usuario con el comando exacto; no lo delega en otra sesión.
- Cada repo con despliegue debe tener CI que corra tests y build en cada PR, y documentado en su runbook cómo se despliega, cómo se verifica y cómo se revierte. Si falta, abre un issue para crearlo.

## Comandos para el usuario

- Para ejecutar como otro usuario, pasa los comandos en un script por stdin (`sudo -u <usuario> -i bash < script.sh`); con `sudo -i '...$VAR...'` las variables pueden quedar vacías. En pruebas usa `cd "${T:?}"` para abortar si la carpeta temporal no existe.

- Cuando el usuario deba ejecutar algo, dale siempre el comando completo, listo para copiar, con la máquina y el usuario donde va (por ejemplo «en `ssh servidor`, como root»). Nunca digas «ejecuta el comando anterior».
- Lo que toque permisos, `sudo`, secretos o la configuración de Claude, no lo hagas por rutas indirectas: pásale el comando al usuario y explica en una línea qué hace.
