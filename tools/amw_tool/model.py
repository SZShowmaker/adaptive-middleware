"""Versioned, strict model shared by CLI, editor and generator."""
import copy
import hashlib
import ipaddress
import json
import re
from pathlib import Path
from . import qos

class ModelError(ValueError): pass
IDENT = re.compile(r'^[A-Za-z][A-Za-z0-9_]*$')
QUAL = re.compile(r'^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z][A-Za-z0-9_]*)*$')
VERSION = re.compile(r'^\d+\.\d+\.\d+$')
RESERVED = set('class struct enum namespace template typename public private protected default delete new operator union long short int float double char bool switch case return void const volatile static auto sizeof module sequence string interface event'.split())
RESERVED.update('alignas alignof and and_eq asm bitand bitor break catch char16_t char32_t compl concept const_cast constexpr continue decltype do dynamic_cast else explicit export extern false for friend goto if inline mutable noexcept not not_eq nullptr or or_eq register reinterpret_cast requires signed static_assert static_cast thread_local this throw true try typedef typeid unsigned using virtual wchar_t while xor xor_eq std'.split())
PRIMITIVES = {'bool':('bool','boolean'), 'uint8':('uint8_t','octet'),'int8':('int8_t','int8'),'int16':('int16_t','short'),'uint16':('uint16_t','unsigned short'),'int32':('int32_t','long'),'uint32':('uint32_t','unsigned long'),'int64':('int64_t','long long'),'uint64':('uint64_t','unsigned long long'),'float32':('float','float'),'float64':('double','double')}
def fail(path, message): raise ModelError(f'{path}: {message}')
def object_(obj, required, optional=(), path='$'):
    if not isinstance(obj,dict): fail(path,'expected object')
    missing=set(required)-obj.keys(); unknown=obj.keys()-set(required)-set(optional)
    if missing: fail(path,'missing '+','.join(sorted(missing)))
    if unknown: fail(path,'unknown '+','.join(sorted(unknown)))
def integer(x, low, high, path):
    if isinstance(x,bool) or not isinstance(x,int) or not low<=x<=high: fail(path,f'expected integer {low}..{high}')
def name(x,path):
    if not isinstance(x,str) or not IDENT.fullmatch(x) or x.lower() in RESERVED or '__' in x: fail(path,'invalid/reserved identifier')
def unique(items,key,path):
    if not isinstance(items,list): fail(path,'expected array')
    result={}
    for i,x in enumerate(items):
        if not isinstance(x,dict) or key not in x: fail(f'{path}[{i}]','missing '+key)
        k=x[key]
        if not isinstance(k,(str,int)) or k in result: fail(path,'duplicate/invalid '+str(k))
        result[k]=x
    return result
def pairs(items):
    obj={}
    for k,v in items:
        if k in obj: raise ModelError('duplicate JSON key: '+k)
        obj[k]=v
    return obj
def loads(text):
    try:return json.loads(text,object_pairs_hook=pairs,parse_constant=lambda x:fail('$','non-finite number '+x))
    except (json.JSONDecodeError,UnicodeError) as e:raise ModelError(str(e)) from e
def read(path): return loads(Path(path).read_text(encoding='utf-8'))
def canonical(x): return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def digest(x):return hashlib.sha256(canonical(x).encode()).hexdigest()
def typename(ref):return ref['ref'].replace('.','_')+'_v'+ref['version'].replace('.','_')
def typekey(ref):
    object_(ref,['ref','version'],path='type reference')
    return (ref['ref'],ref['version'])
def validate_types(library):
    """Validate a type library while a GUI project still has no Apps/deployment."""
    import jsonschema
    schema=read(Path(__file__).resolve().parents[2]/'schemas/bundle.schema.json')
    schema['$ref']='#/definitions/types'
    errors=sorted(jsonschema.Draft7Validator(schema).iter_errors(library),key=lambda e:str(list(e.path)))
    if errors:
        e=errors[0];fail('types.'+'.'.join(str(x) for x in e.path),e.message)
    types={}
    for i,t in enumerate(library['types']):
        p=f'types[{i}]';kind=t.get('kind');object_(t,['id','version','kind', 'fields' if kind=='struct' else 'enumerators'],['description'],p)
        if kind not in ('struct','enum'):fail(p,'supported kinds: struct, enum')
        if not isinstance(t['id'],str) or not QUAL.fullmatch(t['id']):fail(p,'invalid qualified ID')
        for component in t['id'].split('.'):name(component,p)
        if not isinstance(t['version'],str) or not VERSION.fullmatch(t['version']):fail(p,'invalid version')
        key=(t['id'],t['version'])
        if key in types:fail(p,'duplicate type/version')
        types[key]=t
    wire_names=[typename({'ref':k[0],'version':k[1]}).lower() for k in types]
    if len(set(wire_names))!=len(wire_names):fail('types','IDL/C++ name collision')
    dependencies={k:set() for k in types}
    def descriptor(d,path,owner):
        if isinstance(d,str):
            if d not in PRIMITIVES:fail(path,'unknown primitive '+d)
            return
        if not isinstance(d,dict):fail(path,'expected type descriptor')
        if 'ref' in d:
            k=typekey(d)
            if k not in types:fail(path,'unknown type/version '+str(k))
            dependencies[owner].add(k);return
        kind=d.get('kind')
        if kind=='string':object_(d,['kind','max_length'],path=path);integer(d['max_length'],1,1048576,path);return
        if kind not in ('array','sequence'):fail(path,'unknown descriptor')
        if isinstance(d.get('element'),dict) and d['element'].get('kind')=='array' and kind=='sequence':fail(path,'wrap arrays in a named struct before using as sequence element')
        length='length' if kind=='array' else 'max_length';object_(d,['kind','element',length],path=path);integer(d[length],1,1048576,path);descriptor(d['element'],path+'.element',owner)
    for key,t in types.items():
        p=t['id']
        if t['kind']=='enum':
            if not isinstance(t['enumerators'],list) or not t['enumerators']:fail(p,'nonempty enumerators required')
            for n in t['enumerators']:name(n,p)
            if len(set(t['enumerators']))!=len(t['enumerators']):fail(p,'duplicate enumerator')
        else:
            fields=unique(t['fields'],'id',p+'.fields');seen=set()
            if not fields:fail(p,'empty struct unsupported')
            for f in fields.values():
                object_(f,['id','name','type'],['unit','description'],p);integer(f['id'],0,268435455,p);name(f['name'],p)
                if f['name'].lower() in seen:fail(p,'duplicate field name');
                seen.add(f['name'].lower());descriptor(f['type'],p+'.'+f['name'],key)
    order=[];visiting=set();done=set()
    def visit(k):
        if k in visiting:fail(str(k),'recursive types unsupported')
        if k in done:return
        visiting.add(k)
        for other in sorted(dependencies[k]):visit(other)
        visiting.remove(k);done.add(k);order.append(k)
    for k in sorted(types):visit(k)
    return types,order

def validate(bundle):
    import jsonschema
    schema=read(Path(__file__).resolve().parents[2]/'schemas/bundle.schema.json')
    errors=sorted(jsonschema.Draft7Validator(schema).iter_errors(bundle),key=lambda e:str(list(e.path)))
    if errors:
        e=errors[0]; fail('$.'+'.'.join(str(x) for x in e.path), e.message)
    # An editor bundle contains three separately persisted source models.
    object_(bundle,['types','project','deployment'])
    library,project,dep=(bundle[k] for k in ('types','project','deployment'))
    object_(library,['format_version','types']);object_(project,['format_version','project_id','service_interfaces','apps','connections']);object_(dep,['format_version','binding','transport','policies','instances'],['qos'])
    for obj in (library,project,dep):
        if type(obj['format_version']) is not int or obj['format_version']!=1:fail('format_version','only version 1 supported')
    name(project['project_id'],'project_id')
    if dep['binding']!='fastdds':fail('binding','only fastdds is implemented; vsomeip is phase 2')
    types,order=validate_types(library)
    services=unique(project['service_interfaces'],'id','services')
    for sid,s in services.items():
        object_(s,['id','version','events'],['description'],'service '+sid)
        if not QUAL.fullmatch(sid) or not VERSION.fullmatch(s['version']):fail(sid,'invalid service identity')
        events=unique(s['events'],'id',sid+'.events');enames=set()
        if not events:fail(sid,'service needs at least one event')
        for e in events.values():
            object_(e,['id','name','type'],['description'],sid);integer(e['id'],1,65535,sid);name(e['name'],sid)
            if e['name'] in enames:fail(sid,'duplicate event name')
            enames.add(e['name'])
            if typekey(e['type']) not in types:fail(sid,'unknown event type')
            if types[typekey(e['type'])]['kind']!='struct':fail(sid,'event payload must be a struct')
    apps=unique(project['apps'],'id','apps')
    generated_globals={typename({'ref':k[0],'version':k[1]}).lower() for k in types}|{'registry','binding','valid','bytes','to_wire','from_wire','amw','amw_wire','amw_generated','domain_id'}
    for aid,a in apps.items():
        name(aid,'app');object_(a,['id','provides','requires'],path=aid)
        if aid.lower() in generated_globals:fail(aid,'generated C++ name collision')
        generated_globals.add(aid.lower())
        used=set()
        members={'runtime',aid}
        for direction in ('provides','requires'):
            for port in a[direction]:
                object_(port,['id','interface']+(['events'] if direction=='requires' else []),path=aid);name(port['id'],aid)
                if port['id'] in used:fail(aid,'duplicate port ID')
                used.add(port['id']);ref=port['interface'];object_(ref,['ref','version'],path=aid)
                if ref['ref'] not in services or services[ref['ref']]['version']!=ref['version']:fail(aid,'unknown service/version')
                if direction=='requires':
                    ids={e['id'] for e in services[ref['ref']]['events']}
                    if not isinstance(port['events'],list) or not port['events'] or any(type(x)!=int for x in port['events']) or len(set(port['events']))!=len(port['events']) or not set(port['events'])<=ids:fail(aid,'invalid subscribed events')
                for event in services[ref['ref']]['events']:
                    if direction=='requires' and event['id'] not in port['events']:continue
                    field=port['id']+'_'+event['name']
                    symbols=[field] if direction=='provides' else ['on_'+field,field+'_event_']
                    for symbol in symbols:
                        if symbol in members:fail(aid,'generated C++ member collision: '+symbol)
                        members.add(symbol)
    connection_targets=set()
    for c in project['connections']:
        object_(c,['from','to']);object_(c['from'],['app','provided']);object_(c['to'],['app','required'])
        try:
            src=next(p for p in apps[c['from']['app']]['provides'] if p['id']==c['from']['provided'])
            dst=next(p for p in apps[c['to']['app']]['requires'] if p['id']==c['to']['required'])
        except (KeyError,StopIteration):fail('connections','unknown app/port')
        target=(c['to']['app'],dst['id'])
        if target in connection_targets:fail('connections','input has multiple sources')
        connection_targets.add(target)
        if src['interface']!=dst['interface']:fail('connections','incompatible interfaces')
    transport=dep['transport'];object_(transport,['domain','shared_memory','interface_address','peers']);integer(transport['domain'],0,232,'domain')
    if type(transport['shared_memory'])!=bool:fail('shared_memory','expected bool')
    for ip in ([transport['interface_address']] if transport['interface_address'] else [])+transport['peers']:
        try:ipaddress.IPv4Address(ip)
        except ValueError:fail('transport','invalid IPv4 '+str(ip))
    policies=dep['policies']
    if not isinstance(policies,dict) or not policies:fail('policies','nonempty object required')
    for pid,p in policies.items():
        name(pid,'policy');object_(p,[],list(qos.LEGACY)+['dds'],path=pid)
        qos.validate_overrides(p.get('dds',{}),qos.ENDPOINT_SCOPES,'policies.'+pid+'.dds',fail)
        p=qos.resolve_policy(p)
        for field,low,high in [('queue_samples',1,65536),('queue_bytes',1,1073741824),('history_depth',1,65536),('max_blocking_ms',0,60000)]:integer(p[field],low,high,pid+'.'+field)
        for field,values in [('overflow',['discard_oldest','reject']),('reliability',['best_effort','reliable']),('durability',['volatile','transient_local'])]:
            if p[field] not in values:fail(pid,'invalid '+field)
        for scope in qos.ENDPOINT_SCOPES:qos.check_values(scope,qos.effective(scope,policy=p),'policies.'+pid+'.dds.'+scope,fail)
    qos.validate_overrides(dep.get('qos',{}),qos.GROUP_SCOPES,'deployment.qos',fail)
    instances=unique(dep['instances'],'id','instances');provided_ids=set()
    for iid,i in instances.items():
        name(iid,'instance');object_(i,['id','app','provides','requires','policy'],['event_policies','qos'],iid)
        qos.validate_overrides(i.get('qos',{}),qos.GROUP_SCOPES,iid+'.qos',fail)
        if i['app'] not in apps or i['policy'] not in policies:fail(iid,'unknown app/policy')
        for override in i.get('event_policies',{}).values():
            if override not in policies:fail(iid,'unknown event policy')
        app=apps[i['app']]
        if set(i['provides'])!={p['id'] for p in app['provides']} or set(i['requires'])!={p['id'] for p in app['requires']}:fail(iid,'deployment ports must match app')
        for service_id in i['provides'].values():
            name(service_id,iid)
            if service_id in provided_ids:fail(iid,'duplicate service instance ID')
            provided_ids.add(service_id)
    for iid,i in instances.items():
        for port,target in i['requires'].items():
            object_(target,['instance','provided'],path=iid)
            if target['instance'] not in instances:fail(iid,'unknown source instance')
            source=instances[target['instance']]
            if target['provided'] not in source['provides']:fail(iid,'unknown provided port')
            expected={'from':{'app':source['app'],'provided':target['provided']},'to':{'app':i['app'],'required':port}}
            if expected not in project['connections']:fail(iid,'deployment violates logical connection')
    result={'bundle':copy.deepcopy(bundle),'types':types,'order':order,'services':services,'apps':apps,'instances':instances,'policies':policies}
    for iid,instance in instances.items():
        allowed={e['key'] for e in routes(result,iid)}
        if set(instance.get('event_policies',{}))-allowed:fail(iid,'unknown event policy override key')
    result['warnings']=[]
    result['qos']={iid:qos.instance_values(dep,i) for iid,i in instances.items()}
    for iid,groups in result['qos'].items():
        for scope,values in groups.items():qos.check_values(scope,values,iid+'.qos.'+scope,fail)
        controller_names={f['name'] for f in groups['participant']['flow_controllers']}|{'default'}
        topics={}
        for e in routes(result,iid):
            effective=e['qos'];scope='writer' if e['direction']=='provides' else 'reader'
            where=iid+'.'+e['key']
            if e['topic'] in topics and topics[e['topic']]!=e['topic_qos']:fail(where,'same local Topic has conflicting Topic QoS')
            topics[e['topic']]=e['topic_qos']
            if scope=='writer' and effective['publish_mode.flow_controller'] not in controller_names:fail(where,'unknown flow controller')
            if scope=='writer' and effective['publish_mode.flow_controller']!='default' and effective['publish_mode.kind']!='asynchronous':fail(where,'custom flow controller requires asynchronous publish mode')
            if effective['resource_limits.max_instances']!=1:result['warnings'].append(where+': generated types have no DDS key; max_instances is effectively 1')
            if effective['resource_limits.max_samples']=='unlimited':result['warnings'].append(where+': unlimited DDS history can grow independently of the CM queue')
            if effective['data_sharing.kind']!='off':result['warnings'].append(where+': Data-sharing eligibility and shared directory permissions require target runtime verification')
        for scope,values in groups.items():
            for f in qos.fields_for(scope):
                if f.get('kind')=='thread' and values[f['key']]!=f['default']:result['warnings'].append(iid+'.'+f['key']+': thread settings depend on target OS and permissions')
    # Requested/offered checks use the actual effective endpoint values.
    for iid,i in instances.items():
        for e in routes(result,iid):
            if e['direction']=='requires':
                target=i['requires'][e['port']];src=next(x for x in routes(result,target['instance']) if x['port']==target['provided'] and x['event']['id']==e['event']['id'])
                qos.check_compatible(src['qos'],e['qos'],iid+'.'+e['key']+' <- '+target['instance']+'.'+src['key'],fail)
                wp=result['qos'][target['instance']]['publisher']['partition.names'] or ['']
                rp=result['qos'][iid]['subscriber']['partition.names'] or ['']
                matched=qos.partitions_match(wp,rp)
                if matched is False:
                    fail(iid+'.'+e['key'],'publisher/subscriber partitions do not match')
                if matched is None:result['warnings'].append(iid+'.'+e['key']+': partition patterns require runtime DDS matching verification')
    return result

def routes(model,iid):
    dep=model['bundle']['deployment'];instance=model['instances'][iid];app=model['apps'][instance['app']];result=[]
    for direction in ('provides','requires'):
        for port in app[direction]:
            service=model['services'][port['interface']['ref']]
            if direction=='provides':service_instance=instance['provides'][port['id']]
            else:
                target=instance['requires'][port['id']];service_instance=model['instances'][target['instance']]['provides'][target['provided']]
            for event in service['events']:
                if direction=='requires' and event['id'] not in port['events']:continue
                key=port['id']+'.'+event['name'];policy_name=instance.get('event_policies',{}).get(key,instance['policy'])
                policy=qos.resolve_policy(dep['policies'][policy_name])
                result.append({'key':key,'port':port['id'],'event':event,'direction':direction,'policy_name':policy_name,'policy':policy,
                               'qos':qos.effective('writer' if direction=='provides' else 'reader',policy=policy),
                               'topic_qos':qos.effective('topic',policy=policy),
                               'service_instance':service_instance,'topic':'amw/v1/'+service['id']+'/'+service['version']+'/'+service_instance+'/'+str(event['id'])})
    return result

def load_project(path):
    path=Path(path).resolve();project=read(path)
    # On disk: project envelope keeps semantic model and relocatable source references.
    object_(project,['format_version','type_files','deployment_file','model'])
    if project['format_version']!=1:fail('project','unsupported format')
    library={'format_version':1,'types':[]}
    for item in project['type_files']:
        lib=read(path.parent/item);object_(lib,['format_version','types'])
        if lib['format_version']!=1:fail(item,'unsupported type format')
        library['types'].extend(lib['types'])
    return validate({'types':library,'project':project['model'],'deployment':read(path.parent/project['deployment_file'])})
