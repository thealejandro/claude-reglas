import importlib.util
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
SECRETO = "AKIAIOSFODNN7EXAMPLE"  # reglas:permitir
LINEA_SECRETA = "valor = " + SECRETO + "\n"


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

    def commit_secreto(self, relativo="pendiente.txt"):
        self.write(relativo, LINEA_SECRETA)
        self.stage(relativo)
        self.git("commit", "-q", "-m", "pendiente")

    def commit_limpio(self, relativo="limpio.txt"):
        self.write(relativo, "nada\n")
        self.stage(relativo)
        self.git("commit", "-q", "-m", "limpio")

    def rama(self):
        return self.git("symbolic-ref", "--short", "HEAD").stdout.strip()

    def remoto_publicado(self, nombre="origin"):
        """Remoto con la rama actual ya publicada (solo la ref de seguimiento)."""
        self.git("remote", "add", nombre, str(self.repo))
        self.git("update-ref", "refs/remotes/{0}/{1}".format(nombre, self.rama()), "HEAD")

    def seguido(self, relativo="seguido.txt"):
        """Fichero ya versionado y limpio."""
        self.commit_limpio(relativo)
        return relativo

    def assert_secreto(self, result, path):
        return self.assert_denied(result, path, SECRETO, SECRETO[:4])

    def assert_ask(self, result):
        output = self.decision(result)
        self.assertEqual(output["permissionDecision"], "ask", output["permissionDecisionReason"])
        return output["permissionDecisionReason"]

    def otro_repo(self, nombre="otro"):
        """Segundo repo, hermano del de trabajo, con un secreto en el índice."""
        otro = self.repo.parent / nombre
        otro.mkdir()
        for args in (["init", "-q"], ["config", "user.name", "Pruebas"],
                     ["config", "user.email", "pruebas@example.invalid"],
                     ["config", "core.hooksPath", str(self.repo.parent / "sin-hooks")]):
            subprocess.run([GIT, *args], cwd=otro, check=True)
        (otro / "ajeno.txt").write_text(LINEA_SECRETA, encoding="utf-8")
        subprocess.run([GIT, "add", "ajeno.txt"], cwd=otro, check=True)
        return otro

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

    def test_push_sin_remotos_revisa_toda_la_historia(self):
        self.commit_secreto("pendiente.txt")
        self.assert_secreto(self.run_hook("git push origin HEAD"), "pendiente.txt")

    # --- Primer push de una rama sin upstream ---

    def test_primer_push_de_rama_nueva_se_revisa(self):
        self.remoto_publicado()
        self.git("switch", "-q", "-c", "nueva")
        self.commit_secreto()
        for comando in ("git push", "git push -u origin nueva", "git push origin HEAD",
                        "git push --set-upstream origin HEAD:refs/heads/otra",
                        "git push -o ci.skip origin +nueva:nueva", "git push origin --all",
                        'git push -u origin "$(git branch --show-current)"',
                        "git push origin nueva 2>&1 | tail -3"):
            with self.subTest(comando=comando):
                self.assert_secreto(self.run_hook(comando), "pendiente.txt")

    def test_push_de_otra_rama_revisa_esa_rama(self):
        self.remoto_publicado()
        base = self.rama()
        self.git("switch", "-q", "-c", "con-secreto")
        self.commit_secreto()
        self.git("switch", "-q", base)
        self.assert_secreto(self.run_hook("git push origin con-secreto"), "pendiente.txt")
        self.assert_passes(self.run_hook("git push origin " + base))

    def test_push_de_etiquetas(self):
        self.remoto_publicado()
        base = self.rama()
        self.git("switch", "-q", "-c", "aparte")
        self.commit_secreto()
        self.git("tag", "v1")
        self.git("switch", "-q", base)
        for comando in ("git push --tags", "git push origin v1", "git push origin tag v1"):
            with self.subTest(comando=comando):
                self.assert_secreto(self.run_hook(comando), "pendiente.txt")

    def test_rama_nueva_no_repasa_lo_ya_publicado(self):
        self.commit_secreto("publicado.txt")
        self.remoto_publicado()
        self.git("switch", "-q", "-c", "nueva")
        self.commit_limpio()
        self.assert_passes(self.run_hook("git push -u origin nueva"))

    def test_push_a_un_remoto_compara_con_ese_remoto(self):
        self.remoto_publicado("publico")
        self.commit_secreto()
        self.remoto_publicado("privado")
        self.assert_secreto(self.run_hook("git push publico HEAD"), "pendiente.txt")
        self.assert_passes(self.run_hook("git push privado HEAD"))

    def test_rama_creada_en_el_mismo_comando(self):
        self.remoto_publicado()
        self.commit_secreto()
        self.assert_secreto(self.run_hook("git switch -c x && git push -u origin x"), "pendiente.txt")

    def test_borrar_ramas_remotas_no_revisa_commits(self):
        self.remoto_publicado()
        self.commit_secreto()
        for comando in ("git push origin --delete vieja", "git push -d origin vieja", "git push origin :vieja"):
            with self.subTest(comando=comando):
                self.assert_passes(self.run_hook(comando))

    def test_refspec_que_no_se_puede_saber_pregunta(self):
        self.remoto_publicado()
        self.assert_ask(self.run_hook('git push origin "$RAMA_DESCONOCIDA"'))

    def test_gitleaks_recibe_el_rango_del_push_nuevo(self):
        self.remoto_publicado()
        self.commit_limpio()
        registro = self.repo.parent / "gitleaks.txt"
        self.install_fake_gitleaks(
            "import sys\n"
            "open({0!r}, 'a').write(' '.join(sys.argv[1:]) + '\\n')\n"
            "ruta = sys.argv[sys.argv.index('--report-path') + 1]\n"
            "open(ruta, 'w').write('[]')\n".format(str(registro))
        )
        self.assert_passes(self.run_hook("git push -u origin HEAD"))
        self.assertIn("--not --remotes=origin", registro.read_text())

    # --- git commit -a, con rutas y git add en el mismo comando ---

    def test_commit_all_revisa_cambios_sin_preparar(self):
        ruta = self.seguido()
        self.write(ruta, LINEA_SECRETA)
        for comando in ("git commit -a -m x", "git commit -am x", "git commit --all -m x",
                        "git commit -qam 'arreglo'", "git commit -m x -a"):
            with self.subTest(comando=comando):
                self.assert_secreto(self.run_hook(comando), ruta)

    def test_commit_con_rutas_revisa_esas_rutas(self):
        ruta = self.seguido()
        self.write(ruta, LINEA_SECRETA)
        for comando in ("git commit -m x seguido.txt", "git commit seguido.txt -m x",
                        "git commit -m x -- seguido.txt", "git commit -i -m x seguido.txt",
                        "git commit --include -m x -- seguido.txt", "git commit -o -m x .",
                        "git commit -m x seguido.*"):
            with self.subTest(comando=comando):
                self.assert_secreto(self.run_hook(comando), ruta)

    def test_commit_con_rutas_desde_una_subcarpeta(self):
        ruta = self.seguido("sub/seguido.txt")
        self.write(ruta, LINEA_SECRETA)
        self.assert_secreto(self.run_hook("cd sub && git commit -m x seguido.txt"), ruta)

    def test_commit_solo_de_rutas_ignora_el_resto_del_indice(self):
        ruta = self.seguido()
        self.write("preparado.txt", LINEA_SECRETA)
        self.stage("preparado.txt")
        self.write(ruta, "cambio\n")
        self.assert_passes(self.run_hook("git commit -m x seguido.txt"))
        self.assert_secreto(self.run_hook("git commit -i -m x seguido.txt"), "preparado.txt")
        self.assert_secreto(self.run_hook("git commit -am x"), "preparado.txt")

    def test_commit_normal_ignora_cambios_sin_preparar(self):
        ruta = self.seguido()
        self.write(ruta, LINEA_SECRETA)
        for comando in ("git commit -m x", "git commit -m '-a'", "git commit -m -a",
                        "git commit --message=--all", "git commit -m x > salida.txt 2>&1",
                        "git commit -m x # -a seguido.txt"):
            with self.subTest(comando=comando):
                self.assert_passes(self.run_hook(comando))

    def test_commit_all_sin_commits_previos(self):
        nuevo = self.repo.parent / "vacio"
        nuevo.mkdir()
        subprocess.run([GIT, "init", "-q"], cwd=nuevo, check=True)
        (nuevo / "a.txt").write_text("nada\n", encoding="utf-8")
        subprocess.run([GIT, "add", "a.txt"], cwd=nuevo, check=True)
        (nuevo / "a.txt").write_text(LINEA_SECRETA, encoding="utf-8")
        self.assert_secreto(self.run_hook("git -C ../vacio commit -am x"), "a.txt")

    def test_add_y_commit_en_el_mismo_comando(self):
        ruta = self.seguido()
        self.write(ruta, LINEA_SECRETA)
        self.write("sin-seguir.txt", LINEA_SECRETA)
        casos = (("git add seguido.txt && git commit -m x", ruta),
                 ("git add sin-seguir.txt && git commit -m x", "sin-seguir.txt"),
                 ("git add -A && git commit -m x", "sin-seguir.txt"),
                 ("git add . ; git commit -m x", "sin-seguir.txt"),
                 ("git add -u && git commit -m x", ruta))
        for comando, esperado in casos:
            with self.subTest(comando=comando):
                self.assert_secreto(self.run_hook(comando), esperado)

    def test_add_que_no_incluye_el_secreto_pasa(self):
        ruta = self.seguido()
        self.write(".gitignore", "ignorado.txt\n")
        self.write("ignorado.txt", LINEA_SECRETA)
        self.assert_passes(self.run_hook("git add -A && git commit -m x"))
        self.write("sin-seguir.txt", LINEA_SECRETA)
        self.write(ruta, "cambio\n")
        self.assert_passes(self.run_hook("git add -u && git commit -m x"))
        self.assert_passes(self.run_hook("git add seguido.txt && git commit -m x"))
        self.assert_passes(self.run_hook("git add -n sin-seguir.txt && git commit -m x"))
        self.assert_passes(self.run_hook("git add sin-seguir.txt"))
        self.assert_secreto(self.run_hook("git add -f ignorado.txt && git commit -m x"), "ignorado.txt")

    def test_add_de_archivo_sensible_sin_seguir(self):
        self.write("conf/.env", "A=1\n")
        output = self.decision(self.run_hook("git add conf && git commit -m x"))
        self.assertEqual(output["permissionDecision"], "deny")
        self.assertIn("conf/.env:1", output["permissionDecisionReason"])

    # --- Directorio en el que actúa git ---

    def test_git_c_revisa_ese_repo(self):
        otro = self.otro_repo()
        for comando in ("git -C ../otro commit -m x", "git -C {0} commit -m x".format(otro),
                        "git -C .. -C otro commit -m x", "git -c user.name=y -C ../otro commit -m x",
                        "git --no-pager -C '../otro' commit -m x",
                        "git --git-dir=../otro/.git --work-tree=../otro commit -m x"):
            with self.subTest(comando=comando):
                self.assert_secreto(self.run_hook(comando), "ajeno.txt")

    def test_git_c_push(self):
        otro = self.otro_repo()
        subprocess.run([GIT, "commit", "-q", "-m", "x"], cwd=otro, check=True)
        self.assert_secreto(self.run_hook("git -C ../otro push -u origin HEAD"), "ajeno.txt")

    def test_cd_antes_de_git(self):
        otro = self.otro_repo()
        for comando in ("cd ../otro && git commit -m x", "cd {0}; git commit -m x".format(otro),
                        "cd ..\ncd otro\ngit commit -m x", "pushd ../otro >/dev/null && git commit -m x",
                        'D=../otro; cd "$D" && git commit -m x', "export D=../otro && git -C $D commit -m x",
                        "bash -c 'cd ../otro && git commit -m x'", "(cd ../otro && git commit -m x)",
                        "if true; then cd ../otro; git commit -m x; fi",
                        "cd ../otro || exit 1; git commit -m x", "env LANG=C git -C ../otro commit -m x",
                        'echo "$(git -C ../otro commit -m x)"'):
            with self.subTest(comando=comando):
                self.assert_secreto(self.run_hook(comando), "ajeno.txt")

    def test_cd_a_la_raiz_del_repo(self):
        self.write("sub/x.txt", LINEA_SECRETA)
        self.stage("sub/x.txt")
        self.assert_secreto(
            self.run_hook('cd "$(git rev-parse --show-toplevel)" && git commit -m x'), "sub/x.txt")

    def test_el_directorio_de_la_sesion_no_cuenta_si_git_actua_en_otro(self):
        self.write("local.txt", LINEA_SECRETA)
        self.stage("local.txt")
        otro = self.otro_repo()
        subprocess.run([GIT, "rm", "-q", "--cached", "ajeno.txt"], cwd=otro, check=True)
        self.assert_passes(self.run_hook("cd ../otro && git commit -m x"))
        self.assert_passes(self.run_hook("git -C ../otro commit -m x"))
        self.assert_secreto(self.run_hook("(cd ../otro && ls); git commit -m x"), "local.txt")

    def test_directorio_que_no_se_puede_saber_pregunta(self):
        for comando in ('cd "$NO_DEFINIDA" && git commit -m x', 'cd "$(buscar-repo)" && git push',
                        "cd ../no-existe && git commit -m x", 'git -C "$NO_DEFINIDA" push',
                        "for d in a b; do cd $d; git commit -m x; done",
                        "cd - && git commit -m x",
                        "mkdir ../n && cd ../n && git init -q && git commit -m x"):
            with self.subTest(comando=comando):
                self.assert_ask(self.run_hook(comando))

    def test_repo_creado_en_el_mismo_comando_pregunta(self):
        (self.repo.parent / "plano").mkdir()
        self.assert_ask(self.run_hook("cd ../plano && git init -q && git add . && git commit -m x"))

    def test_mencionar_git_en_un_texto_no_pregunta(self):
        (self.repo.parent / "plano").mkdir()
        for comando in ("echo 'git push'", 'grep -r "git commit" .', "echo git push",
                        "cd ../plano && echo 'luego git push'"):
            with self.subTest(comando=comando):
                result = self.run_hook(comando)
                if result.stdout:
                    self.assertEqual(self.decision(result)["permissionDecision"], "allow")

    # --- Carpetas que dependen de lo que pase al ejecutar ---

    def secreto_preparado(self, relativo="local.txt"):
        self.write(relativo, LINEA_SECRETA)
        self.stage(relativo)
        return relativo

    def carpeta_hermana(self, nombre="plano"):
        """Carpeta sin repositorio, al lado del de trabajo."""
        (self.repo.parent / nombre).mkdir()

    def test_cd_condicional_revisa_tambien_la_carpeta_anterior(self):
        ruta = self.secreto_preparado()
        self.carpeta_hermana()
        for comando in ("[ -d nope ] && cd ../plano; git commit -m x",
                        "[ -d nope ] && cd ../plano\ngit commit -m x",
                        "[ -d nope ] && cd ../plano || true; git commit -m x",
                        "if [ -d nope ]; then cd ../plano; fi; git commit -m x",
                        "if false; then cd ../plano; else git commit -m x; fi",
                        "ir() { cd ../plano; }; git commit -m x",
                        "function ir {\n  cd ../plano\n}\ngit commit -m x",
                        "while false; do cd ../plano; done; git commit -m x",
                        "for d in; do cd ../plano; done; git commit -m x",
                        "case $x in a) cd ../plano ;; esac; git commit -m x",
                        "case b in a) cd ../plano ;; b) git commit -m x ;; esac",
                        "if false; then cd ../plano; fi; cd . && git commit -m x",
                        "[ -d nope ] && cd ../plano; bash -c 'git commit -m x'"):
            with self.subTest(comando=comando):
                self.assert_secreto(self.run_hook(comando), ruta)

    def test_cd_que_ha_ocurrido_seguro_no_revisa_la_carpeta_anterior(self):
        self.secreto_preparado()
        otro = self.otro_repo()
        subprocess.run([GIT, "rm", "-q", "--cached", "ajeno.txt"], cwd=otro, check=True)
        for comando in ("true && cd ../otro && git commit -m x",
                        "if true; then cd ../otro; git commit -m x; fi",
                        "(true && cd ../otro; true); cd ../otro && git commit -m x",
                        "x=(cd ../nada); cd ../otro; git commit -m x",
                        "{ cd ../otro; }; git commit -m x"):
            with self.subTest(comando=comando):
                self.assert_passes(self.run_hook(comando))

    def test_carpeta_desconocida_revisa_tambien_la_de_la_sesion(self):
        ruta = self.secreto_preparado()
        self.carpeta_hermana()
        for comando in ("mkdir -p build && cd build && git commit -m x",
                        "(cd no-existe 2>/dev/null; git commit -m x)",
                        'cd "$NO_DEFINIDA" && git commit -m x',
                        'git -C "$NO_DEFINIDA" commit -m x',
                        'cd "$OLDPWD" && git commit -m x',
                        "cd - && git commit -m x",
                        "cd ../plano && true; cd - && git commit -m x",
                        'cd ../plano; cd "$OLDPWD" && git commit -m x',
                        'cd "${NO_DEFINIDA:-.}" && git commit -m x',
                        "mkdir -p build && cd build && git add . && git commit -m x"):
            with self.subTest(comando=comando):
                self.assert_secreto(self.run_hook(comando), ruta)

    def test_carpetas_que_si_se_pueden_saber_no_preguntan(self):
        self.carpeta_hermana()
        for comando in ("cd ../plano && true; cd - && git commit -m x",
                        'cd "${NO_DEFINIDA:-.}" && git commit -m x',
                        'D=../plano; git -C "${D-nada}" commit -m x'):
            with self.subTest(comando=comando):
                self.assert_passes(self.run_hook(comando))

    def test_carpeta_sin_repositorio_no_decide(self):
        # Un «allow» saltaría la confirmación de permisos del resto del comando.
        self.carpeta_hermana()
        for comando in ("cd ../plano && rm -f algo && git push", "cd ../plano && git commit -m x",
                        "git -C ../plano commit -m x"):
            with self.subTest(comando=comando):
                self.assert_passes(self.run_hook(comando))

    def test_fallo_interno_en_formas_nuevas_no_decide(self):
        empty_bin = Path(self.temporary.name) / "sin-git"
        empty_bin.mkdir()
        self.assert_passes(self.run_hook("git -C . commit -m x", path=empty_bin))

    # --- Remotos nuevos y ficheros escritos en el mismo comando ---

    def test_push_a_un_remoto_nuevo_revisa_toda_la_historia(self):
        self.commit_secreto()
        self.remoto_publicado("privado")
        self.git("remote", "add", "publico", str(self.repo))
        self.assert_secreto(self.run_hook("git push publico HEAD"), "pendiente.txt")

    def test_revisa_ficheros_escritos_en_el_mismo_comando(self):
        ruta = self.seguido()
        texto = LINEA_SECRETA.strip()
        casos = (
            ("cat > otro.py <<'EOF'\n{0}\nEOF\ngit add otro.py && git commit -m x", "otro.py"),
            ("echo '{0}' >> seguido.txt && git add seguido.txt && git commit -m x", ruta),
            ("echo '{0}' > seguido.txt && git commit -am x", ruta),
            ("echo '{0}' > seguido.txt && git commit -m x seguido.txt", ruta),
            ("mkdir -p sub && echo '{0}' > sub/n.txt && git add -A && git commit -m x", "sub/n.txt"),
            ("echo '{0}' | tee n.txt && git add . && git commit -m x", "n.txt"),
            ("cd .. && echo '{0}' > repo/n.txt && cd repo && git add n.txt && git commit -m x", "n.txt"),
        )
        for comando, esperado in casos:
            with self.subTest(comando=comando):
                self.assert_secreto(self.run_hook(comando.format(texto)), esperado)
        output = self.decision(self.run_hook("echo A=1 > .env && git add .env && git commit -m x"))
        self.assertEqual(output["permissionDecision"], "deny")
        self.assertIn(".env:1", output["permissionDecisionReason"])

    def test_escrito_que_no_entra_en_el_commit_pasa(self):
        self.write(".gitignore", "ignorado.txt\n")
        self.commit_secreto("publicado.txt")
        texto = LINEA_SECRETA.strip()
        for comando in ("echo '{0}' > ignorado.txt && git add -A && git commit -m x",
                        "echo '{0}' > n.txt && git commit -m x",
                        "echo '{0}' > n.txt && git add -u && git commit -m x",
                        "echo '{0}' > n.txt && git add otro.txt && git commit -m x",
                        "echo '{0}' > ../fuera.txt && git add -A && git commit -m x",
                        "echo limpio >> publicado.txt && git add publicado.txt && git commit -m x",
                        "git add -A && git commit -m x && echo '{0}' > despues.txt"):
            with self.subTest(comando=comando):
                self.assert_passes(self.run_hook(comando.format(texto)))
        self.assert_secreto(self.run_hook(
            "echo '{0}' > ignorado.txt && git add -f ignorado.txt && git commit -m x".format(texto)), "ignorado.txt")

    # --- Argumentos que no se pueden saber, límites y configuración del repo ---

    def test_argumentos_que_pone_la_shell(self):
        self.write("a.py", LINEA_SECRETA)
        for comando in ("git add {a,b}.py && git commit -m x",
                        "echo a.py | xargs git add && git commit -m x"):
            with self.subTest(comando=comando):
                self.assert_secreto(self.run_hook(comando), "a.py")

    def test_add_que_no_se_puede_revisar_pregunta(self):
        self.assert_ask(self.run_hook('git -C "$NO_DEFINIDA" add . && git commit -m x'))

    def test_revisar_no_ejecuta_el_fsmonitor_del_repo(self):
        marca = self.repo.parent / "ejecutado"
        espia = self.repo.parent / "espia"
        espia.write_text("#!{0}\nopen({1!r}, 'w').close()\n".format(sys.executable, str(marca)), encoding="utf-8")
        espia.chmod(0o755)
        self.write("nuevo.txt", "nada\n")
        self.git("config", "core.fsmonitor", str(espia))
        self.run_hook("git add -A && git commit -m x")
        self.assertFalse(marca.exists())

    def test_el_limite_de_tiempo_corta_un_parche_enorme(self):
        spec = importlib.util.spec_from_file_location("anti_filtraciones", HOOK)
        modulo = importlib.util.module_from_spec(spec)
        with unittest.mock.patch.object(sys, "dont_write_bytecode", True):
            spec.loader.exec_module(modulo)
        parche = "diff --git a/x b/x\n+++ b/x\n@@ -0,0 +1,100000 @@\n" + "+linea\n" * 100000
        with self.assertRaises(modulo.HookFailure):
            modulo.parse_patch(parche, time.monotonic() - 1)

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

    def test_ruta_de_body_file_y_repo_no_se_revisan_como_texto(self):
        ruta = self.home / "x.md"
        ruta.write_text("Cuerpo limpio\n")
        self.assertIsNone(self.run_hook("gh issue create --title t --body-file {0}".format(ruta)))
        self.assertIsNone(self.run_hook("gh pr create -F '{0}'".format(ruta)))
        self.assertIsNone(self.run_hook("gh issue create -R acme/web --title t --body 'limpio'"))
        ruta.write_text("IP 10.0.0.5\n")  # el contenido sí se revisa
        self.assertEqual(self.run_hook("gh issue create --title t --body-file {0}".format(ruta))["permissionDecision"], "deny")

    def preparar_commit(self, contenido):
        """Repo git en la carpeta de trabajo con `contenido` en el índice."""
        os.symlink(GIT, self.bin / "git")
        subprocess.run([GIT, "init", "-q"], cwd=self.cwd, check=True)
        (self.cwd / "nuevo.txt").write_text(contenido)
        subprocess.run([GIT, "add", "nuevo.txt"], cwd=self.cwd, check=True)

    @unittest.skipUnless(GIT, "Git es necesario")
    def test_ask_de_gh_no_salta_la_revision_de_git(self):
        self.visibility(None)
        self.preparar_commit("valor = ghp_1234567890abcdef\n")  # reglas:permitir
        salida = self.run_hook("git commit -m x && gh pr create --title t --body 'falla en 10.0.0.5'")
        self.assertEqual(salida["permissionDecision"], "deny")
        self.assertIn("nuevo.txt:", salida["permissionDecisionReason"])

    @unittest.skipUnless(GIT, "Git es necesario")
    def test_ask_de_gh_se_mantiene_con_git_limpio(self):
        self.visibility(None)
        self.preparar_commit("hola\n")
        salida = self.run_hook("git commit -m x && gh pr create --title t --body 'falla en 10.0.0.5'")
        self.assertEqual(salida["permissionDecision"], "ask")

    def test_ask_de_gh_se_mantiene_si_git_falla(self):
        self.visibility(None)  # sin git en el PATH: la revisión de git falla
        salida = self.run_hook("git push && gh pr create --title t --body 'falla en 10.0.0.5'")
        self.assertEqual(salida["permissionDecision"], "ask")
        self.assertIn("parte de git", salida["permissionDecisionReason"])

    # --- Varios gh en un comando y cuerpos que vienen de otra parte ---

    def visibilidad_por_repo(self):
        """`gh` falso: responde según el repo pedido o, sin -R, según la carpeta."""
        gh = self.bin / "gh"
        gh.write_text('#!/bin/sh\n'
                      'case "$3" in\n'
                      '  *publico*) echo PUBLIC ;;\n'
                      '  *privado*) echo PRIVATE ;;\n'
                      '  *) case "$PWD" in *publico*) echo PUBLIC ;; *privado*) echo PRIVATE ;; *) exit 1 ;; esac ;;\n'
                      'esac\n')
        gh.chmod(0o755)

    def assert_decision(self, comando, esperada):
        salida = self.run_hook(comando)
        obtenida = salida["permissionDecision"] if salida else None
        self.assertEqual(obtenida, esperada, "{0}: {1}".format(
            comando, salida and salida["permissionDecisionReason"]))
        return salida

    def test_varios_gh_comprueban_cada_repo(self):
        self.visibilidad_por_repo()
        privado = "gh issue create -R acme/privado --title t --body 'limpio'"
        publico = "gh issue comment 1 -R acme/publico --body 'IP 10.0.0.5'"
        for comando in (privado + " && " + publico, publico + " && " + privado,
                        "gh pr comment 2 -R acme/privado -b 'IP 10.0.0.9'; " + publico,
                        privado + " && gh pr comment 1 --repo=acme/publico -b 'IP 10.0.0.5'",
                        privado + " && gh pr comment 1 -Racme/publico -b 'IP 10.0.0.5'",
                        privado + " && gh issue -R acme/publico comment 1 -b 'IP 10.0.0.5'",
                        privado + " && GH_REPO=acme/publico gh issue comment 1 -b 'IP 10.0.0.5'",
                        privado + " && gh issue comment https://github.com/acme/publico/issues/1 -b 'IP 10.0.0.5'"):
            with self.subTest(comando=comando):
                self.assert_decision(comando, "deny")

    def test_cada_texto_cuenta_para_su_repo(self):
        self.visibilidad_por_repo()
        self.assert_decision("gh issue create -R acme/publico -t t -b limpio && "
                             "gh issue create -R acme/privado -t t -b 'IP 10.0.0.5'", None)

    def test_texto_comun_cuenta_para_todos_los_repos(self):
        self.visibilidad_por_repo()
        self.assert_decision("CUERPO='IP 10.0.0.5'; gh issue create -R acme/privado -t t -b \"$CUERPO\" && "
                             "gh issue create -R acme/publico -t t -b \"$CUERPO\"", "deny")

    def test_cd_decide_el_repo_sin_r(self):
        self.visibilidad_por_repo()
        (self.cwd / "publico").mkdir()
        (self.cwd / "privado").mkdir()
        self.assert_decision("cd publico && gh issue create -t t -b 'IP 10.0.0.5'", "deny")
        self.assert_decision("cd privado && gh issue create -t t -b 'IP 10.0.0.5'", None)
        self.assert_decision('cd "$NO_DEFINIDA" && gh issue create -t t -b \'IP 10.0.0.5\'', "ask")

    def test_repo_que_no_se_puede_saber_pregunta(self):
        self.visibilidad_por_repo()
        self.assert_decision('gh issue create -R "$NO_DEFINIDO" -t t -b \'IP 10.0.0.5\'', "ask")

    def test_cuerpo_por_stdin_o_sustitucion_se_lee(self):
        (self.cwd / "c.md").write_text("Servidor 10.20.30.40\n")
        for comando in ("cat c.md | gh issue create -t t --body-file -",
                        "gh issue create -t t --body-file - < c.md",
                        "gh pr comment 1 -F - <c.md", "gh pr create -F- < c.md",
                        "gh pr create --body-file=/dev/stdin < c.md",
                        'gh issue create -t t --body "$(cat c.md)"',
                        'gh issue create -t t --body="$(< c.md)"',
                        'gh pr comment 1 -b "Antes: $(cat -- c.md)"',
                        'gh pr comment 1 -b "`cat c.md`"',
                        'gh issue create --title "$(cat c.md)" -b x',
                        'B="$(cat c.md)"; gh issue create -t t -b "$B"',
                        'F=c.md; gh issue create -t t -F "$F"',
                        'cat c.md > copia.md && gh issue create -t t -F copia.md',
                        'gh pr comment 1 -F <(cat c.md)',
                        'gh issue create -t t -b "$(cat <<EOF\n$(cat c.md)\nEOF\n)"'):
            with self.subTest(comando=comando):
                self.assert_decision(comando, "deny")

    def test_secreto_leido_de_fichero_se_bloquea_tambien_en_privado(self):
        self.visibility("PRIVATE")
        (self.cwd / "c.md").write_text("token ghp_abcdefgh12345678\n")  # reglas:permitir
        for comando in ('gh issue create -t t --body "$(cat c.md)"', "cat c.md | gh pr comment 1 -F -"):
            with self.subTest(comando=comando):
                salida = self.assert_decision(comando, "deny")
                self.assertNotIn("abcdefgh12345678", salida["permissionDecisionReason"])

    ILEGIBLES = (
        "generar-informe | gh issue create -t t --body-file -",
        "cat c.md | sed s/a/b/ | gh issue create -t t -F -",
        "gh issue create -t t --body-file -",
        'gh issue create -t t --body "$(generar-informe)"',
        'gh pr comment 1 -b "$(cat no-existe.md)"',
        'gh pr comment 1 -b "$NO_DEFINIDA"',
        "gh issue create -t t -F no-existe.md",
        "generar-informe > c.md && gh issue create -t t -F c.md",
        'F=$(mktemp); generar-informe > "$F"; gh issue create -t t -F "$F"',
        "gh pr comment 1 -F <(generar-informe)",
        'read -r B; gh pr comment 1 -b "$B"',
        'gh issue create -R acme/web -t "$(generar-informe)" -b x',
    )

    def test_cuerpo_ilegible_pregunta_si_el_repo_es_publico_o_desconocido(self):
        (self.cwd / "c.md").write_text("limpio\n")
        for visibilidad, esperada in (("PUBLIC", "ask"), (None, "ask"), ("PRIVATE", None)):
            self.visibility(visibilidad)
            for comando in self.ILEGIBLES:
                with self.subTest(visibilidad=visibilidad, comando=comando):
                    self.assert_decision(comando, esperada)

    def test_cuerpos_legibles_y_limpios_pasan(self):
        (self.cwd / "c.md").write_text("limpio\n")
        for comando in ("cat c.md | gh issue create -t t -F -", "gh issue create -t t -F - < c.md",
                        "echo limpio | gh pr comment 1 -F -", "gh pr comment 1 -F - <<< 'limpio'",
                        "gh issue create -t t -F - <<'EOF'\nusa $(algo) y `otro` )\nEOF",
                        'gh pr create -t t -b "$(cat <<\'EOF\'\n- uno) con `código` y $(cosas)\nEOF\n)"',
                        "cat > n.md <<'EOF'\nlimpio\nEOF\ngh issue create -t t -F n.md",
                        'F=$(mktemp); cat > "$F" <<\'EOF\'\nlimpio\nEOF\ngh issue create -t t -F "$F"',
                        'B=limpio; gh pr comment 1 -b "$B"', "gh pr comment 1 -b 'cuesta $5 y `x`'",
                        'gh pr create -t t -b x --head "$(git branch --show-current)"',
                        'gh pr comment "$(ultimo-pr)" -b limpio',
                        'gh pr review 3 -a -b limpio', "gh pr create --fill",
                        'url=$(gh pr create -t t -b limpio) && echo "$url"'):
            with self.subTest(comando=comando):
                self.assert_decision(comando, None)

    def test_cd_condicional_comprueba_todas_las_carpetas_posibles(self):
        self.visibilidad_por_repo()
        (self.cwd / "publico").mkdir()
        (self.cwd / "privado").mkdir()
        gh = "gh issue create -t t -b 'IP 10.0.0.5'"
        for comando in ("cd publico; [ -d nope ] && cd ../privado; ",
                        "cd publico; if false; then cd ../privado; fi; "):
            with self.subTest(comando=comando):
                self.assert_decision(comando + gh, "deny")
        self.assert_decision("cd privado; true && cd . && " + gh, None)

    def test_carpeta_desconocida_en_repo_publico_se_bloquea(self):
        self.assert_decision('cd "$NO_DEFINIDA" && gh issue create -t t -b \'IP 10.0.0.5\'', "deny")

    def test_hosts_propios_del_usuario(self):
        carpeta = self.home / ".config" / "reglas"
        carpeta.mkdir(parents=True)
        (carpeta / "hosts-privados").write_text("# mis equipos\nminas-del-norte\n")
        salida = self.run_hook("gh issue create --title t --body 'caído minas-del-norte'")
        self.assertEqual(salida["permissionDecision"], "deny")


if __name__ == "__main__":
    unittest.main()
