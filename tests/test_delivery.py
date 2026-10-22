"""Delivery must be complete, relocatable and protected as one transaction."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from amw_tool.cli import configuration
from amw_tool.generate import generate
from amw_tool.model import load_project, ModelError
from amw_tool.package import profiles, sha256


class DeliveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='amw delivery ')
        cls.output = Path(cls.temp.name) / 'src-gen'
        cls.config = configuration(ROOT / 'config.local.json')
        cls.model = load_project(ROOT / 'examples/demo/project.cm.json')
        cls.manifest = generate(cls.model, cls.output, cls.config)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_complete_portable_payload(self):
        for file in ('CMakeLists.txt', 'cmake/Deploy.cmake', 'toolchains/aarch64-linux.cmake',
                     'runtime/include/amw/log/log.hpp', 'runtime/src/log.cpp', 'runtime/src/time.cpp',
                     'runtime/src/cm.cpp', 'runtime/third_party/tinyxml2/LICENSE.txt',
                     'config/logging.xml', 'generated/apps.hpp', 'metadata/routes.json', 'demo.amw.json'):
            self.assertIn(file, self.manifest['files'])
        self.assertEqual(set(self.manifest['platforms']), {'linux-x64', 'linux-arm64', 'windows-x64'})
        self.assertFalse(any(p.is_symlink() for p in self.output.rglob('*')))
        for platform in self.manifest['platforms']:
            self.assertIn(f'dependencies/{platform}/profile.cmake', self.manifest['files'])
        for file in self.output.rglob('*.cmake'):
            self.assertNotIn(str(ROOT), file.read_text())

    def test_failed_or_cancelled_update_preserves_delivery(self):
        before = (self.output / 'generation-manifest.json').read_bytes()
        bad = copy.deepcopy(self.config)
        del bad['delivery_sdks']['windows-x64']
        with self.assertRaisesRegex(ModelError, 'delivery_sdks'):
            generate(self.model, self.output, bad)
        cancelled = threading.Event(); cancelled.set()
        with self.assertRaisesRegex(ModelError, 'cancelled'):
            generate(self.model, self.output, self.config, cancelled)
        self.assertEqual(before, (self.output / 'generation-manifest.json').read_bytes())
        self.assertFalse(self.output.with_name('src-gen.lock').exists())
        self.assertFalse(list(self.output.parent.glob('.amw-generate-*')))

    def test_wrong_architecture_is_rejected(self):
        bad = copy.deepcopy(self.config)
        bad['delivery_sdks']['linux-arm64']['sdk_prefix'] = bad['delivery_sdks']['linux-x64']['sdk_prefix']
        with self.assertRaisesRegex(ModelError, 'wrong architecture'):
            profiles(bad)

    def test_nested_output_is_rejected_without_modifying_package(self):
        with self.assertRaisesRegex(ModelError, 'nested inside'):
            generate(self.model, self.output / 'new-directory/src-gen', self.config)
        self.assertFalse((self.output / 'new-directory').exists())

    def test_runtime_is_covered_by_overwrite_protection(self):
        path = self.output / 'runtime/src/log.cpp'
        before = path.read_bytes()
        try:
            path.write_bytes(before + b'\n// local edit\n')
            with self.assertRaisesRegex(ModelError, 'was edited: runtime/src/log.cpp'):
                generate(self.model, self.output, self.config)
            self.assertTrue(path.read_bytes().endswith(b'// local edit\n'))
        finally:
            path.write_bytes(before)
        self.assertEqual(sha256(path), self.manifest['files']['runtime/src/log.cpp'])

    def test_project_bundle_is_covered_by_overwrite_protection(self):
        path = self.output / 'demo.amw.json'
        before = path.read_bytes()
        self.assertEqual(before, (self.output / 'metadata/model.resolved.json').read_bytes())
        self.assertEqual(json.loads(before), self.model['bundle'])
        self.assertEqual(sha256(path), self.manifest['files']['demo.amw.json'])
        try:
            path.write_bytes(before + b'\n')
            with self.assertRaisesRegex(ModelError, 'was edited: demo.amw.json'):
                generate(self.model, self.output, self.config)
            self.assertEqual(path.read_bytes(), before + b'\n')
        finally:
            path.write_bytes(before)


if __name__ == '__main__':
    unittest.main()
