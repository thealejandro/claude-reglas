---
name: ideas
description: Procesa la cola local de ideas, bugs y pendientes que capturan los hooks (~/.local/state/cabo/ideas/cola.jsonl) y los convierte en issues de GitHub, por lotes y con un subagente Haiku. Úsala cuando el hook avise de ideas en cola, al terminar un paso, o cuando el usuario diga «anota», «pule» o «abre tickets».
allowed-tools: Bash(python3 *), Bash(gh *), Agent, AskUserQuestion
---

# Ideas: de la cola a issues

La cola la llenan los hooks sin gastar tokens (formato en el README, «Cola de ideas»). Esta skill la vacía. Todo lo que ejecutas con `gh` pasa por el hook `anti-filtraciones`.

Ayudante de la cola (no edites el JSONL a mano):

```bash
python3 -I "${CLAUDE_SKILL_DIR}/scripts/cola.py" pendientes [--sesion ID] [--repo owner/repo]
python3 -I "${CLAUDE_SKILL_DIR}/scripts/cola.py" resolver HASH creada|comentada|duplicada|descartada [--issue owner/repo#N]
python3 -I "${CLAUDE_SKILL_DIR}/scripts/cola.py" aplazar HASH --motivo "…"
python3 -I "${CLAUDE_SKILL_DIR}/scripts/cola.py" hoy owner/repo
```

## Pasos

1. **Cuota.** Si tienes la herramienta de uso (`get_usage`) y la cuota supera el 80 %, no proceses: `aplazar` cada hash con el motivo «cuota» y díselo al usuario. Si no puedes medirla, sigue.
2. **Leer.** `pendientes` (por defecto todas; con `$ARGUMENTS` = `sesion` solo las de esta sesión). Agrupa por `remoto`. Una entrada sin `remoto` o con uno que no puedas resolver a un repo de GitHub va a «dudosos».
3. **Visibilidad y tipo de repo.** Por cada repo: `gh repo view OWNER/REPO --json visibility,isArchived`. Marca como **proyecto clínico** los repos cuyo `CLAUDE.md`, runbook o descripción lo digan (pacientes, expedientes, enfermería, salud).
4. **Subagente Haiku por lote** (un solo `Agent` por repo, `model: haiku`, effort bajo). Pásale: las entradas del repo (`hash`, `categoria`, `extracto`), la lista de issues abiertos (`gh issue list -R … --state open --limit 200 --json number,title,body,labels`) y los cerrados en 30 días (`gh issue list -R … --state closed --search "closed:>=FECHA" --json number,title,labels`). Pídele, por entrada, un JSON:
   `{"hash":…, "accion":"crear"|"ampliar"|"duplicada"|"descartar"|"dudosa", "issue_existente":N|null, "titulo":…, "cuerpo":…, "prioridad":"alta|media|baja", "decision":true|false, "motivo":…}`.
   Reglas para el subagente: **redacta de nuevo**, nunca copies el extracto literal; sin hosts, IPs, usuarios, rutas de servidores, nombres de clientes ni pacientes; «ampliar» si hay un issue abierto sobre lo mismo y la entrada añade algo; «duplicada» si no añade nada o coincide con uno cerrado en 30 días; «dudosa» si no está claro el destino o el duplicado; «decision» si necesita respuesta del usuario.
5. **Confirmar con `AskUserQuestion`** (agrupa en una sola pregunta por repo, con la lista de lo que harías) cuando el repo sea **público**, la acción sea **dudosa**, el proyecto sea **clínico** o la entrada sea una **decisión**. En el resto, actúa sin preguntar. Si el usuario no responde o no hay interacción, aplaza esas entradas.
6. **Ejecutar.**
   - `ampliar`: `gh issue comment N -R … --body-file` con un comentario nuevo y breve; luego `resolver HASH comentada --issue OWNER/REPO#N`.
   - `crear`: antes, `hoy OWNER/REPO`; si `queda` es 0, `aplazar` con el motivo «tope diario» (tope por repo: 5, ajustable con `IDEAS_TOPE_DIARIO`). Si no, asegura las etiquetas (`idea-auto`, `prioridad: …`, y `decisión` si procede; créalas si no existen) y `gh issue create -R … --label idea-auto,"prioridad: X" --title … --body-file …` con contexto para retomarlo. Luego `resolver HASH creada --issue OWNER/REPO#N`.
   - `duplicada` → `resolver HASH duplicada --issue …`; `descartar` → `resolver HASH descartada`.
   - Si el hook `anti-filtraciones` bloquea, reescribe sin el dato; nunca lo evites con `reglas:permitir`.
7. **Informar.** Una lista breve con enlaces a los issues creados o ampliados, lo aplazado y lo descartado.
