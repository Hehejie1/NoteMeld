const pages={
  docs:[['A01','多端架构设计','桌面端、云端和移动端的 UI、运行时与数据边界'],['A02','多端数据库设计','跨端实体、SQLite、云端存储和缓存边界'],['A03','多端功能地图','功能点、接口、数据、状态和完成度'],['A04','组件库设计','设计元语、基础原语和跨端参考实现']],
  desktop:[['D01','新对话','创建一个新的本地 Agent 对话'],['D03','会话列表与详情','消息、工具、审批、队列、分支与收纳'],['D06','插件应用','Skills、MCP、插件、应用和智能体'],['D09','设置页面','模型、主题、账户、设备、数据和安全设置']],
  apps:[['APP01','笔记应用','笔记、样式模板、Wiki 和旧笔记导入'],['APP02','学习应用','学习空间、白板、掌握验证和复习'],['APP03','监控应用','用量、运行健康、GPU、MCP 和插件状态'],['APP04','系统运行','Agent 诊断、Application、审批、更新和设备连接']],
  cloud:[['C01','登录页面','登录、申请访问和审核结果'],['C02','AI工作台','云端 AI 会话、状态、筛选和运行摘要'],['C03','云端会话','消息、工具、审批、产物和云端运行面板'],['C04','人员管理','访问申请、已加入成员、邀请和账号状态'],['C05','设备管理','一次性配对、设备授权、凭证和运行节点'],['C06','设置页面','账号、安全、通知、模型和云端偏好']],
  mobile:[['M01','移动端首页','快捷入口、任务与 Agent 输入'],['M02','移动端会话','消息、工具、审批与产物查看'],['M03','移动端设置','主题、语言、日志与数据入口'],['M04','记忆库','查看、复制与添加我的记忆'],['M05','字体大小','实时预览、拖拽调整与确认'],['M06','存储空间','数据占用、分类查看与清理']]
};
const all=Object.values(pages).flat(),catalog=document.getElementById('catalog'),frame=document.getElementById('preview');let current=location.hash.slice(1)||'D01',mode=localStorage.getItem('notemeld-prototype-mode')||'preview';if(!all.some(page=>page[0]===current))current='D01';
function info(id){return all.find(page=>page[0]===id)||all[0]}
function renderCatalog(){catalog.innerHTML='<div class="mode-switch" role="group" aria-label="原型模式"><button data-mode="preview" class="'+(mode==='preview'?'active':'')+'">预览模式</button><button data-mode="explain" class="'+(mode==='explain'?'active':'')+'">讲解模式</button></div>'+Object.entries(pages).map(([key,list])=>'<button class="category" data-category="'+key+'"><span>'+({docs:'产品设计文档',desktop:'桌面端 Agent',apps:'应用',cloud:'云端页面',mobile:'移动端'}[key])+'</span><span class="chevron">⌄</span></button><div class="category-items" data-items="'+key+'">'+list.map(page=>'<button class="page-link '+(page[0]===current?'active':'')+'" data-id="'+page[0]+'"><strong>'+page[0]+'　'+page[1]+'</strong><small>'+page[2]+'</small></button>').join('')+'</div>').join('');catalog.querySelectorAll('.page-link').forEach(button=>button.onclick=()=>load(button.dataset.id));catalog.querySelectorAll('.category').forEach(button=>button.onclick=()=>{button.classList.toggle('collapsed');document.querySelector('[data-items="'+button.dataset.category+'"]')?.classList.toggle('collapsed')});catalog.querySelectorAll('[data-mode]').forEach(button=>button.onclick=()=>{mode=button.dataset.mode;localStorage.setItem('notemeld-prototype-mode',mode);renderCatalog();frame.contentWindow?.postMessage({type:'notemeld-prototype-mode',mode},'*')})}
function load(id){current=id;location.hash=id;const group=id.startsWith('APP')?'apps':id[0]==='A'?'cloud':id[0]==='D'?'desktop':id[0]==='C'?'cloud':'mobile';frame.src='./pages/'+group+'/'+id.toLowerCase()+'.html?v=20260907-1';frame.onload=()=>frame.contentWindow.postMessage({type:'notemeld-prototype-mode',mode},'*');renderCatalog()}
window.addEventListener('message',event=>{if(event.data?.type==='notemeld-page'&&info(event.data.id))load(event.data.id)});
window.addEventListener('hashchange',()=>{const id=location.hash.slice(1);if(info(id)&&id!==current)load(id)});
const splitter=document.getElementById('splitter'),catalogPane=document.querySelector('.catalog');let dragging=false;
splitter.onpointerdown=event=>{dragging=true;splitter.classList.add('dragging');splitter.setPointerCapture(event.pointerId)};
splitter.onpointermove=event=>{if(dragging){const width=Math.max(220,Math.min(360,event.clientX));catalogPane.style.width=width+'px'}};
splitter.onpointerup=()=>{dragging=false;splitter.classList.remove('dragging')};
splitter.onpointercancel=splitter.onpointerup;
renderCatalog();load(current);
document.addEventListener('click',event=>{
  if(event.target.closest('[data-mode]')) setTimeout(()=>load(current),0);
});
