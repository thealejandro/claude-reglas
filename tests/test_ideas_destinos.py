"""Destino, repos permitidos, confirmaciones y duplicados de /ideas. Un `gh` falso responde según un guion."""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

RAIZ = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(RAIZ / 'tests'), str(RAIZ / 'hooks')]  # los tests corren con python3 -I
from test_ideas import Base  # noqa: E402
import ideas_cola  # noqa: E402

SCRIPT = RAIZ / 'skills/ideas/scripts/cola.py'

GH_FALSO = '''
import json, os, sys
casa = os.environ['HOME']
with open(os.path.join(casa, 'gh.json')) as f:
    guion = json.load(f)
args = sys.argv[1:]
with open(os.path.join(casa, 'gh.log'), 'a') as f:
    f.write(json.dumps(args) + '\\n')
if guion.get('caido'):
    sys.exit(1)
if args[:2] == ['repo', 'view']:
    repo = guion['repos'].get(args[2])
    if repo is None:
        sys.exit(1)
    print(json.dumps(dict({'nameWithOwner': args[2], 'visibility': 'PRIVATE', 'viewerPermission': 'ADMIN',
                           'isArchived': False}, **repo)))
elif args[:2] == ['issue', 'list']:
    estado = args[args.index('--state') + 1]
    clave = estado if estado != 'closed' else 'closed'
    print(json.dumps(guion.get(clave, [])))
else:
    sys.exit(2)
'''


class DestinosBase(Base):
    def setUp(self):
        super().setUp()
        self.bin = self.home / 'bin'
        self.bin.mkdir()
        gh = self.bin / 'gh'
        gh.write_text('#!' + sys.executable + '\n' + GH_FALSO)
        gh.chmod(0o755)
        self.guion(repos={})

    def guion(self, **datos):
        (self.home / 'gh.json').write_text(json.dumps(datos))

    def config(self, **datos):
        carpeta = self.home / '.config/reglas'
        carpeta.mkdir(parents=True, exist_ok=True)
        (carpeta / 'ideas.json').write_text(json.dumps(datos))

    def llamadas(self):
        registro = self.home / 'gh.log'
        return [json.loads(x) for x in registro.read_text().splitlines()] if registro.exists() else []

    def cmd(self, *args, ok=True):
        entorno = dict(os.environ, HOME=str(self.home), PATH=str(self.bin))
        entorno.pop('CLAUDE_PLUGIN_OPTION_REPO_RUNBOOKS', None)
        r = subprocess.run([sys.executable, '-I', str(SCRIPT), *args], text=True, capture_output=True,
                           timeout=20, env=entorno)
        self.assertEqual(r.returncode == 0, ok, r.stderr)
        return json.loads(r.stdout) if ok and r.stdout.strip() else r.stderr

    def repo_git(self, remoto, nombre='proyecto'):
        raiz = self.home / nombre
        (raiz / '.git').mkdir(parents=True)
        (raiz / '.git/config').write_text(
            '[remote "origin"]\n\turl = git@github.com:{0}.git\n'.format(remoto) if remoto else '')
        return raiz

    def destino(self, prompt, cwd=None):
        antes = len(self.registros())
        self.captura(prompt, cwd=str(cwd) if cwd else None)
        self.assertEqual(len(self.registros()), antes + 1)
        (salida,) = self.cmd('destino', self.registros()[-1]['hash'])
        return salida


class DestinoTests(DestinosBase):
    def test_remoto_propio_privado_sin_confirmaciones(self):
        self.guion(repos={'acme/web': {}})
        d = self.destino('Habría que añadir un filtro', self.repo_git('acme/web'))
        self.assertEqual((d['repo'], d['motivo'], d['permitido'], d['confirmar']), ('acme/web', 'remoto', True, []))

    def test_sin_lista_no_vale_un_repo_de_terceros(self):
        self.guion(repos={'otro/lib': {'viewerPermission': 'READ', 'visibility': 'PUBLIC'}})
        d = self.destino('Habría que añadir un filtro', self.repo_git('otro/lib'))
        self.assertEqual((d['repo'], d['permitido']), ('otro/lib', False))

    def test_lista_de_permitidos_manda_sobre_el_permiso(self):
        self.guion(repos={'acme/web': {}, 'mia/app': {}})
        self.config(repos=['mia/*'])
        self.assertFalse(self.destino('Habría que añadir un filtro', self.repo_git('acme/web'))['permitido'])
        self.assertTrue(self.destino('Habría que añadir otro filtro', self.repo_git('mia/app', 'app'))['permitido'])

    def test_lista_vacia_no_permite_nada(self):
        self.guion(repos={'acme/web': {}})
        self.config(repos=[])
        self.assertFalse(self.destino('Habría que algo', self.repo_git('acme/web'))['permitido'])

    def test_configuracion_rota_falla(self):
        carpeta = self.home / '.config/reglas'
        carpeta.mkdir(parents=True)
        for contenido in ('{', '[]', '{"repos": "mia/*"}', '{"alias": {"web": "sin-barra"}}'):
            with self.subTest(contenido=contenido):
                (carpeta / 'ideas.json').write_text(contenido)
                self.captura('Habría que algo ' + contenido)
                self.assertIn('ideas.json', self.cmd('destino', self.registros()[-1]['hash'], ok=False))

    def test_alias_gana_al_remoto_y_pide_confirmacion(self):
        self.guion(repos={'acme/web': {}, 'acme/api': {}})
        self.config(alias={'la API': 'acme/api'})
        d = self.destino('Habría que versionar la api', self.repo_git('acme/web'))
        self.assertEqual((d['repo'], d['motivo'], d['confirmar'], d['otros']),
                         ('acme/api', 'alias', ['destino dudoso'], ['acme/web']))
        self.assertEqual(self.destino('Habría que documentar la api')['confirmar'], [])

    def test_gist_no_es_mencion(self):
        self.guion(repos={'acme/web': {}})
        raiz = self.repo_git('acme/web')
        d = self.destino('Habría que copiar https://gist.github.com/fulano/abc123', raiz)
        self.assertEqual((d['repo'], d['confirmar']), ('acme/web', []))
        self.assertEqual(self.destino('Habría que ver www.github.com/acme/web', raiz)['motivo'], 'mencion')

    def test_con_lista_y_gh_caido_no_se_permite(self):
        self.guion(caido=True)
        self.config(repos=['acme/*'])
        d = self.destino('Habría que algo', self.repo_git('acme/web'))
        self.assertEqual((d['repo'], d['permitido'], d['error']), ('acme/web', False, 'gh'))

    def test_runbooks_ajeno_no_se_permite(self):
        self.config(runbooks='otro/runbooks')
        for permiso, permitido in (('READ', False), ('TRIAGE', False), ('WRITE', True)):
            with self.subTest(permiso=permiso):
                self.guion(repos={'otro/runbooks': {'viewerPermission': permiso}})
                d = self.destino('Habría que cambiar la IP 10.0.0.5 con permiso ' + permiso)
                self.assertEqual(d['permitido'], permitido)

    def test_mencion_por_referencia_o_url(self):
        self.guion(repos={'acme/api': {}})
        for texto in ('Habría que cerrar acme/api#4', 'Habría que mirar https://github.com/acme/api.git'):
            with self.subTest(texto=texto):
                d = self.destino(texto)
                self.assertEqual((d['repo'], d['motivo']), ('acme/api', 'mencion'))

    def test_una_ruta_suelta_no_es_mencion(self):
        self.guion(repos={'acme/web': {}})
        d = self.destino('Habría que ordenar src/utils', self.repo_git('acme/web'))
        self.assertEqual((d['repo'], d['confirmar']), ('acme/web', []))

    def test_owner_repo_suelto_cuenta_si_esta_en_la_lista(self):
        self.guion(repos={'acme/api': {}})
        self.config(repos=['acme/*'])
        self.assertEqual(self.destino('Habría que tocar acme/api')['motivo'], 'mencion')

    def test_dos_menciones_son_dudosas(self):
        self.guion(repos={'acme/api': {}, 'acme/web': {}})
        d = self.destino('Habría que unir acme/api#1 con acme/web#2')
        self.assertEqual(d['repo'], 'acme/api')
        self.assertIn('destino dudoso', d['confirmar'])
        self.assertEqual(d['otros'], ['acme/web'])

    def test_mencion_ajena_no_desplaza_al_remoto_propio(self):
        self.guion(repos={'acme/web': {}, 'otro/lib': {'viewerPermission': 'READ'}})
        d = self.destino('Habría que copiar lo de otro/lib#3', self.repo_git('acme/web'))
        self.assertEqual((d['repo'], d['permitido']), ('acme/web', True))
        self.assertIn('destino dudoso', d['confirmar'])

    def test_cabo_toml_cuando_no_hay_remoto(self):
        self.guion(repos={'acme/notas': {}})
        raiz = self.repo_git('')
        (raiz / '.cabo.toml').write_text('# x\nrepo = "acme/notas"  # destino\n[otra]\nrepo = "acme/no"\n')
        (raiz / 'sub').mkdir()
        d = self.destino('Habría que ordenar las notas', raiz / 'sub')
        self.assertEqual((d['repo'], d['motivo']), ('acme/notas', 'cabo.toml'))
        self.assertEqual(self.registros()[-1]['repo_cabo'], 'acme/notas')

    def test_cabo_toml_no_sale_del_repo_ni_lee_tablas(self):
        (self.home / '.cabo.toml').write_text('repo = "acme/fuera"\n')
        raiz = self.repo_git('')
        self.captura('Habría que uno', cwd=str(raiz))
        (raiz / '.cabo.toml').write_text('[seccion]\nrepo = "acme/no"\n')
        self.captura('Habría que dos', cwd=str(raiz))
        self.assertEqual([r.get('repo_cabo') for r in self.registros()], [None, None])

    @unittest.skipUnless(hasattr(os, 'getuid'), 'sin usuarios POSIX')
    def test_cabo_toml_de_otro_usuario_se_ignora(self):
        raiz = self.repo_git('')
        (raiz / '.cabo.toml').write_text('repo = "acme/notas"\n')
        self.assertEqual(ideas_cola.repo_cabo(str(raiz)), 'acme/notas')
        with mock.patch('os.getuid', return_value=os.getuid() + 1):
            self.assertEqual(ideas_cola.repo_cabo(str(raiz)), '')

    def test_datos_de_servidor_van_a_runbooks(self):
        self.guion(repos={'acme/runbooks': {}})
        self.config(runbooks='acme/runbooks')
        d = self.destino('Habría que cambiar la IP 10.0.0.5')
        self.assertEqual((d['repo'], d['motivo'], d['permitido']), ('acme/runbooks', 'runbooks', True))
        self.assertEqual(d['confirmar'], ['el filtro redactó algo'])

    def test_runbooks_desde_los_ajustes_del_plugin(self):
        self.guion(repos={'mis-runbooks': {'nameWithOwner': 'yo/mis-runbooks'}})
        (self.home / '.claude').mkdir()
        (self.home / '.claude/settings.json').write_text(json.dumps(
            {'pluginConfigs': {'reglas@thealejandro': {'options': {'repo_runbooks': 'mis-runbooks'}}}}))
        self.assertEqual(self.destino('Habría que cambiar la IP 10.0.0.5')['repo'], 'yo/mis-runbooks')

    def test_datos_de_servidor_en_repo_publico_piden_confirmacion(self):
        self.guion(repos={'acme/web': {'visibility': 'PUBLIC'}})
        self.config(runbooks='acme/runbooks')
        d = self.destino('Habría que mover /srv/web', self.repo_git('acme/web'))
        self.assertEqual(d['alternativa'], 'acme/runbooks')
        for motivo in ('repo público', 'habla de datos de servidores y el repo es público', 'el filtro redactó algo'):
            self.assertIn(motivo, d['confirmar'])

    def test_produccion(self):
        self.guion(repos={'acme/web': {}})
        raiz = self.repo_git('acme/web')
        for texto in ('Habría que avisar antes de desplegar', 'Habría que revisar producción',
                      'Habría que automatizar el deploy'):
            with self.subTest(texto=texto):
                self.assertEqual(self.destino(texto, raiz)['confirmar'], ['afecta a producción'])
        self.assertEqual(self.destino('Habría que mejorar la reproducción de audio', raiz)['confirmar'], [])

    def test_sin_destino_es_borrador(self):
        d = self.destino('Habría que aprender a tocar guitarra')
        self.assertEqual((d['repo'], d['motivo'], d['permitido']), (None, 'borrador', False))
        self.assertEqual(self.llamadas(), [])

    def test_gh_caido_no_desvia_a_otro_repo(self):
        self.guion(caido=True)
        self.config(runbooks='acme/runbooks')
        d = self.destino('Habría que cambiar la IP 10.0.0.5', self.repo_git('acme/web'))
        self.assertEqual((d['repo'], d['permitido'], d['error']), ('acme/web', False, 'gh'))
        self.assertIn('visibilidad desconocida', d['confirmar'])

    def test_repo_archivado_no_permitido(self):
        self.guion(repos={'acme/web': {'isArchived': True}})
        d = self.destino('Habría que algo', self.repo_git('acme/web'))
        self.assertEqual((d['permitido'], d['archivado']), (False, True))

    def test_hash_desconocido(self):
        self.cmd('destino', 'nada', ok=False)


def issue(numero, titulo, estado='OPEN', cerrado=None):
    return {'number': numero, 'title': titulo, 'state': estado, 'closedAt': cerrado}


class SimilaresTests(DestinosBase):
    def similares(self, titulo):
        return self.cmd('similares', '--repo', 'acme/web', '--titulo', titulo)

    def test_franjas(self):
        self.guion(open=[issue(1, 'Añadir filtro por fecha al listado'), issue(2, 'Corregir el inicio de sesión')])
        igual = self.similares('Al listado añadir filtro por fecha')
        self.assertEqual((igual['franja'], igual['candidatos'][0]['numero']), ('duplicada', 1))
        self.assertEqual(self.similares('Filtrar el listado por rango de fechas')['franja'], 'dudosa')
        self.assertEqual(self.similares('Exportar facturas a PDF'), {'repo': 'acme/web', 'franja': 'nueva', 'candidatos': []})

    def test_identico_pero_cerrado_es_dudoso(self):
        self.guion(all=[issue(4, 'Exportar facturas a PDF', 'CLOSED', '2999-01-01T00:00:00Z')])
        salida = self.similares('Exportar facturas a PDF')
        self.assertEqual((salida['franja'], salida['candidatos'][0]['estado']), ('dudosa', 'CLOSED'))

    def test_numeros_distintos_no_son_duplicado(self):
        self.guion(open=[issue(1, 'Actualizar la integración de pagos a la versión 2')])
        self.assertEqual(self.similares('Actualizar la integración de pagos a la versión 3')['franja'], 'dudosa')

    def test_resultado_de_la_busqueda_siempre_es_candidato(self):
        self.guion(all=[issue(9, 'Un título que no se parece en nada')])
        salida = self.similares('Exportar facturas')
        self.assertEqual((salida['franja'], salida['candidatos'][0]['numero']), ('dudosa', 9))

    def test_cerrados_viejos_de_la_busqueda_no_cuentan(self):
        self.guion(all=[issue(9, 'Exportar facturas', 'CLOSED', '2020-01-01T00:00:00Z')])
        self.assertEqual(self.similares('Exportar facturas')['franja'], 'nueva')

    def test_pide_abiertos_y_cerrados_en_30_dias_y_usa_cache(self):
        self.similares('Exportar facturas')
        self.similares('Exportar informes')
        listados = [a for a in self.llamadas() if '--search' not in a]
        cerrados = [a for a in self.llamadas() if any(x.startswith('closed:>=') for x in a)]
        self.assertEqual((len(listados), len(cerrados)), (1, 1))
        cache = self.home / '.local/state/cabo/ideas/cache/acme__web.json'
        self.assertEqual(os.stat(cache).st_mode & 0o777, 0o600)

    def test_resolver_olvida_la_cache(self):
        self.captura('Habría que exportar facturas')
        self.similares('Exportar facturas')
        cache = self.home / '.local/state/cabo/ideas/cache/acme__web.json'
        self.assertTrue(cache.exists())
        self.cmd('resolver', self.registros()[0]['hash'], 'creada', '--issue', 'acme/web#3')
        self.assertFalse(cache.exists())

    def test_gh_caido_es_dudosa(self):
        self.guion(caido=True)
        salida = self.similares('Exportar facturas')
        self.assertEqual(salida['franja'], 'dudosa')
        self.assertIn('error', salida)

    def test_repo_no_valido(self):
        self.cmd('similares', '--repo=--web', '--titulo', 'x', ok=False)
        self.assertEqual(self.llamadas(), [])


if __name__ == '__main__':
    unittest.main()
