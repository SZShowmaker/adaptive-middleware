"""Delivery contract for the static, version-maintained application handbook."""
import copy
import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from amw_tool.cli import configuration
from amw_tool.generate import GUIDE_FILES, emit, generate
from amw_tool.model import ModelError, load_project, validate


class GuideTests(unittest.TestCase):
    def setUp(self):
        self.bundle = load_project(ROOT / 'examples/demo/project.cm.json')['bundle']

    def test_handbook_is_identical_for_different_apps(self):
        changed = copy.deepcopy(self.bundle)
        changed['project']['project_id'] = 'another_project'
        names = {'producer': 'sensor', 'consumer': 'display'}
        for app in changed['project']['apps']:
            app['id'] = names[app['id']]
        for connection in changed['project']['connections']:
            for end in ('from', 'to'):
                connection[end]['app'] = names[connection[end]['app']]
        for instance in changed['deployment']['instances']:
            instance['app'] = names[instance['app']]
        with tempfile.TemporaryDirectory() as temp:
            outputs = [Path(temp) / name for name in ('demo', 'custom')]
            for bundle, output in zip((self.bundle, changed), outputs):
                emit(validate(bundle), output)
                project_file = output / (bundle['project']['project_id'] + '.amw.json')
                self.assertEqual(project_file.read_bytes(), (output / 'metadata/model.resolved.json').read_bytes())
                self.assertEqual(validate(json.loads(project_file.read_text()))['bundle'], bundle)
                for relative in GUIDE_FILES:
                    self.assertEqual(
                        (ROOT / 'docs/app-guide' / relative).read_bytes(),
                        (output / 'guide' / relative).read_bytes())
            self.assertNotEqual((outputs[0] / 'generated/apps.hpp').read_bytes(),
                                (outputs[1] / 'generated/apps.hpp').read_bytes())
            for entry in ('README.md',):
                self.assertEqual((outputs[0] / entry).read_bytes(),
                                 (outputs[1] / entry).read_bytes())

    def test_handbook_manifest_protection_and_legacy_upgrade(self):
        config = configuration(ROOT / 'config.local.json')
        model = validate(self.bundle)
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / 'generated'
            manifest = generate(model, output, config)
            additions = ['guide/' + name for name in GUIDE_FILES]
            additions += ['README.md', 'demo.amw.json']
            for name in additions:
                self.assertEqual(manifest['files'][name],
                                 hashlib.sha256((output / name).read_bytes()).hexdigest())
            # Model an intact older package whose manifest predates the handbook.
            for name in additions:
                (output / name).unlink()
                del manifest['files'][name]
            shutil.rmtree(output / 'guide')
            (output / 'generation-manifest.json').write_text(json.dumps(manifest))
            generate(model, output, config)
            for name in additions:
                self.assertTrue((output / name).is_file(), name)
            guide = output / 'guide/API.md'
            guide.write_text('application team notes; must not be overwritten')
            previous = (output / 'generation-manifest.json').read_bytes()
            with self.assertRaisesRegex(ModelError, 'was edited: guide/API.md'):
                generate(model, output, config)
            self.assertIn('must not be overwritten', guide.read_text())
            self.assertEqual(previous, (output / 'generation-manifest.json').read_bytes())


if __name__ == '__main__':
    unittest.main()
