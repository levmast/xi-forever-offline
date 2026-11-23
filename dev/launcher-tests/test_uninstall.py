"""(lilibun, 2026-11-22) "Uninstall addons and other extensions from the launcher": a Remove on the rows of add-ons and
plugins you downloaded or added, and on Ollama and the AI model. Ashita's own add-ons and ours stay.

Run: python test_uninstall.py      (no server needed; nothing outside a temporary folder is touched)
"""
import json
import os
import shutil
import sys
import tempfile
import types

os.environ.setdefault('XIFO_TEST_PLATFORM', 'windows')
KIT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, KIT)
import launcher_core as core
import launcher_thirdparty as tp
passed = failed = 0


def check(name, ok):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
        print('FAIL:', name)


def write(path, text=''):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='') as handle:
        handle.write(text)


def raises(fn):
    try:
        fn()
    except RuntimeError as error:
        return str(error)
    return None


tmp = tempfile.mkdtemp(prefix='xifo-uninstall-')
try:
    ashita, kit = os.path.join(tmp, 'Ashita'), os.path.join(tmp, 'kit')
    write(os.path.join(ashita, 'addons', 'Cadence', 'cadence.lua'), "addon.version = '1.0'\n" + 'x' * 5000)
    write(os.path.join(ashita, 'addons', 'Cadence', 'lib', 'more.lua'), 'y' * 3000)
    write(os.path.join(ashita, 'addons', 'mything', 'mything.lua'), 'z' * 100)
    write(os.path.join(ashita, 'addons', 'servermenu', 'servermenu.lua'), 'ours')
    write(os.path.join(ashita, 'addons', 'ahgo', 'ahgo.lua'), 'stock')
    write(os.path.join(ashita, 'plugins', 'Nameplate.dll'), 'd' * 2048)
    write(os.path.join(ashita, 'plugins', 'addons.dll'), 'core')
    write(os.path.join(ashita, 'config', 'addons', 'cadence', 'settings.json'), '{"kept": true}')
    write(os.path.join(ashita, 'scripts', 'xifo.txt'), '# Managed\r\n/load addons\r\n/load nameplate\r\n/addon load cadence\r\n/addon load servermenu\r\n# /addon load cadence\r\n')
    write(os.path.join(ashita, 'scripts', 'xifo-2.txt'), '/addon load Cadence\r\n/addon load ahgo\r\n')
    write(os.path.join(ashita, 'scripts', 'notes.md'), '/addon load cadence\n')
    manifest = {'items': [
        {'id': 'cadence', 'name': 'Cadence', 'into': 'ashita', 'check': 'addons/cadence/cadence.lua', 'source': {'type': 'github_release'}},
        {'id': 'nameplate', 'name': 'Nameplate', 'into': 'ashita', 'check': 'plugins/Nameplate.dll', 'source': {'type': 'kit'}},
        {'id': 'eradats', 'name': 'Era-DATs', 'into': 'kit', 'check': 'Era-DATs/ROM', 'source': {'type': 'github_archive'}},
        {'id': 'ollama', 'name': 'Ollama', 'into': 'kit', 'source': {'type': 'installer'}},
    ]}
    write(os.path.join(kit, 'thirdparty.json'), json.dumps(manifest))
    write(os.path.join(kit, 'thirdparty-installed.json'), json.dumps({'cadence': {'version': '1.0'}, 'nameplate': {'version': '2'},
                                                                      'eradats': {'version': 'main'}, 'ollama': {'version': 'x'}}))
    core.remember_added(kit, ['mything'])

    # who may be removed
    check('a download may be removed', core.can_remove('addon', 'cadence', 'download'))
    check('something you added may be removed', core.can_remove('addon', 'mything', 'added by you'))
    check("Ashita's own stays", not core.can_remove('addon', 'ahgo', 'Ashita') and not core.can_remove('plugin', 'addons', 'Ashita'))
    check('ours stays, whatever the row says', not core.can_remove('addon', 'servermenu', 'XI: Forever Offline')
          and not core.can_remove('addon', 'ServerMenu', 'download'))
    check('the row is found whatever its capitals', core.item_path(ashita, 'addon', 'cadence') == os.path.join(ashita, 'addons', 'Cadence')
          and core.item_path(ashita, 'plugin', 'nameplate') == os.path.join(ashita, 'plugins', 'Nameplate.dll'))
    for bad in ('..', '.', '', 'a/b', 'a\\b', 'c:x', '../scripts'):
        check('no path outside the folder for %r' % bad, core.item_path(ashita, 'addon', bad) is None)
    check('its size is everything in its folder', core.path_size(core.item_path(ashita, 'addon', 'cadence')) == 5000 + len("addon.version = '1.0'\n") + 3000)
    check('sizes read well', core.size_text(8 * (1 << 30)) == '8.0 GB' and core.size_text(3 * (1 << 20) + (1 << 19)) == '3.5 MB' and core.size_text(12) == '12 bytes')
    check('refused for ours', 'stays' in (raises(lambda: core.remove_item(ashita, kit, 'addon', 'servermenu', 'XI: Forever Offline')) or ''))
    check("refused for Ashita's own", 'stays' in (raises(lambda: core.remove_item(ashita, kit, 'addon', 'ahgo', 'Ashita')) or ''))
    check('...and both are still there', os.path.isdir(os.path.join(ashita, 'addons', 'servermenu')) and os.path.isdir(os.path.join(ashita, 'addons', 'ahgo')))

    # a downloaded addon
    freed = core.remove_item(ashita, kit, 'addon', 'cadence', 'download')
    check('the addon folder is gone and its size is reported', not os.path.exists(os.path.join(ashita, 'addons', 'Cadence')) and freed > 8000)
    check('its settings are kept', os.path.isfile(os.path.join(ashita, 'config', 'addons', 'cadence', 'settings.json')))
    first = open(os.path.join(ashita, 'scripts', 'xifo.txt'), encoding='utf-8').read()
    check('its load line is out of the script, nothing else', '/addon load cadence\n' not in first.replace('# /addon load cadence', '')
          and '/load addons' in first and '/load nameplate' in first and '/addon load servermenu' in first and '# /addon load cadence' in first)
    second = open(os.path.join(ashita, 'scripts', 'xifo-2.txt'), encoding='utf-8').read()
    check("...and out of the second window's script", 'Cadence' not in second and '/addon load ahgo' in second)
    check('a file that is not a script is left alone', open(os.path.join(ashita, 'scripts', 'notes.md'), encoding='utf-8').read() == '/addon load cadence\n')
    state = tp.load_state(kit)
    check('the download shows as not installed again', 'cadence' not in state and 'nameplate' in state and 'eradats' in state)
    check('the list no longer has it', 'Cadence' not in core.list_addons(ashita) and 'mything' in core.list_addons(ashita))
    check('removing it twice says it is not there', 'not found' in (raises(lambda: core.remove_item(ashita, kit, 'addon', 'cadence', 'download')) or ''))

    # a plugin, and one the player added
    core.remove_item(ashita, kit, 'plugin', 'nameplate', 'download')
    check('the plugin is gone, the others stay', not os.path.exists(os.path.join(ashita, 'plugins', 'Nameplate.dll')) and os.path.isfile(os.path.join(ashita, 'plugins', 'addons.dll')))
    check('its /load line is gone, /load addons stays', '/load nameplate' not in open(os.path.join(ashita, 'scripts', 'xifo.txt'), encoding='utf-8').read()
          and '/load addons' in open(os.path.join(ashita, 'scripts', 'xifo.txt'), encoding='utf-8').read())
    check('...and its download record', 'nameplate' not in tp.load_state(kit))
    core.remove_item(ashita, kit, 'addon', 'mything', 'added by you')
    check('one you added: gone, and forgotten from the added list', not os.path.exists(os.path.join(ashita, 'addons', 'mything')) and core.added_items(kit) == set())

    # which row a download is
    check('place: addon, plugin, and nothing for a tool', tp.place(manifest['items'][0]) == ('addon', 'cadence')
          and tp.place(manifest['items'][1]) == ('plugin', 'nameplate') and tp.place(manifest['items'][2]) is None and tp.place(manifest['items'][3]) is None)

    # the AI model: ollama rm, Ollama started first when it is not running
    calls, started = [], []
    real_find = tp.find_ollama
    tp.find_ollama = lambda kit=None: os.path.join(tmp, 'Ollama', 'ollama.exe')

    def runner(codes):
        def run(args, **kw):
            calls.append(args[1:])
            return types.SimpleNamespace(returncode=codes.get(args[1], 0), stdout='', stderr='Error: model not found' if codes.get(args[1]) else '')
        return run
    check('ollama rm <model> is what runs', tp.remove_model('gemma4:12b', run=runner({}), start=lambda: started.append(1), wait=0) == 'gemma4:12b'
          and calls == [['list'], ['rm', 'gemma4:12b']] and started == [])
    calls.clear()
    tp.remove_model('gemma4:12b', run=runner({'list': 1}), start=lambda: started.append(1), wait=0)
    check('Ollama is started first when it is not running', started == [1] and calls[-1] == ['rm', 'gemma4:12b'])
    said = raises(lambda: tp.remove_model('nope', run=runner({'rm': 1}), start=lambda: None, wait=0))
    check("a refusal comes back with Ollama's own words", said is not None and 'model not found' in said)
    tp.find_ollama = lambda kit=None: None
    check('no Ollama: says so', 'not installed' in (raises(lambda: tp.remove_model('x', run=runner({}), wait=0)) or ''))

    # Ollama itself (Windows: its own uninstaller; the models only when asked)
    write(os.path.join(tmp, 'Ollama', 'ollama.exe'), 'exe')
    write(os.path.join(tmp, 'Ollama', 'unins000.exe'), 'uninstaller')
    models = os.path.join(tmp, 'home', '.ollama', 'models')
    write(os.path.join(models, 'blobs', 'sha256-abc'), 'm' * 4096)
    os.environ['OLLAMA_MODELS'] = models
    tp.find_ollama = lambda kit=None: os.path.join(tmp, 'Ollama', 'ollama.exe')
    ran, lines = [], []
    done = tp.remove_ollama(kit, models=False, run=lambda args: ran.append(args), log=lines.append)
    check("Windows: Ollama's own uninstaller is started", done == ['uninstaller'] and ran == [[os.path.join(tmp, 'Ollama', 'unins000.exe')]])
    check('the models are kept unless asked', os.path.isfile(os.path.join(models, 'blobs', 'sha256-abc')))
    check('the launcher forgets its Ollama record', 'ollama' not in tp.load_state(kit) and 'eradats' in tp.load_state(kit))
    done = tp.remove_ollama(kit, models=True, run=lambda args: ran.append(args), log=lines.append)
    check('asked: the models folder is deleted too', 'models' in done and not os.path.exists(models))
    os.environ['OLLAMA_MODELS'] = os.path.join(tmp, 'home')            # a setting that points at something else
    write(os.path.join(tmp, 'home', 'keep.txt'), 'mine')
    tp.remove_ollama(kit, models=True, run=lambda args: None, log=lines.append)
    check('a models setting that is not a "models" folder is never deleted', os.path.isfile(os.path.join(tmp, 'home', 'keep.txt')))
    os.remove(os.path.join(tmp, 'Ollama', 'unins000.exe'))
    lines.clear()
    done = tp.remove_ollama(kit, models=False, run=lambda args: ran.append(args), log=lines.append)
    check('no uninstaller: points to Windows Settings', done == [] and any('Installed apps' in line for line in lines))
    tp.find_ollama = real_find
    os.environ.pop('OLLAMA_MODELS', None)

    gui = open(os.path.join(KIT, 'launcher_gui.pyw'), encoding='utf-8').read()
    check('the list rows have a Remove for what may be removed', 'core.can_remove(self.kind, n, origin)' in gui and 'def remove(self, name, origin):' in gui)
    check('Get more: Remove for the AI model and for Ollama', 'def remove_ai_model(self, item):' in gui and 'def remove_ollama(self, item):' in gui)
    check('every Remove asks first', gui.count('messagebox.askyesno("Remove') >= 3)
finally:
    shutil.rmtree(tmp, ignore_errors=True)
print(f'{passed} passed, {failed} failed')
sys.exit(1 if failed else 0)
