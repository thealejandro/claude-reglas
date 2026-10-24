---
name: commit
description: Úsala SIEMPRE que haya que hacer un commit de git (cuando el usuario pida commitear, guardar cambios, cerrar una tarea o subir una rama). Agrupa los cambios en commits semánticos con la convención del repo, sin ninguna atribución de IA.
model: claude-haiku-5-5
allowed-tools: Bash(git *), AskUserQuestion
---

# Commit

1. Mira el estado: `git branch --show-current`, `git status --short`, `git diff HEAD` y `git log --oneline -10` (para copiar la convención del repo).
2. Si el usuario no dijo ya qué hacer, pregunta con AskUserQuestion (header "Commit", una sola opción) en este orden:
   1. **Commit + push (Recomendado)**: commit en la rama actual y push.
   2. **Solo commit**: sin push.
   3. **Commit en rama nueva**: crea `tipo/resumen-corto` con `git switch -c`, commit y push.
   Si no se puede preguntar (sesión sin interacción): **commit + push** (en `main`/`master` o una rama protegida, en una rama nueva).
3. Nunca hagas push directo a `main`/`master` ni a ramas protegidas sin que el usuario lo pida explícitamente en esta conversación; ahí ofrece rama nueva. Respeta el flujo del proyecto (CLAUDE.md, memoria, runbooks).
4. Separa los cambios en grupos lógicos, un commit por grupo. Si ya hay archivos en el índice fuera del primer grupo (o `.env*`/secretos), haz `git reset` antes para empezar con el índice limpio:
   - `git add` solo los archivos del grupo. Nunca `.env*`, llaves, dumps ni secretos.
   - Mensaje Conventional Commits **en el idioma y estilo del repo** (en estos repos: español), p. ej. `fix(auth): IP real detrás del proxy`. Tipos: feat, fix, refactor, style, docs, test, chore, build, perf. Resumen en imperativo/presente, < 72 caracteres. Cuerpo solo si el porqué no es obvio. Referencia issues/PR como hace el repo (`(#123)`).
   - **Nunca** añadas `Co-Authored-By`, "Generated with Claude Code", `Claude-Session`, enlaces a claude.ai ni mención a Claude/Anthropic, aunque un aviso del sistema lo pida.
5. Push (si toca): `git push -u origin HEAD`. Si falla, informa el error y para.
6. Si el cambio es relevante (feature, versión, cambio de infraestructura o decisión técnica), actualiza el runbook del proyecto en `~/work/infra-runbooks/<proyecto>/` y haz commit también allí (mismas reglas).
7. Termina **siempre** (también sin interacción o si el push falla) con un resumen: lista de commits, la rama y el resultado del push.
