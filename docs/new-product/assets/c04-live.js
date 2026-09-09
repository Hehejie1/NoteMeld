(()=>{
  if(document.body.dataset.page!=='C04'||!sessionStorage.getItem('notemeld-cloud-token'))return;
  const token=sessionStorage.getItem('notemeld-cloud-token');
  const api=async(path,options={})=>{const response=await fetch(path,{...options,headers:{'Content-Type':'application/json',Authorization:`Bearer ${token}`,...(options.headers||{})}});const payload=await response.json();if(!response.ok)throw new Error(payload.detail||payload.msg||'请求失败');return payload.data};
  const escape=value=>String(value??'').replace(/[&<>\"]/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[char]));
  const review=(button,row)=>{const approved=button.dataset.review==='approved',modal=document.createElement('div');modal.className='modal-backdrop';modal.innerHTML=`<section class="create-dialog" role="dialog" aria-modal="true"><header><div><span class="section-kicker">Access review</span><h2>${approved?'同意':'拒绝'}访问申请</h2><p>该操作会写入访问申请状态和审计记录。</p></div><button class="icon-button" type="button" data-close-review aria-label="关闭">×</button></header><div class="c06-dialog-body"><p>确认${approved?'同意':'拒绝'} <strong>${escape(row.querySelector('.person-identity strong')?.textContent)}</strong> 的申请？</p><p class="form-message" data-review-message role="status"></p><div class="dialog-actions"><button class="secondary-button" type="button" data-close-review>取消</button><button class="primary-button" type="button" data-confirm-review>确认</button></div></div></section>`;document.body.append(modal);const close=()=>modal.remove();modal.querySelectorAll('[data-close-review]').forEach(item=>item.addEventListener('click',close));modal.querySelector('[data-confirm-review]').addEventListener('click',async event=>{event.currentTarget.disabled=true;try{await api('/v1/admin/access-requests/'+encodeURIComponent(row.dataset.requestId)+'/review',{method:'POST',body:JSON.stringify({status:button.dataset.review})});row.remove();close()}catch(error){const message=modal.querySelector('[data-review-message]');message.textContent=error.message;message.className='form-message';event.currentTarget.disabled=false}})};
  document.addEventListener('click',event=>{const button=event.target.closest('[data-review]');if(!button)return;const row=button.closest('[data-request-id]');if(!row)return;event.preventDefault();event.stopImmediatePropagation();button.disabled=true;review(button,row)},true);
  const manageMember=async row=>{
    const userId=row.dataset.userId;
    try{
      const users=await api('/v1/admin/users'),user=users.find(item=>item.id===userId);
      if(!user)throw new Error('成员不存在或已被删除');
      const node=document.createElement('div');node.className='modal-backdrop';
      node.innerHTML=`<section class="create-dialog" role="dialog" aria-modal="true" aria-labelledby="member-title"><header><div><span class="section-kicker">Member management</span><h2 id="member-title">管理成员</h2><p>${escape(user.email||user.username)} · 修改后立即写入 Cloud。</p></div><button class="icon-button" type="button" data-close-member aria-label="关闭">×</button></header><form class="auth-form" data-member-form><label>登录标识<input name="username" value="${escape(user.username)}" required></label><label>显示名称<input name="display_name" value="${escape(user.display_name||user.username)}" required></label><label class="switch-row"><span>账号状态</span><span><input type="checkbox" name="disabled" ${user.disabled?'checked':''}> 停用账号</span></label><label>重置密码 <small class="optional-label">不修改请留空</small><input name="password" type="password" minlength="12" placeholder="至少 12 位"></label><p class="form-message" data-member-message role="status"></p><div class="dialog-actions"><button class="secondary-button danger-button" type="button" data-delete-member>删除成员</button><span></span><button class="secondary-button" type="button" data-close-member>取消</button><button class="primary-button" type="submit">保存修改</button></div></form></section>`;
      document.body.append(node);
      const form=node.querySelector('[data-member-form]'),message=node.querySelector('[data-member-message]'),close=()=>node.remove();
      node.querySelectorAll('[data-close-member]').forEach(item=>item.addEventListener('click',close));
      form.addEventListener('submit',async event=>{
        event.preventDefault();const submit=form.querySelector('[type="submit"]');submit.disabled=true;
        const body={username:form.elements.username.value.trim(),display_name:form.elements.display_name.value.trim(),disabled:form.elements.disabled.checked};
        if(form.elements.password.value)body.password=form.elements.password.value;
        try{await api('/v1/admin/users/'+encodeURIComponent(userId),{method:'PUT',body:JSON.stringify(body)});row.querySelector('.person-identity strong').textContent=body.display_name;row.querySelector('.person-identity small').textContent=user.email||'';row.querySelector('[data-member-status]').textContent=`user · ${body.disabled?'停用':'正常'}`;message.textContent='成员信息已保存';message.className='form-message info';setTimeout(close,550)}catch(error){message.textContent=error.message;message.className='form-message'}finally{submit.disabled=false}
      });
      node.querySelector('[data-delete-member]').addEventListener('click',async event=>{
        if(!window.confirm(`确认删除 ${user.display_name||user.username}？该成员的 Cloud 会话、设备授权和 Token 也会被删除。`))return;
        event.currentTarget.disabled=true;try{await api('/v1/admin/users/'+encodeURIComponent(userId),{method:'DELETE'});row.remove();close()}catch(error){message.textContent=error.message;message.className='form-message';event.currentTarget.disabled=false}
      });
    }catch(error){const message=document.createElement('p');message.className='form-message';message.textContent=error.message;document.querySelector('.people-panel')?.prepend(message);setTimeout(()=>message.remove(),3000)}
  };
  document.addEventListener('click',event=>{const button=event.target.closest('[data-manage-member]');if(!button)return;const row=button.closest('[data-user-id]');if(!row)return;event.preventDefault();event.stopImmediatePropagation();manageMember(row)},true);
  const refreshOverview=async()=>{
    try{
      const [pending,users,invitations]=await Promise.all([api('/v1/admin/access-requests?status=pending'),api('/v1/admin/users'),api('/v1/admin/invitations?status=pending')]);
      const cards=document.querySelectorAll('.people-overview article');
      if(cards[0])cards[0].querySelector('strong').textContent=pending.length;
      if(cards[1]){cards[1].querySelector('strong').textContent=users.filter(item=>!item.disabled).length;cards[1].querySelector('small').textContent=`包含管理员 ${users.filter(item=>item.role==='admin').length} 人`}
      if(cards[2])cards[2].querySelector('strong').textContent=invitations.filter(item=>item.status==='pending').length;
    }catch(error){/* the table loader owns its own visible error state */}
  };
  window.setTimeout(refreshOverview,250);
})();
