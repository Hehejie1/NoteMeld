(()=>{
  if(document.body.dataset.page!=='C03')return;
  const token=sessionStorage.getItem('notemeld-cloud-token'),button=document.querySelector('.cloud-composer .model-button'),send=document.querySelector('.cloud-composer .send-button'),input=document.querySelector('.cloud-composer textarea');
  const refresh=()=>{const hasSession=Boolean(document.body.dataset.sessionId),hasModel=button?.dataset.noModel==='false',hasInput=Boolean(input?.value.trim()),canCreate= document.body.dataset.newSession==='true';if(send){send.disabled=!((hasSession||canCreate)&&hasModel&&hasInput);send.title=!hasSession&&!canCreate?'请先新建或选择会话':!hasModel?'请先在设置中配置模型':!hasInput?'请输入消息':''}};
  input?.addEventListener('input',refresh);refresh();
  if(!token||!button)return;
  fetch('/v1/models',{headers:{Authorization:`Bearer ${token}`}}).then(response=>response.json()).then(payload=>{const models=payload.data||[],enabled=models.filter(item=>item.enabled);const label=button.querySelector('[data-model-label]');if(enabled.length){button.dataset.noModel='false';button.dataset.modelId=button.dataset.modelId||enabled.find(item=>item.is_default)?.id||'';if(!button.dataset.modelId&&label)label.textContent='Auto';button.title=button.dataset.modelId?'切换模型':'Auto：根据发送的文件自动匹配合适的模型，报错时自动切换';}else{button.dataset.noModel='true';if(label)label.textContent='暂无模型';button.title='暂无可用模型，请先到设置中配置模型';}refresh()}).catch(()=>refresh());
  if(document.body) new MutationObserver(refresh).observe(document.body,{attributes:true,attributeFilter:['data-session-id']});
})();
