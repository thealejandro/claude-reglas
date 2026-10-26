#!/usr/bin/env python3
"""Hook SessionStart: imprime REGLAS.md más los bloques de reglas/ cuyas opciones del plugin estén configuradas."""
import os, re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
BLOQUES = (('REPO_RUNBOOKS', 'runbooks.md'), ('SERVIDORES', 'servidores.md'),
           ('SERVIDOR_DESARROLLO', 'otros-agentes.md'))
# Secciones que dependen de herramientas de Claude Code y no aplican a otros agentes.
SOLO_CLAUDE = ('Modelos y subagentes', 'Coordinación entre sesiones', 'Sesiones en servidores', 'Delegar y QA')
MARCA = '<!-- Generado por el plugin reglas (ajustes.py); no editar a mano. -->'
AVISO = ('Las menciones a skills (`/commit`, `/desplegar`), hooks y `SendMessage` son de Claude Code; '
         'el resto aplica igual. Los hooks de git hacen cumplir lo crítico.')

def generar(entorno=os.environ, otros_agentes=False):
    texto = (RAIZ / 'REGLAS.md').read_text(encoding='utf-8')
    valores = {'IDIOMA': entorno.get('CLAUDE_PLUGIN_OPTION_IDIOMA', '').strip() or 'español'}
    for clave, archivo in BLOQUES:
        v = entorno.get('CLAUDE_PLUGIN_OPTION_' + clave, '').strip()
        if v:
            valores[clave] = v
            texto += (RAIZ / 'reglas' / archivo).read_text(encoding='utf-8')
    if otros_agentes:
        partes = re.split(r'(?m)^(?=## )', texto)
        texto = ''.join(p for p in partes if not p.startswith(tuple('## ' + t for t in SOLO_CLAUDE)))
        texto = MARCA + '\n\n' + AVISO + '\n\n' + texto
    return re.sub(r'@([A-Z_]+)@', lambda m: valores.get(m[1], m[0]), texto)

def main():
    try:
        print(generar())
    except Exception:
        print((RAIZ / 'REGLAS.md').read_text(encoding='utf-8'))

if __name__ == '__main__':
    main()
