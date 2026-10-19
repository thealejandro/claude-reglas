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
python3 ~/.claude/plugins/marketplaces/thealejandro/scripts/ajustes.py
# Opcional, para Jev (la key nunca va al repo):
mkdir -p ~/.config/jev && chmod 700 ~/.config/jev
read -rsp 'Key de Jev: ' K; printf 'TYPESAFE_API_KEY=%s\n' "$K" > ~/.config/jev/env; chmod 600 ~/.config/jev/env; unset K
```

Actualizar: `claude plugin marketplace update thealejandro && claude plugin update reglas@thealejandro`. Las sesiones cargan los cambios al iniciarse o retomarse.
