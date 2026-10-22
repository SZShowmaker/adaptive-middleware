from browser_helpers import choose_output_type
"""Default output grouping and subscription edits, including deployment/QoS integrity."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import time
import urllib.request
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from amw_tool.model import load_project, validate

OUT = ROOT / 'out/browser-groups'
OUT.mkdir(parents=True, exist_ok=True)
server = subprocess.Popen([sys.executable, str(ROOT / 'amw'), 'gui', '--port', '18769'], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
try:
    for _ in range(100):
        try:
            urllib.request.urlopen('http://127.0.0.1:18769', timeout=1)
            break
        except Exception:
            if server.poll() is not None:
                raise RuntimeError(server.stdout.read())
            time.sleep(.1)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=['--no-sandbox'])
        page = browser.new_page(viewport={'width': 1440, 'height': 1000})
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto('http://127.0.0.1:18769')
        page.wait_for_function("document.getElementById('status').textContent.includes('就绪')")

        def state():
            return page.evaluate('model')

        def card(name):
            page.locator('#appsTab').click()
            return page.locator('.app').filter(has=page.get_by_role('heading', name=name, exact=True))

        def apply():
            page.locator('#apply').click()
            page.locator('#dialog').wait_for(state='hidden')

        def rejected(message):
            before = state()
            history = page.evaluate('[history.length,future.length,revision]')
            messages = []
            page.once('dialog', lambda d: (messages.append(d.message), d.accept()))
            page.locator('#apply').click()
            assert messages and message in messages[0], messages
            assert state() == before
            assert page.evaluate('[history.length,future.length,revision]') == history
            assert page.locator('#dialog').is_visible()

        def open_model(model):
            validate(model)
            page.locator('#projectFile').set_input_files({'name': 'groups.amw.json', 'mimeType': 'application/json', 'buffer': json.dumps(model).encode()})
            page.wait_for_function('(name) => model.project.project_id === name', arg=model['project']['project_id'])

        fixture = copy.deepcopy(load_project(ROOT / 'examples/demo/project.cm.json')['bundle'])
        fixture['project'].update(project_id='groups', connections=[], apps=[{'id': name, 'provides': [], 'requires': []} for name in ('sensor', 'viewer')])
        fixture['deployment']['instances'] = [{'id': name+'_instance', 'app': name, 'provides': {}, 'requires': {}, 'policy': 'state'} for name in ('sensor', 'viewer')]
        open_model(fixture)
        for name, type_ in [('frame', 'demo.Frame'), ('health', 'demo.Health')]:
            card('sensor').get_by_text('增加输出', exact=True).click()
            assert not page.locator('#outputGroup').is_visible()
            assert page.locator('#outputGroup').input_value() == (':new' if name == 'frame' else 'output')
            page.locator('#outputMessage').fill(name)
            choose_output_type(page, type_+'@1.0.0')
            assert '完整类型名：'+type_ in page.locator('#dialogBody').inner_text()
            apply()
        model = state()
        assert [p['id'] for p in model['project']['apps'][0]['provides']] == ['output']
        assert len(next(s for s in model['project']['service_interfaces'] if s['id']=='groups.sensor.output')['events']) == 2
        validate(model)

        # Automatic input naming, multi-message selection, and a second source
        # connection with a collision-free suggested local name.
        card('viewer').get_by_text('选择输入', exact=True).click()
        assert not page.locator('#inputGroupName').is_visible()
        assert page.locator('#inputGroupName').input_value() == 'sensor_output'
        apply()
        card('viewer').get_by_text('选择输入', exact=True).click()
        assert page.locator('#inputGroupName').input_value() == 'sensor_output_2'
        page.locator('#cancel').click()
        validate(state())

        # Advanced grouping must be explicit when several groups exist.
        card('sensor').get_by_text('增加输出', exact=True).click()
        page.locator('#outputMessage').fill('diagnostic')
        choose_output_type(page, 'demo.Health@1.0.0')
        page.get_by_text('高级：分组设置', exact=True).click()
        page.locator('#outputGroup').select_option(':new')
        page.locator('#outputGroupName').fill('diagnostics')
        apply()
        card('sensor').get_by_text('增加输出', exact=True).click()
        assert page.locator('#outputGroup').is_visible()
        assert page.locator('#outputGroup').input_value() == ''
        page.locator('#outputMessage').fill('detail')
        choose_output_type(page, 'demo.Health@1.0.0')
        rejected('选择数据类型和输出分组')
        page.locator('#outputGroup').select_option('diagnostics')
        apply()
        validate(state())

        card('viewer').get_by_text('选择输入', exact=True).click()
        page.get_by_text('高级：分组设置', exact=True).click()
        page.locator('#inputSource').select_option('sensor|diagnostics')
        assert page.locator('#inputGroupName').input_value() == 'sensor_diagnostics'
        page.locator('#inputGroupName').fill('custom_input')
        page.locator('#inputSource').select_option('sensor|output')
        assert page.locator('#inputGroupName').input_value() == 'custom_input'
        page.locator('#cancel').click()

        # Imported multi-instance bindings must survive editing. Endpoint policy
        # overrides follow renamed inputs and disappear for deselected events.
        fixture = state()
        fixture['project']['project_id'] = 'bindings'
        dep = fixture['deployment']
        sensor2 = copy.deepcopy(dep['instances'][0]);sensor2['id'] = 'sensor_second'
        sensor2['provides'] = {key: 'second_'+key for key in sensor2['provides']}
        viewer2 = copy.deepcopy(dep['instances'][1]);viewer2['id'] = 'viewer_second'
        viewer2['requires']['sensor_output']['instance'] = sensor2['id']
        dep['instances'].extend([sensor2, viewer2])
        for i in dep['instances']:
            if i['app'] == 'viewer':
                i['event_policies'] = {'sensor_output.frame': 'state', 'sensor_output.health': 'state'}
        open_model(fixture)
        before = state()
        card('viewer').get_by_role('button', name='编辑订阅 sensor_output', exact=True).click()
        assert page.locator('#inputSource').is_disabled()
        for checkbox in page.locator('#dialogBody input[type=checkbox]').all():
            checkbox.uncheck()
        rejected('至少选择一条消息')
        page.locator('#dialogBody input[type=checkbox]').first.check()
        page.get_by_text('高级：分组设置', exact=True).click()
        page.locator('#inputGroupName').fill('camera_data')
        apply()
        after = state()
        for i in after['deployment']['instances']:
            if i['app'] == 'viewer':
                old = next(x for x in before['deployment']['instances'] if x['id'] == i['id'])
                assert i['requires']['camera_data'] == old['requires']['sensor_output']
                assert i['event_policies'] == {'camera_data.frame': 'state'}
        assert after['project']['connections'][0]['to']['required'] == 'camera_data'
        validate(after)
        page.locator('#undo').click();assert state() == before
        page.locator('#redo').click();assert state() == after
        card('viewer').get_by_role('button', name='编辑订阅 camera_data', exact=True).click()
        page.locator('#dialogBody input[type=checkbox]').nth(1).check();apply()
        validate(state())
        assert len(state()['project']['apps'][1]['requires']) == 1
        assert len(state()['project']['apps'][1]['requires'][0]['events']) == 2
        page.locator('#flowTab').click()
        page.locator('.edge-badge').first.click()
        page.locator('#removeConnection').click()
        validate(state())
        assert all('event_policies' not in i for i in state()['deployment']['instances'] if i['app'] == 'viewer')
        page.locator('#undo').click()

        # Output/input name collisions are rejected in the form; retry works.
        card('viewer').get_by_text('增加输出', exact=True).click()
        page.locator('#outputMessage').fill('local_status')
        choose_output_type(page, 'demo.Health@1.0.0')
        page.get_by_text('高级：分组设置', exact=True).click()
        page.locator('#outputGroupName').fill('camera_data')
        rejected('分组名已被本 App 的输入使用')
        page.locator('#outputGroupName').fill('status_output');apply()
        card('viewer').get_by_role('button', name='编辑订阅 camera_data', exact=True).click()
        page.get_by_text('高级：分组设置', exact=True).click()
        page.locator('#inputGroupName').fill('status_output')
        rejected('分组名已存在')
        page.locator('#inputGroupName').fill('camera_data');apply()
        validate(state())

        # Short type labels stay unambiguous when namespaces collide.
        fixture = state();fixture['project']['project_id'] = 'type_names'
        duplicate = copy.deepcopy(next(t for t in fixture['types']['types'] if t['id'] == 'demo.Frame'))
        duplicate['id'] = 'camera.Frame';fixture['types']['types'].append(duplicate)
        open_model(fixture)
        card('viewer').get_by_text('增加输出', exact=True).click()
        assert 'demo.Frame' in page.locator('#outputTypeResults button[data-type="demo.Frame@1.0.0"]').inner_text()
        assert 'camera.Frame' in page.locator('#outputTypeResults button[data-type="camera.Frame@1.0.0"]').inner_text()
        page.locator('#cancel').click()
        page.locator('#validate').click()
        page.wait_for_function("document.getElementById('status').textContent === '校验通过'")
        page.locator('#save').click()
        page.wait_for_function("document.getElementById('status').textContent === '草稿已保存'")
        saved = load_project(ROOT/'out/editor/type_names/project.cm.json')['bundle']
        assert saved == state()
        page.screenshot(path=str(OUT/'groups.png'), full_page=True)
        card('sensor').get_by_text('增加输出', exact=True).click()
        page.screenshot(path=str(OUT/'output-form.png'), full_page=True)
        page.set_viewport_size({'width': 680, 'height': 900})
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
        assert not errors, errors
        browser.close()
        print('PASS: default/multiple groups, auto input names, subscription edit, rename, multi-instance bindings, QoS cleanup, retry/undo/redo, type-name collisions, save and backend validation')
finally:
    server.terminate()
    try:
        server.wait(timeout=5)
    except subprocess.TimeoutExpired:
        server.kill();server.wait()
