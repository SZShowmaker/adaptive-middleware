// Structured controls are driven by the server's versioned QoS catalogue.
let qosCataloguePromise;
const qosScopeNames={participant:'通信实例 · Participant',publisher:'发布组 · Publisher',subscriber:'订阅组 · Subscriber',topic:'Topic 默认策略',writer:'输出 · DataWriter',reader:'输入 · DataReader'};
const qosEnumLabels={best_effort:'尽力传输',reliable:'可靠传输',volatile:'不保留给晚加入者',transient_local:'保留本地历史',keep_last:'保留最近样本',keep_all:'保留全部（受资源限制）',shared:'共享所有权',exclusive:'独占所有权',automatic:'自动',synchronous:'同步',asynchronous:'异步',off:'关闭',auto:'自动选择',on:'启用',discard_oldest:'丢弃最旧样本',reject:'拒绝新样本'};
const qosEqual=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
function qosInitial(schema){
 if('default' in schema)return clone(schema.default);
 if('const' in schema)return schema.const;
 if(schema.enum)return schema.enum[0];
 if(schema.oneOf)return qosInitial(schema.oneOf[0]);
 if(schema.type==='object')return Object.fromEntries(Object.entries(schema.properties).map(([k,v])=>[k,qosInitial(v)]));
 if(schema.type==='array')return [];
 if(schema.type==='boolean')return false;
 if(schema.type==='integer')return Math.max(0,schema.minimum||0);
 return '';
}
function qosControl(schema,value,onChange,label){
 const node=el('div',undefined,'qos-control');
 if(schema.oneOf){
  const regular=schema.oneOf.find(s=>!('const' in s)),special=schema.oneOf.find(s=>'const' in s);
  const choice=select([['value','指定值'],['special',special.const==='infinite'?'无限时间':'无限容量']]);choice.setAttribute('aria-label',label+' 模式');
  let current=value,remembered=value===special.const?qosInitial(regular):clone(value);
  const detail=el('div');
  function draw(){detail.replaceChildren();choice.value=current===special.const?'special':'value';if(choice.value==='value')detail.append(qosControl(regular,current,v=>{current=v;remembered=clone(v);onChange(v)},label));}
  choice.onchange=()=>{current=choice.value==='special'?special.const:clone(remembered);onChange(current);draw()};
  node.append(choice,detail);draw();return node;
 }
 if(schema.type==='object'){
  const current=clone(value);
  for(const [key,child]of Object.entries(schema.properties)){
   const row=el('label',({seconds:'秒',nanoseconds:'纳秒',initial:'初始容量',maximum:'最大容量',increment:'增长步长',address:'IPv4 地址',port:'端口',name:'名称',value:'值',propagate:'传播给对端',scheduler:'调度策略',period_ms:'周期（毫秒）',max_bytes_per_period:'每周期最大字节数（0 为无限）',sender_thread:'发送线程',scheduling_policy:'调度策略（-1 为系统默认）',priority:'优先级（-2147483648 为系统默认）',affinity:'CPU 亲和掩码（十进制，0 为默认）',stack_size:'栈大小（字节，-1 为系统默认）'})[key]||key);
   row.append(qosControl(child,current[key],v=>{current[key]=v;onChange(clone(current))},label+'.'+key));node.append(row);
  }return node;
 }
 if(schema.type==='array'){
  const items=clone(value),rows=el('div'),add=el('button','增加一项');add.type='button';add.setAttribute('aria-label',label+' 增加一项');
  function draw(){rows.replaceChildren();items.forEach((item,index)=>{
   const row=el('div',undefined,'qos-array-row'),remove=el('button','移除');remove.type='button';remove.setAttribute('aria-label',label+' 移除第 '+(index+1)+' 项');
   row.append(qosControl(schema.items,item,v=>{items[index]=v;onChange(clone(items))},label+'['+index+']'),remove);
   remove.onclick=()=>{items.splice(index,1);onChange(clone(items));draw()};rows.append(row);
  });add.disabled=items.length>=(schema.maxItems||256)}
  add.onclick=()=>{let item=qosInitial(schema.items);if(item&&typeof item==='object'&&'period_ms'in item){item.period_ms=100;item.name='controller'+(items.length+1);item.sender_thread={scheduling_policy:-1,priority:-2147483648,affinity:'0',stack_size:-1}}items.push(item);onChange(clone(items));draw()};
  node.append(rows,add);draw();return node;
 }
 let control;
 if(schema.enum||'const'in schema){const choices=schema.enum||[schema.const];control=select(choices.map(v=>[String(v),qosEnumLabels[v]?qosEnumLabels[v]+' · '+v:String(v)]));control.value=String(value);control.disabled='const'in schema;control.onchange=()=>onChange(choices.find(v=>String(v)===control.value));}
 else if(schema.type==='boolean'){control=el('input');control.type='checkbox';control.checked=value;control.onchange=()=>onChange(control.checked);}
 else{control=el('input');control.type=schema.type==='integer'?'number':'text';control.value=value;if(schema.minimum!==undefined)control.min=schema.minimum;if(schema.maximum!==undefined)control.max=schema.maximum;if(schema.maxLength)control.maxLength=schema.maxLength;if(control.type==='number')control.step='1';control.oninput=()=>onChange(control.type==='number'?(control.value===''?null:Number(control.value)):control.value);}
 control.setAttribute('aria-label',label);node.append(control);return node;
}
function qosEffective(catalog,scope,policy,overrides){
 const values=Object.fromEntries(catalog.fields.filter(f=>f.scopes.includes(scope)).map(f=>[f.key,clone(f.default)]));
 if(policy){const p={...catalog.legacy_defaults,...policy};Object.assign(values,{'reliability.kind':p.reliability,'durability.kind':p.durability,'history.depth':p.history_depth,'reliability.max_blocking_time':{seconds:Math.floor(p.max_blocking_ms/1000),nanoseconds:(p.max_blocking_ms%1000)*1000000},'resource_limits.max_samples':p.history_depth,'resource_limits.max_instances':1,'resource_limits.max_samples_per_instance':p.history_depth,'resource_limits.allocated_samples':p.history_depth});for(const [k,v]of Object.entries(policy.dds?.topic||{}))if(k in values)values[k]=clone(v);Object.assign(values,policy.dds?.[scope]||{});}
 return Object.assign(values,overrides||{});
}
async function openQos(initialInstance=null,initialEndpoint=null){
 try{
  qosCataloguePromise??=fetch('/api/qos-catalog').then(r=>{if(!r.ok)throw Error('无法加载 QoS 参数说明');return r.json()}).catch(e=>{qosCataloguePromise=null;throw e});
  const catalog=await qosCataloguePromise,draft=clone(model.deployment),startedRevision=revision;
  const body=el('div'),toolbar=el('div',undefined,'row'),area=el('div'),error=el('p',undefined,'error');error.id='qosError';error.setAttribute('role','alert');
  const view=select([['policies','消息策略模板'],['global','项目网络与默认 QoS'],['instances','实例与消息策略分配']]);view.id='qosView';view.setAttribute('aria-label','QoS 配置范围');view.value=initialInstance?'instances':'policies';
  const name=select(Object.keys(draft.policies).map(x=>[x,x]));name.id='qosPolicy';name.setAttribute('aria-label','策略模板');
  const scope=select(Object.entries(qosScopeNames));scope.id='qosScope';scope.setAttribute('aria-label','DDS 实体');scope.value='writer';
  const search=el('input');search.placeholder='搜索参数名称 / DDS 名称';search.setAttribute('aria-label','搜索 QoS 参数');
  let selectedInstance=initialInstance||draft.instances[0]?.id,selectedEndpoint=initialEndpoint||'',filter='';
  toolbar.append(view);body.append(el('p','所有参数均有默认值。按需修改，或恢复继承值；应用后保存工程，再校验并生成 src-gen。'),toolbar,area,error);
  function scopedEditor(parent,sc,store,inherited){
   const fields=catalog.fields.filter(f=>f.scopes.includes(sc)),groups=new Map();
   const controls=[];
   function live(){return {...inherited,...store}}
   function refresh(){const values=live();for(const {f,inputs,badge}of controls){const enabled=!f.active_when||Object.entries(f.active_when).every(([k,v])=>values[k]===v);inputs.disabled=!enabled;badge.textContent=(f.key in store?'已自定义':'继承默认值')+(enabled?'':' · 当前模式不使用此项');}}
   for(const f of fields){
    const category={standard:'DDS 标准 QoS',extension:'Fast DDS 扩展',xtypes:'DDS 类型扩展'}[f.category];
    if(!groups.has(category)){const d=el('details'),sum=el('summary',category);d.open=true;d.append(sum);parent.append(d);groups.set(category,d)}
    const row=el('div',undefined,'qos-field');row.dataset.qosKey=f.key;row.dataset.qosScope=sc;row.dataset.search=(f.label+' '+f.key+' '+category).toLowerCase();
    const title=el('div',undefined,'row'),badge=el('small'),reset=el('button','恢复继承');reset.type='button';reset.setAttribute('aria-label',f.key+' 恢复继承');
    const inputs=el('fieldset');inputs.className='qos-inputs';
    function drawControl(){inputs.replaceChildren(qosControl(f.schema,live()[f.key],v=>{store[f.key]=v;refresh()},f.key));}
    reset.onclick=()=>{delete store[f.key];drawControl();refresh()};
    title.append(el('strong',f.label),badge,reset);row.append(title,el('small',f.key),inputs);
    if(f.help)row.append(el('p',f.help,'muted'));
    row.append(el('small','继承值：'+JSON.stringify(inherited[f.key])));groups.get(category).append(row);controls.push({f,inputs,badge});drawControl();
   }
   const unsupported=el('details');unsupported.append(el('summary','不支持的策略 / 选项（查看原因）'));
   for(const item of catalog.unavailable.filter(x=>x.scopes.includes(sc))){const row=el('div',undefined,'qos-field qos-unavailable');row.dataset.search=(item.key+' '+item.reason).toLowerCase();row.append(el('strong',item.key),el('p',item.reason));unsupported.append(row)}
   parent.append(unsupported);refresh();applyFilter();
  }
  function applyFilter(){for(const row of area.querySelectorAll('[data-search]'))row.hidden=!row.dataset.search.includes(filter)}
  search.oninput=()=>{filter=search.value.trim().toLowerCase();applyFilter()};
  function drawPolicy(){
   const policy=draft.policies[name.value];if(!policy)return;
   const actions=el('div',undefined,'row'),id=el('input'),add=el('button','新建默认策略'),copy=el('button','复制当前策略'),remove=el('button','删除策略'),reset=el('button','整份策略恢复默认');
   id.placeholder='新策略 ID';id.setAttribute('aria-label','新策略 ID');
   function insert(value){if(!/^[A-Za-z][A-Za-z0-9_]*$/.test(id.value)||draft.policies[id.value]){error.textContent='策略 ID 需唯一，使用字母开头的字母、数字或下划线';return}draft.policies[id.value]=value;name.append(new Option(id.value,id.value));name.value=id.value;draw()}
   add.onclick=()=>insert({});copy.onclick=()=>insert(clone(policy));
   remove.onclick=()=>{if(Object.keys(draft.policies).length===1||draft.instances.some(i=>i.policy===name.value||Object.values(i.event_policies||{}).includes(name.value))){error.textContent='仍在使用的策略或最后一份策略不能删除';return}delete draft.policies[name.value];name.selectedOptions[0].remove();draw()};
   reset.onclick=()=>{draft.policies[name.value]={};draw()};actions.append(id,add,copy,remove,reset);
   const queue=el('details');queue.append(el('summary','中间件队列（与 DDS 历史缓存独立）'));
   for(const [key,label,schema]of [['queue_samples','队列样本上限',{type:'integer',minimum:1,maximum:65536}],['queue_bytes','队列字节上限',{type:'integer',minimum:1,maximum:1073741824}],['overflow','队列溢出策略',{enum:['discard_oldest','reject']}]]){
    const row=el('label',label),reset=el('button','恢复默认');reset.onclick=()=>{delete policy[key];draw()};row.append(qosControl(schema,policy[key]??catalog.legacy_defaults[key],v=>policy[key]=v,key),reset);queue.append(row);
   }
   // Old policy fields remain readable, but new changes use explicit entity scopes.
   scope.replaceChildren(...['topic','writer','reader'].map(s=>new Option(qosScopeNames[s],s)));scope.value=scope.dataset.lastEndpoint||'writer';scope.onchange=()=>{scope.dataset.lastEndpoint=scope.value;draw()};
   area.append(el('label','选择策略模板'),name,actions,queue,el('label','配置作用范围'),scope,search);
   policy.dds??={};policy.dds[scope.value]??={};
   const without=clone(policy);delete without.dds[scope.value];
   scopedEditor(area,scope.value,policy.dds[scope.value],qosEffective(catalog,scope.value,without));
  }
  function groupEditor(parent,store,inheritedStore){
   scope.replaceChildren(...['participant','publisher','subscriber'].map(s=>new Option(qosScopeNames[s],s)));scope.value=scope.dataset.lastGroup||'participant';scope.onchange=()=>{scope.dataset.lastGroup=scope.value;draw()};parent.append(el('label','配置作用范围'),scope,search);
   const sc=scope.value;store[sc]??={};scopedEditor(parent,sc,store[sc],qosEffective(catalog,sc,null,inheritedStore?.[sc]));
  }
  function drawGlobal(){
   const network=el('details');network.append(el('summary','网络与发现地址'));network.open=true;
   const schema={type:'object',properties:{domain:{type:'integer',minimum:0,maximum:232},shared_memory:{type:'boolean'},interface_address:{type:'string'},peers:{type:'array',items:{type:'string'},maxItems:256}}};
   network.append(el('p','domain：DDS 域；shared_memory：启用普通共享内存传输；interface_address：本机 IPv4，空值不限制网卡；peers：初始发现对端 IPv4。','muted'),qosControl(schema,draft.transport,v=>draft.transport=v,'transport'));area.append(network);
   draft.qos??={};groupEditor(area,draft.qos,{});
  }
  function drawInstances(){
   if(!draft.instances.length){area.append(el('p','先添加 App，工具会建立默认实例。'));return}
   const picker=select(draft.instances.map(i=>[i.id,i.id+' · '+i.app]));picker.id='qosInstance';picker.setAttribute('aria-label','部署实例');picker.value=selectedInstance;
   if(!picker.value)picker.selectedIndex=0;selectedInstance=picker.value;picker.onchange=()=>{selectedInstance=picker.value;selectedEndpoint='';draw()};
   const instance=draft.instances.find(i=>i.id===selectedInstance),app=model.project.apps.find(a=>a.id===instance.app);
   const assigned=select(Object.keys(draft.policies).map(p=>[p,p]));assigned.setAttribute('aria-label','实例默认策略');assigned.value=instance.policy;assigned.onchange=()=>{instance.policy=assigned.value;draw()};
   area.append(el('label','部署实例'),picker,el('label','实例默认消息策略'),assigned);
   const endpoints=[];
   for(const direction of ['provides','requires'])for(const port of app?.[direction]||[])for(const event of service(port.interface)?.events||[])if(direction==='provides'||port.events.includes(event.id))endpoints.push({key:port.id+'.'+event.name,direction});
   const endpointPicker=select([['','实例分组 QoS'],...endpoints.map(e=>[e.key,(e.direction==='provides'?'输出 ':'输入 ')+e.key])]);endpointPicker.id='qosEndpoint';endpointPicker.setAttribute('aria-label','实例消息端点');endpointPicker.value=selectedEndpoint;endpointPicker.onchange=()=>{selectedEndpoint=endpointPicker.value;draw()};area.append(el('label','端点策略覆盖 / 实例 QoS'),endpointPicker);
   if(selectedEndpoint){
    const override=select([['','继承实例默认策略：'+instance.policy],...Object.keys(draft.policies).map(p=>[p,p])]);override.setAttribute('aria-label','端点策略覆盖');override.value=instance.event_policies?.[selectedEndpoint]||'';
    override.onchange=()=>{instance.event_policies??={};if(override.value)instance.event_policies[selectedEndpoint]=override.value;else delete instance.event_policies[selectedEndpoint];draw()};area.append(override);
    const p=instance.event_policies?.[selectedEndpoint]||instance.policy,edit=el('button','编辑所用策略：'+p);edit.onclick=()=>{name.value=p;view.value='policies';scope.dataset.lastEndpoint=endpoints.find(e=>e.key===selectedEndpoint)?.direction==='provides'?'writer':'reader';draw()};area.append(edit,el('p','策略模板可被多个实例复用。仅修改此端点时，先复制策略，再在这里选择。','muted'));
    const sc=endpoints.find(e=>e.key===selectedEndpoint)?.direction==='provides'?'writer':'reader';area.append(el('pre',JSON.stringify(qosEffective(catalog,sc,draft.policies[p]),null,2)));return;
   }
   instance.qos??={};groupEditor(area,instance.qos,draft.qos||{});
  }
  function draw(){area.replaceChildren();error.textContent='';if(view.value==='policies')drawPolicy();else if(view.value==='global')drawGlobal();else drawInstances();}
  name.onchange=draw;view.onchange=draw;draw();
  modal('QoS、默认策略与网络配置',body,async()=>{
   error.textContent='';
   try{await api('qos',draft)}catch(e){error.textContent=e.message;const first=[...area.querySelectorAll('[data-qos-key]')].find(x=>e.message.includes(x.dataset.qosKey));first?.scrollIntoView({block:'center'});throw e}
   if(revision!==startedRevision)throw Error('工程已修改，请重新打开配置窗口，避免覆盖新的编辑');
   // Remove empty scope objects created for viewing; viewing alone does not dirty a project.
   function prune(store){if(!store)return;for(const key of Object.keys(store))if(Object.keys(store[key]).length===0)delete store[key]}
   for(const p of Object.values(draft.policies)){prune(p.dds);if(p.dds&&Object.keys(p.dds).length===0)delete p.dds}
   prune(draft.qos);if(draft.qos&&Object.keys(draft.qos).length===0)delete draft.qos;
   for(const i of draft.instances){prune(i.qos);if(i.qos&&Object.keys(i.qos).length===0)delete i.qos;if(i.event_policies&&Object.keys(i.event_policies).length===0)delete i.event_policies}
   if(!qosEqual(draft,model.deployment))change(()=>model.deployment=draft);
   report('QoS 配置已应用；生成前请校验完整工程');
  });
 }catch(e){report(e.message,true)}
}
$('deployment').onclick=()=>openQos();
