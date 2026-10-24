"""Pruebas aisladas de ajustes.py: HOME temporal y sin CLI reales."""
import importlib.util
import json
import os
from pathlib import Path
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
                mock.patch.object(ajustes, 'configurar_otros_agentes'):
            ajustes_json = Path(temporal) / '.claude/settings.json'
            ajustes_json.parent.mkdir()
            ajustes_json.write_text(json.dumps({'attribution': {'commit': 'x'}, 'theme': 'dark'}))
            ajustes.aplicar(si_hace_falta=True)
            datos = json.loads(ajustes_json.read_text())
        self.assertEqual(datos['attribution'], {'commit': '', 'pr': '', 'sessionUrl': False})
        self.assertEqual(datos['theme'], 'dark')


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
