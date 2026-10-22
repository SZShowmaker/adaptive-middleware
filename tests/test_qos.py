import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from amw_tool import qos
from amw_tool.model import load_project, validate, routes, ModelError, fail
from amw_tool.generate import emit

class QosTests(unittest.TestCase):
    def setUp(self):
        self.bundle=copy.deepcopy(load_project(ROOT/'examples/demo/project.cm.json')['bundle'])

    def policy(self,scope,**values):
        p=self.bundle['deployment']['policies']['state']
        p.setdefault('dds',{}).setdefault(scope,{}).update(values)
        return p

    def test_defaults_are_complete_and_valid(self):
        import jsonschema
        for scope in qos.SCOPES:
            values=qos.defaults(scope)
            qos.validate_overrides({scope:values},[scope],scope,fail)
            qos.check_values(scope,values,scope,fail)
            for f in qos.fields_for(scope):
                jsonschema.Draft7Validator(f['schema']).validate(f['default'])

    def test_empty_policy_matches_legacy_and_does_not_mutate_input(self):
        old=validate(self.bundle)
        self.bundle['deployment']['policies']['state']={}
        snapshot=copy.deepcopy(self.bundle)
        new=validate(self.bundle)
        self.assertEqual(self.bundle,snapshot)
        for iid in new['instances']:
            self.assertEqual(routes(old,iid),routes(new,iid))

    def test_specific_endpoint_override_and_topic_inheritance(self):
        self.policy('topic',**{'deadline.period':qos.ms(80)})
        self.policy('writer',**{'deadline.period':qos.ms(40)})
        dep=self.bundle['deployment']
        dep['policies']['special']={'dds':{'writer':{'history.kind':'keep_all','deadline.period':qos.ms(40)}}}
        dep['instances'][0]['event_policies']={'perception.health':'special'}
        m=validate(self.bundle);r=routes(m,'camera_front')
        self.assertEqual(r[0]['qos']['deadline.period'],qos.ms(40))
        self.assertEqual(r[1]['qos']['history.kind'],'keep_all')
        self.assertEqual(routes(m,'monitor')[0]['qos']['deadline.period'],qos.ms(80))

    def test_requested_offered_validation_uses_actual_overrides(self):
        for key,writer,reader in [('reliability.kind','best_effort','reliable'),('durability.kind','volatile','transient_local'),
                                  ('deadline.period',qos.ms(30),qos.ms(20)),('ownership.kind','shared','exclusive'),
                                  ('representation.kinds',['xcdr1'],['xcdr2']),('positive_acks.disabled',False,True)]:
            with self.subTest(key=key):
                self.bundle['deployment']['policies']['state']={}
                self.policy('writer',**{key:writer});self.policy('reader',**{key:reader})
                with self.assertRaises(ModelError):validate(self.bundle)

    def test_history_and_resource_consistency(self):
        self.policy('writer',**{'history.depth':17})
        with self.assertRaisesRegex(ModelError,'history.depth'):validate(self.bundle)
        self.policy('writer',**{'history.kind':'keep_all'})
        validate(self.bundle)
        self.policy('writer',**{'resource_limits.max_samples':8})
        with self.assertRaisesRegex(ModelError,'resource_limits'):validate(self.bundle)

    def test_invalid_scalar_duration_enum_and_unknown_property_rejected(self):
        for patch in [{'history.depth':True},{'history.depth':0},{'history.kind':'typo'},
                      {'deadline.period':{'seconds':0,'nanoseconds':1000000000}},
                      {'deadline.period':-1},{'destination_order.kind':'by_source_timestamp'},
                      {'data_sharing.domain_ids':[65536]}]:
            with self.subTest(patch=patch):
                self.bundle['deployment']['policies']['state']={'dds':{'writer':patch}}
                with self.assertRaises(ModelError):validate(self.bundle)

    def test_infinite_and_unlimited_are_explicit(self):
        self.policy('writer',**{'resource_limits.max_samples':'unlimited','history.kind':'keep_all','deadline.period':'infinite'})
        m=validate(self.bundle)
        self.assertTrue(any('unlimited' in w for w in m['warnings']))
        self.policy('writer',**{'data_sharing.kind':'on'})
        with self.assertRaisesRegex(ModelError,'finite sample'):validate(self.bundle)

    def test_liveliness_and_discovery_periods(self):
        self.policy('writer',**{'liveliness.lease_duration':qos.ms(500)})
        with self.assertRaisesRegex(ModelError,'announcement_period'):validate(self.bundle)
        self.policy('writer',**{'liveliness.announcement_period':qos.ms(100)})
        validate(self.bundle)
        self.bundle['deployment']['qos']={'participant':{'discovery.announcement_period':qos.ms(6000)}}
        with self.assertRaisesRegex(ModelError,'discovery'):validate(self.bundle)

    def test_instance_group_inheritance_and_partition_mismatch(self):
        dep=self.bundle['deployment']
        dep['qos']={'publisher':{'partition.names':['vehicle']},'subscriber':{'partition.names':['vehicle']}}
        validate(self.bundle)
        dep['instances'][2]['qos']={'subscriber':{'partition.names':['other']}}
        with self.assertRaisesRegex(ModelError,'partitions'):validate(self.bundle)
        dep['instances'][2]['qos']['subscriber']['partition.names']=['veh*']
        validate(self.bundle)

    def test_flow_controller_reference_and_mode(self):
        self.policy('writer',**{'publish_mode.flow_controller':'limited'})
        with self.assertRaisesRegex(ModelError,'unknown flow'):validate(self.bundle)
        self.bundle['deployment']['qos']={'participant':{'flow_controllers':[{'name':'limited','scheduler':'fifo','max_bytes_per_period':64000,'period_ms':100,'sender_thread':qos.THREAD_DEFAULT}]}}
        with self.assertRaisesRegex(ModelError,'asynchronous'):validate(self.bundle)
        self.policy('writer',**{'publish_mode.kind':'asynchronous'})
        validate(self.bundle)

    def test_invalid_allocation_and_reserved_properties(self):
        self.policy('reader',**{'allocation.matched_publisher_allocation':{'initial':9,'maximum':8,'increment':1}})
        with self.assertRaisesRegex(ModelError,'allocation'):validate(self.bundle)
        self.bundle['deployment']['policies']['state']={}
        self.policy('reader',properties=[{'name':'dds.sec.auth.plugin','value':'anything','propagate':False}])
        with self.assertRaisesRegex(ModelError,'reserved'):validate(self.bundle)

    def test_qos_editor_before_apps_and_network_validation(self):
        dep=self.bundle['deployment'];dep['instances']=[];dep['policies']={'defaults':{}}
        qos.validate_configuration(dep,fail)
        dep['transport']['peers']=['999.1.1.1']
        with self.assertRaisesRegex(ModelError,'IPv4'):qos.validate_configuration(dep,fail)

    def test_effective_snapshot_is_generated_and_public_header_is_clean(self):
        self.policy('writer',**{'publish_mode.kind':'asynchronous','user_data.hex':'00ff',
                               'properties':[{'name':'team','value':'a"\\中文','propagate':True}],
                               'endpoint.unicast_locator_list':[{'address':'127.0.0.1','port':19120}]})
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);m=validate(self.bundle);emit(m,root)
            snapshot=json.loads((root/'metadata/qos.effective.json').read_text())
            self.assertEqual(snapshot['instances']['camera_front']['endpoints']['perception.frame']['effective']['user_data.hex'],'00ff')
            self.assertNotIn('fastdds',(root/'generated/apps.hpp').read_text().lower())
            code=(root/'generated/qos.hpp').read_text()
            self.assertIn('ASYNCHRONOUS_PUBLISH_MODE',code)
            self.assertIn('std::vector<eprosima::fastdds::rtps::octet>{0,255}',code)

    def test_schema_matches_catalogue(self):
        subprocess.run([sys.executable,str(ROOT/'tools/update_qos_schema.py'),'--check'],check=True)

    def test_default_flow_controller_uses_sdk_constant(self):
        code='\n'.join(qos.emit_values('writer',qos.defaults('writer'),'writer'))
        self.assertIn('publish_mode().flow_controller_name = rtps::FASTDDS_FLOW_CONTROLLER_DEFAULT;',code)

    def test_partition_pattern_uncertainty_is_not_false_assurance(self):
        self.assertIsNone(qos.partitions_match(['veh*'],['veh?']))
        self.assertTrue(qos.partitions_match(['vehicle'],['veh*']))
        self.assertFalse(qos.partitions_match(['sensor'],['monitor']))

if __name__=='__main__':unittest.main()
