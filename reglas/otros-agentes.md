
## Delegar y QA en @SERVIDOR_DESARROLLO@

- **Delegar en Codex, Kimi o Cursor (@SERVIDOR_DESARROLLO@):** sigue la skill `otros-agentes`; `agente-lanzar <codex|kimi|cursor> <carpeta-en-rama-propia> ~/work/_logs/<encargo>.md` (worktree aparte, sin push, 2 h, registro en `~/work/_logs/`). Encargo corto: objetivo, «listo cuando», «no toques», commit sin atribución, consultar la doc oficial y, si el contexto crece, dejar el avance en un archivo y seguir desde ahí. Al terminar, revisa su commit antes de abrir la PR.

- **Pruebas de navegador/QA:** pídelas por `SendMessage` a una sesión de @SERVIDOR_DESARROLLO@ con URL, flujo, qué medir y usuario de prueba (nunca credenciales de producción). Esa sesión lanza `qa-pedir`, espera a que exista `estado` y devuelve el informe a quien lo pidió. Solo URLs alcanzables desde el servidor; para localhost hace falta staging o un túnel.
