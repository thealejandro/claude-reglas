#!/usr/bin/env python3
"""SessionStart: si claude-reiniciar-sesiones reinició esta conversación, avisa al modelo una vez."""
import json
import os
import re
import sys


def limpio(valor, patron):
    return valor if isinstance(valor, str) and re.fullmatch(patron, valor) else '?'


def main():
    try:
        sesion = json.load(sys.stdin).get('session_id')
        if not isinstance(sesion, str) or not re.fullmatch('[0-9a-f-]{36}', sesion):
            return
        ruta = os.path.join(os.path.expanduser('~'), '.local/state/claude-reiniciar', sesion + '.json')
        if not os.path.isfile(ruta):
            return
        with open(ruta, encoding='utf-8') as f:
            marca = json.load(f)
        os.remove(ruta)
        print('Aviso del módulo de servidor: esta conversación se reinició automáticamente el '
              f"{limpio(marca.get('fecha'), r'[0-9A-Za-z:. -]{1,32}')} para actualizar Claude Code de "
              f"{limpio(marca.get('de'), r'[0-9A-Za-z.+-]{1,32}')} a {limpio(marca.get('a'), r'[0-9A-Za-z.+-]{1,32}')}. "
              'Díselo al usuario en una frase en tu próxima respuesta.')
    except Exception:
        pass


if __name__ == '__main__':
    main()
