# reglas — plugin de Claude Code

Reglas comunes para todas las sesiones de Claude Code de thealejandro, en cualquier máquina (servidor de desarrollo, Hestia, Windows, Mac).

Incluye:
- `REGLAS.md`, inyectado al inicio de cada sesión (hook `SessionStart`).
- Skill `commit`: commits convencionales en el idioma del repo, sin atribución, sin push a `main` sin permiso. Corre en Haiku.
- Skill `desplegar`: resumen de producción como comentario en la PR, aviso a la sesión del servidor y despliegue solo con el OK del usuario.
- Hook `jev-router`: Jev elige modelo y effort de cada subagente; los `Plan` van con Fable.
- Hook `anti-filtraciones`: bloquea commits y pushes con secretos, archivos sensibles o datos reales.
- `scripts/ajustes.py`: ajustes que un plugin no puede fijar (atribución vacía, confirmación para producción, autocompact 200K).

## Plugins recomendados (midudev/better-claude)

No se copian aquí: los mantiene midudev y se actualizan desde su marketplace. `commit@better-claude` no se instala porque la skill `commit` de este plugin lo sustituye.

```bash
claude plugin marketplace add midudev/better-claude
for p in sub-meter token-meter context-meter image-preview time-machine narrator; do claude plugin install $p@better-claude; done
```

## Hook `anti-filtraciones`

Se ejecuta como `PreToolUse` sobre `Bash`, solo cuando el comando contiene `git commit` o `git push`. En un commit revisa el diff del índice; en un push revisa los commits pendientes respecto a `@{u}`, si la rama tiene upstream.

Bloquea claves privadas y tokens habituales (GitHub, AWS, Slack, Stripe, Anthropic y OpenAI), JWT, asignaciones de contraseñas o claves, archivos `.env` (salvo `.env.example`), claves privadas y SSH, contenido de `_muestras/`, XML de factura FEL y DPI de Guatemala. El motivo del bloqueo indica archivo y línea, y como máximo los primeros cuatro caracteres del hallazgo, nunca el valor completo.

Hay dos formas de declarar una excepción:

- Añadir `reglas:permitir` como comentario en la misma línea.
- Listar la ruta o patrón en `.reglas-permitir`, en la raíz del repositorio, con una entrada por línea.

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

## Ajustes automáticos (1.3.0)

En `SessionStart`, además de mostrar `REGLAS.md`, se ejecuta:

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
python3 -m json.tool hooks/hooks.json > /dev/null
```

## Módulo de servidor

En el servidor Linux con systemd, como root (sustituye `usuario` y `nombre-equipo`):

```bash
bash "$(ls -d ~usuario/.claude/plugins/cache/thealejandro/reglas/*/ | sort -V | tail -1)scripts/instalar-servidor.sh" usuario nombre-equipo
```

Añade `--simular` antes del usuario para revisar las unidades y operaciones sin instalarlas. Requiere Bash, Python 3, sudo, curl, flock y tmux, y `claude` instalado y autenticado para ese usuario, con Remote Control habilitado y `~/work` existente y confiable. Las opciones se contrastaron con los manuales de systemctl, loginctl y tmux y la [documentación oficial de Remote Control](https://code.claude.com/docs/en/remote-control) y del [CLI](https://code.claude.com/docs/en/cli-reference).

Instala los tres scripts en `/usr/local/bin`, activa linger y habilita Remote Control con el nombre del equipo, `same-dir`, capacidad 16 y permisos `auto`. Retoma las sesiones fijas y las guardadas al apagar, espera la red y evita duplicar conversaciones vivas. Omite las abiertas desde la app (`sdk-cli`) al guardar; cada 15 minutos guarda las abiertas y revive solo las fijas caídas. No fija `DOCKER_HOST`.

Conserva `~/.config/claude-arranque/sesiones.conf` existente; las unidades diferentes se respaldan en `.bak.*` con aviso antes de reemplazarlas. Las unidades ya activas incorporan los cambios en su siguiente arranque. El formato de sesiones es `ventana|id|nombre|carpeta`, una por línea.

También activa la actualización diaria del plugin para ese usuario (ver abajo).

### Actualización diaria del plugin

El `autoUpdate` del marketplace no basta en servidores donde las sesiones viven días. Como root:

```bash
bash "$(ls -d ~usuario/.claude/plugins/cache/thealejandro/reglas/*/ | sort -V | tail -1)scripts/instalar-actualizacion.sh" usuario [otro-usuario...]
```

Sirve también para root. Instala `/usr/local/bin/claude-actualizar-reglas` y el temporizador de sistema `claude-actualizar-reglas@<usuario>.timer` (04:00 hora del servidor, hasta 30 min de margen aleatorio; si el equipo estaba apagado, se ejecuta al arrancar). Cada ejecución hace `claude plugin marketplace update thealejandro`, `claude plugin update reglas@thealejandro` y aplica `ajustes.py`; el registro queda en `~/.local/state/claude-actualizar-reglas.log`. No pasa `-y`: si el marketplace declarase un comando, la actualización se rechaza. Las sesiones abiertas cargan la versión nueva con `/reload-plugins` o al reiniciarse. Para actualizar al momento: `systemctl start claude-actualizar-reglas@usuario.service`. Si `ajustes.py` falla al arrancar una sesión, el error queda en `~/.local/state/reglas-ajustes.log`.

Uso como usuario del módulo: `claude-nueva-sesion "Proyecto (equipo)" ~/work/proyecto [archivo-encargo]`. También admite `--retomar <session-id> "Nombre (equipo)" [carpeta]`. La sesión queda registrada para próximos reinicios. `ajustes.py` permite ambos formatos del lanzador instalado en la siguiente sesión del plugin. Desde otro equipo, solicita la apertura por `SendMessage` a una sesión del servidor; en producción confirma primero con el usuario.
