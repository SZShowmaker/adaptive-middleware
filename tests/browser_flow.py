"""Project identity and logical data-flow browser regression; no DDS traffic."""
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

OUT = ROOT / 'out/browser-flow'
OUT.mkdir(parents=True, exist_ok=True)
BASE = load_project(ROOT / 'examples/demo/project.cm.json')['bundle']


def fixture(name, app_ids, edges):
    model = copy.deepcopy(BASE)
    project, deployment = model['project'], model['deployment']
    project.update(project_id=name, apps=[], connections=[])
    deployment['instances'] = []
    interface = {'ref': 'demo.Perception', 'version': '1.0.0'}
    for app_id in app_ids:
        has_output = any(a == app_id for a, _ in edges)
        project['apps'].append({'id': app_id, 'provides': [{'id': 'out', 'interface': interface}] if has_output else [], 'requires': []})
        deployment['instances'].append({'id': app_id + '_instance', 'app': app_id, 'provides': {'out': app_id + '_out'} if has_output else {}, 'requires': {}, 'policy': 'state'})
    for index, (source, target) in enumerate(edges):
        port = 'incoming_' + str(index)
        app = next(a for a in project['apps'] if a['id'] == target)
        app['requires'].append({'id': port, 'interface': interface, 'events': [1, 2]})
        project['connections'].append({'from': {'app': source, 'provided': 'out'}, 'to': {'app': target, 'required': port}})
        instance = next(i for i in deployment['instances'] if i['app'] == target)
        instance['requires'][port] = {'instance': source + '_instance', 'provided': 'out'}
    validate(model)
    return model


server = subprocess.Popen([sys.executable, str(ROOT / 'amw'), 'gui', '--port', '18766'], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
try:
    for _ in range(100):
        try:
            urllib.request.urlopen('http://127.0.0.1:18766', timeout=1)
            break
        except Exception:
            if server.poll() is not None:
                raise RuntimeError(server.stdout.read())
            time.sleep(.1)
    else:
        raise RuntimeError('GUI did not start')
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=['--no-sandbox'])
        page = browser.new_page(viewport={'width': 1440, 'height': 1000})
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto('http://127.0.0.1:18766')
        page.wait_for_function("document.getElementById('projectName').textContent === 'demo'")
        assert page.locator('#projectState').inner_text() == '工程已载入'
        page.locator('#flowTab').click()
        assert page.locator('.flow-node').count() == 2
        assert page.locator('.flow-edge').count() == 1

        page.once('dialog', lambda dialog: dialog.accept('new_vehicle_project'))
        page.locator('#newProject').click()
        assert page.title() == '* new_vehicle_project · Adaptive Middleware'
        assert page.locator('#projectName').inner_text() == 'new_vehicle_project'
        assert page.locator('.flow-node').count() == 0
        assert '还没有 App' in page.locator('#flowCanvas').inner_text()
        page.locator('#undo').click()
        assert page.title() == 'demo · Adaptive Middleware'
        assert page.locator('#projectState').inner_text() == '工程已载入'
        page.locator('#redo').click()
        assert page.locator('#projectName').inner_text() == 'new_vehicle_project'

        def open_model(model):
            data = json.dumps(model, ensure_ascii=False).encode()
            page.locator('#projectFile').set_input_files({'name': 'fixture.amw.json', 'mimeType': 'application/json', 'buffer': data})
            page.wait_for_function('(name) => document.getElementById("projectName").textContent === name', arg=model['project']['project_id'])
            assert page.locator('.flow-node').count() == len(model['project']['apps'])
            assert page.locator('.flow-edge').count() == len(model['project']['connections'])

        branching = fixture('vehicle_pipeline', ['camera_front', 'camera_rear', 'fusion', 'monitor', 'recorder'], [('camera_front', 'fusion'), ('camera_rear', 'fusion'), ('fusion', 'monitor'), ('camera_front', 'monitor')])
        open_model(branching)
        positions = page.locator('.flow-node').evaluate_all('(nodes) => Object.fromEntries(nodes.map(n => [n.dataset.app, Number(n.querySelector("rect").getAttribute("x"))]))')
        assert positions['camera_front'] < positions['fusion'] < positions['monitor']
        page.locator('.edge-badge').first.click()
        assert 'camera_front.out → fusion.incoming_0' in page.locator('#connectionDetail').inner_text()
        assert 'demo.Frame' in page.locator('#connectionDetail').inner_text()
        assert 'demo.Health' in page.locator('#connectionDetail').inner_text()
        page.locator('#removeConnection').click()
        assert page.locator('.flow-edge').count() == 3
        page.locator('#undo').click()
        assert page.locator('.flow-edge').count() == 4
        page.locator('#flowZoomIn').click()
        enlarged = page.locator('#flowZoomLabel').inner_text()
        page.locator('#flowZoomOut').click()
        assert page.locator('#flowZoomLabel').inner_text() != enlarged
        page.locator('#flowFit').click()
        page.locator('#connections').scroll_into_view_if_needed()
        assert page.locator('.project-bar').bounding_box()['y'] >= 0
        page.screenshot(path=str(OUT / 'flow-branching.png'), full_page=True)
        page.locator('#connections').screenshot(path=str(OUT / 'flow-branching-detail.png'))
        page.set_viewport_size({'width': 680, 'height': 900})
        page.locator('#flowFit').click()
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
        page.screenshot(path=str(OUT / 'flow-narrow.png'), full_page=True)
        page.set_viewport_size({'width': 1440, 'height': 1000})

        cycle = fixture('feedback_loop', ['planner', 'controller', 'observer'], [('planner', 'controller'), ('controller', 'planner'), ('planner', 'planner')])
        open_model(cycle)
        # Every path stays inside the canvas, including the feedback and self-loop.
        assert page.locator('.edge-line').evaluate_all('''paths => paths.every(p => {
            const b=p.getBBox(), v=p.ownerSVGElement.viewBox.baseVal;
            return b.x>=0 && b.y>=0 && b.x+b.width<=v.width && b.y+b.height<=v.height;
        })''')
        page.locator('.flow-edge[data-input="incoming_2"]').focus()
        page.keyboard.press('Enter')
        assert 'planner.out → planner.incoming_2' in page.locator('#connectionDetail').inner_text()
        page.locator('#connections').screenshot(path=str(OUT / 'flow-cycle.png'))

        # Save errors keep edits dirty. A delayed save only marks the submitted
        # snapshot saved, never edits made while the request was in flight.
        page.route('**/api/save', lambda route: route.fulfill(status=500, content_type='application/json', body='{"error":"save failed"}'))
        page.locator('#save').click()
        page.wait_for_function("document.getElementById('status').textContent === 'save failed'")
        assert page.locator('#projectState').inner_text() == '未保存更改'
        page.unroute('**/api/save')
        pending = []
        page.route('**/api/save', lambda route: pending.append(route))
        page.locator('#save').click()
        page.wait_for_timeout(100)
        assert len(pending) == 1
        page.once('dialog', lambda dialog: dialog.accept('created_while_saving'))
        page.locator('#appsTab').click()
        page.locator('#addApp').click()
        pending[0].continue_()
        page.wait_for_function("document.getElementById('status').textContent === '草稿已保存'")
        assert page.locator('#projectState').inner_text() == '未保存更改'
        page.locator('#undo').click()
        assert page.locator('#projectState').inner_text() == '草稿已保存'
        assert page.title() == 'feedback_loop · Adaptive Middleware'
        assert not errors, errors
        browser.close()
        print('PASS: project identity, new/open/undo/redo, empty/isolated Apps, branching, skip edges, cycles, self-loop, selection/removal, zoom, narrow viewport, save failure and in-flight edits; no page errors')
finally:
    server.terminate()
    try:
        server.wait(timeout=5)
    except subprocess.TimeoutExpired:
        server.kill()
        server.wait()
