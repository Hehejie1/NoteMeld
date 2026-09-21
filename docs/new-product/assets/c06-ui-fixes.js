/* C06 prototype contract: backup export only; restore is selected at server startup. */
(()=>{
  if(document.body.dataset.page!=='C06')return;
  const token=sessionStorage.getItem('notemeld-cloud-token');
  if(!token)return;
  const request=async(path,options={})=>{const response=await fetch(path,{...options,headers:{'Content-Type':'application/json',Authorization:`Bearer ${token}`,...(options.headers||{})}});const payload=await response.json();if(!response.ok)throw new Error(payload.detail||payload.msg||'请求失败');return payload.data};
  const feedback=text=>{let node=document.querySelector('[data-c06-prototype-message]');if(!node){node=document.createElement('p');node.className='form-message info';node.dataset.c06PrototypeMessage='';document.querySelector('.settings-content')?.prepend(node)}node.textContent=text;setTimeout(()=>node.remove(),3500)};
  document.addEventListener('click',async event=>{
    const backup=event.target.closest('[data-backup-manager]');
    if(backup){event.preventDefault();event.stopImmediatePropagation();backup.disabled=true;try{const spaces=await request('/v1/workspaces');const id=spaces[0]?.id;if(!id){feedback('当前账号没有可备份的 Workspace。');return}const result=await request(`/v1/workspaces/${encodeURIComponent(id)}/backups`,{method:'POST'});feedback(`备份已创建：${result.backup_id||'已生成'}。启动服务端时可指定备份目录恢复。`)}catch(error){feedback(error.message)}finally{backup.disabled=false}return}
    const test=event.target.closest('[data-model-test]');
    if(test){event.preventDefault();event.stopImmediatePropagation();try{await request('/v1/models');feedback('默认模型配置可读取，连接测试接口将在 Cloud Provider 校验接入后执行。')}catch(error){feedback(error.message)}return}
    const copy=event.target.closest('[data-copy-logs]');
    if(copy){event.preventDefault();event.stopImmediatePropagation();try{const logs=await request('/v1/audits?limit=100');await navigator.clipboard.writeText(logs.map(item=>`${item.action} · ${new Date(item.created_at*1000).toLocaleString()}`).join('\n'));feedback('日志已复制。')}catch(error){feedback(error.message)}return}
    const download=event.target.closest('[data-download-logs]');
    if(download){event.preventDefault();event.stopImmediatePropagation();try{const logs=await request('/v1/audits?limit=100');const blob=new Blob([JSON.stringify(logs,null,2)],{type:'application/json'});const link=document.createElement('a');link.href=URL.createObjectURL(blob);link.download='notemeld-cloud-audit-log.json';link.click();URL.revokeObjectURL(link.href);feedback('日志已下载。')}catch(error){feedback(error.message)}}
  },true);
})();
