/* C03: the plus button creates a persisted Cloud session in the default Workspace. */
(()=>{
  if(document.body.dataset.page!=='C03')return;
  const token=sessionStorage.getItem('notemeld-cloud-token');
  if(!token)return;
  const request=async(path,options={})=>{const response=await fetch(path,{...options,headers:{'Content-Type':'application/json',Authorization:`Bearer ${token}`,...(options.headers||{})}});const payload=await response.json();if(!response.ok)throw new Error(Array.isArray(payload.detail)?payload.detail.map(item=>item.msg||item.message).join('；'):(payload.detail||payload.msg||'请求失败'));return payload.data};
  document.querySelector('.conversation-list-head button')?.addEventListener('click',async event=>{
    event.preventDefault();
    event.stopPropagation();
    const button=event.currentTarget;button.disabled=true;
    try{
      const [workspaces,preferences]=await Promise.all([request('/v1/workspaces'),request('/v1/preferences')]);
      const workspaceId=preferences.default_workspace||workspaces[0]?.id||'default';
      await request('/v1/cloud/sessions',{method:'POST',body:JSON.stringify({kind:'cloud_native',title:'新会话',workspace_id:workspaceId})});
      location.reload();
    }catch(error){
      const message=document.createElement('p');message.className='form-message';message.textContent=error.message;button.closest('.conversation-list-head')?.after(message);setTimeout(()=>message.remove(),3500);button.disabled=false;
    }
  });
  document.querySelector('.cloud-composer .send-button')?.addEventListener('click',async event=>{
    if(document.body.dataset.sessionId)return;
    event.preventDefault();
    event.stopImmediatePropagation();
    const send=event.currentTarget;
    const input=document.querySelector('.cloud-composer textarea'), model=document.querySelector('.cloud-composer .model-button');
    const value=input?.value.trim();
    if(!value||model?.dataset.noModel==='true')return;
    send.disabled=true;
    try{
      const [workspaces,preferences]=await Promise.all([request('/v1/workspaces'),request('/v1/preferences')]);
      const workspaceId=preferences.default_workspace||workspaces[0]?.id||'default';
      const session=await request('/v1/cloud/sessions',{method:'POST',body:JSON.stringify({kind:'cloud_native',title:value.slice(0,40),workspace_id:workspaceId})});
      document.body.dataset.sessionId=session.id;
      document.body.dataset.newSession='false';
      await request(`/v1/cloud/sessions/${encodeURIComponent(session.id)}/commands`,{method:'POST',body:JSON.stringify({request_id:crypto.randomUUID(),input:value,attachments:[],model_id:model?.dataset.modelId||null,authorization_mode:document.querySelector('.permission-button')?.dataset.full==='true'?'full':'default'})});
      location.hash=`session=${encodeURIComponent(session.id)}`;
      location.reload();
    }catch(error){
      const message=document.createElement('p');message.className='form-message';message.textContent=error.message;document.querySelector('.cloud-composer-wrap')?.prepend(message);setTimeout(()=>message.remove(),3500);send.disabled=false;
    }
  },true);
})();
