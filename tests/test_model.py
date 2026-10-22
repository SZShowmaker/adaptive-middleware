import copy
from concurrent.futures import ThreadPoolExecutor
import json
import sys
import tempfile
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from amw_tool.model import load_project, validate, loads, ModelError, routes, validate_types
from amw_tool.generate import generate
from amw_tool.cli import configuration
class ModelTests(unittest.TestCase):
    def setUp(self):self.bundle=load_project(ROOT/'examples/demo/project.cm.json')['bundle']
    def test_type_library_before_apps_exist(self):
        library={'format_version':1,'types':[{'id':'vehicle.Category','version':'1.0.0','kind':'enum','enumerators':['Unknown','Vehicle']}]}
        self.assertEqual(len(validate_types(library)[0]),1)
        library['types'][0]['enumerators']=['Unknown','Unknown']
        with self.assertRaises(ModelError):
            validate_types(library)
    def test_sample_and_instance_isolation(self):
        m=validate(self.bundle);self.assertNotEqual(routes(m,'camera_front')[0]['topic'],routes(m,'camera_rear')[0]['topic'])
    def test_duplicate_json(self):
        with self.assertRaises(ModelError):loads('{"a":1,"a":2}')
    def test_unknown_binding(self):
        self.bundle['deployment']['binding']='vsomeip'
        with self.assertRaises(ModelError):validate(self.bundle)
    def test_duplicate_member(self):
        self.bundle['types']['types'][0]['fields'][1]['id']=1
        with self.assertRaises(ModelError):validate(self.bundle)
    def test_recursive_type(self):
        self.bundle['types']['types'][0]['fields'][0]['type']={'ref':'demo.Object','version':'1.0.0'}
        with self.assertRaises(ModelError):validate(self.bundle)
    def test_unknown_field(self):
        self.bundle['types']['types'][0]['surprise']=1
        with self.assertRaises(ModelError):validate(self.bundle)
    def test_mismatch(self):
        p=copy.deepcopy(self.bundle['deployment']['policies']['state']);p['reliability']='reliable';self.bundle['deployment']['policies']['r']=p;self.bundle['deployment']['instances'][2]['policy']='r'
        with self.assertRaisesRegex(ModelError,'RELIABLE'):validate(self.bundle)
    def test_bad_instance(self):
        self.bundle['deployment']['instances'][2]['requires']['perception']['instance']='missing'
        with self.assertRaises(ModelError):validate(self.bundle)
    def test_negative_bound(self):
        self.bundle['types']['types'][1]['fields'][2]['type']['max_length']=-1
        with self.assertRaises(ModelError):validate(self.bundle)
    def test_typo_override(self):
        self.bundle['deployment']['instances'][0]['event_policies']={'perception.typo':'state'}
        with self.assertRaises(ModelError):validate(self.bundle)
    def test_generated_app_name_collision(self):
        for reserved in ('binding', 'domain_id'):
            self.bundle['project']['apps'][0]['id']=reserved
            with self.subTest(name=reserved), self.assertRaisesRegex(ModelError,'name collision'):
                validate(self.bundle)
    def test_generated_member_collision(self):
        app=self.bundle['project']['apps'][0]
        app['id']='perception_frame'
        with self.assertRaisesRegex(ModelError,'member collision'):validate(self.bundle)
    def test_parallel_generation_has_private_preprocessor_output(self):
        config=configuration(ROOT/'config.local.json')
        other=copy.deepcopy(self.bundle)
        other['types']['types'][0]['fields'][0]['name']='different_id'
        models=[validate(self.bundle),validate(other)]
        with tempfile.TemporaryDirectory() as temp:
            outputs=[Path(temp)/'first',Path(temp)/'second']
            with ThreadPoolExecutor(max_workers=2) as executor:
                jobs=[executor.submit(generate,m,o,config) for m,o in zip(models,outputs)]
                for job in jobs:job.result()
            first=(outputs[0]/'generated/wire/messages.hpp').read_text()
            second=(outputs[1]/'generated/wire/messages.hpp').read_text()
            self.assertIn('object_id',first)
            self.assertNotIn('different_id',first)
            self.assertIn('different_id',second)
            self.assertNotIn('object_id',second)
            for output in outputs:self.assertFalse((output/'.gen-tmp').exists())
    def test_generation_is_deterministic_and_failure_preserves_output(self):
        c=configuration(ROOT/'config.local.json');model=validate(self.bundle)
        with tempfile.TemporaryDirectory(prefix='amw unicode 测试 ') as temp:
            output=Path(temp)/'generated';first=generate(model,output,c);second=generate(model,output,c)
            self.assertEqual(first,second)
            sentinel=(output/'generation-manifest.json').read_bytes()
            bad=dict(c,generator_jar=str(Path(temp)/'missing.jar'))
            with self.assertRaises(Exception):generate(model,output,bad)
            self.assertEqual(sentinel,(output/'generation-manifest.json').read_bytes())
            lock=output.with_name(output.name+'.lock');lock.write_text('busy')
            with self.assertRaisesRegex(ModelError,'lock exists'):generate(model,output,c)
            lock.unlink()
            (output/'generated/apps.hpp').write_text('user edit')
            with self.assertRaisesRegex(ModelError,'was edited'):generate(model,output,c)
            self.assertEqual('user edit',(output/'generated/apps.hpp').read_text())
            unmanaged=Path(temp)/'business';unmanaged.mkdir();(unmanaged/'main.cpp').write_text('keep')
            with self.assertRaises(ModelError):generate(model,unmanaged,c)
            self.assertEqual('keep',(unmanaged/'main.cpp').read_text())
if __name__=='__main__':unittest.main()
