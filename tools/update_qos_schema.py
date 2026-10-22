#!/usr/bin/env python3
"""Regenerate the QoS portions of all standalone schemas; --check detects drift."""
import argparse
import json
from pathlib import Path
from amw_tool.qos import scoped_schema, GROUP_SCOPES, ENDPOINT_SCOPES

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args=parser.parse_args()
    changed=[]
    for path in sorted((Path(__file__).resolve().parents[1]/'schemas').glob('*.schema.json')):
        original=path.read_text(encoding='utf-8'); schema=json.loads(original)
        definitions=schema['definitions']
        definitions['policy']['required']=[]
        definitions['policy']['properties']['dds']=scoped_schema(ENDPOINT_SCOPES)
        definitions['instance']['properties']['qos']=scoped_schema(GROUP_SCOPES)
        definitions['deployment']['properties']['qos']=scoped_schema(GROUP_SCOPES)
        updated=json.dumps(schema,ensure_ascii=False,indent=2)+'\n'
        if updated!=original:
            changed.append(path.name)
            if not args.check:path.write_text(updated,encoding='utf-8')
    if args.check and changed:parser.exit(1,'stale QoS schemas: '+', '.join(changed)+'\n')

if __name__=='__main__':main()
