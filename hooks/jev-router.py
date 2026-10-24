#!/usr/bin/env python3
"""Hook PreToolUse (Agent): Jev elige modelo y effort de cada subagente.

Red de seguridad: sin key, con error, timeout (3 s) o confianza baja, no cambia nada
y se queda la elección del orquestador. Los planes siempre van a Fable.
Key: opción jev_api_key del plugin (CLAUDE_PLUGIN_OPTION_JEV_API_KEY) o, si no,
~/.config/jev/env (TYPESAFE_API_KEY=...), modo 600.
"""
import json, os, sys, time, urllib.request

MIN_CONF = 0.6
LOG = os.path.expanduser('~/.claude/jev-router.log')

def log(msg):
    try:
        with open(LOG, 'a') as f:
            f.write(time.strftime('%F %T ') + msg + '\n')
    except OSError:
        pass

def key():
    k = os.environ.get('CLAUDE_PLUGIN_OPTION_JEV_API_KEY', '').strip()
    if k:
        return k
    try:
        for line in open(os.path.expanduser('~/.config/jev/env')):
            k, _, v = line.strip().partition('=')
            if k == 'TYPESAFE_API_KEY' and v:
                return v.strip().strip('"\'')
    except OSError:
        pass
    return os.environ.get('TYPESAFE_API_KEY')

def emit(updated, reason):
    print(json.dumps({'hookSpecificOutput': {
        'hookEventName': 'PreToolUse',
        'updatedInput': updated,
        'additionalContext': reason}}))

def main():
    data = json.load(sys.stdin)
    ti = dict(data.get('tool_input') or {})
    tipo = ti.get('subagent_type') or ''
    desc = (ti.get('description') or '')[:200]
    if tipo == 'fork':
        return
    if tipo == 'Plan':
        if ti.get('model') != 'fable':
            ti['model'] = 'fable'
            emit(ti, 'Jev-router: los planes van con Fable.')
            log(f'plan -> fable | {desc}')
        return
    k = key()
    if not k:
        return
    state = {'tipo_subagente': tipo or 'general-purpose', 'descripcion': desc,
             'tarea': (ti.get('prompt') or '')[:6000]}
    body = {'model': 'jev-latest', 'state': state, 'questions': {
        'modelo': {'type': 'choice',
            'instructions': 'Elige el modelo más barato que haga bien esta tarea de un agente de programación.',
            'criteria': {
                'haiku': 'Mecánica o de bajo riesgo: buscar o localizar código, leer y resumir archivos o logs, correr un comando y reportar, renombrados, ediciones triviales, commits.',
                'sonnet': 'Implementar una tarea bien definida, escribir o arreglar tests, QA, documentación, refactors acotados, depuración normal.',
                'opus': 'Difícil o crítica: depuración compleja, auditoría de seguridad, arquitectura o diseño transversal, revisión final de código sensible, decisiones con mucha ambigüedad.'}},
        'effort': {'type': 'choice',
            'instructions': 'Cuánto razonamiento necesita la tarea.',
            'criteria': {'low': 'Directa, pocos pasos, sin decisiones delicadas.',
                         'medium': 'Varios pasos o algo de criterio.',
                         'high': 'Muchos pasos, mucha incertidumbre o alto costo de equivocarse.'}}}}
    req = urllib.request.Request('https://api.typesafe.ai/v1/systemone',
        data=json.dumps(body).encode(), method='POST',
        headers={'Authorization': f'Bearer {k}', 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=3) as r:
            ans = json.load(r)['answers']
    except Exception as e:
        log(f'error {type(e).__name__} | {desc}')
        return
    m, ef = ans.get('modelo', {}), ans.get('effort', {})
    antes = f"{ti.get('model', '-')}/{ti.get('effort', '-')}"
    cambios = []
    if m.get('confidence', 0) >= MIN_CONF and m.get('choice') in ('haiku', 'sonnet', 'opus'):
        ti['model'] = m['choice']; cambios.append('modelo')
    if ef.get('confidence', 0) >= MIN_CONF and ef.get('choice') in ('low', 'medium', 'high'):
        ti['effort'] = ef['choice']; cambios.append('effort')
    log(f"{antes} -> {ti.get('model', '-')}/{ti.get('effort', '-')} "
        f"(conf {m.get('confidence', 0):.2f}/{ef.get('confidence', 0):.2f}) | {desc}")
    if cambios:
        emit(ti, f"Jev-router asignó {ti.get('model')} con effort {ti.get('effort')}.")

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        log(f'fallo {type(e).__name__}')
    sys.exit(0)
