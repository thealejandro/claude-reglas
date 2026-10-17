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
python3 ~/.claude/plugins/marketplaces/thealejandro/scripts/ajustes.py
# Opcional, para Jev (la key nunca va al repo):
mkdir -p ~/.config/jev && chmod 700 ~/.config/jev
read -rsp 'Key de Jev: ' K; printf 'TYPESAFE_API_KEY=%s\n' "$K" > ~/.config/jev/env; chmod 600 ~/.config/jev/env; unset K
```

Actualizar: `claude plugin marketplace update thealejandro && claude plugin update reglas@thealejandro`. Las sesiones cargan los cambios al iniciarse o retomarse.
