"""Search and explicitly select synthetic sample types, including nested field paths."""
import json
from pathlib import Path
import subprocess
import sys
import time
import urllib.request
from playwright.sync_api import sync_playwright
from browser_helpers import choose_output_type

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
from amw_tool.model import validate
OUT = ROOT/'out/browser-type-search'
OUT.mkdir(parents=True, exist_ok=True)
server = subprocess.Popen([sys.executable, str(ROOT/'amw'), 'gui', '--port', '18770'], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
try:
    for _ in range(100):
        try:
            urllib.request.urlopen('http://127.0.0.1:18770', timeout=1)
            break
        except Exception:
            if server.poll() is not None:
                raise RuntimeError(server.stdout.read())
            time.sleep(.1)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=['--no-sandbox'])
        page = browser.new_page(viewport={'width':1440,'height':1000})
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.goto('http://127.0.0.1:18770')
        page.wait_for_function("document.getElementById('status').textContent.includes('就绪')")
        page.once('dialog', lambda d: d.accept('sample_type_search'));page.locator('#newProject').click()
        page.locator('#file').set_input_files(str(ROOT/'tests/fixtures/sample-types.cmtypes.json'))
        page.locator('#apply').click();page.locator('#dialog').wait_for(state='hidden')
        page.once('dialog', lambda d: d.accept('sample_app'));page.locator('#addApp').click()
        page.get_by_text('增加输出', exact=True).click()
        before = page.evaluate('JSON.stringify(model)')
        page.locator('#outputMessage').fill('sample_message')
        assert page.locator('#apply').is_disabled()
        assert page.locator('#outputTypeResults button').count() == 22
        assert page.locator('#outputTypeResults [aria-pressed=true]').count() == 0
        search = page.locator('#outputTypeSearch')
        search.fill('MESSAGE')
        assert page.locator('#outputTypeResults button').first.get_attribute('data-type') == 'sample.Message@1.0.0'
        search.fill('SAMPLE.MESSAGE')
        assert page.locator('#outputTypeResults button').count() == 1
        assert page.locator('#apply').is_disabled()  # Even a unique result is not implicitly selected.
        search.press('ArrowDown');page.keyboard.press('Enter')
        assert page.locator('#apply').is_enabled()
        assert 'sample.Message @1.0.0' in page.locator('#outputTypeSelection').inner_text()
        page.locator('#outputTypePreview > summary').click()
        page.locator('#outputTypePreview').get_by_text('batch · sample.Batch @1.0.0', exact=True).click()
        page.locator('#outputTypePreview').get_by_text('items · sample.Item @1.0.0 [4]', exact=True).click()
        page.locator('#outputTypePreview').get_by_text('sample_id · uint32', exact=True).wait_for(state='visible')
        search.fill('sample_id')
        assert page.locator('#apply').is_disabled()  # A new query invalidates the old selection.
        root_result = page.get_by_role('button', name='sample.Message @1.0.0', exact=True)
        assert 'batch.items[].sample_id' in root_result.inner_text()
        assert page.get_by_role('button', name='sample.Item @1.0.0', exact=True).count() == 1
        root_result.click()
        page.screenshot(path=str(OUT/'nested-field-search.png'), full_page=True)
        page.set_viewport_size({'width':680,'height':900})
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
        page.set_viewport_size({'width':1440,'height':1000})
        search.fill('通用采集消息')
        assert page.locator('#outputTypeResults button').count() == 1
        search.fill('not_a_real_type')
        assert page.locator('#outputTypeResults button').count() == 0
        assert '没有匹配' in page.locator('#outputTypeResults').inner_text()
        assert page.locator('#apply').is_disabled()
        assert page.evaluate('JSON.stringify(model)') == before
        choose_output_type(page, 'sample.Message@1.0.0')
        page.get_by_text('清除类型选择', exact=True).click()
        assert search.input_value() == ''
        assert page.locator('#apply').is_disabled()
        choose_output_type(page, 'sample.Message@1.0.0')
        page.locator('#apply').click();page.locator('#dialog').wait_for(state='hidden')
        state = page.evaluate('model');validate(state)
        event = state['project']['service_interfaces'][0]['events'][0]
        assert event['type'] == {'ref':'sample.Message','version':'1.0.0'}
        after = page.evaluate('JSON.stringify(model)')
        page.locator('#undo').click();assert page.evaluate('JSON.stringify(model)') == before
        page.locator('#redo').click();assert page.evaluate('JSON.stringify(model)') == after
        page.get_by_text('增加输出', exact=True).click()
        assert page.locator('#apply').is_disabled()  # No remembered first/last selection.
        page.locator('#cancel').click()
        page.locator('#save').click()
        page.wait_for_function("document.getElementById('status').textContent === '草稿已保存'")
        saved=json.loads((ROOT/'out/editor/sample_type_search/types.cmtypes.json').read_text())
        assert saved == state['types']

        # Ambiguous short names/versions, sequence paths, enum exclusion and
        # keyboard movement are exercised with a small validated library.
        fixture = page.evaluate('model');fixture['project']['project_id']='picker_names'
        fixture['types']['types'].extend([
            {'id':'left.Frame','version':'1.0.0','kind':'struct','fields':[{'id':1,'name':'unique_marker','type':'uint32'},{'id':2,'name':'matrix','type':{'kind':'array','length':2,'element':{'kind':'array','length':3,'element':'float32'}}}]},
            {'id':'left.Frame','version':'2.0.0','kind':'struct','fields':[{'id':1,'name':'next_marker','type':'uint32'}]},
            {'id':'right.Frame','version':'1.0.0','kind':'struct','fields':[{'id':1,'name':'items','type':{'kind':'sequence','max_length':8,'element':{'ref':'left.Frame','version':'1.0.0'}}}]},
            {'id':'Choice','version':'1.0.0','kind':'enum','enumerators':['First','Second']}
        ])
        validate(fixture)
        page.locator('#projectFile').set_input_files({'name':'picker.amw.json','mimeType':'application/json','buffer':json.dumps(fixture).encode()})
        page.wait_for_function("model.project.project_id==='picker_names'")
        page.get_by_text('增加输出', exact=True).click()
        search.fill('Frame')
        assert page.get_by_role('button', name='left.Frame @1.0.0', exact=True).count()==1
        assert page.get_by_role('button', name='left.Frame @2.0.0', exact=True).count()==1
        assert page.get_by_role('button', name='right.Frame @1.0.0', exact=True).count()==1
        search.fill('unique_marker')
        assert 'items[].unique_marker' in page.get_by_role('button',name='right.Frame @1.0.0',exact=True).inner_text()
        choose_output_type(page, 'left.Frame@1.0.0')
        page.locator('#outputTypePreview > summary').click()
        assert page.locator('#outputTypePreview').get_by_text('matrix · float32 [2][3]',exact=True).is_visible()
        search.fill('Choice');assert page.locator('#outputTypeResults button').count()==0
        search.fill('left.Frame');search.press('ArrowDown');page.keyboard.press('End');page.keyboard.press('Home');page.keyboard.press('ArrowDown');page.keyboard.press('Enter')
        assert 'left.Frame @2.0.0' in page.locator('#outputTypeSelection').inner_text()
        page.locator('#cancel').click()
        assert page.evaluate('model')==fixture
        # Invalid imported drafts remain inspectable; cycles must not hang search.
        fixture['types']['types'].append({'id':'Cycle','version':'1.0.0','kind':'struct','fields':[{'id':1,'name':'self_ref','type':{'ref':'Cycle','version':'1.0.0'}}]})
        page.locator('#advancedTools > summary').click();page.locator('#edit').click();page.locator('#dialogBody textarea').fill(json.dumps(fixture));page.locator('#apply').click();page.locator('#dialog').wait_for(state='hidden')
        page.get_by_text('增加输出', exact=True).click();search.fill('self_ref')
        assert page.get_by_role('button',name='Cycle @1.0.0',exact=True).count()==1
        page.locator('#cancel').click()
        assert not errors, errors
        browser.close()
        print('PASS: synthetic sample import, no defaults, unique-match explicit confirmation, nested/sequence field paths, case-insensitive/name/description search, preview, keyboard, no-result/clear/reopen, version disambiguation, enum exclusion, cyclic draft guard, undo/redo and save')
finally:
    server.terminate()
    try:server.wait(timeout=5)
    except subprocess.TimeoutExpired:server.kill();server.wait()
