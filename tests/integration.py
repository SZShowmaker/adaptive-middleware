"""Run in an isolated network namespace; no device or existing application is involved."""
import json,re,subprocess,sys,time
from pathlib import Path
build=Path(sys.argv[1]).resolve();processes=[];results={}
def spawn(name,*args):
    p=subprocess.Popen([str(build/name),*args],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True);processes.append(p);return p
try:
    first=spawn('amw_consumer','monitor','3');remaining=spawn('amw_consumer','recorder','7');isolated=spawn('amw_consumer','rear_monitor','4')
    time.sleep(.4);writer=spawn('amw_producer','camera_front','380')
    for name,p in [('early_reader',first),('remaining_reader',remaining),('other_instance',isolated),('writer',writer)]:
        output=p.communicate(timeout=15)[0];results[name]={'code':p.returncode,'output':output}
    assert results['early_reader']['code']==0,results
    assert results['remaining_reader']['code']==0,results
    n=lambda k:int(re.search(r'frames=(\d+)',results[k]['output'])[1])
    assert n('remaining_reader')>n('early_reader')+50,results
    assert results['other_instance']['code']==3 and n('other_instance')==0,results
    assert results['writer']['code']==0,results
    print(json.dumps(results,indent=2));print('PASS: two message types, reader departure, isolated service instance')
finally:
    for p in processes:
        if p.poll() is None:p.terminate()
    for p in processes:
        try:p.wait(timeout=3)
        except subprocess.TimeoutExpired:p.kill();p.wait()
