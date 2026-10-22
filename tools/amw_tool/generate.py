import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from .package import assemble, sha256, check_cancel, safe_relative
from .model import PRIMITIVES, ModelError, canonical, digest, typename, routes

def cpp(d,wire=False):
    if isinstance(d,str):return PRIMITIVES[d][0]
    if 'ref' in d:return ('amw_wire::' if wire else '')+typename(d)
    if d['kind']=='string':return 'std::string'
    inner=cpp(d['element'],wire)
    return f'std::array<{inner}, {d["length"]}>' if d['kind']=='array' else f'std::vector<{inner}>'
def idl(d):
    if isinstance(d,str):return PRIMITIVES[d][1]
    if 'ref' in d:return typename(d)
    if d['kind']=='string':return 'string<'+str(d['max_length'])+'>'
    if d['kind']=='sequence':return f'sequence<{idl(d["element"])}, {d["max_length"]}>'
    return idl(d['element'])
def conversion(d,expr,to=True):
    if isinstance(d,str) or d.get('kind')=='string':return expr
    if 'ref' in d:return ('to_wire' if to else 'from_wire')+'('+expr+')'
    target=cpp(d,to);inner=conversion(d['element'],'item',to)
    if d['kind']=='sequence':return f'[&]{{ {target} out; out.reserve(({expr}).size()); for(const auto& item:({expr})) out.push_back({inner}); return out; }}()'
    return f'[&]{{ {target} out{{}}; size_t index=0; for(const auto& item:({expr})) out[index++]={inner}; return out; }}()'
def valid(d,expr):
    if isinstance(d,str):return f'std::isfinite({expr})' if d.startswith('float') else 'true'
    if 'ref' in d:return f'valid({expr})'
    if d['kind']=='string':return f'({expr}).size()<={d["max_length"]}'
    bound=f'({expr}).size()<={d["max_length"]} && ' if d['kind']=='sequence' else ''
    return bound+f'std::all_of(({expr}).begin(),({expr}).end(),[](const auto& item){{return {valid(d["element"],"item")};}})'
def bytes_(d,expr):
    if isinstance(d,str):return f'sizeof({expr})'
    if 'ref' in d:return f'bytes({expr})'
    if d['kind']=='string':return f'(sizeof({expr})+({expr}).capacity())'
    extra=f'sizeof({expr})' if d['kind']=='sequence' else '0'
    if d['kind']=='sequence':extra+=f'+(({expr}).capacity()-({expr}).size())*sizeof(typename std::decay_t<decltype({expr})>::value_type)'
    return f'[&]{{size_t n={extra};for(const auto& item:({expr})) n+={bytes_(d["element"],"item")};return n;}}()'
def write(path,text):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text,encoding='utf-8')
# A version-maintained handbook, copied byte-for-byte for every project.
GUIDE_FILES = (
    'README.md', 'INTEGRATION.md', 'API.md', 'LOGGING.md', 'QOS.md',
    'examples/logging.cpp', 'examples/logging.xml',
    'examples/CMakeLists.txt', 'examples/publisher.cpp', 'examples/subscriber.cpp',
)

def emit_guide(root):
    source = Path(__file__).resolve().parents[2] / 'docs' / 'app-guide'
    for relative in GUIDE_FILES:
        target = root / 'guide' / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / relative, target)
    write(root / 'README.md', """# src-gen 应用接入包

将整个 src-gen 文件夹交给每位 App 开发者。消息/App 接口、CM、日志、时间工具和三个平台的 DDS SDK 均在包内。
接入步骤见 [通用开发手册](guide/README.md) 和 [集成指南](guide/INTEGRATION.md)。
业务包含 apps.hpp、amw/log/log.hpp、amw/time/time.hpp，通过 amw::app 或独立的 amw::log / amw::time targets 接入。
接口见 generated/apps.hpp 和 generated/types.hpp，实例/路由见 metadata/。
工具链由应用构建时选择，ARM 工具链路径可配置。无需另行安装中间件或 DDS SDK。
重新编辑工程：在配置工作台点击“打开工程”，选择本目录的 `<工程ID>.amw.json`。
该文件包含本次生成使用的类型、App、连接、部署、网络及 QoS 配置，与 metadata/model.resolved.json 内容一致。
metadata/qos.effective.json 是含默认值的有效 QoS 快照，metadata/routes.json 是实例路由；两者用于检查，不是工程入口。
config/logging.xml 是日志启动配置；本机 SDK、生成器路径和界面的自定义生成位置不保存在工程包中。
修改后可保存草稿或向包外导出工程，再重新生成；不要直接编辑包内的工程 JSON。
不要手改本包或将业务文件/构建缓存放入包内；完整内容由 generation-manifest.json 保护。
""")

def emit_qos(model, root):
    from . import qos
    code=['#pragma once', '// Private Fast DDS configuration generated from validated effective values.',
          '#include <amw/cm/fastdds_binding.hpp>', '#include <fastdds/utils/IPLocator.hpp>',
          '#include <fastdds/rtps/flowcontrol/FlowControllerDescriptor.hpp>', '#include <limits>', '#include <stdexcept>',
          'namespace amw_generated_qos {', 'namespace dds=eprosima::fastdds::dds;', 'namespace rtps=eprosima::fastdds::rtps;',
          'inline amw::cm::fastdds::QosConfig make(const std::string& instance) {', 'amw::cm::fastdds::QosConfig q;']
    effective={}
    for idx,(iid,instance) in enumerate(model['instances'].items()):
        code.append(('if' if idx==0 else 'else if')+'(instance=='+qos.cpp_string(iid)+'){')
        groups=qos.instance_values(model['bundle']['deployment'],instance)
        effective[iid]={'groups':groups,'endpoints':{}}
        for scope,values in groups.items():code.extend(qos.emit_values(scope,values,'q.'+scope))
        for route in routes(model,iid):
            key=route['key'];scope='writer' if route['direction']=='provides' else 'reader'
            code.extend(qos.emit_values('topic',route['topic_qos'],'q.topics['+qos.cpp_string(key)+']'))
            code.extend(qos.emit_values(scope,route['qos'],'q.'+scope+'s['+qos.cpp_string(key)+']'))
            effective[iid]['endpoints'][key]={'scope':scope,'policy':route['policy_name'],'topic':route['topic_qos'],'effective':route['qos']}
        code.append('}')
    code.extend(['else throw std::invalid_argument("unknown QoS instance");','return q;','}','}'])
    write(root/'generated/qos.hpp','\n'.join(code)+'\n')
    write(root/'metadata/qos.effective.json',json.dumps({'version':qos.VERSION,'instances':effective,'warnings':model.get('warnings',[])},ensure_ascii=False,indent=2)+'\n')

def emit(model,root):
    types=model['types'];dto=['#pragma once','#include <algorithm>','#include <array>','#include <cmath>','#include <cstdint>','#include <string>','#include <type_traits>','#include <vector>','namespace amw_generated {'];wire=['module amw_wire {'];glue=['#include "apps.hpp"','#include "messagesPubSubTypes.hpp"','#include <amw/cm/fastdds_binding.hpp>','#include <stdexcept>','namespace amw_generated {']
    for key in model['order']:
        t=types[key];n=typename({'ref':key[0],'version':key[1]})
        if t['kind']=='enum':
            dto.append('enum class '+n+' : int32_t {'+', '.join(t['enumerators'])+'};')
            wire.append('enum '+n+' {'+', '.join(n+'_'+x for x in t['enumerators'])+'};')
            dto.append(f'inline bool valid({n} v){{return static_cast<int32_t>(v)>=0 && static_cast<int32_t>(v)<{len(t["enumerators"])};}}')
            dto.append(f'inline size_t bytes({n}){{return sizeof({n});}}')
            glue.extend([f'amw_wire::{n} to_wire({n} x){{return static_cast<amw_wire::{n}>(x);}}',f'{n} from_wire(amw_wire::{n} x){{return static_cast<{n}>(x);}}'])
        else:
            dto.append('struct '+n+' {');wire.append('@final struct '+n+' {')
            for f in t['fields']:
                d=f['type'];dto.append(f'  {cpp(d)} {f["name"]}{{}};')
                suffix=''
                while isinstance(d,dict) and d.get('kind')=='array':suffix+='['+str(d['length'])+']';d=d['element']
                wire.append(f'  @id({f["id"]}) {idl(d)} {f["name"]}{suffix};')
            dto.append('};');wire.append('};')
            dto.append(f'inline bool valid(const {n}& v){{return '+ ' && '.join('('+valid(f['type'],'v.'+f['name'])+')' for f in t['fields'])+';}')
            dto.append(f'inline size_t bytes(const {n}& v){{return '+ '+'.join(bytes_(f['type'],'v.'+f['name']) for f in t['fields'])+';}')
            glue.append(f'amw_wire::{n} to_wire(const {n}& x){{amw_wire::{n} out;')
            for f in t['fields']:glue.append(f'out.{f["name"]}({conversion(f["type"],"x."+f["name"])});')
            glue.append('return out;}')
            glue.append(f'{n} from_wire(const amw_wire::{n}& x){{{n} out;')
            for f in t['fields']:glue.append(f'out.{f["name"]}={conversion(f["type"],"x."+f["name"]+"()",False)};')
            glue.append('return out;}')
    dto.append('}');wire.append('};')
    glue.append('amw::cm::fastdds::TypeRegistry registry(){amw::cm::fastdds::TypeRegistry r;')
    for key in model['order']:
        if types[key]['kind']!='struct':continue
        ref={'ref':key[0],'version':key[1]};n=typename(ref);tid=key[0]+'@'+key[1]
        glue.append(f'r[{json.dumps(tid)}]={{eprosima::fastdds::dds::TypeSupport(new amw_wire::{n}PubSubType()),[](const void* p)->std::shared_ptr<void>{{return std::make_shared<amw_wire::{n}>(to_wire(*static_cast<const {n}*>(p)));}},[](const void* p)->amw::cm::Sample{{return std::make_shared<const {n}>(from_wire(*static_cast<const amw_wire::{n}*>(p)));}}}};')
    glue.append('return r;}')
    transport=model['bundle']['deployment']['transport']
    glue.insert(1,'#include "qos.hpp"')
    glue.insert(1,'#include <utility>')
    glue.append('amw::cm::BindingFactory binding(const std::string& instance, amw::cm::NetworkOptions network){return [instance,network]{amw::cm::TransportConfig c;')
    glue.append(f'c.domain={transport["domain"]};c.shared_memory={str(transport["shared_memory"]).lower()};c.interface_address={json.dumps(transport["interface_address"])};')
    for peer in transport['peers']:glue.append(f'c.peers.push_back({json.dumps(peer)});')
    glue.append('c=amw::cm::apply_network_options(std::move(c),network);return amw::cm::fastdds::create(c,registry(),::amw_generated_qos::make(instance));};}')
    header=['#pragma once','#include "types.hpp"','#include <amw/cm/cm.hpp>','namespace amw_generated {']
    header.append(f'inline constexpr uint32_t domain_id = {transport["domain"]};')
    for aid,app in model['apps'].items():
        header.append(f'class {aid} {{ public: explicit {aid}(const std::string& instance, amw::cm::NetworkOptions network = {{}}); amw::cm::Runtime runtime;')
        glue.append(f'{aid}::{aid}(const std::string& instance, amw::cm::NetworkOptions network):runtime(binding(instance,std::move(network))) {{')
        instance_ids=[iid for iid,i in model['instances'].items() if i['app']==aid]
        if not instance_ids:raise ModelError('each demo app needs at least one deployment instance')
        for idx,iid in enumerate(instance_ids):
            glue.append(('if' if idx==0 else 'else if')+f'(instance=={json.dumps(iid)}){{')
            for route in routes(model,iid):
                e=route['event'];n=typename(e['type']);field=route['key'].replace('.','_');policy=route['policy']
                glue.append('{amw::cm::Event e;')
                for key,val in [('key',route['key']),('topic',route['topic']),('type_id',e['type']['ref']+'@'+e['type']['version'])]:glue.append(f'e.{key}={json.dumps(val)};')
                for key in ['queue_samples','queue_bytes','history_depth','max_blocking_ms']:glue.append(f'e.policy.{key}={policy[key]};')
                for key,value in [('discard_oldest',policy['overflow']=='discard_oldest'),('reliable',policy['reliability']=='reliable'),('transient_local',policy['durability']=='transient_local')]:glue.append(f'e.policy.{key}={str(value).lower()};')
                glue.append(f'e.validate=[](const void* p){{return valid(*static_cast<const {n}*>(p));}};e.size=[](const void* p){{return bytes(*static_cast<const {n}*>(p));}};')
                if route['direction']=='provides':glue.append(f'{field}=amw::cm::Publisher<{n}>(runtime.add_publisher(e));')
                else:glue.append(f'runtime.expect_subscription(e.key);{field}_event_=std::move(e);')
                glue.append('}')
            glue.append('}')
        glue.append('else throw std::invalid_argument("instance does not belong to app");}')
        for direction in ['provides','requires']:
            for port in app[direction]:
                for e in model['services'][port['interface']['ref']]['events']:
                    if direction=='requires' and e['id'] not in port['events']:continue
                    field=port['id']+'_'+e['name'];n=typename(e['type'])
                    if direction=='provides':header.append(f'amw::cm::Publisher<{n}> {field};')
                    else:
                        header.append(f'void on_{field}(std::function<void(std::shared_ptr<const {n}>,amw::cm::SampleInfo)> callback){{ if(!callback) throw std::invalid_argument("empty callback"); runtime.add_subscription({field}_event_,[callback](amw::cm::Sample s,amw::cm::SampleInfo i){{callback(std::static_pointer_cast<const {n}>(s),i);}});}}')
                        header.append(f'private: amw::cm::Event {field}_event_; public:')
        header.append('};')
    header.insert(2,'#include <stdexcept>');header.append('}');glue.append('}')
    write(root/'metadata/messages.idl','\n'.join(wire)+'\n');write(root/'generated/types.hpp','\n'.join(dto)+'\n');write(root/'generated/apps.hpp','\n'.join(header)+'\n');write(root/'generated/apps.cpp','\n'.join(glue)+'\n')
    emit_guide(root)
    emit_qos(model,root)
    project_json=json.dumps(model['bundle'],ensure_ascii=False,indent=2)+'\n'
    write(root/(model['bundle']['project']['project_id']+'.amw.json'),project_json)
    write(root/'metadata/model.resolved.json',project_json)
    write(root/'metadata/routes.json',json.dumps({iid:routes(model,iid) for iid in model['instances']},ensure_ascii=False,indent=2)+'\n')

def generate(model, output, config, cancel=None):
    output=Path(output).resolve()
    for parent in output.parents:
        if (parent/'generation-manifest.json').exists():
            raise ModelError('output must not be nested inside another managed generation directory')
    output.parent.mkdir(parents=True,exist_ok=True)
    lock=output.with_name(output.name+'.lock')
    try:fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    except FileExistsError:raise ModelError('generation lock exists; another generator is active or recovery is needed')
    os.close(fd)
    try:
        if output.exists():
            manifest_path=output/'generation-manifest.json'
            if not manifest_path.is_file():raise ModelError('refusing to overwrite unmanaged output directory')
            old=json.loads(manifest_path.read_text(encoding='utf-8'))
            import hashlib
            expected=set(old['files'])|{'generation-manifest.json'}
            actual={p.relative_to(output).as_posix() for p in output.rglob('*') if p.is_file()}
            if actual!=expected or any(p.is_symlink() for p in output.rglob('*')):raise ModelError('output contains unmanaged files or symlinks; preserve them outside generated directory')
            for rel,sha in old['files'].items():
                check_cancel(cancel)
                if sha256(output/safe_relative(rel))!=sha:raise ModelError('generated file was edited: '+rel)
        return _generate_locked(model,output,config,cancel)
    finally:lock.unlink(missing_ok=True)

def _generate_locked(model,output,config,cancel):
    jar=Path(config['generator_jar']).expanduser().resolve();java=config.get('java','java')
    version=subprocess.run([java,'-jar',str(jar),'-version'],capture_output=True,text=True,check=True).stdout
    if '4.3.0' not in version:raise ModelError('expected Fast DDS-Gen 4.3.0: '+version)
    root=Path(tempfile.mkdtemp(prefix='.amw-generate-',dir=output.parent))
    backup=output.with_name(output.name+'.previous')
    try:
        platforms=assemble(root,config,cancel)
        emit(model,root);(root/'generated/wire').mkdir()
        # Fast DDS-Gen otherwise shares /tmp/messages.idl.cc across concurrent projects.
        preprocessed=root/'.gen-tmp';preprocessed.mkdir()
        command=[java,'-jar',str(jar),'-t',str(preprocessed),'-replace','-flat-output-dir','-d',str(root/'generated/wire'),str(root/'metadata/messages.idl')]
        with subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True) as process:
            try:
                while True:
                    if cancel is not None and cancel.is_set():
                        process.terminate();process.communicate(timeout=5);raise ModelError('generation cancelled; previous output preserved')
                    try:log=process.communicate(timeout=.1)[0];break
                    except subprocess.TimeoutExpired:continue
            except BaseException:
                if process.poll() is None:process.kill();process.communicate()
                raise
        if process.returncode or not (root/'generated/wire/messagesPubSubTypes.hpp').is_file():raise ModelError('Fast DDS-Gen failed:\n'+log)
        if cancel is not None and cancel.is_set():raise ModelError('generation cancelled; previous output preserved')
        shutil.rmtree(preprocessed)
        # Remove random staging paths from official generated comments for deterministic outputs.
        for p in (root/'generated/wire').glob('*'):
            if p.is_file():p.write_text(p.read_text(encoding='utf-8').replace(str(root),'${GENERATION_ROOT}'),encoding='utf-8')
        import hashlib
        files={}
        inode_hashes={}
        for p in sorted(root.rglob('*')):
            if p.is_file():
                check_cancel(cancel)
                stat=p.stat();identity=(stat.st_dev,stat.st_ino)
                if identity not in inode_hashes:inode_hashes[identity]=sha256(p)
                files[p.relative_to(root).as_posix()]=inode_hashes[identity]
        template_hash=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        manifest={'tool_version':'0.2.0','layout_version':2,'platforms':platforms,'template_sha256':template_hash,'format_version':1,'model_sha256':digest(model['bundle']),'generator_version':'4.3.0','generator_sha256':hashlib.sha256(jar.read_bytes()).hexdigest(),'fastdds':'3.6.2.0','fastcdr':'2.3.6','files':files}
        from .qos import VERSION as qos_version
        manifest['qos_defaults_version']=qos_version
        write(root/'generation-manifest.json',json.dumps(manifest,indent=2,sort_keys=True)+'\n')
        if backup.exists():raise ModelError('previous generation backup exists; inspect before retry')
        if output.exists():output.rename(backup)
        try:root.rename(output)
        except BaseException:
            if backup.exists():backup.rename(output)
            raise
        if backup.exists():shutil.rmtree(backup)
        return manifest
    finally:
        if root.exists():shutil.rmtree(root)
