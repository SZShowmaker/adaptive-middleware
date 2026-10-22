// Local output preferences are separate from exported project models.
let deliveryRoot='',pathStorageKey='',defaultDeliveryRoot='',generationBusy=false;
let currentPaths=null,pathRequestKey='',pathRequestVersion=0;
function initializePaths(config){
 defaultDeliveryRoot=config.default_delivery_root;
 pathStorageKey='amw.deliveryRoot:'+config.root;
 try{deliveryRoot=localStorage.getItem(pathStorageKey)||'';}catch(e){deliveryRoot='';}
}
async function refreshGenerationPaths(){
 const projectId=model.project.project_id,key=JSON.stringify([projectId,deliveryRoot]);
 if(key===pathRequestKey){$('generate').disabled=generationBusy||!currentPaths;return;}
 pathRequestKey=key;currentPaths=null;const version=++pathRequestVersion;
 $('generate').disabled=true;$('generationPath').textContent='正在读取生成目录…';
 try{
  const paths=await api('paths',{project_id:projectId,delivery_root:deliveryRoot});
  if(version!==pathRequestVersion)return;
  currentPaths=paths;$('generationPath').textContent='生成目录：'+paths.output;
  $('generationPath').className='';$('generationPath').title='草稿：'+paths.project_file;
  $('generate').disabled=generationBusy;
 }catch(e){
  if(version!==pathRequestVersion)return;
  $('generationPath').textContent='生成目录不可用：'+e.message;$('generationPath').className='error';$('generationPath').title='';
 }
}
function editGenerationLocation(){
 const box=el('div'),label=el('label','生成根目录（留空使用默认位置）'),input=el('input');
 input.id='deliveryRoot';input.value=deliveryRoot;input.placeholder=defaultDeliveryRoot;label.htmlFor=input.id;
 const hint=el('p','填写运行本地 GUI 服务的电脑上的绝对路径。工具会在根目录下创建 <工程ID>/src-gen；工程改名后，旧目录保留。','muted');
 const preview=el('p',undefined,'path-preview');preview.id='pathPreview';
 const local=el('p','设置仅保存在当前浏览器的本机偏好中，不随工程包导出。草稿始终按工程 ID 保存到仓库 out/editor 下。','muted');
 const reset=el('button','恢复默认位置');reset.type='button';
 let valid=false,sequence=0;
 async function update(){
  valid=false;$('apply').disabled=true;const version=++sequence;preview.textContent='正在检查路径…';
  try{
   const paths=await api('paths',{project_id:model.project.project_id,delivery_root:input.value.trim()});
   if(version!==sequence)return;
   preview.replaceChildren(el('div','生成：'+paths.output),el('div','草稿：'+paths.project_file));preview.className='path-preview';valid=true;$('apply').disabled=false;
  }catch(e){if(version===sequence){preview.textContent=e.message;preview.className='path-preview error';}}
 }
 reset.onclick=()=>{input.value='';update();};input.oninput=update;
 box.append(label,input,hint,preview,reset,local);
 modal('生成位置设置',box,()=>{
  deliveryRoot=input.value.trim();
  try{if(deliveryRoot)localStorage.setItem(pathStorageKey,deliveryRoot);else localStorage.removeItem(pathStorageKey);}catch(e){report('位置已应用；浏览器未允许记住设置，关闭页面后将恢复默认。');}
  pathRequestKey='';refreshGenerationPaths();
 },()=>valid);
 update();
}
$('pathSettings').onclick=editGenerationLocation;
$('editGenerationPath').onclick=editGenerationLocation;
