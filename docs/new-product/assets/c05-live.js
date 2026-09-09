(()=>{
  const scopeTabs=[...document.querySelectorAll('.scope-tabs button')];
  const scopeMessage=document.createElement('p');
  scopeMessage.className='form-message info';
  scopeMessage.setAttribute('role','status');
  scopeMessage.hidden=true;
  document.querySelector('.scope-tabs')?.after(scopeMessage);
  scopeTabs.forEach((tab,index)=>tab.addEventListener('click',()=>{
    const runtime=index===1;
    scopeTabs.forEach((item,itemIndex)=>{const active=itemIndex===index;item.classList.toggle('active',active);item.setAttribute('aria-selected',String(active))});
    scopeMessage.hidden=false;
    scopeMessage.textContent=runtime?'当前 Cloud 数据模型只登记可信用户设备，尚未登记独立运行节点；因此此视图为空。':'当前显示已登记的可信用户设备。';
  }));
  if(document.body.dataset.page!=='C05'||!sessionStorage.getItem('notemeld-cloud-token'))return;
  const token=sessionStorage.getItem('notemeld-cloud-token');
  const api=async(path,options={})=>{const response=await fetch(path,{...options,headers:{'Content-Type':'application/json',Authorization:`Bearer ${token}`,...(options.headers||{})}});const payload=await response.json();if(!response.ok)throw new Error(payload.detail||payload.msg||'请求失败');return payload.data};
  const escape=value=>String(value??'').replace(/[&<>\"]/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[char]));
  const openConfirm=(row,button)=>{const node=document.createElement('div');node.className='modal-backdrop';node.innerHTML=`<section class="create-dialog" role="dialog" aria-modal="true"><header><div><span class="section-kicker">Device access</span><h2>撤销设备</h2><p>撤销后关联设备令牌和远程授权立即失效。</p></div><button class="icon-button" type="button" data-close-device-revoke aria-label="关闭">×</button></header><div class="c06-dialog-body"><p>确认撤销设备 <strong>${escape(row.dataset.device||'当前设备')}</strong>？</p><p class="form-message" data-revoke-message role="status"></p><div class="dialog-actions"><button class="secondary-button" type="button" data-close-device-revoke>取消</button><button class="primary-button" type="button" data-confirm-device-revoke>确认撤销</button></div></div></section>`;document.body.append(node);const close=()=>node.remove();node.querySelectorAll('[data-close-device-revoke]').forEach(item=>item.addEventListener('click',close));node.querySelector('[data-confirm-device-revoke]').addEventListener('click',async event=>{event.currentTarget.disabled=true;try{await api('/v1/devices/'+encodeURIComponent(row.dataset.deviceId)+'/revoke',{method:'POST'});row.remove();close()}catch(error){const message=node.querySelector('[data-revoke-message]');message.textContent=error.message;message.className='form-message';event.currentTarget.disabled=false}finally{button.disabled=false}})};
  document.addEventListener('click',event=>{const button=event.target.closest('[data-revoke-device]');if(!button)return;const row=button.closest('[data-device-id]');if(!row)return;event.preventDefault();event.stopImmediatePropagation();button.disabled=true;openConfirm(row,button)},true);
})();
