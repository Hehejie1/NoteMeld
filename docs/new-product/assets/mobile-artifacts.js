(()=>{
  // Design-only fixtures. Production must replace these with authorized,
  // task-scoped artifact IDs and content returned by the Host/API.
  const files=[
    {id:'report',name:'系统架构风险报告.md',type:'Markdown',mime:'text/markdown',icon:'file-text',content:'# 系统架构风险报告\n\n## 概览\n\n本次检查聚焦事件流、设备授权与恢复路径。\n\n- 检查事件重复投递时的幂等处理\n- 明确远程设备离线后的只读行为\n- 补充跨端产物读取的权限校验\n\n## 下一步\n\n逐项确认风险负责人，并在真实 Workspace 中复核证据。'},
    {id:'html',name:'架构概览.html',type:'HTML',mime:'text/html',icon:'file-code-2',content:'<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><style>body{font-family:system-ui,sans-serif;margin:32px;color:#202938}h1{font-size:22px}.card{padding:18px;border:1px solid #dfe5ed;border-radius:14px;background:#f7f9fc}small{color:#68758a}</style></head><body><small>示例产物</small><h1>系统架构概览</h1><div class="card">移动端 → Cloud 控制面 → 桌面 Host<br><br>任务执行与文件事实源由受授权的 Host 管理。</div></body></html>'},
    {id:'log',name:'检查摘要.txt',type:'纯文本',mime:'text/plain',icon:'file-text',content:'检查系统架构 · 示例摘要\n\n检查范围：事件流、权限边界、远程连接。\n发现：3 项需要人工确认的风险。\n状态：报告仍需结合真实项目资料复核。'},
    {id:'yaml',name:'event_bus_config.yaml',type:'YAML',mime:'text/yaml',icon:'file-code-2',content:'event_bus:\n  delivery: at_least_once\n  retry_limit: 3\n  dead_letter_queue: enabled\n# 示例配置，非当前 Workspace 的真实文件'},
    {id:'json',name:'风险清单.json',type:'JSON',mime:'application/json',icon:'file-code-2',content:'{\n  "task": "检查系统架构",\n  "sample": true,\n  "risks": ["事件幂等", "离线只读", "文件权限校验"]\n}'}
  ];
  const page=document.body.dataset.page;
  if(page!=='M09'&&page!=='M10')return;
  const createIcon=(name)=>{const i=document.createElement('i');i.dataset.lucide=name;return i;};
  const refreshIcons=()=>window.lucide?.createIcons({attrs:{'stroke-width':2}});
  const navigate=(id)=>{if(parent!==window)parent.postMessage({type:'notemeld-page',id},'*');else location.href='./'+id.toLowerCase()+'.html';};
  if(page==='M09'){
    const list=document.querySelector('[data-artifact-list]');
    document.querySelector('[data-file-count]').textContent=`${files.length} 个文件`;
    if(!files.length){list.innerHTML='<div class="artifact-empty">当前任务还没有产物</div>';return;}
    files.forEach(file=>{
      const row=document.createElement('button');row.type='button';row.className='artifact-row';row.dataset.artifactId=file.id;row.setAttribute('aria-label',`预览 ${file.name}`);
      const mark=document.createElement('span');mark.className='artifact-file-icon';mark.append(createIcon(file.icon));
      const info=document.createElement('span');const title=document.createElement('strong');title.textContent=file.name;const detail=document.createElement('small');detail.textContent=file.type;info.append(title,detail);
      row.append(mark,info,createIcon('chevron-right'));
      row.addEventListener('click',()=>{sessionStorage.setItem('notemeld-artifact-preview-id',file.id);navigate('M10');});
      list.append(row);
    });
    refreshIcons();return;
  }
  const selectedId=sessionStorage.getItem('notemeld-artifact-preview-id')||files[0]?.id;
  const file=files.find(item=>item.id===selectedId);
  const body=document.querySelector('[data-preview-body]');
  const modes=[...document.querySelectorAll('[data-preview-mode]')];
  const showMessage=(title,description)=>{body.replaceChildren();const box=document.createElement('div');box.className='artifact-preview-message';const strong=document.createElement('strong');strong.textContent=title;const p=document.createElement('p');p.textContent=description;box.append(strong,p);body.append(box);};
  if(!file){document.querySelector('[data-preview-name]').textContent='文件不存在';document.querySelector('.artifact-preview-actions').hidden=true;document.querySelector('[data-preview-download]').hidden=true;showMessage('无法预览','所选文件不在当前任务中，请返回文件列表重新选择。');return;}
  const previewName=document.querySelector('[data-preview-name]');previewName.textContent=file.name;previewName.title=file.name;
  const blob=new Blob([file.content],{type:file.mime+';charset=utf-8'});
  const downloadUrl=URL.createObjectURL(blob);
  const download=document.querySelector('[data-preview-download]');download.href=downloadUrl;download.download=file.name;
  window.addEventListener('pagehide',()=>URL.revokeObjectURL(downloadUrl),{once:true});
  const source=()=>{const pre=document.createElement('pre');pre.textContent=file.content;body.replaceChildren(pre);};
  const markdown=()=>{
    const article=document.createElement('article');article.className='artifact-markdown';
    let list=null,code=null;
    for(const line of file.content.split(/\r?\n/)){
      if(line.startsWith('```')){if(code){code=null;}else{const pre=document.createElement('pre');code=document.createElement('code');pre.append(code);article.append(pre);}list=null;continue;}
      if(code){code.textContent+=line+'\n';continue;}
      if(!line.trim()){list=null;continue;}
      const heading=line.match(/^(#{1,3})\s+(.+)$/);
      if(heading){const h=document.createElement('h'+heading[1].length);h.textContent=heading[2];article.append(h);list=null;continue;}
      const bullet=line.match(/^[-*]\s+(.+)$/);
      if(bullet){if(!list){list=document.createElement('ul');article.append(list);}const li=document.createElement('li');li.textContent=bullet[1];list.append(li);continue;}
      list=null;const p=document.createElement('p');p.textContent=line;article.append(p);
    }
    body.replaceChildren(article);
  };
  const rendered=()=>{
    if(file.mime==='text/html'){
      const iframe=document.createElement('iframe');iframe.title=file.name;iframe.setAttribute('sandbox','');
      iframe.srcdoc=`<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src data: blob:">${file.content}`;
      body.replaceChildren(iframe);
    }else if(file.mime==='text/markdown')markdown();
    else if(file.mime.startsWith('text/')||file.mime==='application/json'||file.mime==='application/xml')source();
    else if(file.mime.startsWith('image/')){const img=document.createElement('img');img.alt=file.name;img.src=downloadUrl;body.replaceChildren(img);}
    else if(file.mime==='application/pdf'){const iframe=document.createElement('iframe');iframe.title=file.name;iframe.src=downloadUrl;body.replaceChildren(iframe);}
    else if(file.mime.startsWith('audio/')||file.mime.startsWith('video/')){const media=document.createElement(file.mime.startsWith('audio/')?'audio':'video');media.controls=true;media.src=downloadUrl;body.replaceChildren(media);}
    else showMessage('暂不支持内嵌预览','此格式无法在浏览器中安全展示，可下载后用对应应用打开。');
  };
  modes.forEach(button=>button.addEventListener('click',()=>{modes.forEach(item=>item.setAttribute('aria-pressed',String(item===button)));const isSource=button.dataset.previewMode==='source';document.querySelector('[data-preview-label]').textContent=isSource?'原文':'预览';if(isSource)source();else rendered();}));
  rendered();refreshIcons();
})();
