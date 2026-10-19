"""Validaciones del lanzador sin ejecutar Claude ni tmux."""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/qa-pedir'


class QaPedirTests(unittest.TestCase):
    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporal.cleanup)
        self.raiz = Path(self.temporal.name)
        self.bin = self.raiz / 'bin'
        self.bin.mkdir()
        self.marca = self.raiz / 'proceso-prohibido'
        # Simular dev hace las pruebas independientes del usuario del ejecutor.
        self.comando('id', 'printf "dev\\n"\n')
        for nombre in ('claude', 'tmux', 'sudo'):
            self.comando(nombre, f'touch {shlex.quote(str(self.marca))}\nexit 99\n')
        self.entorno = {**os.environ, 'PATH': f'{self.bin}:{os.environ["PATH"]}'}
        logs = Path('/home/dev/work/_logs')
        logs.mkdir(parents=True, exist_ok=True)
        self.encargos = tempfile.TemporaryDirectory(prefix='qa-prueba-', dir=logs)
        self.addCleanup(self.encargos.cleanup)
        self.encargo = Path(self.encargos.name) / "encargo ' especial.md"
        self.encargo.write_text('Visita https://example.com y mide LCP.\nTexto literal: $(exit 88) `exit 89`')

    def comando(self, nombre, cuerpo):
        ruta = self.bin / nombre
        ruta.write_text('#!/bin/sh\n' + cuerpo)
        ruta.chmod(0o755)

    def ejecutar(self, *args):
        resultado = subprocess.run([str(SCRIPT), *args], env=self.entorno,
                                   text=True, capture_output=True)
        self.assertFalse(self.marca.exists(), 'Se intentó lanzar Claude, tmux o sudo')
        return resultado

    def test_proyecto_invalido(self):
        for proyecto in ('../repo', 'con espacio', 'a;b', '', 'á'):
            with self.subTest(proyecto=proyecto):
                resultado = self.ejecutar('--simular', proyecto, str(self.encargo))
                self.assertNotEqual(resultado.returncode, 0)
                self.assertIn('Proyecto inválido', resultado.stderr)

    def test_encargo_fuera_de_logs(self):
        fuera = self.raiz / 'encargo.md'
        fuera.write_text('QA')
        resultado = self.ejecutar('--simular', 'demo', str(fuera))
        self.assertNotEqual(resultado.returncode, 0)
        self.assertIn('bajo /home/dev/work/_logs/', resultado.stderr)
        enlace = self.encargo.parent / 'enlace.md'
        enlace.symlink_to(fuera)
        self.assertNotEqual(self.ejecutar('--simular', 'demo', str(enlace)).returncode, 0)

    def test_simulacion(self):
        resultado = self.ejecutar('--simular', 'Demo_22-test', str(self.encargo))
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        carpeta = resultado.stdout.splitlines()[0].removeprefix('Carpeta: ')
        self.assertRegex(carpeta, r'^/home/dev/work/_logs/qa/\d{8}-\d{4}-Demo_22-test$')
        self.assertFalse(Path(carpeta).exists())
        self.assertIn('timeout', resultado.stdout)
        self.assertIn('claude-sonnet-5-5', resultado.stdout)
        self.assertIn('dontAsk', resultado.stdout)
        self.assertIn('chrome-devtools', resultado.stdout)
        self.assertIn('ffmpeg', resultado.stdout)
        self.assertIn('tiempo-agotado', resultado.stdout)
        # El comando impreso se puede analizar sin ejecutar el proceso interior.
        comando = resultado.stdout.split('Comando: ', 1)[1].strip()
        analisis = subprocess.run(['bash', '-n', '-c', comando], capture_output=True)
        self.assertEqual(analisis.returncode, 0)


if __name__ == '__main__':
    unittest.main()
