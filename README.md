# reglas — plugin de Claude Code

Reglas comunes para las sesiones de Claude Code, en cualquier máquina. Son configurables (ver «Configuración»): lo que no se configura no inyecta sus reglas.

Incluye:
- Las reglas, inyectadas al inicio de cada sesión (hook `SessionStart`, `scripts/reglas.py`): `REGLAS.md` más los bloques de `reglas/` cuyas opciones estén configuradas.
- Skill `commit`: commits convencionales en el idioma del repo, sin atribución, sin push a `main` sin permiso. Corre en Haiku.
- Skill `desplegar`: resumen de producción como comentario en la PR, aviso a la sesión del servidor y despliegue solo con el OK del usuario.
- Hook `jev-router`: Jev elige modelo y effort de cada subagente; los `Plan` van con Fable.
- Hook `anti-filtraciones`: bloquea commits y pushes con secretos, archivos sensibles o datos reales.
- `scripts/ajustes.py`: ajustes que un plugin no puede fijar (atribución vacía, también sin enlace de sesión, confirmación para producción, autocompact 200K), el `AGENTS.md` de Codex, Kimi y Cursor y los hooks de git globales.

## Configuración

Al instalar o habilitar el plugin desde `/plugin` aparece un diálogo con estas opciones (ninguna es obligatoria):

| Opción | Qué hace |
|---|---|
| `idioma` | Idioma de las respuestas (por defecto español). |
| `repo_runbooks` | Repo de runbooks; sin él no se inyecta la regla de documentación. |
| `servidores` | Equipos con el módulo de servidor; sin ellos no se inyectan las reglas de sesiones en servidores. |
| `servidor_desarrollo` | Equipo para delegar en otros agentes y hacer QA; sin él no se inyectan esas reglas. |
| `jev_api_key` | Key de Jev (sensible). Alternativa: `~/.config/jev/env`, que sigue valiendo. |

`claude plugin install` en el shell no pregunta: usa `--config clave=valor`. Para reconfigurar, `/plugin configure reglas@thealejandro` o sin interacción:

```bash
printf '%s' '{"idioma":"español","repo_runbooks":"<repo>","servidores":"<equipo-dev>, <equipo-prod>","servidor_desarrollo":"<equipo-dev>"}' | claude plugin configure reglas@thealejandro --values-stdin
```

`claude plugin configure reglas@thealejandro` muestra qué falta. Los cambios requieren reiniciar o `/reload-plugins`.

### Qué es específico del autor

`qa-pedir` y `agente-lanzar` asumen el usuario `dev` y `/home/dev/work`; `instalar-chrome.sh` asume Ubuntu. Quien haga fork debe cambiar el marketplace en `ajustes.py`.

## Plugins recomendados (midudev/better-claude)

No se copian aquí: los mantiene midudev y se actualizan desde su marketplace. `commit@better-claude` no se instala porque la skill `commit` de este plugin lo sustituye.

```bash
claude plugin marketplace add midudev/better-claude
for p in sub-meter token-meter context-meter image-preview time-machine narrator; do claude plugin install $p@better-claude; done
```

## Referencias de UI/UX opcionales (1.15.0)

El marketplace `thealejandro` ofrece dos plugins de terceros que no se instalan con `reglas`: aparecen en `/plugin` y cada uno decide. Van fijados a un commit revisado; su texto entra en el prompt y taste-skill ejecuta scripts en local, así que no siguen la última versión.

| Plugin | Para qué | Instalar |
|---|---|---|
| `frontend-design` (Anthropic, oficial) | Diseño visual con criterio propio, sin plantillas. Empieza por este. | `claude plugin install frontend-design@claude-plugins-official` |
| `ux-designer` ([szilu](https://github.com/szilu/ux-designer-skill)) | Revisar y construir apps de trabajo: usabilidad, WCAG 2.2, formularios, tablas, dashboards, i18n. ~110 tokens por sesión. | `claude plugin install ux-designer@thealejandro` |
| `taste-skill` ([Leonxlnx](https://github.com/Leonxlnx/taste-skill)) | Dirección de arte para landings y páginas públicas, comprobada en un navegador real (Node). ~240 tokens por sesión. | `claude plugin install taste-skill@thealejandro` |

Revisados en esos commits (sin inyecciones ni hooks): ux-designer es solo Markdown. taste-skill no instala nada ni manda datos del proyecto, pero busca imágenes en APIs abiertas (Openverse, Wikimedia, museos, NASA), abre Chrome headless en local, guarda su historial en `~/.taste-skill/` y sus escenas cargan GSAP/Lenis de jsDelivr sin SRI.

No usamos `npx skills add`: copia las skills a `~/.claude/skills` fuera del sistema de plugins, sin versión ni actualización. Tampoco van como `dependencies` de `reglas`, que las instalaría en todas las máquinas.

Para subir una versión: revisar el diff del repo entre el `sha` actual y el nuevo, cambiar `sha` (y `ref`) en `.claude-plugin/marketplace.json` y pasar `claude plugin validate .claude-plugin/marketplace.json`.

## Hook `anti-filtraciones`

Se ejecuta como `PreToolUse` sobre `Bash`, solo cuando el comando contiene `git commit` o `git push`. En un commit revisa el diff del índice; en un push revisa los commits pendientes respecto a `@{u}`, si la rama tiene upstream.

Bloquea claves privadas y tokens habituales (GitHub, AWS, Slack, Stripe, Anthropic y OpenAI), JWT, asignaciones de contraseñas o claves, archivos `.env` (salvo `.env.example`), claves privadas y SSH, contenido de `_muestras/`, XML de factura FEL y DPI de Guatemala. El motivo del bloqueo indica archivo y línea, y como máximo los primeros cuatro caracteres del hallazgo, nunca el valor completo.

Hay dos formas de declarar una excepción:

- Añadir `reglas:permitir` como comentario en la misma línea.
- Listar la ruta o patrón en `.reglas-permitir`, en la raíz del repositorio, con una entrada por línea.

Los mismos controles corren como hooks de git para cualquier agente (ver «Reglas y hooks para Codex, Kimi y Cursor»).

Si `gitleaks` está instalado se ejecuta como revisión adicional; si no, basta la revisión propia. El hook tiene un límite interno total de 5 segundos y, ante un fallo propio, deja continuar la operación con un aviso en lugar de bloquear por error.

Las pruebas usan repositorios Git temporales y se ejecutan con `python3 -m unittest discover tests`.

## Instalar en una máquina

```bash
claude plugin marketplace add thealejandro/claude-reglas
claude plugin install reglas@thealejandro
# Opcional, para Jev (la key nunca va al repo):
mkdir -p ~/.config/jev && chmod 700 ~/.config/jev
read -rsp 'Key de Jev: ' K; printf 'TYPESAFE_API_KEY=%s\n' "$K" > ~/.config/jev/env; chmod 600 ~/.config/jev/env; unset K
```

Actualizar: `claude plugin marketplace update thealejandro && claude plugin update reglas@thealejandro`. Para cargarlos en una sesión abierta basta con `/reload-plugins`; las nuevas los cargan al iniciarse.

Los resultados de `qa-pedir` se borran solos a los 14 días.

## Delegar en Codex, Kimi y Cursor: `agente-lanzar` y skill `otros-agentes`

`scripts/agente-lanzar` lanza Codex, Kimi o Cursor como `dev` en la sesión tmux `agentes`, sobre una carpeta de `~/work` en rama propia (nunca main/master/develop), sin poder hacer push (pushurl falso y `gh` sin sesión), con 2 h máximo y registro en `~/work/_logs/`.

```bash
# En el servidor, como root:
install -m 755 "$(ls -d ~dev/.claude/plugins/cache/thealejandro/reglas/*/ | sort -V | tail -1)scripts/agente-lanzar" /usr/local/bin/agente-lanzar
# Para que el modo auto no lo bloquee, añade en settings.json de quien lo use:
#   "permissions": { "allow": ["Bash(agente-lanzar *)"] }
```

Uso: `agente-lanzar codex ~/work/repo-tarea ~/work/_logs/encargo.md`. Codex corre sin su sandbox (bwrap no puede crear namespaces en Ubuntu con AppArmor); los límites son los de arriba más el usuario `dev` sin sudo.

## QA centralizado: `qa-pedir`

En vmi3582043, instala el lanzador como `agente-lanzar` (como root):

```bash
install -m 755 "$(ls -d ~dev/.claude/plugins/cache/thealejandro/reglas/*/ | sort -V | tail -1)scripts/qa-pedir" /usr/local/bin/qa-pedir
```

Uso: `qa-pedir <proyecto> /home/dev/work/_logs/encargo.md`. El proyecto admite letras ASCII, números, `_` y `-`. Se relanza como `dev` y devuelve `/home/dev/work/_logs/qa/AAAAMMDD-HHMM-<proyecto>/`. Rechaza una carpeta ya existente para no mezclar encargos del mismo minuto. `qa-pedir --simular <proyecto> <encargo.md>` valida e imprime el comando sin crear resultados ni lanzar procesos de QA.

Ejecuta Sonnet (`claude-sonnet-5-5`) durante un máximo de 45 minutos en tmux `qa`, ventana `qa-<proyecto>`, con Chrome DevTools MCP ya configurado. Guarda capturas, video, hojas de contacto, `informe.md` y `ejecucion.log`. Espera a que aparezca `estado`: `ok`, `fallo` o `tiempo-agotado` describen la ejecución, no si la interfaz pasó la revisión. La ventana termina sola; no se registra en `sesiones.conf` ni se revive.

`ajustes.py` añade, si existe el lanzador instalado, `Bash(qa-pedir *)` y `Bash(/usr/local/bin/qa-pedir *)` a `permissions.allow` de quien lo use. Para configurarlo manualmente:

```json
{"permissions": {"allow": ["Bash(qa-pedir *)", "Bash(/usr/local/bin/qa-pedir *)"]}}
```

El proceso usa `dontAsk`, permite las herramientas de `chrome-devtools`, Read/Write en la carpeta de resultados (las escrituras usan reglas `Edit`) y `Bash(ffmpeg *)`, sin conceder Bash general. Sintaxis contrastada con `claude --help` y la [documentación de permisos](https://code.claude.com/docs/en/permissions). No modifica repos ni hace commits. Desde otra máquina, pide el QA por `SendMessage` a una sesión del servidor con URL, flujo, métricas y usuario de prueba, nunca credenciales de producción. Solo URLs alcanzables desde el servidor; localhost requiere staging o un túnel.

## Navegador para QA en todos los agentes (1.3.2)

Chrome del sistema para PDF (Browsershot) y QA, como root: `bash "$(ls -d ~usuario/.claude/plugins/cache/thealejandro/reglas/*/ | sort -V | tail -1)scripts/instalar-chrome.sh" [usuario-de-prueba]`. Instala `google-chrome-stable` con la clave de Google limitada a su repositorio (`Signed-By`), un pin que solo deja entrar ese paquete, `chrome-sandbox` sin SUID (`dpkg-statoverride`), parches por unattended-upgrades y políticas sin Gemini, modelo de IA local, telemetría ni modo en segundo plano. El sandbox usa user namespaces gracias al perfil AppArmor `chrome` de Ubuntu, que es seguro porque `/opt/google/chrome` solo lo escribe root. Nunca des a un binario en una ruta escribible por un usuario (por ejemplo `~/.cache/puppeteer`) un perfil con `userns`: cualquiera con ese usuario podría poner ahí otro programa. Para Browsershot: `BROWSERSHOT_CHROME_PATH=/usr/bin/google-chrome` y `~/.puppeteerrc.json` con `{"skipDownload": true}`.

Un solo navegador compartido. En un servidor nuevo, como root: `bash "$(ls -d ~dev/.claude/plugins/cache/thealejandro/reglas/*/ | sort -V | tail -1)scripts/instalar-navegador.sh" dev` (librerías de Chromium, `xvfb`, fuentes, Chromium de Playwright y `chrome-devtools-mcp`; sin él se usa `npx`). `ajustes.py` crea `~/.local/bin/chromium-qa`, que arranca el Chromium de Playwright más reciente (sigue funcionando tras actualizar Playwright), y registra Chrome DevTools MCP (`--headless --isolated`) en Claude (`claude mcp add -s user`), Codex (`codex mcp add`), Kimi (`~/.kimi-code/mcp.json`) y Cursor (`~/.cursor/mcp.json`) cuando están instalados, y añade el permiso de `agente-lanzar` si el lanzador existe. No toca entradas que ya existan. En servidores con Hestia no registra el navegador y quita el que hubiera: allí no se hace QA y `npx @latest` ejecutaría código sin fijar.

## Reglas y hooks para Codex, Kimi y Cursor (1.14.0)

`ajustes.py` (una vez por versión) hace dos cosas para los agentes que no son Claude:

- **Reglas.** Genera un `AGENTS.md` con la misma fuente que las reglas de Claude (`scripts/reglas.py`, sin las secciones propias de Claude Code: modelos y subagentes, coordinación entre sesiones, sesiones en servidores y delegar/QA) y lo escribe en `~/.codex/`, `~/.kimi-code/` y `~/.cursor/`. Solo si esa carpeta existe y el `AGENTS.md` no existe o ya lleva la marca `Generado por el plugin reglas`: uno propio nunca se pisa. Las opciones del plugin se leen de `pluginConfigs` en `~/.claude/settings.json`. Cursor CLI no tiene archivo global documentado: `agente-lanzar` antepone `~/.cursor/AGENTS.md` al encargo.
- **Hooks de git.** Crea `~/.config/git/hooks/{pre-commit,commit-msg,pre-push}` y fija `core.hooksPath` global, solo si estaba vacío (si apunta a otro sitio, avisa y no lo toca). Cada hook llama a `hooks/git-hook.py` del plugin instalado, que reutiliza `anti-filtraciones.py`:
  - `pre-commit`: mismos controles que `anti-filtraciones` sobre el índice.
  - `commit-msg`: rechaza `Co-Authored-By` de una IA, «Generated with» seguido de un agente, `Claude-Session`, enlaces `claude.ai/code` y el emoji de robot.
  - `pre-push`: bloquea el push a `main`/`master` y revisa los commits que se envían.

Ante un fallo interno, o si falta el plugin o `python3`, los hooks dejan pasar y avisan por stderr. Es un guardarraíl, no un sandbox.

**Encadenado.** Como `core.hooksPath` sustituye a `.git/hooks`, cada hook global ejecuta después el hook local del repo (`$(git rev-parse --git-common-dir)/hooks/<nombre>`) si existe. **Limitación:** los repos que fijan su propio `core.hooksPath` (husky, lefthook) siguen mandando: ahí se pierde el hook del plugin, no el suyo, y solo les llegan las reglas en texto.

**Push confirmado a `main`.** Con el OK del usuario: `git push origin main --no-verify` (sigue casando con la regla ask `Bash(git push origin main*)`). El merge de PRs con `gh pr merge` no se ve afectado.

**Desinstalar:** `git config --global --unset core.hooksPath && rm -r ~/.config/git/hooks`, y borrar los `AGENTS.md` que lleven la marca. Volver a ejecutar `ajustes.py` los recrea.

Fuera de alcance: orquestación, contexto/autocompact de otros agentes, un `CLAUDE.md` que importe `AGENTS.md` y un `config.toml` por agente.

## Ajustes automáticos (1.3.0)

En `SessionStart`, además de inyectar las reglas con `scripts/reglas.py`, se ejecuta:

```bash
python3 -I "${CLAUDE_PLUGIN_ROOT}/scripts/ajustes.py" --si-hace-falta
```

Requiere Python 3. Aplica los ajustes una vez por versión y guarda la versión del
plugin en `~/.claude/.reglas-ajustes` únicamente después de completarlos. Cuando la
marca coincide, sale en menos de un segundo sin leer ni reescribir los ajustes.
Este modo no imprime nada y devuelve código 0 incluso ante errores de lectura,
JSON o escritura; si falla antes de guardar la marca, reintenta en otra sesión.

El script conserva los demás ajustes de `~/.claude/settings.json` y configura:

- Atribución vacía en commits y PRs.
- `AGENTS.md` para Codex, Kimi y Cursor, y hooks de git globales (ver la sección siguiente).
- Confirmación para los comandos de producción ya contemplados por el plugin.
- Ventana de autocompact de 200K para los modelos definidos, respetando valores existentes.
- Marketplace `thealejandro` con este formato:

```json
{
  "extraKnownMarketplaces": {
    "thealejandro": {
      "source": { "source": "github", "repo": "thealejandro/claude-reglas" },
      "autoUpdate": true
    }
  }
}
```

Formato contrastado con la documentación oficial de
[`extraKnownMarketplaces`](https://code.claude.com/docs/en/settings-reference#extraknownmarketplaces)
y su [ejemplo de registro y actualización](https://code.claude.com/docs/en/plugins/org#require-a-marketplace-and-its-plugins):
`autoUpdate` es un booleano junto a `source`. La actualización efectiva depende de
Claude Code y de las políticas de mayor precedencia.

Para reaplicar los ajustes tras cambios manuales, ejecuta en tu máquina:

```bash
python3 -I ~/.claude/plugins/marketplaces/thealejandro/scripts/ajustes.py
```

El modo manual comprueba siempre los ajustes y muestra el resultado. Solo si hay
cambios crea una copia `~/.claude/settings.json.bak-*` del archivo existente y lo
reemplaza de forma atómica. Una segunda ejecución no modifica archivos ni crea
copias adicionales. La marca evita reaplicar cambios manuales posteriores desde
el hook; una versión nueva vuelve a aplicar los ajustes.

Las reglas de despliegue/CI también requieren activar alertas de Dependabot en
repositorios nuevos o que carezcan de ellas, activar escaneo de secretos cuando
sean públicos y avisar al usuario de las alertas abiertas.

## Comprobación aislada

Desde la raíz del repo, usa un HOME temporal para no modificar tus ajustes reales:

```bash
HOME_PRUEBA=$(mktemp -d)
HOME="$HOME_PRUEBA" python3 -I scripts/ajustes.py
HOME="$HOME_PRUEBA" python3 -I scripts/ajustes.py
HOME="$HOME_PRUEBA" python3 -I scripts/ajustes.py --si-hace-falta
python3 -I scripts/reglas.py > /dev/null
python3 -m json.tool hooks/hooks.json > /dev/null
claude plugin validate .
```

## Módulo de servidor

En el servidor Linux con systemd, como root (sustituye `usuario` y `nombre-equipo`):

```bash
bash "$(ls -d ~usuario/.claude/plugins/cache/thealejandro/reglas/*/ | sort -V | tail -1)scripts/instalar-servidor.sh" usuario nombre-equipo
```

Añade `--simular` antes del usuario para revisar las unidades y operaciones sin instalarlas. Requiere Bash, Python 3, sudo, curl, flock y tmux, y `claude` instalado y autenticado para ese usuario, con Remote Control habilitado y `~/work` existente y confiable. Las opciones se contrastaron con los manuales de systemctl, loginctl y tmux y la [documentación oficial de Remote Control](https://code.claude.com/docs/en/remote-control) y del [CLI](https://code.claude.com/docs/en/cli-reference).

Instala los cuatro scripts en `/usr/local/bin`, activa linger y habilita Remote Control con el nombre del equipo, `same-dir`, capacidad 16 y permisos `auto`. Retoma las sesiones fijas y las guardadas al apagar, espera la red y evita duplicar conversaciones vivas. Omite las abiertas desde la app (`sdk-cli`) al guardar; cada 15 minutos guarda las abiertas y revive solo las fijas caídas. Cada noche reinicia las quietas con versión antigua (ver abajo). No fija `DOCKER_HOST`.

Conserva `~/.config/claude-arranque/sesiones.conf` existente; las unidades diferentes se respaldan en `.bak.*` con aviso antes de reemplazarlas. Las unidades ya activas incorporan los cambios en su siguiente arranque. El formato de sesiones es `ventana|id|nombre|carpeta`, una por línea.

También activa la actualización diaria del plugin para ese usuario (ver abajo).

### Actualización diaria del plugin

El `autoUpdate` del marketplace no basta en servidores donde las sesiones viven días. Como root:

```bash
bash "$(ls -d ~usuario/.claude/plugins/cache/thealejandro/reglas/*/ | sort -V | tail -1)scripts/instalar-actualizacion.sh" usuario [otro-usuario...]
```

Sirve también para root. Instala `/usr/local/bin/claude-actualizar-reglas` y el temporizador de sistema `claude-actualizar-reglas@<usuario>.timer` (04:00 hora del servidor, hasta 30 min de margen aleatorio; si el equipo estaba apagado, se ejecuta al arrancar). Cada ejecución hace `claude plugin marketplace update thealejandro`, `claude plugin update reglas@thealejandro` y aplica `ajustes.py`; el registro queda en `~/.local/state/claude-actualizar-reglas.log`. No pasa `-y`: si el marketplace declarase un comando, la actualización se rechaza. Las sesiones abiertas cargan la versión nueva con `/reload-plugins` o al reiniciarse. Para actualizar al momento: `systemctl start claude-actualizar-reglas@usuario.service`. Si `ajustes.py` falla al arrancar una sesión, el error queda en `~/.local/state/reglas-ajustes.log`.

La instancia de root (`claude-actualizar-reglas@root`) renueva además los lanzadores de `/usr/local/bin` que ya estén instalados y hayan cambiado (`claude-arranque`, `claude-nueva-sesion`, `claude-guardar-abiertas`, `claude-reiniciar-sesiones`, `agente-lanzar`, `qa-pedir` y el propio `claude-actualizar-reglas`), desde su caché del plugin y solo si los archivos son de root y nadie más puede escribirlos (1.14.1). No instala los que falten ni toca unidades systemd: si el módulo de servidor trae un script nuevo, lo avisa en el registro para reinstalar con `instalar-servidor.sh`. Requiere haber reinstalado una vez la actualización diaria con la 1.14.1 o posterior (`instalar-actualizacion.sh`).

Uso como usuario del módulo: `claude-nueva-sesion "Proyecto (equipo)" ~/work/proyecto [archivo-encargo]`. También admite `--retomar <session-id> "Nombre (equipo)" [carpeta]`. La sesión queda registrada para próximos reinicios. Si Claude Code no tiene aceptada la confianza de la carpeta (en un repo cuenta su raíz, no la carpeta padre), la sesión se queda en ese diálogo: el script abre la ventana, sale con código 3 y da el `tmux attach` para aceptarla a mano. Después, `claude-nueva-sesion --registrar "Nombre (equipo)"` apunta la sesión ya abierta sin relanzarla (1.12.1). `ajustes.py` permite ambos formatos del lanzador instalado en la siguiente sesión del plugin. Desde otro equipo, solicita la apertura por `SendMessage` a una sesión del servidor; en producción confirma primero con el usuario.

### Reinicio nocturno tras actualizar Claude Code (1.13.0)

Una sesión de Claude Code que lleva días abierta sigue con la versión con la que arrancó aunque el CLI se haya actualizado. El temporizador `claude-reiniciar-sesiones.timer` (04:45 hora del servidor, sin recuperar ejecuciones perdidas; el plugin se actualiza a las 04:00) ejecuta `claude-reiniciar-sesiones --actualizar`: hace `claude update` (si falla, sigue con lo instalado), guarda las abiertas con `claude-guardar-abiertas` y reinicia las sesiones que cumplen todo esto:

- Interactivas de terminal (`kind` interactive, `entrypoint` cli) y corriendo en un panel de la sesión tmux `sesiones`. Nunca toca las abiertas desde la app (`sdk-cli`) ni las de `claude-rc.service`, ni la propia sesión que lo ejecute.
- Con una versión menor que la instalada (`claude --version`).
- Quietas: `status` idle y sin actividad hace al menos 30 minutos (`--quietud MIN`), y con el archivo de la conversación sin modificar durante ese mismo tiempo.
- Sin nadie mirándolas: ningún cliente tmux adjunto a su ventana y ninguna otra ventana con el mismo nombre.

Para cada una, de una en una: apunta una marca, escribe `/exit` en su panel (espera `REINICIAR_ESPERA_SALIDA`, 30 s; si no sale, SIGTERM y otros `REINICIAR_ESPERA_TERM`, 20 s), cierra su ventana por id (SIGKILL con aviso en mayúsculas como último recurso), la retoma con `claude-arranque` y espera hasta `REINICIAR_ESPERA_RETOMA` (60 s) a que reaparezca (un reintento; si no, `FALLO` en el log con el comando `claude-nueva-sesion --retomar` para hacerlo a mano). Entre sesiones pausa `REINICIAR_PAUSA` (10 s). Si el script muere con una sesión cerrada, intenta relanzarla al salir. Termina con código 1 si hubo algún `FALLO`.

Se puede probar sin tocar nada con `claude-reiniciar-sesiones --simular` (también `--sesion-tmux NOMBRE`): lista lo que reiniciaría y las sesiones omitidas con el motivo. Registro en `~/.local/state/claude-reiniciar.log` (últimas 500 líneas). Las marcas `~/.local/state/claude-reiniciar/<id>.json` (`de`, `a`, `fecha`, `nombre`) se borran a los 7 días; el hook `aviso-reinicio.py` (SessionStart) lee la marca de la conversación retomada, la borra y pide a Claude que avise al usuario en su primera respuesta. El script no está en los permisos que añade `ajustes.py`: se lanza desde la unidad o a mano.

Para desactivarlo: `systemctl --user disable --now claude-reiniciar-sesiones.timer`. Para ejecutarlo ya: `systemctl --user start claude-reiniciar-sesiones.service`.

Limitaciones: un permiso pendiente o un texto a medio escribir en el prompt se pierden al reiniciar (por eso exige quietud; antes de cada reinicio vuelve a comprobarla). El formato de `~/.claude/sessions/*.json` no está documentado: si un campo falta o no tiene la forma esperada, la sesión se omite y no se reinicia.
