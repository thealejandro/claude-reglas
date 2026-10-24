"""Pruebas de reglas.py y de hooks.json."""
import importlib.util
import json
from pathlib import Path
import re
import unittest

RAIZ = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('reglas', RAIZ / 'scripts/reglas.py')
reglas = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reglas)

MARCADOR = re.compile(r'@[A-Z_]+@')


class ReglasTest(unittest.TestCase):
    def test_sin_opciones_solo_lo_general(self):
        t = reglas.generar({})
        self.assertIn('Responde siempre en español', t)
        for ausente in ('agente-lanzar', 'qa-pedir', 'claude-nueva-sesion', 'runbooks'):
            self.assertNotIn(ausente, t)
        self.assertIsNone(MARCADOR.search(t))

    def test_con_opciones_incluye_bloques(self):
        t = reglas.generar({'CLAUDE_PLUGIN_OPTION_SERVIDOR_DESARROLLO': 'srv-prueba',
                            'CLAUDE_PLUGIN_OPTION_REPO_RUNBOOKS': 'mis-runbooks',
                            'CLAUDE_PLUGIN_OPTION_SERVIDORES': 'a, b'})
        for presente in ('srv-prueba', 'qa-pedir', 'mis-runbooks', 'claude-nueva-sesion'):
            self.assertIn(presente, t)
        self.assertIsNone(MARCADOR.search(t))

    def test_idioma(self):
        self.assertIn('Responde siempre en English', reglas.generar({'CLAUDE_PLUGIN_OPTION_IDIOMA': 'English'}))


class HooksTest(unittest.TestCase):
    def test_scripts_existen(self):
        texto = (RAIZ / 'hooks/hooks.json').read_text()
        json.loads(texto)
        rutas = re.findall(r'\$\{CLAUDE_PLUGIN_ROOT\}/([^"\\ ]+)', texto)
        self.assertTrue(rutas)
        for r in rutas:
            self.assertTrue((RAIZ / r).is_file(), r)


if __name__ == '__main__':
    unittest.main()
