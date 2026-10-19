import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "hooks" / "anti-filtraciones.py"
GIT = shutil.which("git")


@unittest.skipUnless(GIT, "Git es necesario para estas pruebas")
class AntiFiltracionesTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        base = Path(self.temporary.name)
        self.repo = base / "repo"
        self.repo.mkdir()
        self.bin = base / "bin"
        self.bin.mkdir()
        os.symlink(GIT, self.bin / "git")
        self.git("init", "-q")
        self.git("config", "user.name", "Pruebas")
        self.git("config", "user.email", "pruebas@example.invalid")
        self.write("inicial.txt", "inicio\n")
        self.git("add", "inicial.txt")
        self.git("commit", "-q", "-m", "inicial")

    def git(self, *args):
        return subprocess.run(
            [GIT, *args],
            cwd=self.repo,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
            check=True,
        )

    def write(self, relative, content=""):
        path = self.repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def stage(self, *paths):
        self.git("add", "--", *paths)

    def run_hook(self, command="git commit -m prueba", path=None):
        environment = os.environ.copy()
        environment["PATH"] = str(path or self.bin)
        environment["GIT_CONFIG_NOSYSTEM"] = "1"
        for variable in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
            environment.pop(variable, None)
        payload = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": command},
            "cwd": str(self.repo),
        }
        return subprocess.run(
            [sys.executable, str(HOOK)],
            input=json.dumps(payload),
            cwd=self.repo,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
            timeout=10,
            check=False,
        )

    def decision(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.strip(), "el hook no emitió una decisión")
        output = json.loads(result.stdout)
        return output["hookSpecificOutput"]

    def assert_passes(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")

    def assert_denied(self, result, path, secret, prefix):
        output = self.decision(result)
        self.assertEqual(output["permissionDecision"], "deny")
        reason = output["permissionDecisionReason"]
        self.assertIn(path + ":", reason)
        self.assertIn(prefix, reason)
        self.assertNotIn(secret, reason)
        return reason

    def reset_and_remove(self, relative):
        self.git("reset", "-q")
        (self.repo / relative).unlink()

    def configure_upstream(self):
        branch = self.git("symbolic-ref", "--short", "HEAD").stdout.strip()
        self.git("remote", "add", "origin", str(self.repo))
        self.git("update-ref", "refs/remotes/origin/" + branch, "HEAD")
        self.git("config", "branch." + branch + ".remote", "origin")
        self.git("config", "branch." + branch + ".merge", "refs/heads/" + branch)

    def install_fake_gitleaks(self, body):
        executable = self.bin / "gitleaks"
        executable.write_text("#!" + sys.executable + "\n" + body, encoding="utf-8")
        executable.chmod(0o755)

    def test_bloquea_secretos_en_commit(self):
        jwt = (
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
            "eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IlBydWViYSJ9."
            "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
        )
        cases = (
            ("clave privada", "-----BEGIN OPENSSH PRIVATE KEY-----\n", "BEGIN OPENSSH PRIVATE KEY", "BEGI"),  # reglas:permitir
            ("GitHub ghp", "valor = ghp_1234567890abcdef\n", "ghp_1234567890abcdef", "ghp_"),  # reglas:permitir
            ("GitHub PAT", "valor = github_pat_11ABCDEFGHIJKLMNOPQRSTUVWXYZ\n", "github_pat_11ABCDEFGHIJKLMNOPQRSTUVWXYZ", "gith"),  # reglas:permitir
            ("GitHub gho", "valor = gho_1234567890abcdef\n", "gho_1234567890abcdef", "gho_"),  # reglas:permitir
            ("AWS", "valor = AKIAIOSFODNN7EXAMPLE\n", "AKIAIOSFODNN7EXAMPLE", "AKIA"),  # reglas:permitir
            ("Slack", "valor = xoxb-123456789012-abcdefghijkl\n", "xoxb-123456789012-abcdefghijkl", "xoxb"),  # reglas:permitir
            ("Stripe", "valor = sk_live_1234567890abcdef\n", "sk_live_1234567890abcdef", "sk_l"),  # reglas:permitir
            ("Anthropic", "valor = sk-ant-api03-1234567890abcdef\n", "sk-ant-api03-1234567890abcdef", "sk-a"),  # reglas:permitir
            ("OpenAI", "valor = sk-proj-1234567890abcdef\n", "sk-proj-1234567890abcdef", "sk-p"),  # reglas:permitir
            ("JWT", "valor = " + jwt + "\n", jwt, "eyJh"),
            ("asignación", 'password = "valor_super_secreto"\n', "valor_super_secreto", "valo"),  # reglas:permitir
        )
        for index, (label, content, secret, prefix) in enumerate(cases):
            with self.subTest(caso=label):
                relative = "secreto-{0}.txt".format(index)
                self.write(relative, content)
                self.stage(relative)
                try:
                    self.assert_denied(self.run_hook(), relative, secret, prefix)
                finally:
                    self.reset_and_remove(relative)

    def test_bloquea_archivos_sensibles(self):
        paths = (".env", "certificado.pem", "servidor.key", "id_rsa", "id_ed25519", "_muestras/factura.xml")
        for relative in paths:
            with self.subTest(archivo=relative):
                self.write(relative)
                self.stage(relative)
                try:
                    output = self.decision(self.run_hook())
                    self.assertEqual(output["permissionDecision"], "deny")
                    self.assertIn(relative + ":1", output["permissionDecisionReason"])
                    self.assertIn("archivo sensible", output["permissionDecisionReason"])
                finally:
                    self.reset_and_remove(relative)

    def test_permite_env_example(self):
        self.write(".env.example", "DATABASE_URL=sqlite:///basededatos.sqlite3\n")
        self.stage(".env.example")
        self.assert_passes(self.run_hook())

    def test_bloquea_datos_reales(self):
        cases = (
            ("documento FEL", "<dte:GTDocumento version=\"0.1\">\n", "<dte:GTDocumento", "<dte"),  # reglas:permitir
            (
                "autorización FEL",
                "<dte:SAT>\n<dte:NumeroAutorizacion>PRUEBA</dte:NumeroAutorizacion>\n</dte:SAT>\n",  # reglas:permitir
                "NumeroAutorizacion",
                "Nume",
            ),
            ("DPI", "documento = \"1234 56789 0101\"\n", "1234 56789 0101", "1234"),  # reglas:permitir
        )
        for index, (label, content, value, prefix) in enumerate(cases):
            with self.subTest(caso=label):
                relative = "dato-{0}.xml".format(index)
                self.write(relative, content)
                self.stage(relative)
                try:
                    self.assert_denied(self.run_hook(), relative, value, prefix)
                finally:
                    self.reset_and_remove(relative)

    def test_permite_excepcion_en_la_misma_linea(self):
        self.write("permitido.txt", 'token = "valor_de_prueba_largo"  # reglas:permitir\n')
        self.stage("permitido.txt")
        self.assert_passes(self.run_hook())

    def test_permite_ruta_en_reglas_permitir(self):
        self.write(".reglas-permitir", ".env\n")
        self.write(".env", 'password = "valor_de_prueba_largo"\n')  # reglas:permitir
        self.stage(".reglas-permitir", ".env")
        self.assert_passes(self.run_hook())

    def test_permite_codigo_normal_sin_falsos_positivos(self):
        self.write("normal.py", (
            "import os\n"
            "password = os.environ.get('PASSWORD')\n"
            "api_key = 'corto'\n"
            "token = '12345678901'\n"
            "numero = 1234567890101\n"
            "texto = '1234567890101'\n"
            "valor = 'cabecera.carga.firma'\n"
        ))
        self.stage("normal.py")
        self.assert_passes(self.run_hook())

    def test_no_actua_con_comandos_que_no_son_commit_ni_push(self):
        self.write("secreto.txt", "valor = ghp_1234567890abcdef\n")  # reglas:permitir
        self.stage("secreto.txt")
        self.assert_passes(self.run_hook("python3 -m unittest discover tests"))

    def test_no_bloquea_lineas_eliminadas(self):
        self.write("historico.txt", "valor = ghp_1234567890abcdef\n")  # reglas:permitir
        self.stage("historico.txt")
        self.git("commit", "-q", "-m", "histórico")
        self.git("rm", "-q", "historico.txt")
        self.assert_passes(self.run_hook())

    def test_bloquea_commit_pendiente_en_push(self):
        self.configure_upstream()
        self.write("pendiente.txt", "valor = AKIAIOSFODNN7EXAMPLE\n")  # reglas:permitir
        self.stage("pendiente.txt")
        self.git("commit", "-q", "-m", "pendiente")
        self.assert_denied(
            self.run_hook("git push origin HEAD"),
            "pendiente.txt",
            "AKIAIOSFODNN7EXAMPLE",  # reglas:permitir
            "AKIA",
        )

    def test_permite_push_con_codigo_normal(self):
        self.configure_upstream()
        self.write("pendiente.py", "def suma(a, b):\n    return a + b\n")
        self.stage("pendiente.py")
        self.git("commit", "-q", "-m", "pendiente")
        self.assert_passes(self.run_hook("git push origin HEAD"))

    def test_push_sin_upstream_no_revisa_commits(self):
        self.write("pendiente.txt", "valor = AKIAIOSFODNN7EXAMPLE\n")  # reglas:permitir
        self.stage("pendiente.txt")
        self.git("commit", "-q", "-m", "pendiente")
        self.assert_passes(self.run_hook("git push origin HEAD"))

    def test_usa_gitleaks_sin_mostrar_el_secreto(self):
        self.install_fake_gitleaks(
            "import json, sys\n"
            "ruta = sys.argv[sys.argv.index('--report-path') + 1]\n"
            "with open(ruta, 'w') as informe:\n"
            "    json.dump([{'File': 'normal.txt', 'StartLine': 1, 'Secret': 'abcdEFGH123456'}], informe)\n"
            "sys.exit(1)\n"
        )
        self.write("normal.txt", "contenido normal\n")
        self.stage("normal.txt")
        self.assert_denied(self.run_hook(), "normal.txt", "abcdEFGH123456", "abcd")

    def test_fallo_interno_deja_pasar_y_avisa(self):
        empty_bin = Path(self.temporary.name) / "sin-git"
        empty_bin.mkdir()
        self.write("normal.txt", "contenido normal\n")
        self.stage("normal.txt")
        output = self.decision(self.run_hook(path=empty_bin))
        self.assertEqual(output["permissionDecision"], "allow")
        self.assertIn("fallo interno", output["permissionDecisionReason"])
        self.assertIn("se permite la operación", output["permissionDecisionReason"])

    def test_gitleaks_con_timeout_deja_pasar_y_avisa(self):
        self.install_fake_gitleaks("import time\ntime.sleep(10)\n")
        self.write("normal.txt", "contenido normal\n")
        self.stage("normal.txt")
        started = time.monotonic()
        output = self.decision(self.run_hook())
        self.assertLess(time.monotonic() - started, 8)
        self.assertEqual(output["permissionDecision"], "allow")
        self.assertIn("tiempo interno agotado", output["permissionDecisionReason"])
        self.assertIn("se permite la operación", output["permissionDecisionReason"])


if __name__ == "__main__":
    unittest.main()
