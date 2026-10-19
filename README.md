# reglas — plugin de Claude Code

Reglas comunes para todas las sesiones de Claude Code de thealejandro, en cualquier máquina (servidor de desarrollo, Hestia, Windows, Mac).

Incluye:
- `REGLAS.md`, inyectado al inicio de cada sesión (hook `SessionStart`).
- Skill `commit`: commits convencionales en el idioma del repo, sin atribución, sin push a `main` sin permiso.
- Hook `jev-router`: Jev elige modelo y effort de cada subagente; los `Plan` van con Fable.
- Hook `anti-filtraciones`: bloquea commits y pushes con secretos, archivos sensibles o datos reales.
- `scripts/ajustes.py`: ajustes que un plugin no puede fijar (atribución vacía, confirmación para producción, autocompact 200K).

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

Actualizar: `claude plugin marketplace update thealejandro && claude plugin update reglas@thealejandro`. Las sesiones cargan los cambios al iniciarse o retomarse.

## Delegar en Codex y Kimi: `agente-lanzar`

`scripts/agente-lanzar` lanza Codex o Kimi como `dev` en la sesión tmux `agentes`, sobre una carpeta de `~/work` en rama propia (nunca main/master/develop), sin poder hacer push (pushurl falso y `gh` sin sesión), con 2 h máximo y registro en `~/work/_logs/`.

```bash
# En el servidor, como root:
install -m 755 "$(ls -d ~dev/.claude/plugins/cache/thealejandro/reglas/*/ | tail -1)scripts/agente-lanzar" /usr/local/bin/agente-lanzar
# Para que el modo auto no lo bloquee, añade en settings.json de quien lo use:
#   "permissions": { "allow": ["Bash(agente-lanzar *)"] }
```

Uso: `agente-lanzar codex ~/work/repo-tarea ~/work/_logs/encargo.md`. Codex corre sin su sandbox (bwrap no puede crear namespaces en Ubuntu con AppArmor); los límites son los de arriba más el usuario `dev` sin sudo.

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
