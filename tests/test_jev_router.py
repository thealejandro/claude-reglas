"""Pruebas de la lectura de la key de jev-router.py con HOME temporal."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

RAIZ = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('jev_router', RAIZ / 'hooks/jev-router.py')
jev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(jev)


class KeyTest(unittest.TestCase):
    def setUp(self):
        temporal = tempfile.TemporaryDirectory()
        self.addCleanup(temporal.cleanup)
        self.home = Path(temporal.name)
        p = mock.patch.dict(os.environ, HOME=str(self.home))
        p.start()
        self.addCleanup(p.stop)
        for var in ('TYPESAFE_API_KEY', 'CLAUDE_PLUGIN_OPTION_JEV_API_KEY'):
            os.environ.pop(var, None)

    def escribir_archivo(self):
        (self.home / '.config/jev').mkdir(parents=True)
        (self.home / '.config/jev/env').write_text('TYPESAFE_API_KEY=del-archivo\n')

    def test_opcion_gana_al_archivo(self):
        self.escribir_archivo()
        with mock.patch.dict(os.environ, CLAUDE_PLUGIN_OPTION_JEV_API_KEY=' de-opcion '):
            self.assertEqual(jev.key(), 'de-opcion')

    def test_sin_opcion_lee_el_archivo(self):
        self.escribir_archivo()
        self.assertEqual(jev.key(), 'del-archivo')

    def test_sin_nada(self):
        self.assertIsNone(jev.key())


if __name__ == '__main__':
    unittest.main()
