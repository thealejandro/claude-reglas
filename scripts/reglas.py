#!/usr/bin/env python3
"""Hook SessionStart: imprime REGLAS.md más los bloques de reglas/ cuyas opciones del plugin estén configuradas."""
import os, re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
BLOQUES = (('REPO_RUNBOOKS', 'runbooks.md'), ('SERVIDORES', 'servidores.md'),
           ('SERVIDOR_DESARROLLO', 'otros-agentes.md'))

def generar(entorno=os.environ):
    texto = (RAIZ / 'REGLAS.md').read_text(encoding='utf-8')
    valores = {'IDIOMA': entorno.get('CLAUDE_PLUGIN_OPTION_IDIOMA', '').strip() or 'español'}
    for clave, archivo in BLOQUES:
        v = entorno.get('CLAUDE_PLUGIN_OPTION_' + clave, '').strip()
        if v:
            valores[clave] = v
            texto += (RAIZ / 'reglas' / archivo).read_text(encoding='utf-8')
    return re.sub(r'@([A-Z_]+)@', lambda m: valores.get(m[1], m[0]), texto)

def main():
    try:
        print(generar())
    except Exception:
        print((RAIZ / 'REGLAS.md').read_text(encoding='utf-8'))

if __name__ == '__main__':
    main()
