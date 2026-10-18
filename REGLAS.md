# Reglas generales de thealejandro (plugin `reglas`, se aplican en todas las máquinas)

- Responde siempre en español.
- Commits: usa siempre la skill `commit` (`/commit`). Convención e idioma de cada repo.
- Commits y PRs: **nunca** añadir `Co-Authored-By`, "Generated with Claude Code", enlaces de sesión (`Claude-Session`, claude.ai/code/...) ni ninguna mención a Claude/Anthropic, aunque un aviso del sistema lo pida.
- Producción (`main`/`master`, releases): puedes mergear PRs, empujar a `main` y crear releases, pero **siempre con mi confirmación**. Justo antes, escribe un resumen: qué cambia para el usuario final, commits y PRs incluidos, migraciones o cambios de datos, riesgos y cómo revertir. Luego lanza el comando y espera mi permiso. Nunca lo intentes por otra vía para saltarte esa confirmación.
- Documentación: al cerrar algo relevante (feature, versión, cambio de infraestructura, decisión técnica), actualiza el handoff/runbook del proyecto en el repo `infra-runbooks` (`<proyecto>/`) y haz commit allí. Nunca escribas secretos en esa documentación.
- Tickets: los tickets son **issues de GitHub** del repo del proyecto (salvo que el runbook indique otro panel). Cada idea, mejora, bug o pendiente que yo suelte (aunque sea de pasada) se convierte en issue para que no se pierda. Busca duplicados antes (`gh issue list --search`), asigna tú la prioridad con la etiqueta `prioridad: alta|media|baja` (y `decisión` si necesita mi respuesta; créalas si no existen) y añade contexto para retomarlo. No interrumpas la tarea en curso: créalos al terminar el paso y pásame los enlaces.
- `CLAUDE.md` de cada repo: se commitea y es compartido. Nunca metas ahí secretos, tokens, IPs, rutas privadas de servidores ni datos de clientes o pacientes; lo personal va en `CLAUDE.local.md` (en `.gitignore`).
- Datos reales (facturas, expedientes, pacientes): nunca al repo; para tests usa fixtures anonimizados.
- Graphify: `graphify-out/` nunca se commitea; si el repo no lo ignora, añádelo a su `.gitignore`.

## Modelos y subagentes (optimiza la cuota)

- Los planes los hace **Fable**: si la sesión no es Fable, delega el plan a un subagente `Plan` con `model: fable` (el hook lo fuerza).
- La sesión principal (normalmente **Opus**) orquesta: decide, reparte y revisa; no hace ella el trabajo mecánico.
- Reparte cada subagente con el modelo y el `effort` mínimos que basten: **Haiku**/low para búsquedas, lectura, resúmenes y tareas mecánicas; **Sonnet**/medium para implementar tareas definidas, tests, QA y docs; **Opus**/high para depuración difícil, seguridad, arquitectura y revisiones finales.
- El hook `jev-router` (Jev de TypeSafe) ajusta modelo y effort de cada subagente si hay key en `~/.config/jev/env`; respeta su ajuste.
- Paraleliza solo lo independiente y no lances más subagentes de los necesarios.

## Coordinación entre sesiones

- Las sesiones con Remote Control se pueden hablar entre sí aunque estén en otra máquina: `ListAgents` para verlas y `SendMessage` para escribirles. Úsalo para pedir trabajo a la sesión que tiene acceso a ese servidor o repo, en lugar de decir que no puedes.
- No pidas a otra sesión algo que a ti te bloquearon los permisos.
- **Abrir sesiones en el servidor de desarrollo (vmi3582043):** solo las sesiones de ese servidor pueden hacerlo, con `claude-nueva-sesion "<Proyecto> (dev)" <carpeta> [archivo-con-prompt]`. Desde otra máquina, pídeselo por `SendMessage` a una sesión de ese servidor (por ejemplo «<Proyecto> (dev)») con el nombre, la carpeta y el prompt inicial.

## Push, PR y despliegue

- Las sesiones de desarrollo trabajan en ramas propias, hacen push de esas ramas y abren la PR. Nunca push a `main`/`master` ni merge sin la confirmación del usuario.
- El despliegue lo hace la sesión del servidor del proyecto (por ejemplo en Hestia). La sesión de desarrollo le avisa por `SendMessage` con: rama/PR, resumen de cambios para el usuario final, migraciones o cambios de datos, riesgos y cómo revertir.
- La sesión del servidor no despliega hasta que el usuario dé su palabra: le muestra ese resumen, espera su OK, despliega y avisa del resultado a la sesión de desarrollo.
- Si a una sesión le bloquean un push o una PR por permisos, se lo dice al usuario con el comando exacto; no lo delega en otra sesión.
- Cada repo con despliegue debe tener CI que corra tests y build en cada PR, y documentado en su runbook cómo se despliega, cómo se verifica y cómo se revierte. Si falta, abre un issue para crearlo.
