"""Pruebas aisladas de ajustes.py: HOME temporal y sin CLI reales."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

RAIZ = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('ajustes', RAIZ / 'scripts/ajustes.py')
ajustes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ajustes)


class NavegadorTest(unittest.TestCase):
    def setUp(self):
        temporal = tempfile.TemporaryDirectory()
        self.addCleanup(temporal.cleanup)
        self.home = Path(temporal.name)
        for parche in (mock.patch.dict(os.environ, HOME=str(self.home)),
                       mock.patch.object(ajustes.shutil, 'which', return_value=None),
                       mock.patch.object(ajustes.subprocess, 'run', side_effect=AssertionError('CLI PROHIBIDO'))):
            parche.start()
            self.addCleanup(parche.stop)
        self.cursor = self.home / '.cursor/mcp.json'
        self.cursor.parent.mkdir()
        self.cursor.write_text(json.dumps({'mcpServers': {'otro': {'command': 'x'},
                                                          'chrome-devtools': {'command': 'npx'}}}))

    def servidores(self):
        return json.loads(self.cursor.read_text())['mcpServers']

    def test_produccion_quita_el_navegador_y_respeta_lo_demas(self):
        with mock.patch.object(ajustes, 'HESTIA', self.home):
            ajustes.configurar_otros_agentes()
        self.assertEqual(self.servidores(), {'otro': {'command': 'x'}})

    def test_desarrollo_registra_el_navegador(self):
        with mock.patch.object(ajustes, 'HESTIA', self.home / 'no-existe'):
            ajustes.configurar_otros_agentes()
        servidores = self.servidores()
        self.assertEqual(servidores['otro'], {'command': 'x'})
        self.assertEqual(servidores['chrome-devtools']['type'], 'stdio')
        self.assertIn('--headless', servidores['chrome-devtools']['args'])


class AtribucionTest(unittest.TestCase):
    def test_quita_toda_la_atribucion_y_conserva_lo_demas(self):
        with tempfile.TemporaryDirectory() as temporal, \
                mock.patch.dict(os.environ, HOME=temporal), \
                mock.patch.object(ajustes, 'configurar_otros_agentes'), \
                mock.patch.object(ajustes, 'escribir_agents_md'), \
                mock.patch.object(ajustes, 'instalar_hooks_git'):
            ajustes_json = Path(temporal) / '.claude/settings.json'
            ajustes_json.parent.mkdir()
            ajustes_json.write_text(json.dumps({'attribution': {'commit': 'x'}, 'theme': 'dark'}))
            ajustes.aplicar(si_hace_falta=True)
            datos = json.loads(ajustes_json.read_text())
        self.assertEqual(datos['attribution'], {'commit': '', 'pr': '', 'sessionUrl': False})
        self.assertEqual(datos['theme'], 'dark')


class AgentsMdTest(unittest.TestCase):
    def setUp(self):
        temporal = tempfile.TemporaryDirectory()
        self.addCleanup(temporal.cleanup)
        self.home = Path(temporal.name)
        parche = mock.patch.dict(os.environ, HOME=str(self.home))
        parche.start()
        self.addCleanup(parche.stop)

    def test_escribe_solo_donde_hay_carpeta_y_respeta_uno_propio(self):
        (self.home / '.codex').mkdir()
        (self.home / '.kimi-code').mkdir()
        (self.home / '.kimi-code/AGENTS.md').write_text('mío\n')
        datos = {'pluginConfigs': {'reglas@thealejandro': {'options': {'idioma': 'English'}}}}
        ajustes.escribir_agents_md(datos, RAIZ)
        codex = self.home / '.codex/AGENTS.md'
        self.assertTrue(codex.read_text().startswith('<!-- Generado por el plugin reglas'))
        self.assertIn('Responde siempre en English', codex.read_text())
        self.assertEqual((self.home / '.kimi-code/AGENTS.md').read_text(), 'mío\n')
        self.assertFalse((self.home / '.cursor').exists())
        os.utime(codex, (1, 1))
        ajustes.escribir_agents_md(datos, RAIZ)
        self.assertEqual(codex.stat().st_mtime, 1)

    def test_actualiza_el_que_lleva_la_marca(self):
        (self.home / '.cursor').mkdir()
        ruta = self.home / '.cursor/AGENTS.md'
        ruta.write_text('<!-- Generado por el plugin reglas (ajustes.py); no editar a mano. -->\nviejo\n')
        ajustes.escribir_agents_md({}, RAIZ)
        self.assertIn('Responde siempre en español', ruta.read_text())


@unittest.skipUnless(shutil.which('git'), 'Git es necesario')
class HooksGitTest(unittest.TestCase):
    def setUp(self):
        temporal = tempfile.TemporaryDirectory()
        self.addCleanup(temporal.cleanup)
        self.home = Path(temporal.name)
        self.config = self.home / 'gitconfig'
        for parche in (mock.patch.dict(os.environ, HOME=str(self.home), GIT_CONFIG_GLOBAL=str(self.config),
                                       GIT_CONFIG_NOSYSTEM='1'),):
            parche.start()
            self.addCleanup(parche.stop)

    def hooks_path(self):
        return subprocess.run(['git', 'config', '--global', '--get', 'core.hooksPath'],
                              capture_output=True, text=True).stdout.strip()

    def test_instala_los_tres_hooks_y_fija_hooks_path(self):
        self.assertIsNone(ajustes.instalar_hooks_git())
        carpeta = self.home / '.config/git/hooks'
        for nombre in ('pre-commit', 'commit-msg', 'pre-push'):
            self.assertTrue(os.access(carpeta / nombre, os.X_OK), nombre)
            self.assertEqual((carpeta / nombre).read_text(), ajustes.HOOK_GIT)
        self.assertEqual(self.hooks_path(), str(carpeta))
        self.assertIsNone(ajustes.instalar_hooks_git())

    def test_no_toca_un_hooks_path_ajeno(self):
        self.config.write_text('[core]\n\thooksPath = /otro/sitio\n')
        self.assertIn('/otro/sitio', ajustes.instalar_hooks_git())
        self.assertEqual(self.hooks_path(), '/otro/sitio')


class RegistroTest(unittest.TestCase):
    def test_si_hace_falta_registra_el_error_sin_fallar(self):
        with tempfile.TemporaryDirectory() as temporal, \
                mock.patch.dict(os.environ, HOME=temporal), \
                mock.patch.object(ajustes, 'aplicar', side_effect=RuntimeError('fallo de prueba')), \
                mock.patch('sys.argv', ['ajustes.py', '--si-hace-falta']):
            ajustes.main()
            registro = (Path(temporal) / '.local/state/reglas-ajustes.log').read_text()
        self.assertIn('RuntimeError: fallo de prueba', registro)

if __name__ == '__main__':
    unittest.main()
