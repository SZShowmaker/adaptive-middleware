"""Fast DDS 3.6.2 configuration catalogue, defaults, validation and C++ mapping.

This is the single source for editor controls and deployment schemas. JSON stores
only overrides; effective values are resolved before checking or generating code.
DDS types stay behind NetworkBinding, never in public business DTOs.
"""
import copy
import json
import math
import re

VERSION = 'fastdds-3.6.2/amw-qos-1'
SCOPES = ['participant', 'publisher', 'subscriber', 'topic', 'writer', 'reader']
GROUP_SCOPES = SCOPES[:3]
ENDPOINT_SCOPES = SCOPES[3:]
LEGACY = dict(queue_samples=16, queue_bytes=4194304, overflow='discard_oldest',
              reliability='best_effort', durability='volatile', history_depth=16, max_blocking_ms=20)
FIELDS = []

def integer(low=0, high=2147483647):
    return dict(type='integer', minimum=low, maximum=high)

def obj(properties):
    return dict(type='object', properties=properties, required=list(properties), additionalProperties=False)

def array(items, **kw):
    return dict(type='array', items=items, maxItems=256, **kw)

STRING = dict(type='string', maxLength=4096, pattern=r'^[^\x00]*$')
BOOL = dict(type='boolean')
DURATION = {'oneOf': [obj({'seconds': integer(0, 2147483646), 'nanoseconds': integer(0, 999999999)}), {'const': 'infinite'}]}
ALLOCATION = obj({'initial': integer(), 'maximum': {'oneOf': [integer(), {'const': 'unlimited'}]}, 'increment': integer()})
THREAD = obj({'scheduling_policy': integer(-1), 'priority': integer(-2147483648),
              'affinity': dict(type='string', pattern=r'^(0|[1-9][0-9]{0,19})$'), 'stack_size': integer(-1)})
THREAD_DEFAULT = dict(scheduling_policy=-1, priority=-2147483648, affinity='0', stack_size=-1)
LOCATOR = obj({'address': dict(type='string', format='ipv4'), 'port': integer(0, 65535)})
PROPERTY = obj({'name': dict(type='string', minLength=1, maxLength=256, pattern=r'^[^\x00]*$'),
                'value': STRING, 'propagate': BOOL})
FLOW = obj({'name': dict(type='string', pattern=r'^[A-Za-z][A-Za-z0-9_]*$'),
            'scheduler': {'enum': ['fifo', 'round_robin', 'high_priority', 'priority_with_reservation']},
            'max_bytes_per_period': integer(), 'period_ms': integer(1), 'sender_thread': THREAD})

def field(key, scopes, label, default, schema, cpp=None, category='standard', **kw):
    FIELDS.append(dict(key=key, scopes=scopes.split(), label=label, default=default,
                       schema=schema, cpp=cpp, category=category, **kw))

def enum(key, scopes, label, default, choices, cpp, **kw):
    field(key, scopes, label, default, {'enum': list(choices)}, cpp, choices=choices, **kw)

def duration(key, scopes, label, default, cpp, **kw):
    field(key, scopes, label, default, DURATION, cpp, kind='duration', **kw)

def ms(n):
    return dict(seconds=n // 1000, nanoseconds=(n % 1000) * 1000000)

for key, label, default, choices, member in [
    ('reliability.kind', '可靠性', 'best_effort', {'best_effort': 'BEST_EFFORT_RELIABILITY_QOS', 'reliable': 'RELIABLE_RELIABILITY_QOS'}, 'reliability'),
    ('durability.kind', '持久性', 'volatile', {'volatile': 'VOLATILE_DURABILITY_QOS', 'transient_local': 'TRANSIENT_LOCAL_DURABILITY_QOS'}, 'durability'),
    ('history.kind', '历史模式', 'keep_last', {'keep_last': 'KEEP_LAST_HISTORY_QOS', 'keep_all': 'KEEP_ALL_HISTORY_QOS'}, 'history'),
    ('ownership.kind', '所有权', 'shared', {'shared': 'SHARED_OWNERSHIP_QOS', 'exclusive': 'EXCLUSIVE_OWNERSHIP_QOS'}, 'ownership'),
    ('liveliness.kind', '活性检测方式', 'automatic', {'automatic': 'AUTOMATIC_LIVELINESS_QOS'}, 'liveliness')]:
    enum(key, 'topic writer reader', label, default, choices, member+'().kind')
duration('reliability.max_blocking_time', 'topic writer reader', '可靠写入最大阻塞时间', ms(20), 'reliability().max_blocking_time')
field('history.depth', 'topic writer reader', '历史深度', 16, integer(1), 'history().depth', active_when={'history.kind': 'keep_last'})
for key, label, default in [('max_samples', '样本总上限', 16), ('max_instances', 'DDS 数据实例上限', 1),
                             ('max_samples_per_instance', '每个 DDS 数据实例样本上限', 16)]:
    field('resource_limits.'+key, 'topic writer reader', label, default,
          {'oneOf': [integer(1), {'const': 'unlimited'}]}, 'resource_limits().'+key, kind='limit',
          help='DDS 数据实例按 key 区分，与 App 部署实例不同。当前生成类型无 key。')
for key, label, default in [('allocated_samples', '初始分配样本数', 16), ('extra_samples', '额外样本数', 1)]:
    field('resource_limits.'+key, 'topic writer reader', label, default, integer(), 'resource_limits().'+key)
duration('deadline.period', 'topic writer reader', '更新截止周期', 'infinite', 'deadline().period',
         help='DDS 检测超期；不会替业务定时发布。当前 CM 未提供 deadline 状态回调。')
duration('lifespan.duration', 'topic writer reader', '样本有效期', 'infinite', 'lifespan().duration')
duration('liveliness.lease_duration', 'topic writer reader', '活性租约', 'infinite', 'liveliness().lease_duration')
duration('liveliness.announcement_period', 'topic writer reader', '自动活性通告周期', 'infinite', 'liveliness().announcement_period')
field('ownership_strength.value', 'writer', '独占所有权强度', 0, integer(0, 4294967295), 'ownership_strength().value', active_when={'ownership.kind': 'exclusive'})
field('transport_priority.value', 'topic writer', '传输优先级', 0, integer(-2147483648), 'transport_priority().value',
      help='实际效果依赖传输和操作系统，不是业务线程优先级或实时性保证。')
for key, scopes, label in [('user_data', 'participant writer reader', '用户数据'), ('topic_data', 'topic', 'Topic 附加数据'), ('group_data', 'publisher subscriber', '分组附加数据')]:
    field(key+'.hex', scopes, label+'（十六进制字节）', '', dict(type='string', pattern=r'^(?:[0-9a-fA-F]{2})*$', maxLength=65534), key+'()', kind='hex')
field('partition.names', 'publisher subscriber', '分区名称', [], array(STRING, uniqueItems=True), 'partition()', kind='partitions', help='空列表表示默认空名称分区；收发分区必须能匹配。')
field('entity_factory.autoenable_created_entities', 'participant publisher subscriber', '自动启用实体', True, {'const': True}, 'entity_factory().autoenable_created_entities',
      help='当前 CM 启动流程要求自动启用，不支持延迟 enable。')

# XTypes are standard DDS extensions; generated DTOs still use exact type/version.
field('representation.kinds', 'topic writer reader', '数据表示', ['xcdr1'],
      array({'enum': ['xcdr1', 'xcdr2']}, minItems=1, uniqueItems=True), 'representation().m_value', kind='representation', category='xtypes')
enum('type_consistency.kind', 'reader', '类型一致性', 'allow_type_coercion',
     {'allow_type_coercion': 'ALLOW_TYPE_COERCION', 'disallow_type_coercion': 'DISALLOW_TYPE_COERCION'}, 'type_consistency().m_kind', category='xtypes',
     help='本项目仍要求相同消息契约，不因此承诺跨版本自动兼容。')
for key, label, default in [('ignore_sequence_bounds', '忽略序列边界', True), ('ignore_string_bounds', '忽略字符串边界', True),
                          ('ignore_member_names', '忽略成员名', False), ('prevent_type_widening', '禁止类型拓宽', False), ('force_type_validation', '强制类型验证', False)]:
    field('type_consistency.'+key, 'reader', label, default, BOOL, 'type_consistency().m_'+key, category='xtypes')

enum('publish_mode.kind', 'writer', 'DDS 发布模式', 'synchronous', {'synchronous': 'SYNCHRONOUS_PUBLISH_MODE', 'asynchronous': 'ASYNCHRONOUS_PUBLISH_MODE'},
     'publish_mode().kind', category='extension', help='CM 本身已有发送队列；此项控制其后的 DDS 发送。')
field('publish_mode.flow_controller', 'writer', '流量控制器', 'default', STRING, 'publish_mode().flow_controller_name', category='extension', active_when={'publish_mode.kind': 'asynchronous'})
field('flow_controllers', 'participant', '自定义流量控制器', [], array(FLOW), 'flow_controllers()', kind='flows', category='extension')
enum('data_sharing.kind', 'writer reader', 'Data-sharing 模式', 'off', {'off': 'OFF', 'auto': 'AUTO', 'on': 'ON'}, None,
     kind='data_sharing', category='extension', help='与普通 SHM Transport 不同；on 要求数据类型和内存策略满足条件，可能导致启动失败。')
field('data_sharing.directory', 'writer reader', 'Data-sharing 目录', '', STRING, None, category='extension')
field('data_sharing.domain_ids', 'writer reader', 'Data-sharing 域 ID', [], array(integer(0, 65535), uniqueItems=True), None, category='extension')
field('data_sharing.max_domains', 'writer reader', 'Data-sharing 最大域数（0 为无限）', 0, integer(0, 4294967295), None, category='extension')
enum('endpoint.history_memory_policy', 'writer reader', '历史内存分配策略', 'preallocated_with_realloc',
     {'preallocated': 'PREALLOCATED_MEMORY_MODE', 'preallocated_with_realloc': 'PREALLOCATED_WITH_REALLOC_MEMORY_MODE',
      'dynamic_reserve': 'DYNAMIC_RESERVE_MEMORY_MODE', 'dynamic_reusable': 'DYNAMIC_REUSABLE_MEMORY_MODE'},
     'endpoint().history_memory_policy', namespace='rtps', category='extension')
for scope in ['writer', 'reader']:
    prefix = 'reliable_'+scope+'_qos'
    field('positive_acks.disabled', scope, '禁用正向 ACK', False, BOOL, prefix+'().disable_positive_acks.enabled', category='extension')
    if scope == 'writer':
        duration('positive_acks.duration', scope, '禁用 ACK 时的样本保留时间', 'infinite', prefix+'().disable_positive_acks.duration', category='extension', active_when={'positive_acks.disabled': True})
        field('rtps.disable_heartbeat_piggyback', scope, '禁用随数据附带心跳', False, BOOL, prefix+'().disable_heartbeat_piggyback', category='extension')
    times = [('initial_heartbeat_delay', 12), ('heartbeat_period', 3000), ('nack_response_delay', 5), ('nack_supression_duration', 0)] if scope == 'writer' else [('initial_acknack_delay', 70), ('heartbeat_response_delay', 5)]
    for key, default in times:
        duration('rtps.'+key, scope, key+'（可靠传输时序）', ms(default), prefix+'().times.'+key, category='extension')
for scopes, key, initial, maximum in [('writer', 'matched_subscriber_allocation', 0, 'unlimited'), ('writer', 'reader_filters_allocation', 0, 32),
                                   ('reader', 'matched_publisher_allocation', 0, 'unlimited'), ('reader', 'sample_infos_allocation', 32, 'unlimited'), ('reader', 'outstanding_reads_allocation', 2, 'unlimited')]:
    field('allocation.'+key, scopes, key+'（资源分配）', dict(initial=initial, maximum=maximum, increment=1), ALLOCATION,
          scopes+'_resource_limits().'+key, kind='allocation', category='extension')
field('allocation.max_samples_per_read', 'reader', '一次读取样本数上限', 32, integer(1), 'reader_resource_limits().max_samples_per_read', category='extension')
for key in ['unicast_locator_list', 'multicast_locator_list', 'remote_locator_list']:
    field('endpoint.'+key, 'writer reader', key+'（UDPv4 地址）', [], array(LOCATOR), 'endpoint().'+key, kind='locators', category='extension')
field('endpoint.ignore_non_matching_locators', 'writer reader', '忽略不匹配地址', False, BOOL, 'endpoint().ignore_non_matching_locators', category='extension')
field('properties', 'participant writer reader', '自定义发现属性', [], array(PROPERTY), 'properties().properties()', kind='properties', category='extension',
      help='用于自定义元数据。内置功能属性须通过已建模的专用配置项设置，避免绕过校验。')
duration('discovery.lease_duration', 'participant', '发现租约', ms(6000), 'wire_protocol().builtin.discovery_config.leaseDuration', category='extension')
duration('discovery.announcement_period', 'participant', '发现通告周期', ms(2000), 'wire_protocol().builtin.discovery_config.leaseDuration_announcementperiod', category='extension')
for key in ['default_unicast_locator_list', 'default_multicast_locator_list']:
    field('wire_protocol.'+key, 'participant', key+'（UDPv4 地址）', [], array(LOCATOR), 'wire_protocol().'+key, kind='locators', category='extension')
field('wire_protocol.ignore_non_matching_locators', 'participant', '忽略不匹配发现地址', False, BOOL, 'wire_protocol().ignore_non_matching_locators', category='extension')
for key, label in [('send_socket_buffer_size', '发送套接字缓冲区'), ('listen_socket_buffer_size', '接收套接字缓冲区')]:
    field('transport.'+key, 'participant', label+'（字节，0 使用系统默认）', 2097152, integer(0, 4294967295), 'transport().'+key, category='extension')
for scopes, key, cpp in [('participant', 'timed_events', 'timed_events_thread()'), ('participant', 'builtin_sender', 'builtin_controllers_sender_thread()'),
                         ('participant', 'type_lookup', 'typelookup_service_thread()'), ('reader', 'data_sharing_listener', 'data_sharing().data_sharing_listener_thread()')]:
    field('thread.'+key, scopes, key+' 线程', THREAD_DEFAULT, THREAD, cpp, kind='thread', category='extension',
          help='默认值沿用操作系统调度。自定义优先级、亲和性及栈大小依赖平台和权限；Windows 忽略 scheduling_policy。')

for key, initial, increment in [('participants', 0, 1), ('readers', 0, 1), ('writers', 0, 1), ('send_buffers.network_buffers_config', 16, 16)]:
    field('allocation.'+key, 'participant', key+'（发现资源分配）', dict(initial=initial, maximum='unlimited', increment=increment),
          ALLOCATION, 'allocation().'+key, kind='allocation', category='extension')
for key, default in [('locators.max_unicast_locators', 4), ('locators.max_multicast_locators', 1), ('send_buffers.preallocated_number', 0),
                     ('data_limits.max_properties', 0), ('data_limits.max_user_data', 0), ('data_limits.max_partitions', 0), ('data_limits.max_datasharing_domains', 0)]:
    field('allocation.'+key, 'participant', key+'（发现资源上限）', default, integer(), 'allocation().'+key, category='extension')
field('allocation.send_buffers.dynamic', 'participant', '动态增加发送缓冲区', False, BOOL, 'allocation().send_buffers.dynamic', category='extension')

# Complete policy-level inventory. Unsupported controls are visible but not accepted
# as overrides (including on import); a header declaration is not an implementation.
UNAVAILABLE = [
    dict(key=k, scopes=s.split(), category='standard', reason='Fast DDS 3.6.2 官方文档标注未实现。')
    for k, s in [('DestinationOrderQosPolicy', 'topic writer reader'), ('DurabilityServiceQosPolicy', 'topic writer'),
                 ('LatencyBudgetQosPolicy', 'topic writer reader'), ('PresentationQosPolicy', 'publisher subscriber'),
                 ('ReaderDataLifecycleQosPolicy', 'reader'), ('TimeBasedFilterQosPolicy', 'reader'), ('WriterDataLifecycleQosPolicy', 'writer')]
]
UNAVAILABLE += [
    dict(key='durability.transient / persistent', scopes=['topic', 'writer', 'reader'], category='standard', reason='需要持久化服务和部署资源；本中间件尚未接入。'),
    dict(key='liveliness.manual_by_participant / manual_by_topic', scopes=['topic', 'writer', 'reader'], category='standard', reason='当前公共 CM 没有手动 assert_liveliness 接口。'),
    dict(key='EntityFactory.autoenable=false', scopes=GROUP_SCOPES, category='standard', reason='当前 CM 启动流程要求自动启用实体。'),
    dict(key='RTPSEndpointQos.static_ids / external_locators', scopes=['writer', 'reader'], category='extension', reason='静态发现和外部地址映射尚未接入部署模型。'),
    dict(key='WireProtocolConfigQos.discovery_modes / prefix / external_locators', scopes=['participant'], category='extension', reason='当前仅支持 SIMPLE 发现与 UDPv4 地址；服务器、静态发现及自定义 GUID 尚未接入。'),
    dict(key='TransportConfigQos.custom_transports', scopes=['participant'], category='extension', reason='当前交付支持 UDPv4 与可选普通 SHM；TCP/TLS、自定义传输插件尚未接入。'),
    dict(key='PropertyPolicyQos.builtin_plugins / binary_properties', scopes=['participant', 'writer', 'reader'], category='extension', reason='安全、持久化等插件需专用部署与校验；不能用自由属性绕过支持边界。'),
    dict(key='ParticipantResourceLimitsQos.content_filter', scopes=['participant'], category='extension', reason='内容过滤尚未接入公共 CM；当前按完整消息订阅。'),
]

def fields_for(scope):
    return [f for f in FIELDS if scope in f['scopes']]

def defaults(scope):
    return {f['key']: copy.deepcopy(f['default']) for f in fields_for(scope)}

def scoped_schema(scopes):
    return {'type': 'object', 'properties': {s: {'type': 'object', 'properties': {f['key']: f['schema'] for f in fields_for(s)}, 'additionalProperties': False} for s in scopes}, 'additionalProperties': False}

def catalogue():
    return dict(version=VERSION, scopes=SCOPES, fields=[{k:v for k,v in f.items() if k not in ('cpp', 'namespace', 'choices')} for f in FIELDS],
                unavailable=UNAVAILABLE, legacy_defaults=LEGACY)

def resolve_policy(policy):
    return dict(copy.deepcopy(LEGACY), **copy.deepcopy(policy))

def effective(scope, overrides=None, policy=None):
    result = defaults(scope)
    if policy is not None:
        p = resolve_policy(policy)
        result.update({'reliability.kind': p['reliability'], 'durability.kind': p['durability'],
                       'history.depth': p['history_depth'], 'reliability.max_blocking_time': ms(p['max_blocking_ms']),
                       'resource_limits.max_samples': p['history_depth'], 'resource_limits.max_instances': 1,
                       'resource_limits.max_samples_per_instance': p['history_depth'], 'resource_limits.allocated_samples': p['history_depth']})
        result.update(p.get('dds', {}).get('topic', {}))
        # Only Topic policies applicable to this endpoint are inherited.
        result = {k:v for k,v in result.items() if k in defaults(scope)}
        result.update(p.get('dds', {}).get(scope, {}))
    if overrides:
        result.update(overrides)
    return result

def duration_ns(value):
    return math.inf if value == 'infinite' else value['seconds'] * 1000000000 + value['nanoseconds']

def limit(value):
    return math.inf if value == 'unlimited' else value

def check_values(scope, values, path, fail):
    if scope in ENDPOINT_SCOPES:
        depth = values['history.depth']; maximum = limit(values['resource_limits.max_samples'])
        per_instance = limit(values['resource_limits.max_samples_per_instance'])
        if maximum < per_instance:
            fail(path+'.resource_limits', 'max_samples must be >= max_samples_per_instance')
        if values['history.kind'] == 'keep_last' and depth > min(maximum, per_instance):
            fail(path+'.history.depth', 'KEEP_LAST depth exceeds resource_limits')
        if values['resource_limits.allocated_samples'] > maximum:
            fail(path+'.resource_limits.allocated_samples', 'initial allocation exceeds max_samples')
        lease = duration_ns(values['liveliness.lease_duration'])
        announcement = duration_ns(values['liveliness.announcement_period'])
        if lease == 0 or (scope != 'reader' and lease != math.inf and announcement >= lease):
            fail(path+'.liveliness', 'announcement_period must be less than finite lease_duration; lease must be positive')
        if duration_ns(values['deadline.period']) == 0:
            fail(path+'.deadline.period', 'period must be positive')
    if scope == 'writer' and len(values['representation.kinds']) != 1:
        fail(path+'.representation.kinds', 'Writer must offer exactly one data representation')
    if scope in ('writer', 'reader'):
        if values['data_sharing.max_domains'] and len(values['data_sharing.domain_ids']) > values['data_sharing.max_domains']:
            fail(path+'.data_sharing.domain_ids', 'domain list exceeds max_domains')
        if values['data_sharing.kind'] == 'on' and values['endpoint.history_memory_policy'] not in ('preallocated', 'preallocated_with_realloc'):
            fail(path+'.data_sharing.kind', 'ON requires preallocated or preallocated_with_realloc memory')
        if values['data_sharing.kind'] == 'on' and values['resource_limits.max_samples'] == 'unlimited':
            fail(path+'.resource_limits.max_samples', 'Data-sharing ON requires a finite sample capacity')
    if scope == 'participant':
        if duration_ns(values['discovery.announcement_period']) >= duration_ns(values['discovery.lease_duration']):
            fail(path+'.discovery', 'announcement_period must be less than lease_duration')
        names=[x['name'] for x in values['flow_controllers']]
        if len(names) != len(set(names)) or 'default' in names:
            fail(path+'.flow_controllers', 'duplicate or reserved controller name')
        for index,flow in enumerate(values['flow_controllers']):
            if int(flow['sender_thread']['affinity']) > 18446744073709551615:
                fail(path+'.flow_controllers['+str(index)+'].sender_thread.affinity', 'expected uint64 decimal string')
    if scope == 'writer' and duration_ns(values['rtps.heartbeat_period']) == 0:
        fail(path+'.rtps.heartbeat_period', 'heartbeat period must be positive')
    for f in fields_for(scope):
        value=values[f['key']]; where=path+'.'+f['key']
        if f.get('kind') == 'allocation':
            if value['initial'] > limit(value['maximum']) or (value['increment'] == 0 and value['initial'] != value['maximum']):
                fail(where, 'allocation requires initial <= maximum; fixed allocation requires initial == maximum')
        if f.get('kind') == 'thread' and int(value['affinity']) > 18446744073709551615:
            fail(where+'.affinity', 'expected uint64 decimal string')
        if f.get('kind') == 'properties':
            names=[x['name'] for x in value]
            if len(names) != len(set(names)):
                fail(where, 'duplicate property name')
            if any(n.lower().startswith(('dds.', 'fastdds.', 'fast_rtps.', 'rtps.', 'eprosima.')) for n in names):
                fail(where, 'reserved DDS properties must use dedicated supported controls')

def validate_overrides(overrides, scopes, path, fail):
    import jsonschema
    errors=list(jsonschema.Draft7Validator(scoped_schema(scopes), format_checker=jsonschema.FormatChecker()).iter_errors(overrides))
    if errors:
        e=errors[0]; fail(path+'.'+'.'.join(map(str,e.path)), e.message)

def instance_values(dep, instance):
    return {s: effective(s, {**dep.get('qos', {}).get(s, {}), **instance.get('qos', {}).get(s, {})}) for s in GROUP_SCOPES}

def validate_configuration(dep, fail):
    """Validate form drafts, including projects with no Apps yet."""
    import jsonschema
    from pathlib import Path
    schema=json.loads((Path(__file__).resolve().parents[2]/'schemas/deployment.schema.json').read_text())
    schema['definitions']['deployment']['properties']['instances']['minItems']=0
    errors=list(jsonschema.Draft7Validator(schema,format_checker=jsonschema.FormatChecker()).iter_errors(dep))
    if errors:
        e=errors[0];fail('deployment.'+'.'.join(map(str,e.path)),e.message)
    import ipaddress
    transport=dep['transport']
    for value in ([transport['interface_address']] if transport['interface_address'] else [])+transport['peers']:
        try:ipaddress.IPv4Address(value)
        except ValueError:fail('deployment.transport','invalid IPv4 '+str(value))
    for name,p in dep['policies'].items():
        for scope in ENDPOINT_SCOPES:check_values(scope,effective(scope,policy=p),'policies.'+name+'.'+scope,fail)
    for scope in GROUP_SCOPES:check_values(scope,effective(scope,dep.get('qos',{}).get(scope)), 'deployment.qos.'+scope,fail)
    for instance in dep['instances']:
        for scope,values in instance_values(dep,instance).items():check_values(scope,values,instance['id']+'.'+scope,fail)
        if any(name not in dep['policies'] for name in [instance['policy'],*instance.get('event_policies',{}).values()]):fail(instance['id'],'unknown policy')

def check_compatible(writer, reader, path, fail):
    if reader['reliability.kind'] == 'reliable' and writer['reliability.kind'] != 'reliable':
        fail(path, 'Reader requires RELIABLE from BEST_EFFORT Writer')
    if reader['durability.kind'] == 'transient_local' and writer['durability.kind'] != 'transient_local':
        fail(path, 'durability mismatch')
    if writer['ownership.kind'] != reader['ownership.kind']:
        fail(path, 'ownership kind mismatch')
    for key in ['deadline.period', 'liveliness.lease_duration']:
        if duration_ns(writer[key]) > duration_ns(reader[key]):
            fail(path+'.'+key, 'Writer offered duration exceeds Reader requested duration')
    if not set(writer['representation.kinds']) & set(reader['representation.kinds']):
        fail(path+'.representation.kinds', 'no common data representation')
    if reader['positive_acks.disabled'] and not writer['positive_acks.disabled']:
        fail(path+'.positive_acks.disabled', 'Reader disables ACKs but Writer expects them')

def partitions_match(offered, requested):
    """Check portable glob cases; backslash and pattern/pattern pairs need DDS.

    Return None when static matching is indeterminate instead of silently claiming
    full POSIX fnmatch equivalence with Python's fnmatch implementation.
    """
    import fnmatch
    unknown=False
    for a in offered or ['']:
        for b in requested or ['']:
            if a==b:return True
            if '\\' in a or '\\' in b or (any(c in a for c in '*?[') and any(c in b for c in '*?[')):
                unknown=True;continue
            if fnmatch.fnmatchcase(a,b) or fnmatch.fnmatchcase(b,a):return True
    return None if unknown else False

def cpp_string(value):
    # Escape bytes, not source encodings; fixed-width octal escapes cannot consume
    # a following digit. This also handles non-ASCII and untrusted model strings.
    return '"'+''.join(chr(b) if 32 <= b < 127 and b not in (34,92) else '\\%03o' % b for b in value.encode('utf-8'))+'"'

def cpp_value(value):
    if isinstance(value, bool): return str(value).lower()
    if isinstance(value, str): return cpp_string(value)
    return str(value)

def cpp_duration(value):
    return 'dds::c_TimeInfinite' if value == 'infinite' else '{'+str(value['seconds'])+', '+str(value['nanoseconds'])+'u}'

def cpp_thread(target, value):
    return [target+'.'+k+' = '+(v+'ULL' if k == 'affinity' else str(v))+';' for k,v in value.items()]

def emit_values(scope, values, target):
    lines=[]
    for f in fields_for(scope):
        key=f['key']; value=values[key]; member=f['cpp']; kind=f.get('kind')
        if member is None: continue
        lhs=target+'.'+member
        if kind == 'duration': rhs=cpp_duration(value)
        elif kind == 'limit': rhs='-1' if value == 'unlimited' else str(value)
        elif kind == 'representation': rhs='{'+','.join('dds::'+{'xcdr1':'XCDR_DATA_REPRESENTATION','xcdr2':'XCDR2_DATA_REPRESENTATION'}[v] for v in value)+'}'
        elif kind == 'allocation':
            rhs='{'+str(value['initial'])+', '+('(std::numeric_limits<size_t>::max)()' if value['maximum']=='unlimited' else str(value['maximum']))+', '+str(value['increment'])+'}'
        elif kind == 'thread': lines.extend(cpp_thread(lhs,value));continue
        elif kind == 'hex':
            lines.append(lhs+'.data_vec(std::vector<eprosima::fastdds::rtps::octet>{'+','.join(str(b) for b in bytes.fromhex(value))+'});');continue
        elif kind == 'partitions':
            lines.append(lhs+'.clear();')
            lines.extend(lhs+'.push_back('+cpp_string(v)+');' for v in value);continue
        elif kind == 'locators':
            lines.append(lhs+'.clear();')
            for locator in value:
                lines.append('{rtps::Locator_t loc; loc.kind=LOCATOR_KIND_UDPv4; loc.port='+str(locator['port'])+'; rtps::IPLocator::setIPv4(loc, '+cpp_string(locator['address'])+'); '+lhs+'.push_back(loc);}')
            continue
        elif kind == 'properties':
            # Preserve SDK-provided discovery metadata; no duplicate reserved names allowed.
            lines.extend(lhs+'.emplace_back('+cpp_string(p['name'])+', '+cpp_string(p['value'])+', '+cpp_value(p['propagate'])+');' for p in value);continue
        elif kind == 'flows':
            for flow in value:
                # SDK FlowControllerDescriptor holds the name as std::string.
                lines += ['{auto f=std::make_shared<rtps::FlowControllerDescriptor>();', 'f->name='+cpp_string(flow['name'])+';',
                          'f->scheduler=rtps::FlowControllerSchedulerPolicy::'+flow['scheduler'].upper()+';',
                          'f->max_bytes_per_period='+str(flow['max_bytes_per_period'])+';', 'f->period_ms='+str(flow['period_ms'])+'ULL;']
                lines.extend(cpp_thread('(*f).sender_thread',flow['sender_thread']))
                lines.append(lhs+'.push_back(f);}')
            continue
        elif key == 'publish_mode.flow_controller' and value == 'default': rhs='rtps::FASTDDS_FLOW_CONTROLLER_DEFAULT'
        elif 'choices' in f: rhs=f.get('namespace','dds')+'::'+f['choices'][value]
        else: rhs=cpp_value(value)
        lines.append(lhs+' = '+rhs+';')
    if scope in ('writer','reader'):
        ds=target+'.data_sharing()'; kind=values['data_sharing.kind']
        lines.append(ds+'.set_max_domains('+str(values['data_sharing.max_domains'])+');')
        if kind == 'off': lines.append(ds+'.off();')
        else: lines.append(ds+'.'+('automatic' if kind=='auto' else 'on')+'('+cpp_string(values['data_sharing.directory'])+', std::vector<uint16_t>{'+','.join(map(str,values['data_sharing.domain_ids']))+'});')
    return lines
