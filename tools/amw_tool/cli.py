import argparse
import json
import subprocess
import sys
from pathlib import Path
from .model import load_project, validate, read, ModelError
from .generate import generate
from .package import profiles
from .paths import project_paths
ROOT=Path(__file__).resolve().parents[2]
def configuration(path):
    p=Path(path).resolve();c=read(p)
    for key in ('sdk_prefix','generator_jar','java'):
        if key in c and c[key] and (key!='java' or '/' in c[key] or '\\' in c[key]):
            x=Path(c[key]).expanduser();c[key]=str(x if x.is_absolute() else (p.parent/x).resolve())
    for entry in c.get('delivery_sdks',{}).values():
        for key in ('sdk_prefix',):
            x=Path(entry[key]).expanduser();entry[key]=str(x if x.is_absolute() else (p.parent/x).resolve())
        for key,value in entry.get('extra_files',{}).items():
            x=Path(value).expanduser();entry['extra_files'][key]=str(x if x.is_absolute() else (p.parent/x).resolve())
    return c
def save_bundle(directory,b):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    for name,value in [('types.cmtypes.json',b['types']),('deployment.json',b['deployment']),('project.cm.json',{'format_version':1,'type_files':['types.cmtypes.json'],'deployment_file':'deployment.json','model':b['project']})]:
        p=directory/name;tmp=p.with_suffix(p.suffix+'.tmp');tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');tmp.replace(p)
    return directory/'project.cm.json'
def main(argv=None):
    parser=argparse.ArgumentParser(prog='amw');sub=parser.add_subparsers(dest='command',required=True)
    for command in ('validate','generate','gui','build','doctor'):
        p=sub.add_parser(command);p.add_argument('--config',default=str(ROOT/'config.local.json'))
        if command!='doctor':p.add_argument('--project',default=str(ROOT/'examples/demo/project.cm.json'))
        if command in ('generate','build'):p.add_argument('--output',help='output directory (default: out/delivery/<project_id>/src-gen)')
        if command=='build':
            p.add_argument('--build-dir',default=str(ROOT/'out/build/native'));p.add_argument('--toolchain');p.add_argument('--build-type',choices=['Debug','Release','RelWithDebInfo'],default='Debug');p.add_argument('--demo',action='store_true')
        if command=='gui':p.add_argument('--port',type=int,default=8765)
    args=parser.parse_args(argv)
    try:
        if args.command=='validate':m=load_project(args.project);print(json.dumps({'valid':True,'types':len(m['types']),'apps':len(m['apps']),'instances':len(m['instances']),'warnings':m['warnings']},ensure_ascii=False));return 0
        c=configuration(args.config)
        if args.command=='doctor':
            selected=profiles(c)
            result=subprocess.run([c.get('java','java'),'-jar',c['generator_jar'],'-version'],capture_output=True,text=True,check=True)
            assert '4.3.0' in result.stdout,'generator version mismatch'
            print(json.dumps({'delivery_sdks':{p:str(v[0]) for p,v in selected.items()},'generator':result.stdout.strip(),'binding':'fastdds'},indent=2));return 0
        if args.command=='gui':
            from .server import serve
            serve(Path(args.project),c,args.port);return 0
        m=load_project(args.project)
        if args.output is None:args.output=project_paths(ROOT,m['bundle']['project']['project_id'])['output']
        manifest=generate(m,args.output,c);print('Generated',Path(args.output).resolve(),manifest['model_sha256'])
        if args.command=='build':
            command=['cmake','-S',str(ROOT),'-B',str(Path(args.build_dir).resolve()),'-DAMW_GENERATED_DIR='+str(Path(args.output).resolve()),'-DCMAKE_BUILD_TYPE='+args.build_type,'-DAMW_BUILD_DEMO='+('ON' if args.demo else 'OFF')]
            if args.toolchain:command+=['-DCMAKE_TOOLCHAIN_FILE='+str(Path(args.toolchain).resolve()),'-DBUILD_TESTING=OFF']
            subprocess.run(command,check=True);subprocess.run(['cmake','--build',args.build_dir,'--parallel','4'],check=True)
        return 0
    except (ModelError,ValueError,KeyError,AssertionError,OSError,subprocess.CalledProcessError) as e:print(str(e),file=sys.stderr);return 2
