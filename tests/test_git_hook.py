"""Pruebas de hooks/git-hook.py y de su encadenado con el hook local, con HOME y git global temporales."""
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock

RAIZ = Path(__file__).resolve().parents[1]
HOOK = RAIZ / 'hooks/git-hook.py'
GIT = shutil.which('git')
spec = importlib.util.spec_from_file_location('ajustes', RAIZ / 'scripts/ajustes.py')
ajustes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ajustes)
CEROS = '0' * 40


@unittest.skipUnless(GIT, 'Git es necesario para estas pruebas')
class GitHookTest(unittest.TestCase):
    def setUp(self):
        temporal = tempfile.TemporaryDirectory()
        self.addCleanup(temporal.cleanup)
        base = Path(temporal.name)
        self.home = base / 'home'
        self.home.mkdir()
        self.repo = base / 'repo'
        self.repo.mkdir()
        self.env = {**os.environ, 'HOME': str(self.home), 'GIT_CONFIG_GLOBAL': str(base / 'gitconfig'),
                    'GIT_CONFIG_NOSYSTEM': '1'}
        for variable in ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE'):
            self.env.pop(variable, None)
        self.git('init', '-q', '-b', 'main')
        self.git('config', 'user.name', 'Pruebas')
        self.git('config', 'user.email', 'pruebas@example.invalid')
        self.escribir('inicial.txt', 'inicio\n')
        self.git('add', 'inicial.txt')
        self.git('commit', '-q', '-m', 'inicial')

    def git(self, *args, check=True):
        return subprocess.run([GIT, *args], cwd=self.repo, env=self.env, capture_output=True, text=True, check=check)

    def escribir(self, relativo, contenido):
        ruta = self.repo / relativo
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(contenido, encoding='utf-8')

    def hook(self, *args, entrada=''):
        return subprocess.run([sys.executable, '-I', str(HOOK), *args], cwd=self.repo, env=self.env,
                              input=entrada, capture_output=True, text=True, timeout=15)

    def mensaje(self, texto):
        ruta = self.repo / 'MSG'
        ruta.write_text(texto, encoding='utf-8')
        return self.hook('commit-msg', str(ruta)).returncode

    def test_commit_msg(self):
        self.assertEqual(self.mensaje('feat: algo\n\nCo-Authored-By: Claude <noreply@anthropic.com>\n'), 1)
        self.assertEqual(self.mensaje('feat: algo\n\nClaude-Session: https://claude.ai/code/session_x\n'), 1)
        self.assertEqual(self.mensaje('feat: algo\n\nGenerated with Claude Code\n'), 1)
        self.assertEqual(self.mensaje('feat: algo\n\n# Co-Authored-By: Claude\n'), 0)
        self.assertEqual(self.mensaje('docs: explica cómo se generated with plantillas\n'), 0)
        self.assertEqual(self.mensaje('feat: añade un hook\n\nCo-Authored-By: Ana <ana@example.com>\n'), 0)
        self.assertEqual(self.mensaje('fix: no añadir el trailer Claude-Session ni Co-Authored-By de Claude\n'), 0)

    def test_pre_commit(self):
        self.escribir('.env', 'A=1\n')
        self.git('add', '.env')
        self.assertEqual(self.hook('pre-commit').returncode, 1)
        self.git('reset', '-q')
        (self.repo / '.env').unlink()
        self.escribir('app.py', 'print("hola")\n')
        self.git('add', 'app.py')
        self.assertEqual(self.hook('pre-commit').returncode, 0)

    def push(self, remota, local=None, remoto=CEROS):
        local = local or self.git('rev-parse', 'HEAD').stdout.strip()
        return self.hook('pre-push', 'origin', 'x', entrada='refs/heads/rama {0} {1} {2}\n'.format(local, remota, remoto))

    def test_pre_push(self):
        self.assertEqual(self.push('refs/heads/main').returncode, 1)
        self.assertEqual(self.push('refs/heads/master').returncode, 1)
        self.git('checkout', '-q', '-b', 'rama')
        self.escribir('ok.txt', 'nada\n')
        self.git('add', 'ok.txt')
        self.git('commit', '-q', '-m', 'ok')
        self.assertEqual(self.push('refs/heads/rama').returncode, 0)
        self.escribir('mal.txt', 'valor = ghp_1234567890abcdef\n')  # reglas:permitir
        self.git('add', 'mal.txt')
        self.git('commit', '-q', '-m', 'mal')
        self.assertEqual(self.push('refs/heads/rama').returncode, 1)
        base = self.git('rev-parse', 'HEAD~1').stdout.strip()
        self.assertEqual(self.push('refs/heads/rama', remoto=base).returncode, 1)

    def test_fallo_interno_deja_pasar(self):
        resultado = self.hook('commit-msg', str(self.repo / 'no-existe'))
        self.assertEqual(resultado.returncode, 0)
        self.assertIn('fallo interno', resultado.stderr)

    def test_encadena_al_hook_local(self):
        cache = self.home / '.claude/plugins/cache/thealejandro/reglas'
        cache.mkdir(parents=True)
        (cache / '1.0.0').symlink_to(RAIZ)
        with unittest.mock.patch.dict(os.environ, self.env):
            ajustes.instalar_hooks_git()
        marcador = self.repo / 'marcador'
        local = self.repo / '.git/hooks/commit-msg'
        local.write_text('#!/bin/sh\ntouch "{0}"\n'.format(marcador))
        local.chmod(0o755)
        self.escribir('a.txt', 'a\n')
        self.git('add', 'a.txt')
        self.assertEqual(self.git('commit', '-q', '-m', 'feat: limpio', check=False).returncode, 0)
        self.assertTrue(marcador.exists())
        marcador.unlink()
        self.escribir('b.txt', 'b\n')
        self.git('add', 'b.txt')
        sucio = self.git('commit', '-q', '-m', 'feat: x\n\nCo-Authored-By: Claude <c@anthropic.com>', check=False)
        self.assertNotEqual(sucio.returncode, 0)
        self.assertFalse(marcador.exists())


if __name__ == '__main__':
    unittest.main()
