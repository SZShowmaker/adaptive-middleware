"""Run in a disposable repository copy: structured QoS editing and delivery."""
import json
from pathlib import Path
import subprocess
import sys
import time
import urllib.request
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
server=subprocess.Popen([sys.executable,str(ROOT/'amw'),'gui','--port','18768'],cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
try:
    for _ in range(100):
        try:urllib.request.urlopen('http://127.0.0.1:18768',timeout=1);break
        except Exception:
            if server.poll() is not None:raise RuntimeError(server.stdout.read())
            time.sleep(.1)
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,args=['--no-sandbox'])
        page=browser.new_page(viewport={'width':1440,'height':1000});errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto('http://127.0.0.1:18768');page.wait_for_function("document.getElementById('status').textContent.includes('就绪')")
        snapshot=page.evaluate('JSON.stringify(model)')
        def open_qos():page.locator('#deployment').click();page.locator('#qosView').wait_for()
        def apply():page.locator('#apply').click();page.locator('#dialog').wait_for(state='hidden')
        def field(key):return page.locator('.qos-field[data-qos-key="'+key+'"]')
        open_qos()
        assert field('history.depth').locator('input[type=number]').input_value()=='16'
        assert field('reliability.kind').locator('select').input_value()=='best_effort'
        apply();assert page.evaluate('JSON.stringify(model)')==snapshot
        # Invalid input is rejected without changing the project; retry in same dialog.
        open_qos();field('history.depth').locator('input[type=number]').fill('17')
        messages=[];page.once('dialog',lambda d:(messages.append(d.message),d.accept()))
        page.locator('#apply').click();page.wait_for_function("document.getElementById('qosError').textContent.includes('history.depth')")
        assert messages and page.evaluate('JSON.stringify(model)')==snapshot
        field('history.depth').locator('input[type=number]').fill('8')
        field('reliability.kind').locator('select').select_option('reliable')
        field('publish_mode.kind').locator('select').select_option('asynchronous')
        field('properties').get_by_role('button',name='properties 增加一项',exact=True).click()
        field('properties').get_by_label('properties[0].name',exact=True).fill('application.team')
        field('properties').get_by_label('properties[0].value',exact=True).fill('界面策略')
        field('properties').get_by_label('properties[0].propagate',exact=True).check()
        field('deadline.period').get_by_label('deadline.period 模式',exact=True).select_option('value')
        field('deadline.period').get_by_label('deadline.period.seconds',exact=True).fill('1')
        # Enum-dependent controls become disabled without losing other values.
        field('history.kind').locator('select').select_option('keep_all')
        assert field('history.depth').locator('input[type=number]').is_disabled()
        field('history.kind').locator('select').select_option('keep_last')
        apply()
        changed=page.evaluate('JSON.stringify(model)');assert changed!=snapshot
        page.locator('#undo').click();assert page.evaluate('JSON.stringify(model)')==snapshot
        page.locator('#redo').click();assert page.evaluate('JSON.stringify(model)')==changed
        # New policy is usable without filling its QoS fields.
        open_qos();page.get_by_label('新策略 ID',exact=True).fill('fresh')
        page.get_by_role('button',name='新建默认策略',exact=True).click();apply()
        assert page.evaluate('JSON.stringify(model.deployment.policies.fresh)')=='{}'
        # Configure an endpoint with a different reusable policy using selectors.
        open_qos();page.locator('#qosView').select_option('instances')
        page.locator('#qosInstance').select_option('camera_front')
        page.locator('#qosEndpoint').select_option('perception.health')
        page.get_by_label('端点策略覆盖',exact=True).select_option('fresh');apply()
        page.locator('#validate').click();page.wait_for_function("document.getElementById('status').textContent==='校验通过'")
        # Project publisher/subscriber settings are independently editable.
        open_qos();page.locator('#qosView').select_option('global')
        for scope in ('publisher','subscriber'):
            page.locator('#qosScope').select_option(scope)
            field('partition.names').get_by_role('button',name='partition.names 增加一项',exact=True).click()
            field('partition.names').get_by_label('partition.names[0]',exact=True).fill('ui_qos')
        apply()
        # Client-side effective display and server resolution must agree.
        page.locator('#validate').click();page.wait_for_function("document.getElementById('status').textContent==='校验通过'")
        page.locator('#resultDetails > summary').click()
        validation=json.loads(page.locator('#result').inner_text())
        client=page.evaluate("qosCataloguePromise.then(c=>qosEffective(c,'writer',model.deployment.policies.state))")
        assert client==validation['routes']['camera_front'][0]['qos']
        page.locator('#generate').click();page.wait_for_function("document.getElementById('status').textContent.startsWith('生成完成')",timeout=180000)
        delivery=ROOT/'out/delivery/demo/src-gen'
        effective=json.loads((delivery/'metadata/qos.effective.json').read_text())
        frame=effective['instances']['camera_front']['endpoints']['perception.frame']['effective']
        assert frame['history.depth']==8 and frame['publish_mode.kind']=='asynchronous'
        assert frame['properties'][0]['value']=='界面策略'
        assert effective['instances']['camera_front']['endpoints']['perception.health']['effective']['history.depth']==16
        page.locator('#save').click();page.wait_for_function("document.getElementById('status').textContent==='草稿已保存'")
        open_qos();page.get_by_label('搜索 QoS 参数',exact=True).fill('history')
        evidence=ROOT/'out/browser-qos';evidence.mkdir(parents=True,exist_ok=True)
        page.screenshot(path=str(evidence/'qos-editor.png'),full_page=True)
        page.locator('#cancel').click()
        assert not errors,errors
        browser.close()
        print('PASS: defaults, no-op apply, validation retry, enums/numbers/durations/lists, dependencies, undo/redo, policy assignment, group QoS, effective parity, generation and save')
finally:
    server.terminate()
    try:server.wait(timeout=5)
    except subprocess.TimeoutExpired:server.kill();server.wait()
