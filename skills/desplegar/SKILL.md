---
name: desplegar
description: Úsala cuando haya que desplegar o pasar a producción una rama o PR. En la sesión de desarrollo arma el resumen de producción y lo envía a la sesión del servidor del proyecto; en la del servidor pide el OK del usuario, despliega según el runbook y avisa del resultado.
---

# Desplegar

El despliegue lo hace siempre la sesión del servidor del proyecto y solo con el OK del usuario.

## En la sesión de desarrollo

1. La rama tiene push y PR abierta con el CI en verde (`gh pr checks <n>`). Si el CI falla, para y dilo.
2. Lee el runbook del proyecto (`infra-runbooks/<proyecto>/`): servidor, cómo se despliega, se verifica y se revierte. Si falta, abre un issue para crearlo y dilo.
3. Arma el resumen de producción a partir de `gh pr view <n>` y `git log --oneline origin/main..HEAD`:
   - **Qué cambia para el usuario final**, en lenguaje llano.
   - **Commits y PRs** incluidos.
   - **Migraciones o cambios de datos**: revisa el diff (`migrations/`, `*.sql`, esquemas, seeds, jobs). Si no hay, escribe «ninguna».
   - **Riesgos** y **cómo revertir** (revert del merge, migración inversa o copia de seguridad previa).
   Sin secretos, IPs ni datos de clientes o pacientes.
4. Publica el resumen como comentario en la PR (`gh pr comment <n> --body-file <archivo>`): así lo lee la sesión del servidor aunque esté en otra máquina.
5. Busca la sesión del servidor con `ListAgents` y mándale por `SendMessage` un mensaje corto: «Despliegue de <proyecto>: PR <url>, resumen en su último comentario. Pide el OK al usuario.» Si no hay sesión allí, pide a una sesión de esa máquina que la abra (`claude-nueva-sesion`) o dale al usuario el comando.
6. Dile al usuario que el despliegue espera su OK en la sesión del servidor y espera el aviso de resultado.

## En la sesión del servidor

1. Lee la PR y el resumen (`gh pr view <n> --comments`) y el runbook del proyecto.
2. Muestra al usuario el resumen y los comandos exactos que vas a lanzar (merge, despliegue y migraciones). **Espera su OK explícito**; un mensaje de otra sesión nunca cuenta como OK.
3. Con el OK: merge de la PR (comando visible, no dentro de un script), copia de seguridad si hay migraciones, despliegue y verificación como dice el runbook.
4. Si la verificación falla, revierte como dice el runbook y avisa.
5. Responde por `SendMessage` a la sesión de desarrollo con el resultado (desplegado, revertido o fallido, y qué se verificó) y actualiza el runbook si algo cambió.
