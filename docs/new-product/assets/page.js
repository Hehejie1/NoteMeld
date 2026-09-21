const data={APP01:['笔记应用','笔记、样式模板、Wiki 和旧笔记导入','我的笔记','笔记列表　·　样式模板　·　Wiki 图谱　·　导入'],APP02:['学习应用','学习空间、语义白板、掌握验证和复习','我的学习空间','学习路径　·　白板　·　掌握证据　·　复习'],APP03:['监控应用','用量、运行健康、GPU、MCP 和插件状态','运行总览','Token 用量　·　运行任务　·　资源状态　·　健康检查'],APP04:['系统运行','Agent 诊断、Application、审批、更新和设备连接','系统状态','Agent Turn　·　安全审批　·　设备连接　·　Host'],D01:['新对话','创建一个新的本地 Agent 对话','开始新对话','告诉 Agent 你想完成什么，支持使用 / 调用能力和使用 @ 添加上下文。'],D02:['新建会话','选择本地、云端原生或远程设备会话','选择运行位置','本地会话　　云端原生会话　　远程设备会话'],D03:['会话列表与详情','消息、工具、审批、队列、分支与收纳','当前会话','消息时间线　·　工具调用　·　审批　·　队列'],D04:['文件与产物','查看、编辑、引用和打开 Agent 生成的产物','当前产物','系统架构研究报告.md　·　Markdown　·　刚刚生成'],D06:['插件应用','Skills、MCP、插件、应用和智能体','已安装能力','Skills　·　MCP　·　插件　·　Application　·　Agent'],D07:['远程设备','配对、授权、在线状态和活动记录','设备列表','MacBook Pro　·　在线　　Windows Workstation　·　离线'],D08:['设备连接授权','选择 workspace、权限、模型并建立连接','连接设置','目标设备　·　workspace　·　模型　·　授权有效期'],D09:['设置页面','模型、主题、账户、设备、数据和安全设置','设置分组','模型　·　主题　·　账户　·　设备　·　数据与安全'],C01:['云端登录','普通用户和管理员共用登录入口','登录云端','云端用户名　　密码　　登录'],C02:['云端会话工作台','云端原生 Agent 会话与 workspace 管理','云端会话','研究报告　·　活跃　　项目规划　·　暂停'],C03:['云端会话详情','消息、事件、产物、队列、审批和同步状态','云端 Agent','云端消息时间线　·　事件　·　产物　·　审批'],C04:['分享/导入本地会话','将本地会话复制为独立的云端新会话','导入清单','历史　·　摘要　·　文件　·　记忆　·　非敏感配置'],C05:['云端 Workspace','文件、产物、容量、备份和恢复状态','Workspace 状态','文件与产物　·　磁盘用量　·　备份　·　恢复'],C06:['设备与授权','设备、远程授权和撤销','授权设备','当前设备　·　控制设备　·　宿主设备　·　撤销授权'],C07:['管理员管理','用户、角色、配额和审计，按权限显示','管理员菜单','用户管理　·　设备管理　·　配额　·　审计'],M01:['移动端 Agent 首页','移动端 Agent 对话工作台','移动端对话','左上角菜单　·　Agent 对话主体　·　右上角新建/产物/更多'],M02:['移动端会话详情','消息、工具、审批与产物查看','移动端会话','流式消息　·　底部输入　·　产物 Sheet　·　返回会话'],M03:['移动端远程控制','选择设备、workspace、权限和模型','远程控制','选择在线设备　·　选择 workspace　·　确认权限'],M04:['移动端审批与恢复','批准危险操作或恢复中断任务','审批操作','批准　·　拒绝　·　继续原任务　·　终止并处理下一条'],M05:['移动端设备配对','二维码、短码和双向确认','设备配对','扫描二维码　·　输入短码　·　双向确认　·　加密连接'],M06:['移动端账户安全','设备、token、恢复密钥和退出登录','账户安全','当前设备　·　已授权设备　·　token 轮换　·　恢复密钥'],M07:['移动端应用页','从会话进入应用并返回会话','应用页面','左上角返回会话　·　应用内容　·　允许的数据范围'],M08:['移动端同步状态','云端连接、relay、缓存和宿主队列','同步状态','云端连接　·　实时 relay　·　本地缓存　·　宿主队列']};

(() => { const link=document.createElement('link'); link.rel='stylesheet'; link.href='../../design-system/tokens.css'; document.head.append(link); const primitiveLink=document.createElement('link'); primitiveLink.rel='stylesheet'; primitiveLink.href='../../design-system/primitives.css'; document.head.append(primitiveLink); const script=document.createElement('script'); script.src='../../design-system/primitives.js'; script.dataset.nmDesignSystem='true'; document.head.append(script); })();
function mountIcons(){
  if(!window.lucide)return;
  const put=(node,name)=>{if(!node||node.dataset.iconized)return;node.innerHTML=`<i data-lucide="${name}"></i>`;node.dataset.iconized='true'};
  document.querySelectorAll('[data-icon]').forEach(node=>{if(!node.getAttribute('data-lucide'))node.setAttribute('data-lucide',node.getAttribute('data-icon'));node.setAttribute('aria-hidden','true')});
  const sideIcons=['panel-left-close','bell','search'];
  document.querySelectorAll('.sidebar-actions button').forEach((node,i)=>put(node,sideIcons[i]||'circle'));
  const quickIcons=['plus','puzzle','settings'];
  document.querySelectorAll('.quick-link span').forEach((node,i)=>{node.innerHTML=`<i data-lucide="${quickIcons[i]||'circle'}"></i>`});
  const headerIcons={'分享':'share-2','切换置顶摘要':'pin','切换底部面板':'panel-bottom','切换侧边面板':'panel-right','更多':'more-horizontal','打开底部面板':'panel-bottom','打开侧边面板':'panel-right'};
  document.querySelectorAll('.agent-header-actions button').forEach(node=>put(node,headerIcons[node.getAttribute('aria-label')]||'more-horizontal'));
  document.querySelectorAll('.workspace-picker span,.workspace-context span').forEach(node=>{node.innerHTML='<i data-lucide="folder-open"></i>'});
  document.querySelectorAll('.add-button').forEach(node=>{node.innerHTML='<i data-lucide="plus"></i><span>添加</span>'});
  document.querySelectorAll('.permission-button').forEach(node=>{node.innerHTML='<i data-lucide="shield-check"></i><span>默认权限</span><span class="chevron">⌄</span>'});
  document.querySelectorAll('.model-button').forEach(node=>{node.innerHTML='<i data-lucide="sparkles"></i><span data-model-label>Auto</span><span class="chevron">⌄</span>'});
  document.querySelectorAll('.voice-button').forEach(node=>put(node,'mic'));
  document.querySelectorAll('.send-button').forEach(node=>put(node,'arrow-up'));
  document.querySelectorAll('.panel-close,[data-popup-close]').forEach(node=>put(node,'x'));
  document.querySelectorAll('.lucide').forEach(node=>{node.setAttribute('aria-hidden','true')});
  window.lucide.createIcons({attrs:{'stroke-width':2}});
}
const id=document.body.dataset.page,p=data[id]||data.D01;document.title='NoteMeld · '+p[0];document.getElementById('eyebrow')&&(document.getElementById('eyebrow').textContent=id+' · '+p[0]);document.getElementById('title')&&(document.getElementById('title').textContent=p[0]);document.getElementById('desc')&&(document.getElementById('desc').textContent=p[1]);document.getElementById('primaryTitle')&&(document.getElementById('primaryTitle').textContent=p[2]);document.getElementById('primaryText')&&(document.getElementById('primaryText').textContent=p[3]);
const pagePathMap={C01:'/cloud/pages/cloud/c01.html',C02:'/cloud/pages/cloud/c02.html',C03:'/cloud/pages/cloud/c03.html',C04:'/cloud/pages/cloud/c04.html',C05:'/cloud/pages/cloud/c05.html',C06:'/cloud/pages/cloud/c06.html',C07:'/cloud/pages/cloud/c07.html',APP01:'../apps/app01.html',APP02:'../apps/app02.html',APP03:'../apps/app03.html',APP04:'../apps/app04.html'};
document.querySelectorAll('[data-go]').forEach(a=>a.onclick=e=>{e.preventDefault();const target=a.dataset.go;if(window.parent!==window)parent.postMessage({type:'notemeld-page',id:target},'*');else if(pagePathMap[target])window.location.href=pagePathMap[target]});
if(window.parent!==window)parent.postMessage({type:'notemeld-page-loaded',id},'*');
mountIcons();
document.querySelectorAll('.model-option').forEach(option=>option.addEventListener('click',()=>{
  document.querySelectorAll('.model-option').forEach(item=>item.classList.toggle('selected',item===option));
  const label=option.querySelector('strong')?.textContent?.trim();
  if(label) document.querySelectorAll('[data-model-label]').forEach(node=>node.textContent=label);
  document.querySelectorAll('[data-popup]').forEach(popup=>popup.classList.remove('is-open'));
}));

let explainConfigPromise;
const explainConfig=()=>explainConfigPromise||(explainConfigPromise=fetch('../../config/feature-registry.json').then(response=>response.json()));
const showExplainFeature=(feature,defaults)=>{const modal=document.createElement('dialog');modal.className='prototype-explain-dialog';const list=value=>(value||[]).join('、')||'待补充';modal.innerHTML=`<form method="dialog"><div class="doc-dialog-kicker">功能说明 · ${feature?.id||'未登记'}</div><h2>${feature?.title||'页面交互'}</h2><p>${feature?.description||'该交互点的功能说明尚未登记。'}</p><p><strong>实现状态：</strong>${feature?.status||'待设计'}</p><p><strong>状态流：</strong>${list(feature?.state)}</p><p><strong>接口：</strong>${list(feature?.api)}</p><p><strong>数据：</strong>${list(feature?.tables)}</p><p><strong>执行动作：</strong>${feature?.interaction?.action||defaults.action||'执行页面交互'}</p><p><strong>成功结果：</strong>${feature?.interaction?.success||defaults.success||'显示成功状态'}</p><p><strong>失败结果：</strong>${feature?.interaction?.failure||defaults.failure||'显示失败状态'}</p><p><strong>预览逻辑：</strong>${feature?.interaction?.preview_behavior||defaults.preview_behavior||'执行原型交互'}</p><p><strong>讲解逻辑：</strong>${feature?.interaction?.explain_behavior||defaults.explain_behavior||'拦截点击并展示说明'}</p><button>知道了</button></form>`;document.body.append(modal);modal.showModal();modal.addEventListener('close',()=>modal.remove(),{once:true})};
const bindExplainFeatures=()=>explainConfig().then(config=>{
  const featureMap=config.features||{},bindings=config.bindings||{};
  Object.entries(bindings).forEach(([featureId,selectors])=>{const feature=featureMap[featureId];if(!feature||feature.page!==id)return;(selectors||[]).forEach(selector=>document.querySelectorAll(selector).forEach(element=>{element.dataset.featureId=featureId}))});
  if(document.body.dataset.explainHandler)return;
  document.body.dataset.explainHandler='true';
  document.addEventListener('click',event=>{if(!document.body.classList.contains('explain-mode')||event.target.closest('dialog'))return;const interactive=event.target.closest('a,button,[role="button"]'),bound=event.target.closest('[data-feature-id]'),target=(interactive?.dataset.featureId?interactive:bound)||interactive||bound;if(!target)return;event.preventDefault();event.stopPropagation();const feature=featureMap[target.dataset.featureId];showExplainFeature(feature?{...feature,id:target.dataset.featureId}:undefined,config.interaction_defaults||{})},true);
});
window.addEventListener('message',event=>{if(event.data?.type!=='notemeld-prototype-mode')return;document.body.classList.toggle('explain-mode',event.data.mode==='explain');if(event.data.mode==='explain')bindExplainFeatures().catch(()=>{})});
