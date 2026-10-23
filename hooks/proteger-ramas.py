#!/usr/bin/env python3
"""PreToolUse Bash: un git merge o git pull sobre main/master pregunta al usuario.

Una regla ask no puede saber la rama actual; este hook sí. Su "ask" fuerza la
pregunta también en modo auto (https://code.claude.com/docs/en/hooks), en vez de
que el clasificador bloquee el merge sin preguntar.
"""
import json
import os
import re
import shlex
import subprocess
import sys

RAMAS_PROTEGIDAS = {'main', 'master'}
GIT_RE = re.compile(r'\bgit\b')


def carpeta_de(partes, cwd):
    """Carpeta del repo: la de `git -C`, si no la del último `cd`, si no la de la sesión."""
    carpeta = cwd
    for i, parte in enumerate(partes):
        if parte == 'cd' and i + 1 < len(partes):
            carpeta = os.path.join(carpeta, os.path.expanduser(partes[i + 1]))
        if parte == '-C' and i > 0 and partes[i - 1] == 'git' and i + 1 < len(partes):
            return os.path.join(carpeta, os.path.expanduser(partes[i + 1]))
    return carpeta


def es_merge(partes):
    for i, parte in enumerate(partes):
        if parte != 'git':
            continue
        resto = partes[i + 1:]
        while len(resto) >= 2 and resto[0] in ('-C', '-c'):
            resto = resto[2:]
        if resto and resto[0] in ('merge', 'pull'):
            return True
    return False


def main():
    try:
        datos = json.load(sys.stdin)
        comando = datos.get('tool_input', {}).get('command', '')
        if not GIT_RE.search(comando):
            return
        partes = shlex.split(comando)
    except (ValueError, json.JSONDecodeError):
        return
    if not es_merge(partes):
        return
    carpeta = carpeta_de(partes, datos.get('cwd') or os.getcwd())
    try:
        # safe.directory: root puede consultar repos de dev sin el error de propietario.
        rama = subprocess.run(['git', '-c', 'safe.directory=*', '-C', carpeta, 'branch', '--show-current'],
                              capture_output=True,
                              text=True, timeout=3, check=False).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return
    if rama in RAMAS_PROTEGIDAS:
        print(json.dumps({'hookSpecificOutput': {
            'hookEventName': 'PreToolUse',
            'permissionDecision': 'ask',
            'permissionDecisionReason': f'Merge sobre {rama} en {carpeta}: es producción, confirma tú.',
        }}, ensure_ascii=False))


if __name__ == '__main__':
    main()
