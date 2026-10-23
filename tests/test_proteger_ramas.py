import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HOOK = Path(__file__).resolve().parents[1] / 'hooks/proteger-ramas.py'


class ProtegerRamasTests(unittest.TestCase):
    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporal.cleanup)
        self.repo = Path(self.temporal.name)
        subprocess.run(['git', 'init', '-q', '-b', 'main', str(self.repo)], check=True)

    def decision(self, comando, cwd=None):
        entrada = json.dumps({'tool_input': {'command': comando}, 'cwd': str(cwd or self.repo)})
        r = subprocess.run([sys.executable, '-I', str(HOOK)], input=entrada, text=True,
                           capture_output=True, timeout=10)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)['hookSpecificOutput']['permissionDecision'] if r.stdout.strip() else None

    def test_merge_y_pull_sobre_main_preguntan(self):
        self.assertEqual(self.decision('git merge --ff-only rama'), 'ask')
        self.assertEqual(self.decision('git pull'), 'ask')
        self.assertEqual(self.decision(f'sudo -u dev git -C {self.repo} merge rama', cwd='/'), 'ask')
        self.assertEqual(self.decision(f'cd {self.repo} && git merge rama', cwd='/'), 'ask')

    def test_otras_ramas_y_comandos_no_preguntan(self):
        self.assertIsNone(self.decision('git status'))
        subprocess.run(['git', '-C', str(self.repo), 'switch', '-q', '-c', 'feat/x'], check=True)
        self.assertIsNone(self.decision('git merge main'))


if __name__ == '__main__':
    unittest.main()
