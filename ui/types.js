// Structured type editing. The backend remains the authority for all type rules.
function typeInput(label, value, name, parent) {
 const input=el('input');input.value=value??'';input.dataset.field=name;
 const wrapper=el('label',label);wrapper.append(input);parent.append(wrapper);return input;
}
function descriptorEditor(value='uint32') {
 const node=el('div',undefined,'descriptor-editor'),details=el('div');
 const primitives=['bool','uint8','int8','uint16','int16','uint32','int32','uint64','int64','float32','float64'];
 const options=primitives.map(x=>[x,x]);
 options.push(['string','字符串'],['array','定长数组'],['sequence','有界列表']);
 for(const t of model.types.types)options.push(['ref:'+t.id+'@'+t.version,t.id+' @'+t.version]);
 const selected=typeof value==='string'?value:value.ref?'ref:'+value.ref+'@'+value.version:value.kind;
 if(!options.some(([v])=>v===selected))options.push([selected,selected]);
 const kind=select(options);kind.dataset.field='descriptor';kind.value=selected;
 let bound,child;
 function draw(initial){
  details.replaceChildren();bound=null;child=null;
  if(['string','array','sequence'].includes(kind.value)){
   bound=typeInput(kind.value==='array'?'元素个数':'最大长度',initial?.length??initial?.max_length??16,'bound',details);
   bound.type='number';bound.min='1';bound.max='1048576';
  }
  if(['array','sequence'].includes(kind.value)){
   details.append(el('small','元素类型'));child=descriptorEditor(initial?.element??'uint32');details.append(child.node);
  }
 }
 kind.onchange=()=>draw();draw(typeof value==='object'?value:null);node.append(kind,details);
 return {node,read(){
  const k=kind.value;
  if(k.startsWith('ref:')){const [ref,version]=k.slice(4).split('@');return {ref,version};}
  if(k==='string')return {kind:k,max_length:Number(bound.value)};
  if(k==='array'||k==='sequence')return {kind:k,[k==='array'?'length':'max_length']:Number(bound.value),element:child.read()};
  return k;
 }};
}
async function commitTypes(library, baseRevision) {
 await api('types',library);
 if(revision!==baseRevision)throw Error('校验期间工程已变化，请重新打开编辑窗口');
 change(()=>model.types=library);
}
function editType(original=null) {
 const baseRevision=revision,body=el('div'),identity=el('div',undefined,'row');body.append(identity);
 const id=typeInput('类型 ID',original?.id??'','type-id',identity);
 const version=typeInput('版本',original?.version??'1.0.0','type-version',identity);
 const kind=select([['struct','结构体'],['enum','枚举']]);kind.dataset.field='type-kind';kind.value=original?.kind??'struct';identity.append(kind);
 if(original){id.disabled=true;version.disabled=true;kind.disabled=true;}
 const description=typeInput('说明',original?.description??'','type-description',body);
 const members=el('div');body.append(members);const rows=[];
 function addField(field={id:Math.max(0,...rows.map(r=>Number(r.id.value)))+1,name:'',type:'uint32'}){
  const node=el('div',undefined,'type-field'),line=el('div',undefined,'row');node.append(line);
  const row={node};row.id=typeInput('字段编号',field.id,'id',line);row.id.type='number';
  row.name=typeInput('字段名',field.name,'name',line);
  row.type=descriptorEditor(field.type);node.append(row.type.node);
  row.unit=typeInput('单位（可选）',field.unit,'unit',line);
  row.description=typeInput('说明（可选）',field.description,'description',node);
  const remove=el('button','移除字段');remove.onclick=()=>{rows.splice(rows.indexOf(row),1);node.remove();};node.append(remove);
  rows.push(row);members.append(node);
 }
 const add=el('button','添加字段');add.id='addTypeField';add.onclick=()=>addField();body.append(add);
 const enumerators=el('textarea');enumerators.dataset.field='enumerators';enumerators.placeholder='每行一个枚举成员，例如 Unknown、Vehicle（各占一行）';enumerators.value=(original?.enumerators??[]).join('\n');body.append(enumerators);
 function show(){members.hidden=add.hidden=kind.value!=='struct';enumerators.hidden=kind.value!=='enum';}
 kind.onchange=show;for(const f of original?.fields??[{id:1,name:'',type:'uint32'}])addField(f);show();
 if(original)body.append(el('p','修改会影响引用此类型的全部 App。已有版本的字段变化需同步更新收发双方；需要共存时请新建类型版本。','muted'));
 modal(original?'编辑消息类型':'新建消息类型',body,async()=>{
  const type={id:id.value.trim(),version:version.value.trim(),kind:kind.value};
  if(description.value)type.description=description.value;
  if(kind.value==='enum')type.enumerators=enumerators.value.split(/\r?\n/).map(x=>x.trim()).filter(Boolean);
  else type.fields=rows.map(r=>{const f={id:Number(r.id.value),name:r.name.value.trim(),type:r.type.read()};if(r.unit.value)f.unit=r.unit.value;if(r.description.value)f.description=r.description.value;return f;});
  const library=clone(model.types),index=library.types.findIndex(t=>t.id===type.id&&t.version===type.version);
  if(!original&&index>=0)throw Error('类型 ID 和版本已存在');
  if(original){if(index<0)throw Error('类型已不存在');library.types[index]=type;}else library.types.push(type);
  await commitTypes(library,baseRevision);
 });
}
function removeType(type){
 if(!confirm('删除 '+type.id+' @'+type.version+'？被其他类型或消息引用时将拒绝删除。'))return;
 const candidate=clone(model),baseRevision=revision;
 candidate.types.types=candidate.types.types.filter(t=>!(t.id===type.id&&t.version===type.version));
 if(candidate.project.service_interfaces.some(s=>s.events.some(e=>e.type.ref===type.id&&e.type.version===type.version))){report('类型被输出消息引用，请先修改对应输出',true);return;}
 const checked=candidate.types.types.length?api('types',candidate.types):Promise.resolve();
 checked.then(()=>{
  if(revision!==baseRevision)throw Error('工程已变化，请重试');
  change(()=>model=candidate);
 }).catch(e=>report(e.message,true));
}
$('newType').onclick=()=>editType();
