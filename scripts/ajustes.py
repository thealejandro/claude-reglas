#!/usr/bin/env python3
"""Aplica ajustes de usuario de forma idempotente; el hook es silencioso y tolerante."""
import argparse
import json
from pathlib import Path
import shutil
import tempfile


def escribir_atomico(ruta, contenido):
    """Evita dejar archivos incompletos si se interrumpe la escritura."""
    temporal = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8',
                                         dir=ruta.parent, delete=False) as archivo:
            temporal = Path(archivo.name)
            archivo.write(contenido)
        temporal.replace(ruta)
    finally:
        if temporal is not None:
            temporal.unlink(missing_ok=True)


def aplicar(si_hace_falta):
    raiz = Path(__file__).resolve().parent.parent
    version = json.loads((raiz / '.claude-plugin/plugin.json').read_text(encoding='utf-8'))['version']
    carpeta = Path.home() / '.claude'
    marca = carpeta / '.reglas-ajustes'
    if si_hace_falta and marca.exists() and marca.read_text(encoding='utf-8').strip() == version:
        return

    ruta = carpeta / 'settings.json'
    original = ruta.read_text(encoding='utf-8') if ruta.exists() else None
    datos = json.loads(original) if original is not None else {}
    anteriores = json.loads(original) if original is not None else None
    datos['attribution'] = {'commit': '', 'pr': ''}
    preguntar = datos.setdefault('permissions', {}).setdefault('ask', [])
    for regla in ['Bash(gh pr merge *)', 'Bash(gh api *merge*)', 'Bash(git push origin main*)',
                  'Bash(git push origin master*)', 'Bash(git push * HEAD:main*)', 'Bash(gh release create *)']:
        if regla not in preguntar:
            preguntar.append(regla)
    modelos = datos.setdefault('modelSettings', {})
    for modelo in ('claude-fable-5-1', 'claude-opus-5-5', 'claude-sonnet-5-5', 'claude-haiku-5-5'):
        modelos.setdefault(modelo, {}).setdefault('autoCompactWindow', 200000)
    marketplace = datos.setdefault('extraKnownMarketplaces', {}).setdefault('thealejandro', {})
    marketplace['source'] = {'source': 'github', 'repo': 'thealejandro/claude-reglas'}
    marketplace['autoUpdate'] = True

    carpeta.mkdir(parents=True, exist_ok=True)
    if datos != anteriores:
        if original is not None:
            # Un nombre único evita sobrescribir copias creadas en el mismo segundo.
            with tempfile.NamedTemporaryFile(dir=carpeta, prefix='settings.json.bak-', delete=False) as copia:
                respaldo = Path(copia.name)
            shutil.copyfile(ruta, respaldo)
        escribir_atomico(ruta, json.dumps(datos, indent=2, ensure_ascii=False) + '\n')
    if not marca.exists() or marca.read_text(encoding='utf-8').strip() != version:
        escribir_atomico(marca, version + '\n')
    if not si_hace_falta:
        print('Ajustes aplicados en', ruta)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--si-hace-falta', action='store_true',
                        help='Aplica una vez por versión, sin salida y siempre con código 0.')
    argumentos = parser.parse_args()
    if argumentos.si_hace_falta:
        try:
            aplicar(True)
        except Exception:
            # No bloquear SessionStart; sin marca nueva se reintentará en otra sesión.
            pass
        return
    aplicar(False)


if __name__ == '__main__':
    main()
