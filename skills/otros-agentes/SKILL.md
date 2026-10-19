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

Tienen el navegador Chrome DevTools MCP (sin ventana, pero renderiza todo: capturas, consola, red y trazas de rendimiento) para QA de interfaz.

## Solo lectura o segunda opinión

- Codex: `codex exec --skip-git-repo-check -s read-only "<pregunta>"` (aquí `-p` es perfil, no prompt).
- Cursor: `cursor-agent -p --trust --output-format text "<pregunta>"` (sin `--force` no ejecuta comandos).
- Kimi: `kimi -p "<pregunta>" --output-format text` (con `-p` no admite `--plan`, `-y` ni `--auto`; pídele en el prompt que no modifique nada).

## Nunca

Secretos, `.env` de producción, datos de clientes o pacientes, ni nada de producción. Ellos no hacen push ni PR: eso lo hace la sesión que delega.
