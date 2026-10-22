from browser_helpers import choose_output_type
"""Create a contract through structured type forms, then generate a complete delivery."""
import json
from pathlib import Path
import subprocess
import sys
import time
import urllib.request
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
server=subprocess.Popen([sys.executable,str(ROOT/'amw'),'gui','--port','18767'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
try:
    for _ in range(100):
        try:
            urllib.request.urlopen('http://127.0.0.1:18767',timeout=1);break
        except Exception:
            if server.poll() is not None:raise RuntimeError(server.stdout.read())
            time.sleep(.1)
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,args=['--no-sandbox'])
        page=browser.new_page(viewport={'width':1440,'height':1000});errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto('http://127.0.0.1:18767');page.wait_for_function("document.getElementById('status').textContent.includes('就绪')")
        page.once('dialog',lambda d:d.accept('structured_project'));page.locator('#newProject').click()
        def new_type(name,kind='struct'):
            page.locator('#newType').click()
            page.locator('[data-field=type-id]').fill(name)
            page.locator('[data-field=type-kind]').select_option(kind)
        def apply():
            page.locator('#apply').click();page.locator('#dialog').wait_for(state='hidden')
        new_type('vehicle.Category','enum')
        page.locator('[data-field=enumerators]').fill('Unknown\nVehicle\nPedestrian');apply()
        new_type('vehicle.Object')
        row=page.locator('.type-field').first
        row.locator('[data-field=name]').fill('object_id')
        page.locator('#addTypeField').click();row=page.locator('.type-field').nth(1)
        row.locator('[data-field=name]').fill('position')
        row.locator('[data-field=unit]').fill('m')
        row.locator('[data-field=descriptor]').first.select_option('array')
        row.locator('[data-field=bound]').fill('3')
        row.locator('[data-field=descriptor]').nth(1).select_option('float32')
        page.locator('#addTypeField').click();row=page.locator('.type-field').nth(2)
        row.locator('[data-field=name]').fill('category')
        row.locator('[data-field=descriptor]').select_option('ref:vehicle.Category@1.0.0');apply()
        new_type('vehicle.Frame')
        row=page.locator('.type-field').first
        row.locator('[data-field=name]').fill('objects')
        row.locator('[data-field=descriptor]').first.select_option('sequence')
        row.locator('[data-field=bound]').fill('128')
        row.locator('[data-field=descriptor]').nth(1).select_option('ref:vehicle.Object@1.0.0')
        page.locator('#addTypeField').click();row=page.locator('.type-field').nth(1)
        row.locator('[data-field=name]').fill('sensor')
        row.locator('[data-field=descriptor]').select_option('string')
        row.locator('[data-field=bound]').fill('32');apply()
        assert page.locator('#types .library-type').count()==3
        before=page.evaluate('JSON.stringify(model)')
        page.locator('#types .library-type').filter(has_text='vehicle.Frame').click()
        page.locator('#typeDetailDialog').get_by_text('编辑结构',exact=True).click()
        # Backend validation rejects a duplicate without changing state/history.
        row=page.locator('.type-field').nth(1);row.locator('[data-field=name]').fill('objects')
        messages=[]
        page.once('dialog',lambda d:(messages.append(d.message),d.accept()))
        page.locator('#apply').click()
        page.wait_for_function("!document.getElementById('apply').disabled")
        assert messages and 'duplicate' in messages[0]
        assert page.evaluate('JSON.stringify(model)')==before
        row.locator('[data-field=name]').fill('sensor_name');apply()
        page.locator('#undo').click();assert page.evaluate('JSON.stringify(model)')==before
        page.locator('#redo').click()
        for app in ('sensor','viewer'):
            page.once('dialog',lambda d,name=app:d.accept(name));page.locator('#addApp').click()
        page.locator('.app').first.get_by_text('增加输出',exact=True).click()
        page.locator('#outputMessage').fill('frame')
        choose_output_type(page, 'vehicle.Frame@1.0.0');apply()
        page.locator('.app').nth(1).get_by_text('选择输入',exact=True).click()
        apply()
        page.locator('#validate').click();page.wait_for_function("document.getElementById('status').textContent==='校验通过'")
        page.locator('#generate').click();page.wait_for_function("document.getElementById('status').textContent.startsWith('生成完成')",timeout=120000)
        package=ROOT/'out/delivery/structured_project/src-gen'
        manifest=json.loads((package/'generation-manifest.json').read_text())
        assert len(manifest['platforms'])==3
        assert (package/'runtime/src/log.cpp').is_file()
        assert (package/'generated/apps.hpp').is_file()
        page.locator('#save').click();page.wait_for_function("document.getElementById('status').textContent==='草稿已保存'")
        (ROOT/'out/browser-types').mkdir(parents=True,exist_ok=True)
        page.screenshot(path=str(ROOT/'out/browser-types/types-and-delivery.png'),full_page=True)
        assert not errors,errors
        browser.close()
        print('PASS: structured enum/nested types/array/sequence/string, validation retry, undo/redo, two Apps, subscription, complete three-platform delivery')
finally:
    server.terminate()
    try:server.wait(timeout=5)
    except subprocess.TimeoutExpired:server.kill();server.wait()
