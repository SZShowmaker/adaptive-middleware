from browser_helpers import choose_output_type
import os,subprocess,time,json,urllib.request,sys
from pathlib import Path
from playwright.sync_api import sync_playwright
root=Path(__file__).resolve().parents[1];evidence=root/'out/browser-test';evidence.mkdir(parents=True,exist_ok=True)
server=subprocess.Popen([sys.executable,str(root/'amw'),'gui','--port','18765'],cwd=root,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
try:
    for _ in range(80):
        try:urllib.request.urlopen('http://127.0.0.1:18765',timeout=1);break
        except Exception:
            if server.poll() is not None:raise RuntimeError(server.stdout.read())
            time.sleep(.1)
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,args=['--no-sandbox'])
        page=browser.new_page(viewport={'width':1440,'height':1000});errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto('http://127.0.0.1:18765');page.wait_for_function("document.getElementById('status').textContent.includes('就绪')")
        assert page.locator('.app').count()==2
        page.locator('#search').fill('distance');assert page.locator('#types .library-type').count()==2
        page.locator('#search').fill('')
        page.locator('#validate').click();page.wait_for_function("document.getElementById('status').textContent==='校验通过'")
        page.locator('#file').set_input_files(str(root/'examples/demo/types/messages.cmtypes.json'))
        page.locator('#apply').click();assert page.locator('#types .library-type').count()==3
        # Add a second event to an existing app through the structured form.
        page.locator('.app').first.get_by_text('增加输出',exact=True).click()
        page.locator('#outputMessage').fill('extra_health')
        choose_output_type(page, 'demo.Health@1.0.0');page.locator('#apply').click()
        assert page.locator('.port').filter(has_text='extra_health').count()==1
        page.locator('#undo').click();assert page.locator('.port').filter(has_text='extra_health').count()==0
        page.locator('#generate').click();page.wait_for_function("document.getElementById('status').textContent.startsWith('生成完成')",timeout=60000)
        page.locator('#save').click();page.wait_for_function("document.getElementById('status').textContent==='草稿已保存'")
        page.screenshot(path=str(evidence/'editor.png'),full_page=True)
        # Build a fresh independent project through the UI, without editing JSON.
        page.once('dialog', lambda dialog: dialog.accept('fresh_project'))
        page.locator('#newProject').click()
        assert page.locator('.app').count()==0
        assert page.locator('#projectName').inner_text() == 'fresh_project'
        assert page.locator('#projectState').inner_text() == '未保存更改'
        assert page.title() == '* fresh_project · Adaptive Middleware'
        page.locator('#file').set_input_files(str(root/'examples/demo/types/messages.cmtypes.json'))
        page.locator('#apply').click()
        for app_id in ('sensor', 'display'):
            page.once('dialog', lambda dialog, value=app_id: dialog.accept(value))
            page.locator('#addApp').click()
        page.locator('.app').first.get_by_text('增加输出',exact=True).click()
        page.get_by_text('高级：分组设置', exact=True).click()
        page.locator('#outputGroupName').fill('perception')
        page.locator('#outputMessage').fill('frame')
        choose_output_type(page, 'demo.Frame@1.0.0');page.locator('#apply').click()
        page.locator('.app').nth(1).get_by_text('选择输入',exact=True).click()
        page.get_by_text('高级：分组设置', exact=True).click()
        page.locator('#inputGroupName').fill('incoming')
        page.locator('#apply').click()
        assert page.locator('.input').count()==1
        # Retry in the SAME modal after rollback must update the live App.
        def card(app_id):
            page.locator('#appsTab').click()
            return page.locator('.app').filter(has=page.get_by_role('heading', name=app_id, exact=True))

        def snapshot():
            return page.evaluate('JSON.stringify(model)')

        def history_state():
            return page.evaluate('({history: history.length, future: future.length, revision})')

        def rejected(message):
            messages = []
            def accept(dialog):
                messages.append(dialog.message)
                dialog.accept()
            page.once('dialog', accept)
            page.locator('#apply').click()
            assert messages == [message], messages
            assert page.locator('#dialog').is_visible()

        page.once('dialog', lambda dialog: dialog.accept('sensor2'))
        page.locator('#addApp').click()
        card('sensor2').get_by_text('增加输出', exact=True).click()
        page.get_by_text('高级：分组设置', exact=True).click()
        page.locator('#outputGroupName').fill('perception')
        page.locator('#outputMessage').fill('frame')
        choose_output_type(page, 'demo.Frame@1.0.0')
        page.locator('#apply').click()
        before_input = snapshot()
        before_history = history_state()
        card('display').get_by_text('选择输入', exact=True).click()
        page.locator('#dialogBody select').select_option('sensor2|perception')
        page.get_by_text('高级：分组设置', exact=True).click()
        page.locator('#inputGroupName').fill('incoming')
        for _ in range(2):
            rejected('分组名已存在，请换一个名称；修改已有输入请使用“编辑订阅”')
            assert snapshot() == before_input
            assert history_state() == before_history
        page.locator('#inputGroupName').fill('incoming_secondary')
        page.locator('#apply').click()
        assert card('display').locator('.input').count() == 2, 'retry lost the new input port'
        assert card('display').get_by_text('输入 incoming_secondary.frame ← demo.Frame', exact=True).count() == 1
        page.locator('#flowTab').click()
        page.locator('.flow-edge[data-input="incoming_secondary"]').focus()
        page.keyboard.press('Enter')
        assert page.locator('#connectionDetail').get_by_text('sensor2.perception → display.incoming_secondary', exact=True).count() == 1
        after_input = snapshot()
        state = json.loads(after_input)
        display = next(a for a in state['project']['apps'] if a['id'] == 'display')
        assert [p['id'] for p in display['requires']] == ['incoming', 'incoming_secondary']
        instance = next(i for i in state['deployment']['instances'] if i['app'] == 'display')
        assert instance['requires']['incoming_secondary'] == {'instance': 'sensor2_instance', 'provided': 'perception'}
        page.locator('#undo').click()
        assert snapshot() == before_input
        assert card('display').locator('.input').count() == 1
        page.locator('#redo').click()
        assert snapshot() == after_input
        assert card('display').locator('.input').count() == 2

        # Output retry can introduce a new port after rejecting a duplicate event.
        card('sensor2').get_by_text('增加输出', exact=True).click()
        page.locator('#outputMessage').fill('frame')
        choose_output_type(page, 'demo.Frame@1.0.0')
        before_history = history_state()
        for _ in range(2):
            rejected('消息名已存在')
            assert snapshot() == after_input
            assert history_state() == before_history
        page.get_by_text('高级：分组设置', exact=True).click()
        page.locator('#outputGroup').select_option(':new')
        page.locator('#outputGroupName').fill('extra')
        page.locator('#apply').click()
        assert card('sensor2').get_by_text('输出 extra.frame → demo.Frame', exact=True).count() == 1
        after_output = snapshot()
        state = json.loads(after_output)
        instance = next(i for i in state['deployment']['instances'] if i['app'] == 'sensor2')
        assert instance['provides']['extra'] == 'sensor2_instance_extra'
        page.locator('#undo').click()
        assert snapshot() == after_input
        page.locator('#redo').click()
        assert snapshot() == after_output

        # Cancel after rejection must not create edits or erase redo history.
        page.locator('#undo').click()
        before_cancel = snapshot()
        before_history = history_state()
        card('display').get_by_text('选择输入', exact=True).click()
        page.get_by_text('高级：分组设置', exact=True).click()
        page.locator('#inputGroupName').fill('incoming')
        rejected('分组名已存在，请换一个名称；修改已有输入请使用“编辑订阅”')
        page.locator('#cancel').click()
        assert snapshot() == before_cancel
        assert history_state() == before_history
        page.locator('#redo').click()
        assert snapshot() == after_output
        page.locator('#flowTab').click()
        page.locator('.flow-edge[data-input="incoming_secondary"]').focus()
        page.keyboard.press('Enter')
        page.locator('#removeConnection').click()
        assert card('display').locator('.input').count() == 1
        page.locator('#undo').click()
        assert snapshot() == after_output
        assert card('display').locator('.input').count() == 2
        page.locator('#validate').click();page.wait_for_function("document.getElementById('status').textContent==='校验通过'")
        page.locator('#generate').click();page.wait_for_function("document.getElementById('status').textContent.startsWith('生成完成')",timeout=60000)
        page.locator('#save').click();page.wait_for_function("document.getElementById('status').textContent==='草稿已保存'")
        page.screenshot(path=str(evidence/'editor-fresh.png'),full_page=True)
        assert page.locator('#projectState').inner_text() == '草稿已保存'
        assert page.title() == 'fresh_project · Adaptive Middleware'
        saved_project = json.loads((root/'out/editor/fresh_project/project.cm.json').read_text(encoding='utf-8'))
        saved_deployment = json.loads((root/'out/editor/fresh_project/deployment.json').read_text(encoding='utf-8'))
        assert saved_project['model'] == json.loads(after_output)['project']
        assert saved_deployment == json.loads(after_output)['deployment']
        print('PASS: duplicate input/output retry, undo/redo, cancel, remove connection, saved model consistency')
        assert not errors,errors
        print(json.dumps({'browser':'Chromium','console_errors':errors,'checks':['render','field search','type import','add output','undo','validate','generate','save','new project','add apps','subscribe entire event','generate fresh project'],'screenshot':str(evidence/'editor.png')},indent=2))
        browser.close()
finally:
    server.terminate()
    try:server.wait(timeout=5)
    except subprocess.TimeoutExpired:server.kill();server.wait()
