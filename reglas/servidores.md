
## Sesiones en servidores (módulo de servidor: @SERVIDORES@)

- **Migrar una sesión** (por ejemplo, sacarla del home): escribe un traspaso sin secretos en `~/.config/claude-arranque/traspasos/<nombre>.md` (objetivo, estado, decisiones, pendientes, OKs pendientes), abre la nueva con `claude-nueva-sesion "<Nombre> (<equipo>)" ~/work/<proyecto> <encargo>` (encargo: «lee el traspaso y espera al usuario») y avisa al usuario para que cierre la vieja con `/exit`. Escribir el traspaso pide permiso al usuario en el chat.
- El plugin se actualiza solo cada día a las 04:00 en las máquinas con `claude-actualizar-reglas`; las sesiones abiertas cargan la versión nueva con `/reload-plugins`, sin reiniciarlas.
- **Abrir sesiones en servidores con el módulo:** cualquier sesión puede pedir por `SendMessage` a una sesión del servidor destino que ejecute `claude-nueva-sesion "<Nombre> (<equipo>)" <carpeta> [encargo]` (encargo: archivo con el prompt inicial). Abrir una sesión no cambia configuración y se hace sin preguntar al usuario, salvo en servidores de producción, donde se confirma con él.
