#!/usr/bin/env python3
"""Aplica a ~/.claude/settings.json los ajustes que un plugin no puede fijar:
sin atribución, confirmación para producción y autocompact de 200K. Idempotente."""
import json, os, shutil, time
p = os.path.expanduser('~/.claude/settings.json')
d = json.load(open(p)) if os.path.exists(p) else {}
if os.path.exists(p):
    shutil.copy(p, p + time.strftime('.bak-%Y%m%d%H%M%S'))
d['attribution'] = {'commit': '', 'pr': ''}
ask = d.setdefault('permissions', {}).setdefault('ask', [])
for r in ['Bash(gh pr merge *)', 'Bash(gh api *merge*)', 'Bash(git push origin main*)',
          'Bash(git push origin master*)', 'Bash(git push * HEAD:main*)', 'Bash(gh release create *)']:
    if r not in ask:
        ask.append(r)
ms = d.setdefault('modelSettings', {})
for m in ('claude-fable-5-1', 'claude-opus-5-5', 'claude-sonnet-5-5', 'claude-haiku-5-5'):
    ms.setdefault(m, {}).setdefault('autoCompactWindow', 200000)
os.makedirs(os.path.dirname(p), exist_ok=True)
json.dump(d, open(p, 'w'), indent=2, ensure_ascii=False)
open(p, 'a').write('\n')
print('Ajustes aplicados en', p)
