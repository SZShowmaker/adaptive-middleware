"""Default project destinations must isolate projects before any writes."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
from amw_tool import cli
from amw_tool.model import load_project, ModelError
from amw_tool.paths import project_paths


class ProjectPathTests(unittest.TestCase):
    def test_drafts_survive_project_switch_and_rename(self):
        bundle = load_project(ROOT/'examples/demo/project.cm.json')['bundle']
        with tempfile.TemporaryDirectory() as tmp:
            for project_id in ('first', 'second'):
                bundle['project']['project_id'] = project_id
                paths = project_paths(tmp, project_id)
                cli.save_bundle(paths['draft'], bundle)
            self.assertEqual(load_project(Path(tmp)/'out/editor/first/project.cm.json')['bundle']['project']['project_id'], 'first')
            self.assertEqual(load_project(Path(tmp)/'out/editor/second/project.cm.json')['bundle']['project']['project_id'], 'second')

    def test_invalid_paths_do_not_create_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            for project_id in ('../escape', '/absolute', 'a/b', 'a\\b', '..', '', 'CON', 'Lpt1'):
                with self.subTest(project_id=project_id), self.assertRaises(ModelError):
                    project_paths(tmp, project_id)
            with self.assertRaises(ModelError):project_paths(tmp, 'valid', '../relative')
            self.assertEqual(list(Path(tmp).iterdir()), [])
            base = Path(tmp)/'custom root';base.mkdir()
            (base/'linked').symlink_to(Path(tmp), target_is_directory=True)
            with self.assertRaises(ModelError):project_paths(tmp, 'linked', str(base))

    def test_cli_default_follows_model_and_explicit_output_wins(self):
        model = load_project(ROOT/'examples/demo/project.cm.json')
        model = copy.deepcopy(model);model['bundle']['project']['project_id'] = 'different_project'
        with tempfile.TemporaryDirectory() as tmp, patch.object(cli, 'ROOT', Path(tmp)), patch.object(cli, 'configuration', return_value={}), patch.object(cli, 'load_project', return_value=model), patch.object(cli, 'generate', return_value={'model_sha256':'test'}) as generate:
            self.assertEqual(cli.main(['generate']), 0)
            self.assertEqual(generate.call_args.args[1], str(Path(tmp)/'out/delivery/different_project/src-gen'))
            self.assertEqual(cli.main(['generate', '--output', str(Path(tmp)/'custom/src-gen')]), 0)
            self.assertEqual(generate.call_args.args[1], str(Path(tmp)/'custom/src-gen'))


if __name__ == '__main__':unittest.main()
