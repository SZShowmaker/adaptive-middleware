"""Bounded type library, read-only inspector, workspace views and operation feedback."""
import json
from pathlib import Path
import subprocess
import sys
import time
import urllib.request
from playwright.sync_api import sync_playwright
from browser_helpers import choose_output_type
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'out/browser-workspace';OUT.mkdir(parents=True,exist_ok=True)
server=subprocess.Popen([sys.executable,str(ROOT/'amw'),'gui','--port','18771'],cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
try:
    for _ in range(100):
        try:urllib.request.urlopen('http://127.0.0.1:18771',timeout=1);break
        except Exception:
            if server.poll() is not None:raise RuntimeError(server.stdout.read())
            time.sleep(.1)
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,args=['--no-sandbox'])
        page=browser.new_page(viewport={'width':1440,'height':1000});errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto('http://127.0.0.1:18771');page.wait_for_function("document.getElementById('status').textContent.includes('就绪')")
        page.once('dialog',lambda d:d.accept('sample_workspace'));page.locator('#newProject').click()
        page.locator('#file').set_input_files(str(ROOT/'tests/fixtures/sample-types.cmtypes.json'))
        page.locator('#apply').click();page.locator('#dialog').wait_for(state='hidden')
        assert page.locator('#types .library-type').count()==22
        assert page.locator('#types').evaluate('n=>n.scrollHeight>n.clientHeight')
        assert page.evaluate('document.documentElement.scrollHeight <= window.innerHeight+20')
        y=page.locator('#search').bounding_box()['y']
        page.locator('#types').evaluate('n=>n.scrollTop=n.scrollHeight')
        assert page.locator('#search').bounding_box()['y']==y
        before=page.evaluate('[JSON.stringify(model),history.length,future.length,revision]')
        page.locator('#typeFilter').select_option('used');assert page.locator('#types .library-type').count()==0
        page.locator('#typeFilter').select_option('all');page.locator('#search').fill('sample_id')
        assert page.locator('#types .library-type').count()==5
        page.get_by_role('button',name='查看类型 sample.Message @1.0.0',exact=True).click()
        assert '尚未用于 App 输出' in page.locator('#typeOutputUses').inner_text()
        page.locator('#typeDetailBody').get_by_role('button',name='sample.Batch @1.0.0',exact=True).click()
        assert page.locator('#typeDetailTitle').inner_text()=='sample.Batch @1.0.0'
        page.locator('#typeDetailBody').get_by_role('button',name='sample.Item @1.0.0',exact=True).click()
        page.locator('#typeDetailBody').get_by_text('sample_id · uint32',exact=True).click()
        page.wait_for_function("document.getElementById('typeDetailBody').textContent.includes('样本编号')")
        page.keyboard.press('Escape');assert not page.locator('#typeDetailDialog').is_visible()
        assert page.evaluate('[JSON.stringify(model),history.length,future.length,revision]')==before
        page.locator('#search').fill('')
        page.once('dialog',lambda d:d.accept('sample_app'));page.locator('#addApp').click()
        page.get_by_text('增加输出',exact=True).click();page.locator('#outputMessage').fill('sample_message')
        choose_output_type(page,'sample.Message@1.0.0');page.locator('#apply').click();page.locator('#dialog').wait_for(state='hidden')
        page.locator('#typeFilter').select_option('used');assert page.locator('#types .library-type').count()==1
        assert 'sample.Message' in page.locator('#types').inner_text()
        page.locator('#undo').click();assert page.locator('#types .library-type').count()==0
        page.locator('#redo').click();assert page.locator('#types .library-type').count()==1
        page.locator('#typeFilter').select_option('all');page.locator('#search').fill('sample.Item')
        page.get_by_role('button',name='查看类型 sample.Item @1.0.0',exact=True).click()
        assert 'sample_app.output.sample_message · 嵌套于 sample.Message @1.0.0' in page.locator('#typeOutputUses').inner_text()
        page.screenshot(path=str(OUT/'type-inspector.png'),full_page=True)
        page.locator('#closeTypeDetail').click();page.locator('#search').fill('')
        # A large library must not change page height. Long names remain inspectable.
        extra={'format_version':1,'types':[{'id':'bulk.VeryLongTypeNameForLibraryLayout'+str(i),'version':'1.0.0','kind':'struct','fields':[{'id':1,'name':'value','type':'uint32'}]} for i in range(180)]}
        extra['types'].append({'id':'bulk.State','version':'1.0.0','kind':'enum','enumerators':['Ready','Running']})
        height=page.evaluate('document.documentElement.scrollHeight')
        page.locator('#file').set_input_files({'name':'bulk.cmtypes.json','mimeType':'application/json','buffer':json.dumps(extra).encode()})
        page.locator('#apply').click();page.locator('#dialog').wait_for(state='hidden')
        assert page.locator('#types .library-type').count()==203
        assert page.evaluate('document.documentElement.scrollHeight')==height
        page.locator('#typeFilter').select_option('enum');assert page.locator('#types .library-type').count()==1
        page.get_by_role('button',name='查看类型 bulk.State @1.0.0',exact=True).click()
        assert 'Ready、Running' in page.locator('#typeDetailBody').inner_text()
        page.locator('#closeTypeDetail').click();page.locator('#typeFilter').select_option('all')
        before=page.evaluate('[JSON.stringify(model),history.length,future.length,revision]')
        page.locator('#flowTab').click();assert page.locator('#connections').is_visible();assert not page.locator('#appsView').is_visible()
        page.wait_for_function("parseFloat(document.querySelector('#flowCanvas svg').style.width)>0")
        page.locator('#appsTab').click();assert page.locator('#appsView').is_visible()
        assert page.evaluate('[JSON.stringify(model),history.length,future.length,revision]')==before
        page.locator('#validate').click();page.wait_for_function("document.getElementById('status').textContent==='校验通过'")
        assert not page.locator('#resultDetails').evaluate('n=>n.open')
        page.locator('#resultDetails > summary').click();assert '"valid": true' in page.locator('#result').inner_text()
        page.locator('#resultDetails > summary').click()
        page.route('**/api/validate',lambda route:route.fulfill(status=422,content_type='application/json',body=json.dumps({'error':'测试：消息引用缺失'})))
        page.locator('#validate').click();page.wait_for_function("document.getElementById('status').textContent.includes('测试：')")
        assert '消息引用缺失' in page.locator('#resultMessages').inner_text()
        page.unroute('**/api/validate')
        page.locator('#validate').click();page.wait_for_function("document.getElementById('status').textContent==='校验通过'")
        page.locator('#types').evaluate('n=>n.scrollTop=0')
        page.screenshot(path=str(OUT/'workspace-desktop.png'),full_page=True)
        page.set_viewport_size({'width':680,'height':900})
        assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
        assert page.locator('.library-panel').bounding_box()['height']<=325
        page.locator('#search').fill('sample.Message');page.get_by_role('button',name='查看类型 sample.Message @1.0.0',exact=True).click()
        assert page.locator('#typeDetailDialog').bounding_box()['width']<=680
        page.locator('#closeTypeDetail').click()
        page.screenshot(path=str(OUT/'workspace-narrow.png'),full_page=True)
        assert not errors,errors
        browser.close();print('PASS: sample/203 types, bounded independent scrolling, filters, nested search, inspector/references/output uses, read-only history, undo/redo, view switch, feedback and responsive layouts')
finally:
    server.terminate()
    try:server.wait(timeout=5)
    except subprocess.TimeoutExpired:server.kill();server.wait()
