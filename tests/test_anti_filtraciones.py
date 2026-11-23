import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import unittest.mock

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
        # Sin los hooks globales de 1.14.0: su pre-commit rechazaría los secretos de prueba.
        self.git("config", "core.hooksPath", str(base / "sin-hooks"))
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

    def test_bloquea_con_mnemonic_prefix(self):
        self.write(".env")
        self.stage(".env")
        try:
            with unittest.mock.patch.dict(os.environ, {"GIT_CONFIG_COUNT": "1",
                    "GIT_CONFIG_KEY_0": "diff.mnemonicPrefix", "GIT_CONFIG_VALUE_0": "true"}):
                output = self.decision(self.run_hook())
            self.assertEqual(output["permissionDecision"], "deny")
        finally:
            self.reset_and_remove(".env")

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


class AntiFiltracionesGhTests(unittest.TestCase):
    """#72: cuerpos de gh issue/pr. Un `gh` falso responde a `gh repo view --json visibility`."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.home = self.base / "home"
        self.home.mkdir()
        self.bin = self.base / "bin"
        self.bin.mkdir()
        self.cwd = self.base / "trabajo"
        self.cwd.mkdir()
        self.visibility("PUBLIC")

    def visibility(self, value):
        gh = self.bin / "gh"
        if value is None:
            gh.write_text("#!/bin/sh\nexit 1\n")
        else:
            gh.write_text("#!/bin/sh\necho {0}\n".format(value))
        gh.chmod(0o755)

    def run_hook(self, command):
        payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash",
                   "tool_input": {"command": command}, "cwd": str(self.cwd)}
        result = subprocess.run(
            [sys.executable, "-I", str(HOOK)], input=json.dumps(payload), cwd=self.cwd,
            env={"PATH": str(self.bin), "HOME": str(self.home)}, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            encoding="utf-8", timeout=10, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)["hookSpecificOutput"] if result.stdout.strip() else None

    def test_secreto_en_cuerpo_se_bloquea_aunque_el_repo_sea_privado(self):
        self.visibility("PRIVATE")
        for comando in ("gh issue create --title t --body 'token ghp_abcdefgh12345678'",
                        "gh pr comment 3 --body 'AKIAABCDEFGHIJKLMNOP'",
                        "gh issue comment 3 -b \"clave sk-ant-abcdefgh1234\""):
            with self.subTest(comando=comando):
                salida = self.run_hook(comando)
                self.assertEqual(salida["permissionDecision"], "deny")
                self.assertNotIn("abcdefgh12345678", salida["permissionDecisionReason"])

    def test_secreto_en_body_file(self):
        self.visibility("PRIVATE")
        (self.cwd / "cuerpo.md").write_text("hola\ntoken ghp_abcdefgh12345678\n")
        for comando in ("gh issue create --title t --body-file cuerpo.md", "gh pr create -F cuerpo.md",
                        "gh pr create --body-file=cuerpo.md", "gh issue create --body-file './cuerpo.md'"):
            with self.subTest(comando=comando):
                self.assertEqual(self.run_hook(comando)["permissionDecision"], "deny")

    def test_cuerpo_con_heredoc(self):
        comando = "gh pr create --title t --body \"$(cat <<'EOF'\nServidor 192.168.1.20\nEOF\n)\""
        self.assertEqual(self.run_hook(comando)["permissionDecision"], "deny")

    def test_privados_en_repo_publico(self):
        for texto in ("falla en 10.0.0.5", "el host nas.tailnet.ts.net", "ruta /home/dev/app", "ruta /srv/web",
                      "ssh deploy@servidor.example.com", "dirección fd00:1234:5678:9abc::1", "equipo caja.local"):
            for verbo in ("gh issue create --title t --body", "gh pr comment 4 -b", "gh issue comment 2 --body",
                          "gh pr create --body"):
                with self.subTest(texto=texto, verbo=verbo):
                    salida = self.run_hook("{0} '{1}'".format(verbo, texto))
                    self.assertEqual(salida["permissionDecision"], "deny")
                    self.assertIn("público", salida["permissionDecisionReason"])

    def test_privados_en_body_file_de_repo_publico(self):
        (self.cwd / "c.md").write_text("Servidor 10.20.30.40\n")
        self.assertEqual(self.run_hook("gh issue create --title t --body-file c.md")["permissionDecision"], "deny")

    def test_privados_permitidos_en_repo_privado(self):
        self.visibility("PRIVATE")
        self.assertIsNone(self.run_hook("gh issue create --title t --body 'falla en 10.0.0.5 y /home/dev/app'"))

    def test_visibilidad_desconocida_pregunta(self):
        self.visibility(None)
        salida = self.run_hook("gh issue create --title t --body 'falla en 10.0.0.5'")
        self.assertEqual(salida["permissionDecision"], "ask")

    def test_texto_normal_pasa_sin_consultar_gh(self):
        self.visibility(None)
        self.assertIsNone(self.run_hook("gh issue create --title 'Añadir filtro' --body 'Versión 1.2.3, puerto 8080, 127.0.0.1'"))

    def test_marca_permitir_por_linea(self):
        (self.cwd / "c.md").write_text("Servidor 10.20.30.40 reglas:permitir\n")
        self.assertIsNone(self.run_hook("gh issue create --title t --body-file c.md"))

    def test_repo_explicito_y_otros_comandos_gh(self):
        self.assertEqual(self.run_hook("gh issue create -R acme/web --title t --body 'IP 10.0.0.5'")["permissionDecision"], "deny")
        self.assertIsNone(self.run_hook("gh issue list --search 'IP 10.0.0.5'"))
        self.assertIsNone(self.run_hook("gh pr view 3 --json body"))
        self.assertIsNone(self.run_hook("echo 10.0.0.5"))

    def test_hosts_propios_del_usuario(self):
        carpeta = self.home / ".config" / "reglas"
        carpeta.mkdir(parents=True)
        (carpeta / "hosts-privados").write_text("# mis equipos\nminas-del-norte\n")
        salida = self.run_hook("gh issue create --title t --body 'caído minas-del-norte'")
        self.assertEqual(salida["permissionDecision"], "deny")


if __name__ == "__main__":
    unittest.main()
