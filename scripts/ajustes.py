#!/usr/bin/env python3
"""Aplica ajustes de usuario de forma idempotente; el hook es silencioso y tolerante."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import traceback

# Servidor de producción: sin navegador y con preguntas para los cambios de sistema.
HESTIA = Path('/usr/local/hestia')


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


def navegador_mcp():
    """Chrome DevTools MCP compartido: binario instalado una vez y Chromium de Playwright vía envoltorio."""
    instalado = shutil.which('chrome-devtools-mcp') or str(Path.home() / '.local/bin/chrome-devtools-mcp')
    if Path(instalado).exists():
        comando, args = instalado, []
    else:
        comando, args = 'npx', ['-y', 'chrome-devtools-mcp@latest']
    args += ['--headless', '--isolated']
    if list(Path.home().glob('.cache/ms-playwright/chromium-*/chrome-linux*/chrome')):
        # El envoltorio busca la versión más reciente al arrancar: sobrevive a las actualizaciones de Playwright.
        envoltorio = Path.home() / '.local/bin/chromium-qa'
        envoltorio.parent.mkdir(parents=True, exist_ok=True)
        escribir_atomico(envoltorio, '#!/bin/sh\nexec "$(ls -d "$HOME"/.cache/ms-playwright/chromium-*/chrome-linux*/chrome | sort -V | tail -1)" "$@"\n')
        envoltorio.chmod(0o755)
        args += ['--executablePath', str(envoltorio)]
    return comando, args


def configurar_otros_agentes():
    """Da a Claude, Codex, Kimi y Cursor, si están instalados, el mismo navegador para QA.

    En producción lo quita: sin binario, el MCP se ejecuta con npx @latest (código sin fijar)
    y la QA de navegador se hace en el servidor de desarrollo, no ahí.
    """
    produccion = HESTIA.exists()
    if not produccion:
        comando, args = navegador_mcp()
    for carpeta, extra in (('.kimi-code', {}), ('.cursor', {'type': 'stdio'})):
        if not (Path.home() / carpeta).is_dir():
            continue
        ruta = Path.home() / carpeta / 'mcp.json'
        datos = json.loads(ruta.read_text(encoding='utf-8')) if ruta.exists() else {}
        servidores = datos.setdefault('mcpServers', {})
        nuevo = None if produccion else {**extra, 'command': comando, 'args': args}
        if servidores.get('chrome-devtools') != nuevo:
            if nuevo is None:
                del servidores['chrome-devtools']
            else:
                servidores['chrome-devtools'] = nuevo
            escribir_atomico(ruta, json.dumps(datos, indent=2, ensure_ascii=False) + '\n')
    claude = shutil.which('claude') or str(Path.home() / '.local/bin/claude')
    if Path(claude).exists():
        subprocess.run([claude, 'mcp', 'remove', '-s', 'user', 'chrome-devtools'], capture_output=True, timeout=10, check=False)
        if not produccion:
            subprocess.run([claude, 'mcp', 'add', '-s', 'user', 'chrome-devtools', '--', comando, *args],
                           capture_output=True, timeout=10, check=False)
    codex = Path.home() / '.codex' / 'config.toml'
    if shutil.which('codex') and codex.exists():
        subprocess.run(['codex', 'mcp', 'remove', 'chrome-devtools'], capture_output=True, timeout=10, check=False)
        if not produccion:
            subprocess.run(['codex', 'mcp', 'add', 'chrome-devtools', '--', comando, *args],
                           capture_output=True, timeout=10, check=False)


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
    # Una regla ask pregunta al usuario incluso en modo auto (también por Remote Control),
    # en vez de dejar que el clasificador bloquee la acción sin preguntar.
    extra = ['Edit(~/.config/claude-arranque/traspasos/**)']
    if HESTIA.exists():
        # Servidor de producción con Hestia: los cambios de sistema siempre preguntan.
        extra += ['Bash(v-*)', 'Bash(apt install *)', 'Bash(apt-get install *)', 'Bash(apt upgrade*)',
                  'Bash(apt-get upgrade*)', 'Bash(systemctl restart *)', 'Bash(systemctl reload *)']
    for regla in extra:
        if regla not in preguntar:
            preguntar.append(regla)
    modelos = datos.setdefault('modelSettings', {})
    for modelo in ('claude-fable-5-1', 'claude-opus-5-5', 'claude-sonnet-5-5', 'claude-haiku-5-5'):
        modelos.setdefault(modelo, {}).setdefault('autoCompactWindow', 200000)
    marketplace = datos.setdefault('extraKnownMarketplaces', {}).setdefault('thealejandro', {})
    marketplace['source'] = {'source': 'github', 'repo': 'thealejandro/claude-reglas'}
    marketplace['autoUpdate'] = True
    for lanzador in ('agente-lanzar', 'qa-pedir', 'claude-nueva-sesion'):
        if Path('/usr/local/bin', lanzador).exists():
            permitir = datos['permissions'].setdefault('allow', [])
            for regla in [f'Bash({lanzador} *)', f'Bash(/usr/local/bin/{lanzador} *)']:
                if regla not in permitir:
                    permitir.append(regla)

    carpeta.mkdir(parents=True, exist_ok=True)
    if datos != anteriores:
        if original is not None:
            # Un nombre único evita sobrescribir copias creadas en el mismo segundo.
            with tempfile.NamedTemporaryFile(dir=carpeta, prefix='settings.json.bak-', delete=False) as copia:
                respaldo = Path(copia.name)
            shutil.copyfile(ruta, respaldo)
        escribir_atomico(ruta, json.dumps(datos, indent=2, ensure_ascii=False) + '\n')
    configurar_otros_agentes()
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
            # No bloquear SessionStart, pero dejar rastro; sin marca nueva se reintentará en otra sesión.
            try:
                registro = Path.home() / '.local/state/reglas-ajustes.log'
                registro.parent.mkdir(parents=True, exist_ok=True)
                with registro.open('a', encoding='utf-8') as archivo:
                    archivo.write(time.strftime('== %F %T\n') + traceback.format_exc())
            except OSError:
                pass
        return
    aplicar(False)


if __name__ == '__main__':
    main()
