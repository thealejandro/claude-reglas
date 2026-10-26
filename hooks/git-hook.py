#!/usr/bin/env python3
"""Hooks de git globales (pre-commit, commit-msg, pre-push) para agentes sin hooks propios.

Reutilizan las funciones de anti-filtraciones.py. Ante un fallo interno dejan pasar y avisan por stderr.
"""
import importlib.util
import os
import re
import shutil
import sys
import time
from pathlib import Path

RAMAS_PROTEGIDAS = ('refs/heads/main', 'refs/heads/master')
CEROS = '0' * 40
ATRIBUCION = re.compile(
    r'(?i)^\s*co-authored-by:.*\b(claude|anthropic|codex|openai|cursor|kimi|moonshot)\b'
    r'|^\W*generated with .*(claude|codex|cursor|kimi|openai|anthropic)'
    r'|^\s*claude-session:|claude\.ai/code/session|🤖')


def cargar_af():
    spec = importlib.util.spec_from_file_location('anti_filtraciones', Path(__file__).with_name('anti-filtraciones.py'))
    af = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(af)
    return af


def revisar(af, root, deadline, patch, accion, log_opts=None):
    permitidas = af.load_allowed_paths(root)
    hallazgos, anadidas = af.scan_patch(patch, permitidas)
    avisos = []
    ejecutable = shutil.which('gitleaks')
    if ejecutable:
        extra, avisos = af.gitleaks_scan(ejecutable, root, [accion], deadline, permitidas, {accion: anadidas}, log_opts)
        hallazgos.extend(extra)
    hallazgos = af.unique_findings(hallazgos)
    return af.decision_reason(hallazgos, avisos) if hallazgos else None


def pre_commit(af, deadline):
    root = af.repository_root(os.getcwd(), deadline)
    return revisar(af, root, deadline, af.staged_patch(root, deadline), 'commit')


def commit_msg(archivo):
    lineas = Path(archivo).read_text(encoding='utf-8', errors='replace').splitlines()
    for linea in lineas:
        if not linea.startswith('#') and ATRIBUCION.search(linea):
            return 'El mensaje de commit lleva atribución a una IA («{0}»); quítala.'.format(linea.strip())
    return None


def pre_push(af, deadline, entrada):
    root = af.repository_root(os.getcwd(), deadline)
    for linea in entrada.splitlines():
        partes = linea.split()
        if len(partes) != 4:
            continue
        _, local, remota, remoto = partes
        if local == CEROS:
            continue
        if remota in RAMAS_PROTEGIDAS:
            return ('Push a {0} bloqueado: se hace solo con confirmación del usuario y '
                    '`git push origin main --no-verify`.'.format(remota.rsplit('/', 1)[-1]))
        rango = [local, '--not', '--remotes'] if remoto == CEROS else [remoto + '..' + local]
        resultado = af.run(af.git_command('log', '--format=', '--patch', '--no-color', '--no-ext-diff',
                                          '--no-textconv', '--unified=0', *rango, '--'), root, deadline)
        if resultado.returncode != 0:
            raise af.HookFailure('git log de commits a empujar no pudo completarse')
        motivo = revisar(af, root, deadline, resultado.stdout, 'push', ' '.join(rango))
        if motivo:
            return motivo
    return None


def main(argv):
    deadline = time.monotonic() + 5
    nombre = argv[1] if len(argv) > 1 else ''
    if nombre == 'commit-msg':
        motivo = commit_msg(argv[2])
    elif nombre in ('pre-commit', 'pre-push'):
        af = cargar_af()
        deadline = time.monotonic() + af.TIMEOUT
        motivo = pre_commit(af, deadline) if nombre == 'pre-commit' else pre_push(af, deadline, sys.stdin.read())
    else:
        return 0
    if motivo:
        print(motivo, file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    try:
        codigo = main(sys.argv)
    except Exception as error:
        print('reglas: fallo interno del hook de git ({0}); se permite la operación.'.format(type(error).__name__),
              file=sys.stderr)
        codigo = 0
    sys.exit(codigo)
