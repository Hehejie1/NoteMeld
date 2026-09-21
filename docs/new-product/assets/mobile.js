(()=>{
  const designTokens=document.createElement('link'); designTokens.rel='stylesheet'; designTokens.href='../../design-system/tokens.css'; document.head.append(designTokens);
  const designPrimitives=document.createElement('link'); designPrimitives.rel='stylesheet'; designPrimitives.href='../../design-system/primitives.css'; document.head.append(designPrimitives);
  const designScript=document.createElement('script'); designScript.src='../../design-system/primitives.js'; designScript.dataset.nmDesignSystem='true'; document.head.append(designScript);
  const iconize=()=>{
    document.querySelectorAll('[data-icon]').forEach(node=>{
      node.setAttribute('data-lucide',node.dataset.icon);
      node.removeAttribute('data-icon');
    });
    window.lucide?.createIcons({attrs:{'stroke-width':2}});
  };

  const loadGsap=()=>new Promise(resolve=>{
    if(window.gsap){resolve(window.gsap);return;}
    const script=document.createElement('script');
    script.src='../../assets/vendor/gsap.min.js';
    script.onload=()=>resolve(window.gsap);
    script.onerror=()=>resolve(null);
    document.head.appendChild(script);
  });

  const navigate=id=>{
    if(parent!==window) parent.postMessage({type:'notemeld-page',id},'*');
    else location.href='./'+id.toLowerCase()+'.html';
  };

  if(document.body.dataset.page==='M01'){
    document.querySelector('.mobile-home > .mobile-section')?.remove();
    const drawerHeaderAction=document.querySelector('[data-menu-panel] header button');
    if(drawerHeaderAction){
      drawerHeaderAction.removeAttribute('data-go');
      drawerHeaderAction.setAttribute('data-menu-close','');
      drawerHeaderAction.setAttribute('aria-label','关闭菜单');
      drawerHeaderAction.innerHTML='<i data-icon="x"></i>';
    }
    const drawerSettings=document.querySelector('.drawer-close');
    if(drawerSettings){
      drawerSettings.classList.add('drawer-settings');
      drawerSettings.removeAttribute('data-menu-close');
      drawerSettings.dataset.go='M03';
      drawerSettings.innerHTML='<i data-icon="settings"></i><span><strong>iPhone 15 Pro</strong><small>NoteMeld Mobile · v0.9.0</small></span>';
    }
  }

  const newSessionIcon=document.querySelector('[aria-label="新建会话"] [data-icon]');
  if(newSessionIcon) newSessionIcon.dataset.icon='message-circle-plus';
  iconize();
  document.querySelectorAll('[data-go]').forEach(node=>node.addEventListener('click',event=>{
    event.preventDefault();
    navigate(node.dataset.go);
  }));

  const panel=document.querySelector('[data-menu-panel]');
  const scrim=document.querySelector('.drawer-scrim');
  const openMenu=()=>{if(panel)panel.hidden=false;if(scrim)scrim.hidden=false;window.gsap?.fromTo(panel,{xPercent:-100},{xPercent:0,duration:.42,ease:'power3.out'});};
  const closeMenu=()=>{if(panel)panel.hidden=true;if(scrim)scrim.hidden=true;};
  document.querySelectorAll('[data-menu]').forEach(node=>node.addEventListener('click',openMenu));
  document.querySelectorAll('[data-menu-close]').forEach(node=>node.addEventListener('click',closeMenu));

  document.querySelectorAll('.work-tabs button').forEach(button=>button.addEventListener('click',()=>{
    document.querySelectorAll('.work-tabs button').forEach(item=>item.classList.toggle('active',item===button));
  }));

  const savedTheme=localStorage.getItem('notemeld-theme');
  if(savedTheme) document.body.dataset.theme=savedTheme;
  const storedFontSize=Number(localStorage.getItem('notemeld-font-size'))||16;
  document.documentElement.style.setProperty('--mobile-font-scale',String(storedFontSize/16));
  const fontSummary=document.querySelector('[data-font-summary]');
  if(fontSummary) fontSummary.textContent=storedFontSize<=14?'小':storedFontSize>=18?'大':'标准';
  document.querySelectorAll('.theme-tabs button').forEach(button=>{
    button.classList.toggle('active',(savedTheme||'系统')===button.textContent.trim());
    button.addEventListener('click',()=>{
      const theme=button.textContent.trim();
      document.querySelectorAll('.theme-tabs button').forEach(item=>item.classList.toggle('active',item===button));
      document.body.dataset.theme=theme;
      localStorage.setItem('notemeld-theme',theme);
    });
  });

  const action=document.querySelector('[data-action-popover]');
  const backdrop=document.querySelector('[data-sheet-backdrop]');
  const sheets={
    attachment:document.querySelector('[data-attachment-sheet]'),
    model:document.querySelector('[data-model-sheet]'),
    permission:document.querySelector('[data-permission-sheet]'),
    language:document.querySelector('[data-language-sheet]'),
    log:document.querySelector('[data-log-sheet]')
  };
  const accessModal=document.querySelector('[data-access-modal]');
  const closeSheets=()=>{
    if(action)action.hidden=true;
    if(backdrop)backdrop.hidden=true;
    Object.values(sheets).forEach(sheet=>{if(sheet)sheet.hidden=true;});
    if(accessModal) accessModal.hidden=true;
  };
  const openSheet=sheet=>{
    closeSheets();
    if(backdrop)backdrop.hidden=false;
    if(sheet){
      sheet.hidden=false;
      window.gsap?.fromTo(sheet,{yPercent:100,autoAlpha:0},{yPercent:0,autoAlpha:1,duration:.42,ease:'power3.out',overwrite:'auto'});
    }
  };
  document.querySelector('[data-sheet-backdrop]')?.addEventListener('click',closeSheets);
  document.querySelectorAll('[data-sheet-close]').forEach(button=>button.addEventListener('click',closeSheets));

  document.querySelectorAll('[data-composer]').forEach(composer=>{
    const input=composer.querySelector('input');
    let engaged=false;
    const sync=()=>{
      const expanded=Boolean(input?.value.trim())||engaged||composer.contains(document.activeElement);
      composer.classList.toggle('is-expanded',expanded);
      composer.setAttribute('aria-expanded',String(expanded));
    };
    input?.addEventListener('focus',()=>{engaged=true;sync();});
    input?.addEventListener('input',sync);
    input?.addEventListener('blur',()=>setTimeout(sync,0));
    composer.querySelectorAll('button').forEach(button=>button.addEventListener('pointerdown',()=>{engaged=true;sync();}));
    composer.addEventListener('composer:reset',()=>{engaged=false;sync();});
  });

  document.querySelector('[data-actions]')?.addEventListener('click',()=>{
    closeSheets();
    if(action){
      action.hidden=false;
      window.gsap?.fromTo(action,{scale:.92,y:-8,autoAlpha:0},{scale:1,y:0,autoAlpha:1,duration:.25,ease:'power2.out'});
    }
  });
  document.querySelector('[data-products]')?.addEventListener('click',()=>{
    closeSheets();
    navigate('M09');
  });
  document.querySelector('[data-delete-chat]')?.addEventListener('click',()=>{
    closeSheets();
    const title=document.querySelector('.chat-header strong');
    if(title) title.textContent='新建会话';
    const list=document.querySelector('.chat-scroll');
    if(list) list.innerHTML='<p class="chat-date">刚刚 · 云端工作</p><div class="agent-label"><span>✦</span>NoteMeld Agent</div><div class="message agent-message"><p>新的云端会话已准备好。告诉我你想完成什么。</p></div>';
  });

  document.querySelector('[data-model-open]')?.addEventListener('click',()=>openSheet(sheets.model));
  document.querySelectorAll('[data-model-choice]').forEach(choice=>choice.addEventListener('click',()=>{
    const label=document.querySelector('[data-model-label]');
    if(label) label.textContent=choice.dataset.modelChoice;
    closeSheets();
  }));
  document.querySelectorAll('[data-permission-toggle]').forEach(button=>button.addEventListener('click',()=>openSheet(sheets.permission)));
  document.querySelectorAll('[data-permission-choice]').forEach(choice=>choice.addEventListener('click',()=>{
    if(choice.dataset.permissionChoice==='full'){
      closeSheets();
      if(accessModal) accessModal.hidden=false;
      return;
    }
    document.querySelectorAll('[data-permission-choice]').forEach(item=>item.classList.toggle('selected',item===choice));
    document.querySelectorAll('[data-permission-toggle]').forEach(button=>{
      button.setAttribute('aria-pressed','false');
      button.querySelector('[data-permission-label]')?.replaceChildren(document.createTextNode('默认权限'));
    });
    closeSheets();
  }));
  document.querySelector('[data-access-cancel]')?.addEventListener('click',()=>{if(accessModal) accessModal.hidden=true;});
  document.querySelector('[data-access-confirm]')?.addEventListener('click',()=>{
    document.querySelectorAll('[data-permission-choice]').forEach(item=>item.classList.toggle('selected',item.dataset.permissionChoice==='full'));
    document.querySelectorAll('[data-permission-toggle]').forEach(button=>{button.setAttribute('aria-pressed','true');button.querySelector('[data-permission-label]')?.replaceChildren(document.createTextNode('完全访问'));});
    if(accessModal) accessModal.hidden=true;
  });

  document.querySelectorAll('[data-file-add]').forEach(button=>button.addEventListener('click',()=>openSheet(sheets.attachment)));
  const chooseFile=selector=>document.querySelector(selector)?.click();
  document.querySelector('[data-camera-open]')?.addEventListener('click',()=>chooseFile('[data-camera-input]'));
  document.querySelector('[data-gallery-open]')?.addEventListener('click',()=>chooseFile('[data-gallery-input]'));
  document.querySelector('[data-files-open]')?.addEventListener('click',()=>chooseFile('[data-files-input]'));
  ['camera','gallery','files'].forEach(kind=>document.querySelector(`[data-${kind}-input]`)?.addEventListener('change',event=>{
    if(event.target.files?.length){document.querySelectorAll('[data-composer] input').forEach(input=>{input.placeholder=`已添加 ${event.target.files.length} 个文件，继续告诉 Agent…`;input.focus();});closeSheets();}
  }));
  const capabilityData={skills:[['会议纪要整理','从录音或文本提炼结论与行动项'],['网页研究','检索资料并整理带来源的摘要'],['代码审查','检查 Workspace 代码并标记风险']],plugins:[['浏览器','访问网页并提取可引用内容'],['文档处理','读取、转换和生成办公文档'],['终端','在授权范围内执行命令']],apps:[['笔记应用','把结果整理进 NoteMeld 笔记'],['学习空间','生成学习卡片与复习计划'],['监控中心','查看 Agent 与设备状态']],agents:[['研究助理','擅长检索、归纳和引用'],['项目管家','拆解任务并持续跟进'],['代码专家','定位工程问题并提出修复建议']]};
  const renderCapabilities=(type,query='')=>{
    const list=document.querySelector('[data-capability-list]'); if(!list)return;
    const values=capabilityData[type]||[]; const filtered=values.filter(([name,desc])=>(name+desc).includes(query));
    list.className='capability-list'; list.innerHTML=filtered.map(([name,desc])=>`<button class="capability-item" data-capability-choice="${name}"><i data-icon="${type==='skills'?'sparkles':type==='plugins'?'puzzle':type==='apps'?'grid-2x2':'bot'}"></i><span><strong>${name}</strong><small>${desc}</small></span><i class="check" data-icon="plus"></i></button>`).join('')||'<p class="sheet-description">没有匹配的内容</p>';
    iconize();
  };
  document.querySelectorAll('[data-capability-tab]').forEach(tab=>tab.addEventListener('click',()=>{
    document.querySelectorAll('[data-capability-tab]').forEach(item=>item.classList.toggle('active',item===tab));
    const library=document.querySelector('[data-capability-library]'); if(library) library.hidden=false;
    renderCapabilities(tab.dataset.capabilityTab,document.querySelector('[data-capability-search]')?.value||'');
  }));
  document.querySelector('[data-capability-search]')?.addEventListener('input',event=>{const active=document.querySelector('[data-capability-tab].active');renderCapabilities(active?.dataset.capabilityTab||'skills',event.target.value.trim());});

  document.querySelector('[data-language-open]')?.addEventListener('click',()=>openSheet(sheets.language));
  document.querySelectorAll('[data-language-choice]').forEach(choice=>choice.addEventListener('click',()=>{
    const value=document.querySelector('[data-language-open] em');
    if(value) value.textContent=choice.dataset.languageChoice;
    localStorage.setItem('notemeld-language',choice.dataset.languageChoice);
    closeSheets();
  }));

  document.querySelector('[data-notification-toggle]')?.addEventListener('click',event=>{
    const button=event.currentTarget;
    const enabled=button.getAttribute('aria-pressed')!=='true';
    button.setAttribute('aria-pressed',String(enabled));
    const state=button.querySelector('[data-notification-state]');
    if(state) state.textContent=enabled?'已开启':'已关闭';
  });

  const concat=(...parts)=>{
    const length=parts.reduce((sum,part)=>sum+part.length,0);
    const output=new Uint8Array(length);
    let offset=0;
    parts.forEach(part=>{output.set(part,offset);offset+=part.length;});
    return output;
  };
  const u16=value=>new Uint8Array([value&255,(value>>>8)&255]);
  const u32=value=>new Uint8Array([value&255,(value>>>8)&255,(value>>>16)&255,(value>>>24)&255]);
  const crcTable=Array.from({length:256},(_,n)=>{
    let c=n;
    for(let k=0;k<8;k++) c=(c&1)?0xedb88320^(c>>>1):c>>>1;
    return c>>>0;
  });
  const crc32=bytes=>{
    let crc=0xffffffff;
    bytes.forEach(byte=>{crc=crcTable[(crc^byte)&255]^(crc>>>8);});
    return (crc^0xffffffff)>>>0;
  };
  const makeZip=(name,text)=>{
    const encoder=new TextEncoder();
    const fileName=encoder.encode(name);
    const data=encoder.encode(text);
    const crc=crc32(data);
    const now=new Date();
    const dosTime=(now.getHours()<<11)|(now.getMinutes()<<5)|(now.getSeconds()>>1);
    const dosDate=((now.getFullYear()-1980)<<9)|((now.getMonth()+1)<<5)|now.getDate();
    const local=concat(u32(0x04034b50),u16(20),u16(0),u16(0),u16(dosTime),u16(dosDate),u32(crc),u32(data.length),u32(data.length),u16(fileName.length),u16(0),fileName,data);
    const central=concat(u32(0x02014b50),u16(20),u16(20),u16(0),u16(0),u16(dosTime),u16(dosDate),u32(crc),u32(data.length),u32(data.length),u16(fileName.length),u16(0),u16(0),u16(0),u16(0),u32(0),u32(0),fileName);
    const end=concat(u32(0x06054b50),u16(0),u16(0),u16(1),u16(1),u32(central.length),u32(local.length),u16(0));
    return new Blob([local,central,end],{type:'application/zip'});
  };

  let pendingLogBlob=null;
  let pendingLogFile=null;
  document.querySelector('[data-log-export]')?.addEventListener('click',()=>openSheet(sheets.log));
  document.querySelectorAll('[data-log-range]').forEach(button=>button.addEventListener('click',async()=>{
    const progress=document.querySelector('[data-export-progress]');
    const state=document.querySelector('[data-export-state]');
    document.querySelectorAll('[data-log-range]').forEach(item=>item.disabled=true);
    if(progress) progress.hidden=false;
    const spin=window.gsap?.to(progress?.querySelector('span'),{rotation:360,duration:.8,ease:'none',repeat:-1});
    if(state) state.textContent='收集 '+button.dataset.logRange+'…';
    await new Promise(resolve=>setTimeout(resolve,650));
    if(state) state.textContent='压缩并脱敏…';
    await new Promise(resolve=>setTimeout(resolve,550));
    const log='NoteMeld diagnostic log\nRange: '+button.dataset.logRange+'\nGenerated: '+new Date().toISOString()+'\nSensitive fields: redacted\n';
    const blob=makeZip('notemeld.log',log);
    const file=new File([blob],'NoteMeld-logs.zip',{type:'application/zip'});
    pendingLogBlob=blob;
    pendingLogFile=file;
    spin?.kill();
    if(state) state.textContent='ZIP 已生成，可分享或保存';
    const shareButton=document.querySelector('[data-share-zip]');
    if(shareButton) shareButton.hidden=false;
    document.querySelectorAll('[data-log-range]').forEach(item=>item.disabled=false);
  }));
  document.querySelector('[data-share-zip]')?.addEventListener('click',async()=>{
    if(!pendingLogBlob||!pendingLogFile) return;
    const state=document.querySelector('[data-export-state]');
    const downloadZip=()=>{
      const link=document.createElement('a');
      link.href=URL.createObjectURL(pendingLogBlob);
      link.download=pendingLogFile.name;
      link.click();
      setTimeout(()=>URL.revokeObjectURL(link.href),1000);
    };
    try{
      if(navigator.canShare?.({files:[pendingLogFile]})) await navigator.share({files:[pendingLogFile],title:'NoteMeld 日志'});
      else downloadZip();
    }catch(error){
      if(error?.name==='AbortError'){
        if(state) state.textContent='已取消分享';
      }else{
        downloadZip();
        if(state) state.textContent='已下载 ZIP，可从其他软件分享';
      }
    }
  });

  document.querySelector('[data-clear-log]')?.addEventListener('click',()=>{
    if(!window.confirm('确定清除本机运行日志吗？此操作不可撤销。')) return;
    const state=document.querySelector('[data-log-state]');
    if(state) state.textContent='已清除';
    window.gsap?.fromTo(state,{scale:.8,color:'#d95763'},{scale:1,color:'#7b879a',duration:.4,ease:'back.out(1.7)'});
  });

  const showToast=message=>{
    const toast=document.querySelector('[data-toast]');
    if(!toast) return;
    toast.textContent=message;
    toast.hidden=false;
    if(window.gsap) window.gsap.fromTo(toast,{y:12,autoAlpha:0},{y:0,autoAlpha:1,duration:.28,ease:'power2.out'});
    setTimeout(()=>{if(window.gsap) window.gsap.to(toast,{autoAlpha:0,duration:.2,onComplete:()=>toast.hidden=true});else toast.hidden=true;},1500);
  };

  document.querySelector('[data-copy-memory]')?.addEventListener('click',async()=>{
    const text=document.querySelector('[data-memory-document]')?.innerText||'';
    try{await navigator.clipboard.writeText(text);showToast('已复制到剪贴板');}
    catch{showToast('复制失败，请稍后重试');}
  });
  document.querySelector('[data-add-memory]')?.addEventListener('click',()=>{
    const input=document.querySelector('[data-memory-input]');
    const value=input?.value.trim();
    if(!value){input?.focus();return;}
    const article=document.createElement('article');
    article.innerHTML='<h2>新增记忆</h2><p></p>';
    article.querySelector('p').textContent=value;
    document.querySelector('[data-memory-document]')?.appendChild(article);
    input.value='';
    showToast('记忆已添加');
    window.gsap?.fromTo(article,{y:16,autoAlpha:0},{y:0,autoAlpha:1,duration:.4,ease:'power2.out'});
  });

  const range=document.querySelector('[data-font-range]');
  const updateFontPreview=value=>{
    const size=Number(value);
    document.documentElement.style.setProperty('--preview-font-size',size+'px');
    const label=document.querySelector('[data-font-label]');
    const name=size<=14?'小':size>=18?'大':'标准';
    if(label) label.textContent=name+' · '+size+'px';
  };
  if(range){
    const saved=Number(localStorage.getItem('notemeld-font-size'))||16;
    range.value=String(saved);
    updateFontPreview(saved);
    range.addEventListener('input',()=>updateFontPreview(range.value));
  }
  document.querySelector('[data-system-font]')?.addEventListener('click',event=>{
    const button=event.currentTarget;
    const enabled=button.getAttribute('aria-pressed')!=='true';
    button.setAttribute('aria-pressed',String(enabled));
    if(range) range.disabled=enabled;
  });
  document.querySelector('[data-font-confirm]')?.addEventListener('click',()=>{
    const value=range?.value||'16';
    localStorage.setItem('notemeld-font-size',value);
    const saved=document.querySelector('[data-font-saved]');
    if(saved) saved.hidden=false;
    window.gsap?.fromTo(saved,{y:8,autoAlpha:0},{y:0,autoAlpha:1,duration:.32,ease:'power2.out'});
    setTimeout(()=>navigate('M03'),550);
  });

  const updateStorageTotal=()=>{
    const total=[...document.querySelectorAll('[data-storage-item]')].reduce((sum,item)=>sum+Number(item.dataset.size||0),0);
    const label=document.querySelector('[data-storage-total]');
    if(label) label.textContent=total<.01?'0 KB':total.toFixed(2)+' MB';
    return total;
  };
  const clearStorageItem=button=>{
    const item=button.closest('[data-storage-item]');
    if(!item||Number(item.dataset.size)===0) return;
    button.disabled=true;
    button.textContent='清理中';
    const bar=item.querySelector('.item-progress i');
    const finish=()=>{
      item.dataset.size='0';
      item.querySelector('[data-size-label]').textContent='0 KB';
      button.textContent='已清理';
      if(bar) bar.style.width='0';
      updateStorageTotal();
      showToast('清理完成');
    };
    if(window.gsap) window.gsap.to(bar,{scaleX:0,transformOrigin:'left center',duration:.55,ease:'power3.inOut',onComplete:finish});
    else setTimeout(finish,350);
  };
  document.querySelectorAll('[data-clear-storage]').forEach(button=>button.addEventListener('click',()=>{
    if(window.confirm('清除这类数据吗？部分本地数据清理后无法恢复。')) clearStorageItem(button);
  }));
  document.querySelector('[data-clear-all-storage]')?.addEventListener('click',()=>{
    if(!window.confirm('确定清除全部本机数据吗？此操作不可撤销。')) return;
    document.querySelectorAll('[data-clear-storage]').forEach((button,index)=>setTimeout(()=>clearStorageItem(button),index*120));
  });

  document.querySelectorAll('.mobile-composer .send').forEach(button=>button.addEventListener('click',()=>{
    const input=button.closest('.mobile-composer')?.querySelector('input');
    if(input?.value.trim()){input.value='';input.placeholder='已发送，Agent 正在处理…';button.closest('.mobile-composer')?.dispatchEvent(new Event('composer:reset'));}
  }));

  loadGsap().then(gsap=>{
    if(!gsap) return;
    gsap.defaults({duration:.48,ease:'power2.out'});
    const mm=gsap.matchMedia();
    mm.add({reduceMotion:'(prefers-reduced-motion: reduce)'},context=>{
      if(context.conditions.reduceMotion) return;
      gsap.from('.mobile-header',{y:-12,autoAlpha:0,duration:.38});
      gsap.from('[data-motion]',{y:18,scale:.985,autoAlpha:0,stagger:.07,duration:.5,clearProps:'transform,opacity,visibility'});
      gsap.from('.settings-group>button,.storage-list article',{y:8,autoAlpha:0,stagger:.035,duration:.34,clearProps:'transform,opacity,visibility'});
    });
  });
})();
