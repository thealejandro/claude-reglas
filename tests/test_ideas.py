import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

HOOKS = Path(__file__).resolve().parents[1] / 'hooks'


class Base(unittest.TestCase):
    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporal.cleanup)
        self.home = Path(self.temporal.name)
        self.cola = self.home / '.local/state/cabo/ideas/cola.jsonl'

    def hook(self, nombre, entrada):
        r = subprocess.run([sys.executable, '-I', str(HOOKS / nombre)], input=json.dumps(entrada), text=True,
                           capture_output=True, timeout=10, env=dict(os.environ, HOME=str(self.home)))
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout) if r.stdout.strip() else None

    def captura(self, prompt, sesion='s1', cwd=None):
        return self.hook('ideas-captura.py', {'session_id': sesion, 'cwd': cwd or str(self.home), 'prompt': prompt})

    def registros(self):
        if not self.cola.exists():
            return []
        return [json.loads(x) for x in self.cola.read_text(encoding='utf-8').splitlines()]

    def resolver(self, hash_):
        with open(self.cola, 'a', encoding='utf-8') as f:
            f.write(json.dumps({'v': 1, 'tipo': 'resuelta', 'hash': hash_, 'estado': 'creada',
                                'issue': 'o/r#1', 'fecha': '2026-01-01T00:00:00Z'}) + '\n')


class IdeasTests(Base):
    def test_captura_marcadores(self):
        casos = {'Habría que mejorar el login': 'idea', 'estaría bien exportar a CSV': 'idea',
                 'Más adelante: un modo oscuro': 'idea', 'También quiero un filtro': 'idea',
                 'idea: botón de ayuda': 'idea', 'Deberíamos migrar la base': 'idea',
                 'Hay un bug al guardar': 'bug', 'Queda pendiente la factura': 'pendiente'}
        for prompt, categoria in casos.items():
            with self.subTest(prompt=prompt):
                salida = self.captura(prompt)
                self.assertIn('Idea anotada', salida['hookSpecificOutput']['additionalContext'])
                self.assertEqual(salida['hookSpecificOutput']['hookEventName'], 'UserPromptSubmit')
                self.assertEqual(self.registros()[-1]['categoria'], categoria)

    def test_debería_singular(self):
        self.captura('Debería poder exportar a CSV')
        self.assertEqual(self.registros()[0]['categoria'], 'idea')

    def test_no_captura_citas_codigo_ni_terminal(self):
        casos = ['> Queda pendiente de merge.\n\nVale', '> hay un bug\n> más adelante lo vemos\nVale, sigue',
                 'Mira:\n```\nbug en la línea 3\n```\nGracias', 'Mira:\n```\nbug sin cerrar',
                 'usuario@equipo:~$ make test\nFAIL: bug en el test\n\nOk',
                 '$ ./probar\nhay un bug aquí\n\nVale']
        for prompt in casos:
            with self.subTest(prompt=prompt):
                self.assertIsNone(self.captura(prompt))
        self.assertFalse(self.cola.exists())

    def test_captura_lo_propio_junto_a_cita_y_codigo(self):
        self.captura('> pendiente de merge\n\nHabría que añadir un filtro\n```\nbug\n```')
        (r,) = self.registros()
        self.assertEqual(r['categoria'], 'idea')
        self.assertNotIn('merge', r['extracto'])
        self.assertNotIn('bug', r['extracto'])

    def test_sin_marcador_no_hace_nada(self):
        self.assertIsNone(self.captura('Arregla el test que falla en CI, gracias'))
        self.assertFalse(self.cola.exists())

    def test_ignora_comandos_y_prompts_vacios(self):
        self.assertIsNone(self.captura('/ideas habría que algo'))
        self.assertIsNone(self.captura('<task-notification>bug</task-notification>'))
        self.assertIsNone(self.captura('   '))
        self.assertFalse(self.cola.exists())

    def test_formato_de_la_entrada_y_permisos(self):
        self.captura('Habría que revisar esto', sesion='abc')
        (r,) = self.registros()
        self.assertEqual(sorted(r), sorted(['v', 'tipo', 'fecha', 'sesion', 'cwd', 'remoto', 'categoria', 'extracto', 'hash']))
        self.assertEqual((r['v'], r['tipo'], r['sesion'], r['categoria']), (1, 'idea', 'abc', 'idea'))
        self.assertRegex(r['hash'], r'^[0-9a-f]{16}$')
        self.assertRegex(r['fecha'], r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$')
        self.assertEqual(os.stat(self.cola).st_mode & 0o777, 0o600)
        self.assertEqual(os.stat(self.cola.parent).st_mode & 0o777, 0o700)

    def test_extracto_redactado(self):
        self.captura('Habría que cambiar el host srv1.tailnet.ts.net, la IP 10.1.2.3, ssh deploy@srv1.tailnet.ts.net, '
                     'la ruta /home/dev/proyecto y el token ghp_abcdefgh12345678 y el DPI 1234 12345 1234.')
        texto = self.registros()[0]['extracto']
        for fuga in ('ts.net', '10.1.2.3', 'deploy@', '/home/dev', 'ghp_abcdefgh', '1234 12345 1234'):
            self.assertNotIn(fuga, texto)
        self.assertIn('[ip]', texto)

    def test_extracto_tope_de_500(self):
        self.captura('Habría que ' + 'palabra ' * 400)
        self.assertLessEqual(len(self.registros()[0]['extracto']), 500)

    def test_remoto_desde_git_config(self):
        repo = self.home / 'repo'
        (repo / '.git').mkdir(parents=True)
        (repo / '.git/config').write_text('[remote "origin"]\n\turl = https://usuario:clave@github.com/acme/web.git\n')
        (repo / 'sub').mkdir()
        self.captura('Habría que algo', cwd=str(repo / 'sub'))
        self.assertEqual(self.registros()[0]['remoto'], 'acme/web')

    def test_duplicado_exacto_no_se_repite(self):
        self.captura('Habría que revisar esto')
        self.assertIsNone(self.captura('Habría que revisar esto'))
        self.assertEqual(len(self.registros()), 1)

    def test_rapido(self):
        self.captura('Habría que revisar esto')
        inicio = time.monotonic()
        for i in range(5):
            self.captura('Habría que revisar esto %d' % i)
        self.assertLess((time.monotonic() - inicio) / 5, 0.25)  # holgado: incluye el arranque de Python

    def test_stop_bloquea_una_vez(self):
        self.captura('Habría que revisar esto', sesion='s1')
        salida = self.hook('ideas-stop.py', {'session_id': 's1', 'stop_hook_active': False})
        self.assertEqual(salida['decision'], 'block')
        self.assertIn('revisar esto', salida['reason'])
        self.assertIsNone(self.hook('ideas-stop.py', {'session_id': 's1', 'stop_hook_active': False}))

    def test_stop_respeta_stop_hook_active(self):
        self.captura('Habría que revisar esto', sesion='s1')
        self.assertIsNone(self.hook('ideas-stop.py', {'session_id': 's1', 'stop_hook_active': True}))
        self.assertEqual([r['tipo'] for r in self.registros()], ['idea'])  # sin aviso: aún puede bloquear

    def test_stop_solo_de_su_sesion_y_sin_resueltas(self):
        self.captura('Habría que revisar esto', sesion='s1')
        self.assertIsNone(self.hook('ideas-stop.py', {'session_id': 's2'}))
        self.resolver(self.registros()[0]['hash'])
        self.assertIsNone(self.hook('ideas-stop.py', {'session_id': 's1'}))

    def test_stop_sin_cola(self):
        self.assertIsNone(self.hook('ideas-stop.py', {'session_id': 's1'}))
        self.assertIsNone(self.hook('ideas-stop.py', {}))

    def test_inicio_reinyecta_pendientes(self):
        self.assertIsNone(self.hook('ideas-inicio.py', {'session_id': 's1', 'source': 'compact'}))
        self.captura('Habría que revisar esto', sesion='s1')
        self.captura('También quiero un filtro', sesion='s2')
        salida = self.hook('ideas-inicio.py', {'session_id': 's1', 'source': 'compact'})
        self.assertEqual(salida['hookSpecificOutput']['hookEventName'], 'SessionStart')
        self.assertIn('2 ideas en cola', salida['hookSpecificOutput']['additionalContext'])
        self.assertIn('1 de esta sesión', salida['hookSpecificOutput']['additionalContext'])
        self.resolver(self.registros()[0]['hash'])
        self.assertIn('1 idea en cola', self.hook('ideas-inicio.py', {'session_id': 's1'})['hookSpecificOutput']['additionalContext'])

    def test_cola_con_lineas_rotas_o_de_otra_version(self):
        self.cola.parent.mkdir(parents=True)
        self.cola.write_text('basura\n{"v":2,"tipo":"idea","hash":"x"}\n[1]\n', encoding='utf-8')
        self.assertIsNone(self.hook('ideas-inicio.py', {'session_id': 's1'}))
        self.captura('Habría que revisar esto')
        self.assertEqual(len(self.cola.read_text(encoding='utf-8').splitlines()), 4)

    def test_entrada_invalida_no_rompe(self):
        for nombre in ('ideas-captura.py', 'ideas-stop.py', 'ideas-inicio.py'):
            r = subprocess.run([sys.executable, '-I', str(HOOKS / nombre)], input='no es json', text=True,
                               capture_output=True, timeout=10, env=dict(os.environ, HOME=str(self.home)))
            self.assertEqual((r.returncode, r.stdout), (0, ''))


class ColaScriptTests(Base):
    SCRIPT = HOOKS.parent / 'skills/ideas/scripts/cola.py'

    def cola_cmd(self, *args, ok=True, entorno=None):
        r = subprocess.run([sys.executable, '-I', str(self.SCRIPT), *args], text=True, capture_output=True,
                           timeout=10, env=dict(os.environ, HOME=str(self.home), **(entorno or {})))
        self.assertEqual(r.returncode == 0, ok, r.stderr)
        return json.loads(r.stdout) if r.stdout.strip() else None

    def test_tope_diario_no_numerico_usa_el_valor_por_defecto(self):
        for valor, tope in (('cinco', 5), ('3.5', 5), ('', 5), ('  ', 5), (' 7 ', 7), ('0', 0)):
            with self.subTest(valor=valor):
                salida = self.cola_cmd('hoy', 'acme/web', entorno={'IDEAS_TOPE_DIARIO': valor})
                self.assertEqual(salida['tope'], tope)
        self.assertEqual(self.cola_cmd('pendientes', entorno={'IDEAS_TOPE_DIARIO': 'x'}), [])

    def test_flujo_pendientes_resolver_tope(self):
        self.captura('Habría que revisar esto', sesion='s1')
        self.captura('Hay un bug al guardar', sesion='s2')
        self.assertEqual(len(self.cola_cmd('pendientes')), 2)
        (uno,) = self.cola_cmd('pendientes', '--sesion', 's1')
        self.cola_cmd('resolver', uno['hash'], 'creada', '--issue', 'acme/web#7')
        self.assertEqual(len(self.cola_cmd('pendientes')), 1)
        self.assertEqual(self.cola_cmd('hoy', 'acme/web'), {'repo': 'acme/web', 'creados_hoy': 1, 'tope': 5, 'queda': 4})
        self.assertEqual(self.cola_cmd('hoy', 'acme/otro')['creados_hoy'], 0)
        self.cola_cmd('resolver', 'inexistente', 'creada', ok=False)

    def test_aplazada_sigue_pendiente_y_compactar(self):
        self.captura('Habría que revisar esto')
        (uno,) = self.cola_cmd('pendientes')
        self.cola_cmd('aplazar', uno['hash'], '--motivo', 'cuota')
        self.assertEqual(len(self.cola_cmd('pendientes')), 1)
        with open(self.cola, 'a', encoding='utf-8') as f:
            f.write(json.dumps({'v': 1, 'tipo': 'idea', 'hash': 'viejo', 'fecha': '2020-01-01T00:00:00Z'}) + '\n')
            f.write(json.dumps({'v': 1, 'tipo': 'resuelta', 'hash': 'viejo', 'estado': 'creada', 'fecha': '2020-01-02T00:00:00Z'}) + '\n')
        self.assertEqual(self.cola_cmd('compactar'), {'antes': 4, 'despues': 2})
        self.assertEqual(os.stat(self.cola).st_mode & 0o777, 0o600)


if __name__ == '__main__':
    unittest.main()
