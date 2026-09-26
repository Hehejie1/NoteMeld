(()=>{
  if(document.body.dataset.page!=='C03')return;
  const AUTO_TITLE='Auto：根据你发送的文件自动匹配合适的模型；执行报错时自动切换其他可用模型';
  const NO_MODEL_TITLE='暂无可用模型，请先到设置中配置模型';
  // 纯原型预览（静态服务器，没有 /v1 接口）下用于演示的模型，避免弹层误报“未登录”。
  const DEMO_MODELS=[
    {id:'demo-balanced',name:'均衡模型',model:'demo-balanced',enabled:true,is_default:true},
    {id:'demo-fast',name:'快速模型',model:'demo-fast',enabled:true},
    {id:'demo-long',name:'长文本模型',model:'demo-long-context',enabled:true}
  ];
  const labelOf=button=>button.querySelector('[data-model-label]');
  const close=()=>document.querySelectorAll('.c03-choice-popover').forEach(node=>node.remove());
  // 参考 antd Select Trigger/Dropdown：弹层 portal 到 body，用 fixed 紧贴触发按钮，
  // 可超出父容器；下方空间不足时自动翻转到上方。
  const popup=(button,className,html)=>{
    close();
    const node=document.createElement('div');
    node.className=`c03-choice-popover ${className}`;
    node.innerHTML=html;
    node.style.visibility='hidden';
    document.body.append(node);
    const rect=button.getBoundingClientRect();
    const h=node.offsetHeight,w=node.offsetWidth;
    const spaceBelow=innerHeight-rect.bottom,spaceAbove=rect.top;
    if(spaceBelow>=h||spaceBelow>=spaceAbove){
      node.style.top=(rect.bottom+6)+'px';
    }else{
      node.style.bottom=(innerHeight-rect.top+6)+'px';
    }
    let left=rect.left;
    if(left+w>innerWidth-8)left=Math.max(8,innerWidth-w-8);
    node.style.left=left+'px';
    node.style.minWidth=Math.max(rect.width,200)+'px';
    node.style.maxHeight=Math.min(320,spaceBelow>=h||spaceBelow>=spaceAbove?spaceBelow-10:spaceAbove-10)+'px';
    node.style.visibility='visible';
    return node;
  };
  const replaceButton=selector=>{const old=document.querySelector(selector);if(!old)return null;const fresh=old.cloneNode(true);old.replaceWith(fresh);return fresh};
  const setAuto=button=>{button.dataset.modelId='';button.dataset.noModel='false';const label=labelOf(button);if(label)label.textContent='Auto';button.title=AUTO_TITLE};
  const setModel=(button,model)=>{button.dataset.modelId=model.id;button.dataset.noModel='false';const label=labelOf(button);if(label)label.textContent=model.name;button.title=`当前模型：${model.name}（${model.model}）。切换回 Auto 可按文件自动匹配`};
  const renderModelChoices=(button,models,{demo}={})=>{
    const enabled=models.filter(item=>item.enabled!==false);
    if(!enabled.length){
      popup(button,'model-popover','<p>没有可用模型，请先到设置中添加模型。</p>');
      return;
    }
    const current=button.dataset.modelId||'';
    const autoSelected=current===''?'aria-selected="true"':'';
    const note=demo?'<p class="model-popover-note">原型预览未连接云端接口，以下为演示模型；连接真实云端后显示组织配置的模型。</p>':'';
    const node=popup(button,'model-popover',`${note}<button type="button" data-model-choice="auto" ${autoSelected}><span><strong>Auto</strong><small>按发送的文件自动匹配，报错自动切换</small></span><span>自动</span></button>${enabled.map(item=>`<button type="button" data-model-choice="${item.id}" aria-selected="${item.id===current}"><span><strong>${item.name}</strong><small>${item.model}</small></span></button>`).join('')}`);
    node.querySelector('[data-model-choice="auto"]').addEventListener('click',()=>{setAuto(button);close();document.querySelector('.cloud-composer textarea')?.dispatchEvent(new Event('input'))});
    node.querySelectorAll('[data-model-choice]:not([data-model-choice="auto"])').forEach(choice=>choice.addEventListener('click',()=>{const model=enabled.find(item=>item.id===choice.dataset.modelChoice);if(model)setModel(button,model);close();document.querySelector('.cloud-composer textarea')?.dispatchEvent(new Event('input'))}));
  };
  const permission=replaceButton('.permission-button');
  permission?.addEventListener('click',event=>{event.preventDefault();event.stopImmediatePropagation();const full=permission.dataset.full==='true';const node=popup(permission,'permission-popover',`<p>当前为${full?'完全授权':'默认权限'}，所有操作都会在安全沙箱约束内进行，超出范围会请求你的允许。</p><hr><label class="choice-toggle"><span>允许完全访问</span><input type="checkbox" ${full?'checked':''}></label>`);node.querySelector('input').addEventListener('change',change=>{permission.dataset.full=String(change.currentTarget.checked);permission.querySelector('span').textContent=change.currentTarget.checked?'完全授权':'默认权限';close()})});
  const model=replaceButton('.model-button');
  model?.addEventListener('click',event=>{
    event.preventDefault();event.stopImmediatePropagation();
    const token=sessionStorage.getItem('notemeld-cloud-token');
    if(!token){
      // 静态原型预览：没有真实登录态，展示演示模型而不是“未登录”报错。
      if(!model.dataset.modelLoaded){model.dataset.modelLoaded='demo';if(model.dataset.noModel==='true')setAuto(model);}
      renderModelChoices(model,DEMO_MODELS,{demo:true});
      return;
    }
    fetch('/v1/models',{headers:{Authorization:`Bearer ${token}`}}).then(response=>response.json()).then(payload=>{
      const models=payload.data||[];
      renderModelChoices(model,models);
      if(models.filter(item=>item.enabled).length){model.dataset.modelLoaded='true';if(!model.dataset.modelId)setAuto(model);}
    }).catch(error=>popup(model,'model-popover',`<p>${error.message}</p>`));
  });
  document.addEventListener('mousedown',event=>{if(!event.target.closest('.c03-choice-popover,.permission-button,.model-button'))close()});
  window.addEventListener('resize',close);
  document.querySelector('[data-session-scroll]')?.addEventListener('scroll',close,true);
})();
