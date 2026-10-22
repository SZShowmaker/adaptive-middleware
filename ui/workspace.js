// Workspace state is presentation-only: filtering, inspecting and switching
// views never mutate the model or its undo/save history.
let inspectedType=null;
const typeKey=t=>t.id+'@'+t.version;
function typeReferences(t){
 const refs=[];
 for(const f of t.fields||[]){let d=f.type;while(d&&typeof d==='object'&&['array','sequence'].includes(d.kind))d=d.element;if(d&&d.ref)refs.push(d.ref+'@'+d.version);}
 return [...new Set(refs)];
}
function outputTypeUses(){
 const uses=[];
 for(const app of model.project.apps)for(const port of app.provides)for(const event of service(port.interface)?.events||[])uses.push({key:event.type.ref+'@'+event.type.version,label:app.id+'.'+port.id+'.'+event.name});
 return uses;
}
function renderTypeLibrary(){
 const list=$('types'),scroll=list.scrollTop,library=model.types.types,inspector=createTypeInspector(library),used=new Set(outputTypeUses().map(x=>x.key));
 const query=$('search').value.trim().toLowerCase(),words=query.split(/\s+/).filter(Boolean),filter=$('typeFilter').value;
 list.replaceChildren();let total=0;
 for(const [label,predicate] of [['用于消息输出',t=>used.has(typeKey(t))],['其他结构体',t=>t.kind==='struct'&&!used.has(typeKey(t))],['枚举',t=>t.kind==='enum'&&!used.has(typeKey(t))]]){
  const entries=[];
  for(const t of library){
   if(!predicate(t)||(filter==='used'&&!used.has(typeKey(t)))||(['struct','enum'].includes(filter)&&t.kind!==filter))continue;
   const paths=inspector.paths(t),text=[t.id,t.version,t.description,...paths,...(t.fields||[]).flatMap(f=>[f.description||'',f.unit||'']),...(t.enumerators||[])].join(' ').toLowerCase();
   if(!words.every(w=>text.includes(w)))continue;
   entries.push({type:t,paths});
  }
  if(!entries.length)continue;
  list.append(el('h3',label+' · '+entries.length,'library-group'));
  for(const {type:t,paths} of entries){
   const button=el('button',undefined,'library-type');button.dataset.type=typeKey(t);button.title=t.id+' @'+t.version;button.setAttribute('aria-label','查看类型 '+t.id+' @'+t.version);button.setAttribute('aria-pressed',String(inspectedType===typeKey(t)));
   button.append(el('strong',t.id),el('small',(t.kind==='enum'?'枚举 · '+t.enumerators.length+' 项':'结构体 · '+t.fields.length+' 个字段')+' · v'+t.version));
   if(query){const path=paths.find(p=>words.some(w=>p.toLowerCase().includes(w))),reason=path?'字段：'+path:'匹配名称、说明、单位或枚举项';const match=el('small',reason,'type-match');match.title=reason;button.append(match);}
   button.onclick=()=>openTypeDetail(typeKey(t));list.append(button);total++;
  }
 }
 $('typeCount').textContent=total+' / '+library.length;
 if(!total)list.append(el('p',library.length?'没有匹配类型。请调整搜索词或筛选条件。':'还没有消息类型。新建或导入类型 JSON 开始配置。','empty-state'));
 list.scrollTop=scroll;
}
function openTypeDetail(key){
 const library=model.types.types,t=library.find(t=>typeKey(t)===key);if(!t)return;
 inspectedType=key;renderTypeLibrary();const body=$('typeDetailBody'),inspector=createTypeInspector(library),map=new Map(library.map(t=>[typeKey(t),t]));
 $('typeDetailTitle').textContent=t.id+' @'+t.version;body.replaceChildren();
 const actions=el('div',undefined,'row'),edit=el('button','编辑结构'),remove=el('button','删除类型');
 edit.onclick=()=>{$('typeDetailDialog').close();editType(clone(t));};remove.onclick=()=>{$('typeDetailDialog').close();removeType(t);};actions.append(edit,remove);body.append(actions);
 if(t.description){const description=el('details');description.append(el('summary','类型说明'),el('p',t.description,'type-description'));body.append(description);}
 const shape=el('div',undefined,'type-shape');shape.append(el('h3',t.kind==='enum'?'枚举成员':'字段结构'));inspector.fields(t,shape,new Set());body.append(shape);
 function relation(title,keys){
  const section=el('section');section.append(el('h3',title));
  if(!keys.length)section.append(el('p','无','muted'));
  for(const ref of keys){const button=el('button',ref.replace('@',' @'),'reference-link');button.disabled=!map.has(ref);button.onclick=()=>openTypeDetail(ref);section.append(button);}
  body.append(section);
 }
 relation('直接依赖的类型',typeReferences(t));
 relation('直接引用它的类型',library.filter(x=>typeReferences(x).includes(key)).map(typeKey));
 function contains(root,target,seen=new Set()){
  if(root===target)return true;if(seen.has(root)||!map.has(root))return false;seen.add(root);
  return typeReferences(map.get(root)).some(ref=>contains(ref,target,seen));
 }
 const uses=outputTypeUses().filter(use=>contains(use.key,key)),section=el('section');section.id='typeOutputUses';section.append(el('h3','相关 App 输出'));
 if(!uses.length)section.append(el('p','尚未用于 App 输出','muted'));
 for(const use of uses)section.append(el('p',use.label+(use.key===key?' · 直接输出':' · 嵌套于 '+use.key.replace('@',' @'))));body.append(section);
 const json=el('details');json.append(el('summary','查看类型 JSON'),el('pre',JSON.stringify(t,null,2)));body.append(json);
 if(!$('typeDetailDialog').open)$('typeDetailDialog').showModal();
 $('typeDetailDialog').scrollTop=0;
}
$('closeTypeDetail').onclick=()=>$('typeDetailDialog').close();
$('typeDetailDialog').addEventListener('close',()=>{const button=[...$('types').querySelectorAll('button')].find(b=>b.dataset.type===inspectedType);(button||$('search')).focus({preventScroll:true});});
$('typeFilter').onchange=()=>{$('types').scrollTop=0;renderTypeLibrary();};
function setWorkspaceView(view){
 for(const name of ['apps','flow']){const active=name===view;$(name+'View').hidden=!active;$(name+'Tab').setAttribute('aria-selected',String(active));$(name+'Tab').tabIndex=active?0:-1;}
 if(view==='flow')requestAnimationFrame(fitFlow);
}
for(const name of ['apps','flow']){
 $(name+'Tab').onclick=()=>setWorkspaceView(name);
 $(name+'Tab').onkeydown=e=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(e.key)){e.preventDefault();const next=e.key==='Home'?'apps':e.key==='End'?'flow':name==='apps'?'flow':'apps';setWorkspaceView(next);$(next+'Tab').focus();}};
}
$('advancedTools').addEventListener('click',e=>{if(e.target.closest('button'))$('advancedTools').open=false;});
document.addEventListener('click',e=>{if(!$('advancedTools').contains(e.target))$('advancedTools').open=false;});
$('advancedTools').addEventListener('keydown',e=>{if(e.key==='Escape'){$('advancedTools').open=false;$('advancedTools').querySelector('summary').focus();}});
function showResult(value){
 $('result').textContent=JSON.stringify(value,null,2);
 const messages=value.error?[value.error]:value.warnings||[];
 $('resultMessages').replaceChildren(...messages.map(message=>el('li',message)));$('resultMessages').hidden=!messages.length;
}
