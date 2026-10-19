# reglas — plugin de Claude Code

Reglas comunes para todas las sesiones de Claude Code de thealejandro, en cualquier máquina (servidor de desarrollo, Hestia, Windows, Mac).

Incluye:
- `REGLAS.md`, inyectado al inicio de cada sesión (hook `SessionStart`).
- Skill `commit`: commits convencionales en el idioma del repo, sin atribución, sin push a `main` sin permiso.
- Hook `jev-router`: Jev elige modelo y effort de cada subagente; los `Plan` van con Fable.
- `scripts/ajustes.py`: ajustes que un plugin no puede fijar (atribución vacía, confirmación para producción, autocompact 200K).

## Instalar en una máquina

```bash
claude plugin marketplace add thealejandro/claude-reglas
claude plugin install reglas@thealejandro
# Opcional, para Jev (la key nunca va al repo):
mkdir -p ~/.config/jev && chmod 700 ~/.config/jev
read -rsp 'Key de Jev: ' K; printf 'TYPESAFE_API_KEY=%s\n' "$K" > ~/.config/jev/env; chmod 600 ~/.config/jev/env; unset K
```

Actualizar: `claude plugin marketplace update thealejandro && claude plugin update reglas@thealejandro`. Las sesiones cargan los cambios al iniciarse o retomarse.

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
