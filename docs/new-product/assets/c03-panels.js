(()=>{
  if(document.body.dataset.page!=='C03')return;
  const red=document.querySelector('[data-session-red]');
  if(!red)return;
  const DEFAULTS={side:290,bottom:220};
  const panelOf=which=>document.querySelector(`[data-panel="${which}"]`);

  const syncToggles=()=>{
    document.querySelectorAll('[data-panel-toggle]').forEach(btn=>{
      const open=red.dataset[btn.dataset.panelToggle]==='open';
      btn.classList.toggle('is-active',open);
      btn.setAttribute('aria-pressed',String(open));
    });
  };
  const applySize=which=>{
    const panel=panelOf(which);
    if(!panel)return;
    if(red.dataset[which]==='open'){
      const size=panel._size??DEFAULTS[which];
      panel._size=size;
      if(which==='side'){panel.style.width=size+'px';panel.style.flexBasis=size+'px';}
      else{panel.style.height=size+'px';panel.style.flexBasis=size+'px';}
    }else if(which==='side'){panel.style.width='0px';panel.style.flexBasis='0px';}
    else{panel.style.height='0px';panel.style.flexBasis='0px';}
  };
  const setPanel=(which,open)=>{
    if(open)red.dataset[which]='open';else delete red.dataset[which];
    applySize(which);syncToggles();
  };

  document.querySelectorAll('[data-panel-toggle]').forEach(btn=>btn.addEventListener('click',event=>{
    event.preventDefault();
    const which=btn.dataset.panelToggle;
    setPanel(which,red.dataset[which]!=='open');
  }));
  document.querySelectorAll('[data-panel-close]').forEach(btn=>btn.addEventListener('click',()=>setPanel(btn.dataset.panelClose,false)));
  syncToggles();

  // ===== Drag resizing =====
  const startDrag=(handle,{orientation,which,min,max})=>{
    handle.addEventListener('pointerdown',event=>{
      if(red.dataset[which]!=='open')return;
      event.preventDefault();
      handle.setPointerCapture(event.pointerId);
      const panel=panelOf(which);
      const startPos=orientation==='x'?event.clientX:event.clientY;
      const startSize=panel._size??DEFAULTS[which];
      red.classList.add('resizing');handle.classList.add('dragging');
      const move=moveEvent=>{
        const delta=orientation==='x'?startPos-moveEvent.clientX:startPos-moveEvent.clientY;
        const next=Math.round(Math.min(max,Math.max(min,startSize+delta)));
        panel._size=next;applySize(which);
      };
      const up=()=>{
        handle.removeEventListener('pointermove',move);handle.removeEventListener('pointerup',up);
        red.classList.remove('resizing');handle.classList.remove('dragging');
      };
      handle.addEventListener('pointermove',move);handle.addEventListener('pointerup',up);
    });
  };
  startDrag(document.querySelector('[data-resize="side"]'),{orientation:'x',which:'side',min:220,max:520});
  startDrag(document.querySelector('[data-resize="bottom"]'),{orientation:'y',which:'bottom',min:120,max:Math.max(320,innerHeight*0.6)});
})();
