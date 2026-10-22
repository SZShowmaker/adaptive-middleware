function createTypeInspector(library){
 const key=t=>t.id+'@'+t.version,types=new Map(library.map(t=>[key(t),t]));
 // Index paths through references/arrays without expanding array elements.
 // An imported draft may contain cycles or missing refs before validation.
 function fieldPaths(type,prefix='',seen=new Set()){
  if(seen.has(key(type)))return [];
  const branch=new Set(seen);branch.add(key(type));const paths=[];
  for(const field of type.fields||[]){
   let path=prefix+field.name,d=field.type;paths.push(path);
   while(d&&typeof d==='object'&&['array','sequence'].includes(d.kind)){path+='[]';d=d.element;}
   if(d&&typeof d==='object'&&d.ref){const target=types.get(d.ref+'@'+d.version);if(target)paths.push(...fieldPaths(target,path+'.',branch));}
  }
  return paths;
 }
 function descriptor(d){
  if(typeof d==='string')return d;
  if(!d||typeof d!=='object')return '未知类型';
  if(d.ref)return d.ref+' @'+d.version;
  if(d.kind==='array'){
   const dimensions=[];let element=d;
   while(element&&element.kind==='array'){dimensions.push('['+element.length+']');element=element.element;}
   return descriptor(element)+' '+dimensions.join('');
  }
  if(d.kind==='sequence')return descriptor(d.element)+' 列表（最多 '+d.max_length+' 项）';
  if(d.kind==='string')return '字符串（最多 '+d.max_length+' 字节）';
  return '未知类型';
 }
 function fields(type,parent,seen){
  if(seen.has(key(type))){parent.append(el('p','循环引用，请先校验类型库','error'));return;}
  const branch=new Set(seen);branch.add(key(type));
  if(type.kind==='enum'){parent.append(el('p',(type.enumerators||[]).join('、')));return;}
  for(const f of type.fields||[]){
   const row=el('details'),title=el('summary',f.name+' · '+descriptor(f.type)+(f.unit?' · 单位 '+f.unit:''));
   row.append(title);parent.append(row);
   // Populate nested structures and lengthy enum descriptions only on demand.
   let populated=false;
   row.addEventListener('toggle',()=>{
    if(!row.open||populated)return;populated=true;
    if(f.description)row.append(el('p',f.description,'type-description'));
    let d=f.type;while(d&&typeof d==='object'&&['array','sequence'].includes(d.kind))d=d.element;
    if(d&&typeof d==='object'&&d.ref){
     const target=types.get(d.ref+'@'+d.version);
     if(target)fields(target,row,branch);else row.append(el('p','引用类型缺失，请先校验类型库','error'));
    }else if(!f.description)row.append(el('p','无字段说明','muted'));
   });
  }
 }
 return {paths:fieldPaths,fields,descriptor};
}

// Search the current library only. Selecting a result stores its full ID/version;
// typing a query never creates a type or silently picks the first match.
function createOutputTypePicker(library,onChange){
 const node=el('div',undefined,'type-picker'),search=el('input');search.type='search';
 search.placeholder='输入类型名、说明或字段名搜索';search.autocomplete='off';
 formField(node,'数据类型',search,'outputTypeSearch');
 const count=el('p',undefined,'muted'),results=el('div',undefined,'type-results'),selection=el('div'),preview=el('details');
 count.id='outputTypeCount';count.setAttribute('aria-live','polite');search.setAttribute('aria-describedby',count.id);
 results.id='outputTypeResults';results.setAttribute('role','group');results.setAttribute('aria-label','匹配的数据类型');
 selection.id='outputTypeSelection';selection.setAttribute('aria-live','polite');preview.id='outputTypePreview';
 node.append(count,results,selection,preview);
 const key=t=>t.id+'@'+t.version;
 let selected=null;
 const lower=s=>String(s||'').toLocaleLowerCase();
 const inspector=createTypeInspector(library),fields=inspector.fields;
 const entries=library.filter(t=>t.kind==='struct').map(t=>({type:t,paths:inspector.paths(t)}));
 function showSelection(){
  selection.replaceChildren();preview.replaceChildren();preview.open=false;preview.hidden=!selected;
  if(!selected){selection.append(el('p','尚未选择类型。请点击搜索结果，搜索文字不会自动成为类型。','muted'));return;}
  selection.append(el('p','完整类型名：'+selected.id+' @'+selected.version));
  const clear=el('button','清除类型选择');clear.type='button';clear.onclick=()=>{selected=null;search.value='';draw();showSelection();onChange();search.focus();};selection.append(clear);
  preview.append(el('summary','结构预览（'+(selected.fields||[]).length+' 个字段）'));
  if(selected.description)preview.append(el('p',selected.description,'type-description'));
  fields(selected,preview,new Set());
 }
 function draw(){
  const query=lower(search.value.trim()),tokens=query.split(/\s+/).filter(Boolean),matches=[];
  for(const entry of entries){
   const t=entry.type,name=lower(t.id+' @'+t.version),description=lower(t.description),paths=entry.paths;
   const haystack=name+' '+description+' '+paths.map(lower).join(' ');
   if(!tokens.every(word=>haystack.includes(word)))continue;
   const hitPaths=query?paths.filter(path=>tokens.some(word=>lower(path).includes(word))):[];
   const short=lower(t.id.split('.').pop());
   const score=!query?0:lower(t.id)===query||short===query?0:lower(t.id).startsWith(query)||short.startsWith(query)?1:name.includes(query)?2:description.includes(query)?3:4;
   matches.push({type:t,hitPaths,score});
  }
  matches.sort((a,b)=>a.score-b.score);
  count.textContent=matches.length+' / '+entries.length+' 个结构体'+(query?'匹配；点击一项确认类型。':'；可直接选择，也可输入关键词。');
  results.replaceChildren();
  if(!matches.length){results.append(el('p','没有匹配的结构体。请尝试类型名或字段名；需要新类型时先在类型库中定义。','muted'));return;}
  for(const {type:t,hitPaths} of matches){
   const button=el('button',undefined,'type-result');button.type='button';button.dataset.type=key(t);
   button.setAttribute('aria-label',t.id+' @'+t.version);button.setAttribute('aria-pressed',selected===t?'true':'false');
   button.append(el('strong',t.id.split('.').pop()+' @'+t.version),el('span',t.id,'muted'));
   if(t.description)button.append(el('span',t.description.length>120?t.description.slice(0,120)+'…':t.description,'muted'));
   for(const path of hitPaths.slice(0,3))button.append(el('span','匹配字段：'+path,'type-match'));
   if(hitPaths.length>3)button.append(el('span','另有 '+(hitPaths.length-3)+' 个字段路径匹配，可展开结构预览查看。','muted'));
   button.onclick=()=>{selected=t;draw();showSelection();onChange();results.querySelectorAll('button')[matches.findIndex(x=>x.type===t)]?.focus({preventScroll:true});};
   results.append(button);
  }
 }
 search.oninput=()=>{selected=null;draw();showSelection();onChange();};
 search.onkeydown=e=>{
  const buttons=results.querySelectorAll('button');
  if(buttons.length&&['ArrowDown','ArrowUp'].includes(e.key)){e.preventDefault();buttons[e.key==='ArrowDown'?0:buttons.length-1].focus();}
 };
 results.onkeydown=e=>{
  const buttons=[...results.querySelectorAll('button')],index=buttons.indexOf(document.activeElement);
  if(index<0||!['ArrowDown','ArrowUp','Home','End'].includes(e.key))return;
  e.preventDefault();const next=e.key==='Home'?0:e.key==='End'?buttons.length-1:Math.max(0,Math.min(buttons.length-1,index+(e.key==='ArrowDown'?1:-1)));buttons[next].focus();
 };
 draw();showSelection();return {node,get value(){return selected?key(selected):'';}};
}
