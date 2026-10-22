"""Project-scoped draft/output paths and local delivery root preferences."""
import json
from pathlib import Path
import subprocess
import sys
import time
import urllib.request
from playwright.sync_api import sync_playwright
from browser_helpers import choose_output_type
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'out/browser-paths';OUT.mkdir(parents=True,exist_ok=True)
server=subprocess.Popen([sys.executable,str(ROOT/'amw'),'gui','--port','18772'],cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
try:
    for _ in range(100):
        try:urllib.request.urlopen('http://127.0.0.1:18772',timeout=1);break
        except Exception:
            if server.poll() is not None:raise RuntimeError(server.stdout.read())
            time.sleep(.1)
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,args=['--no-sandbox'])
        page=browser.new_page(viewport={'width':1440,'height':1000});errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto('http://127.0.0.1:18772');page.wait_for_function("document.getElementById('status').textContent.includes('就绪')")
        def rename(name):
            bundle=page.evaluate('model');bundle['project']['project_id']=name
            page.locator('#advancedTools > summary').click();page.locator('#edit').click()
            page.locator('#dialogBody textarea').fill(json.dumps(bundle));page.locator('#apply').click();page.locator('#dialog').wait_for(state='hidden')
            page.wait_for_function('(name)=>document.getElementById("generationPath").textContent.includes("/"+name+"/src-gen")',arg=name)

        def save():
            page.locator('#save').click();page.wait_for_function("document.getElementById('status').textContent==='草稿已保存'")

        rename('path_first');save()
        first=ROOT/'out/editor/path_first/project.cm.json';before=first.read_bytes()
        rename('path_second');save()
        assert first.read_bytes()==before
        assert (ROOT/'out/editor/path_second/project.cm.json').is_file()
        original=page.evaluate('[JSON.stringify(model),history.length,revision]')
        page.locator('#editGenerationPath').click();page.locator('#deliveryRoot').fill('../invalid')
        page.wait_for_function("document.getElementById('pathPreview').textContent.includes('absolute path')")
        assert page.locator('#apply').is_disabled()
        custom=ROOT/'out/custom delivery'
        page.locator('#deliveryRoot').fill(str(custom))
        page.wait_for_function("!document.getElementById('apply').disabled")
        page.locator('#apply').click();page.locator('#dialog').wait_for(state='hidden')
        page.wait_for_function('(path)=>document.getElementById("generationPath").textContent.includes(path)',arg=str(custom/'path_second/src-gen'))
        assert page.evaluate('[JSON.stringify(model),history.length,revision]')==original
        # Reload keeps the local location preference; loading another model derives a new project subdirectory.
        page.reload();page.wait_for_function("document.getElementById('status').textContent.includes('就绪')")
        page.wait_for_function('(path)=>document.getElementById("generationPath").textContent.includes(path)',arg=str(custom/'path_second/src-gen'))
        page.locator('#generate').click();page.wait_for_function("document.getElementById('cancelGeneration').disabled===false")
        rename('path_third')
        assert page.locator('#generate').is_disabled()
        page.wait_for_function("document.getElementById('status').textContent.startsWith('生成完成')",timeout=120000)
        assert str(custom/'path_second/src-gen') in page.locator('#status').inner_text()
        assert '请重新生成' in page.locator('#status').inner_text()
        resolved=json.loads((custom/'path_second/src-gen/metadata/model.resolved.json').read_text())
        assert resolved['project']['project_id']=='path_second'
        assert not (custom/'path_third/src-gen').exists()
        save();assert first.read_bytes()==before
        page.locator('#editGenerationPath').click();page.get_by_role('button',name='恢复默认位置',exact=True).click()
        page.wait_for_function("!document.getElementById('apply').disabled")
        page.locator('#apply').click();page.locator('#dialog').wait_for(state='hidden')
        page.wait_for_function('(path)=>document.getElementById("generationPath").textContent.includes(path)',arg=str(ROOT/'out/delivery/path_third/src-gen'))
        # An invalid draft ID must never become a filesystem path, even through direct requests.
        invalid=page.evaluate('model');invalid['project']['project_id']='../escaped'
        response=page.evaluate('async bundle=>{try{await api("save",bundle);return "accepted"}catch(e){return e.message}}',invalid)
        assert 'invalid/reserved identifier' in response
        assert not (ROOT/'out/escaped').exists()
        assert first.read_bytes()==before
        # The delivered project file restores the submitted generation snapshot,
        # even though the editor was changed while generation ran.
        project_file=custom/'path_second/src-gen/path_second.amw.json'
        assert json.loads(project_file.read_text())==resolved
        with page.expect_file_chooser() as chooser:
            page.locator('#open').click()
        chooser.value.set_files(str(project_file))
        page.wait_for_function("model.project.project_id==='path_second'")
        assert page.evaluate('model')==resolved
        page.screenshot(path=str(OUT/'project-paths.png'),full_page=True)
        assert not errors,errors
        browser.close();print('PASS: isolated drafts, renamed paths, custom root persistence/reset, invalid path rejection, real generation uses submitted project/path during edits')
finally:
    server.terminate()
    try:server.wait(timeout=5)
    except subprocess.TimeoutExpired:server.kill();server.wait()
