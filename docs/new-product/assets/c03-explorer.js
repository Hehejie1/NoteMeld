(()=>{
  if(document.body.dataset.page!=='C03')return;

  // ===== 当前对话空间的文件树数据 =====
  let nextId=1;
  const makeNode=spec=>Object.assign({id:'n'+nextId++,expanded:false},spec);
  const ROOT=makeNode({name:'NoteMeld',type:'folder',expanded:true,children:[
    makeNode({name:'docs',type:'folder',expanded:true,children:[
      makeNode({name:'new-product',type:'folder',expanded:true,children:[
        makeNode({name:'assets',type:'folder',expanded:true,children:[
          makeNode({name:'vendor',type:'folder',children:[makeNode({name:'lucide.js',type:'file'})]}),
          makeNode({name:'c03-controls.css',type:'file',status:'M'}),
          makeNode({name:'c03-controls.js',type:'file',status:'M'}),
          makeNode({name:'c03-panels.js',type:'file',status:'U'}),
          makeNode({name:'cloud.css',type:'file'}),
          makeNode({name:'cloud.js',type:'file'}),
          makeNode({name:'page.js',type:'file'}),
          makeNode({name:'logo.png',type:'file'})
        ]}),
        makeNode({name:'pages',type:'folder',children:[
          makeNode({name:'cloud',type:'folder',children:[
            makeNode({name:'c03.html',type:'file'}),
            makeNode({name:'c02.html',type:'file'})
          ]})
        ]}),
        makeNode({name:'index.html',type:'file'}),
        makeNode({name:'README.md',type:'file'})
      ]})
    ]}),
    makeNode({name:'run_notemeld.sh',type:'file'})
  ]});

  const treeEl=document.querySelector('[data-file-tree]');
  const searchInput=document.querySelector('[data-explorer-search-input]');

  // ===== 工具 =====
  const findParent=(node,target,parent=null)=>{
    if(node===target)return parent;
    for(const child of node.children||[]){
      const found=findParent(child,target,node);
      if(found!==null)return found;
    }
    return null;
  };
  const uniqueName=(folder,name)=>{
    const names=(folder.children||[]).map(c=>c.name);
    if(!names.includes(name))return name;
    const dot=name.lastIndexOf('.');
    const base=dot>0?name.slice(0,dot):name;
    const ext=dot>0?name.slice(dot):'';
    let i=2,candidate;
    do{candidate=`${base} ${i}${ext}`;i++}while(names.includes(candidate));
    return candidate;
  };
  const pathOf=node=>{
    const segs=[];let cur=node;
    while(cur){segs.unshift(cur.name);cur=findParent(ROOT,cur);}
    return '/'+segs.join('/');
  };
  const flatten=(node,out=[])=>{if(node.type==='file')out.push(node);node.children?.forEach(c=>flatten(c,out));return out};
  const allFiles=flatten(ROOT);
  const iconFor=node=>{
    if(node.type==='folder')return node.expanded?'folder-open':'folder';
    const ext=(node.name.split('.').pop()||'').toLowerCase();
    if(['js','mjs'].includes(ext))return 'file-code';
    if(['css','scss'].includes(ext))return 'file-code-2';
    if(['png','jpg','svg','gif','webp'].includes(ext))return 'file-image';
    if(ext==='md')return 'file-text';
    if(ext==='sh')return 'terminal';
    return 'file';
  };
  const statusColor={M:'var(--explorer-modified)',U:'var(--explorer-untracked)'};

  // ===== 右键菜单 =====
  const closeMenu=()=>document.querySelectorAll('.ctx-menu').forEach(n=>n.remove());
  const openMenu=(x,y,items)=>{
    closeMenu();
    const menu=document.createElement('div');menu.className='ctx-menu';
    menu.innerHTML=items.map((it,i)=>it?`<button class="ctx-item" data-i="${i}"><i data-icon="${it.icon}" class="ctx-icon"></i><span>${it.label}</span></button>`:'<hr>').join('');
    document.body.append(menu);
    const w=menu.offsetWidth,h=menu.offsetHeight;
    menu.style.left=Math.min(x,innerWidth-w-8)+'px';
    menu.style.top=Math.min(y,innerHeight-h-8)+'px';
    window.lucide?.createIcons({attrs:{'stroke-width':2,'aria-hidden':'true'}});
    menu.querySelectorAll('.ctx-item').forEach(btn=>btn.addEventListener('click',()=>{const fn=items[Number(btn.dataset.i)].action;closeMenu();fn&&fn();}));
  };

  // ===== 中间弹窗 =====
  const closeModal=()=>document.querySelectorAll('.ui-modal-backdrop').forEach(n=>n.remove());
  const promptModal=({title,initial,confirmText='确定'},onOk)=>{
    closeModal();
    const back=document.createElement('div');back.className='ui-modal-backdrop';
    back.innerHTML=`<div class="ui-modal" role="dialog" aria-modal="true"><h3>${title}</h3><input class="ui-modal-input" value="${initial}"/><div class="ui-modal-actions"><button class="ui-btn ghost" data-cancel>取消</button><button class="ui-btn primary" data-ok>${confirmText}</button></div></div>`;
    document.body.append(back);
    const input=back.querySelector('input');
    const commit=()=>{const value=input.value.trim();if(value){closeModal();onOk(value);}};
    input.focus();input.setSelectionRange(0,initial.indexOf('.')>0?initial.indexOf('.'):initial.length);
    input.addEventListener('keydown',e=>{if(e.key==='Enter')commit();if(e.key==='Escape')closeModal()});
    back.addEventListener('mousedown',e=>{if(e.target===back)closeModal()});
    back.querySelector('[data-cancel]').addEventListener('click',closeModal);
    back.querySelector('[data-ok]').addEventListener('click',commit);
  };
  const confirmModal=({title,message,confirmText='删除'},onOk)=>{
    closeModal();
    const back=document.createElement('div');back.className='ui-modal-backdrop';
    back.innerHTML=`<div class="ui-modal" role="dialog" aria-modal="true"><h3>${title}</h3><p class="ui-modal-text">${message}</p><div class="ui-modal-actions"><button class="ui-btn ghost" data-cancel>取消</button><button class="ui-btn danger" data-ok>${confirmText}</button></div></div>`;
    document.body.append(back);
    back.addEventListener('mousedown',e=>{if(e.target===back)closeModal()});
    back.querySelector('[data-cancel]').addEventListener('click',closeModal);
    back.querySelector('[data-ok]').addEventListener('click',()=>{closeModal();onOk()});
  };

  // ===== 节点操作 =====
  const createChild=(folder,type)=>{
    const initial=type==='folder'?'新建文件夹':'新建文件.txt';
    promptModal({title:type==='folder'?'新建文件夹':'新建文件',initial,confirmText:'创建'},name=>{
      const node=makeNode({name:uniqueName(folder,name),type});
      folder.children=folder.children||[];
      folder.children.push(node);
      folder.expanded=true;
      render();
    });
  };
  const renameNode=node=>{
    promptModal({title:'重命名',initial:node.name,confirmText:'保存'},name=>{
      const parent=findParent(ROOT,node);
      node.name=uniqueName(parent,name);
      render();
    });
  };
  const deleteNode=node=>{
    confirmModal({title:'删除文件',message:`确定删除 “${node.name}” 吗？`},()=>{
      const parent=findParent(ROOT,node);
      parent.children=parent.children.filter(c=>c!==node);
      render();
    });
  };
  const addToChat=node=>{
    const row=document.querySelector('.attachment-row');
    if(!row)return;
    const tag=document.createElement('span');
    tag.className='ref-chip';
    tag.dataset.path=pathOf(node);
    tag.innerHTML=`<i data-icon="file-text" class="ref-chip-icon"></i><span class="ref-chip-name">${node.name}</span><button class="ref-chip-close" aria-label="移除引用"><i data-icon="x"></i></button>`;
    tag.querySelector('.ref-chip-close').addEventListener('click',()=>tag.remove());
    row.append(tag);
    window.lucide?.createIcons({attrs:{'stroke-width':2,'aria-hidden':'true'}});
  };

  // ===== 文件树渲染 =====
  const renderNodeRow=(node,depth)=>{
    const wrap=document.createElement('div');
    wrap.className='tree-node'+(node.type==='folder'&&node.expanded?' expanded':'');
    const row=document.createElement('button');
    row.type='button';row.className='tree-row';
    row.style.paddingLeft=(depth*12+8)+'px';
    const expander=node.type==='folder'
      ? `<i data-icon="${node.expanded?'chevron-down':'chevron-right'}" class="tree-expander"></i>`
      : '<span class="tree-expander-spacer"></span>';
    row.innerHTML=`${expander}<i data-icon="${iconFor(node)}" class="tree-icon ${node.type}"></i><span class="tree-name">${node.name}</span>${node.status?`<span class="tree-status" style="color:${statusColor[node.status]}">${node.status}</span>`:''}`;
    wrap.append(row);

    row.addEventListener('click',()=>{
      if(node.type==='folder'){node.expanded=!node.expanded;render();}
      else{document.querySelectorAll('.tree-row.active').forEach(r=>r.classList.remove('active'));row.classList.add('active');}
    });
    row.addEventListener('contextmenu',e=>{
      e.preventDefault();
      const common=[
        {icon:'pencil',label:'重命名',action:()=>renameNode(node)},
        {icon:'corner-up-left',label:'添加到聊天',action:()=>addToChat(node)},
        null,
        {icon:'trash-2',label:'删除',action:()=>deleteNode(node)}
      ];
      const folderExtra=[
        {icon:'file-plus',label:'新建文件',action:()=>createChild(node,'file')},
        {icon:'folder-plus',label:'新建文件夹',action:()=>createChild(node,'folder')},
        null
      ];
      openMenu(e.clientX,e.clientY,node.type==='folder'?folderExtra.concat(common):common);
    });

    if(node.type==='folder'&&node.expanded&&node.children){
      const childWrap=document.createElement('div');childWrap.className='tree-children';
      node.children.forEach(c=>childWrap.append(renderNodeRow(c,depth+1)));
      wrap.append(childWrap);
    }
    return wrap;
  };
  const render=()=>{
    treeEl.innerHTML='';
    treeEl.append(renderNodeRow(ROOT,0));
    window.lucide?.createIcons({attrs:{'stroke-width':2,'aria-hidden':'true'}});
  };
  render();

  // ===== 文件搜索 =====
  const runSearch=()=>{
    const q=searchInput.value.trim().toLowerCase();
    treeEl.innerHTML='';
    if(!q){render();return;}
    const matches=allFiles.filter(f=>f.name.toLowerCase().includes(q));
    if(!matches.length){treeEl.innerHTML='<p class="tree-empty">未找到匹配文件</p>';return;}
    matches.forEach(f=>{
      const row=document.createElement('button');
      row.type='button';row.className='tree-row search-result';
      row.style.paddingLeft='8px';
      row.innerHTML=`<span class="tree-expander-spacer"></span><i data-icon="${iconFor(f)}" class="tree-icon"></i><span class="tree-name">${f.name}</span>`;
      row.addEventListener('contextmenu',e=>{
        e.preventDefault();
        openMenu(e.clientX,e.clientY,[
          {icon:'pencil',label:'重命名',action:()=>renameNode(f)},
          {icon:'corner-up-left',label:'添加到聊天',action:()=>addToChat(f)},
          null,
          {icon:'trash-2',label:'删除',action:()=>deleteNode(f)}
        ]);
      });
      treeEl.append(row);
    });
    window.lucide?.createIcons({attrs:{'stroke-width':2,'aria-hidden':'true'}});
  };
  searchInput.addEventListener('input',runSearch);

  // ===== 根菜单（ellipsis） =====
  document.querySelector('[data-explorer-menu]').addEventListener('click',e=>{
    e.preventDefault();e.stopPropagation();
    const r=e.currentTarget.getBoundingClientRect();
    openMenu(r.left,r.bottom+6,[
      {icon:'file-plus',label:'新建文件',action:()=>createChild(ROOT,'file')},
      {icon:'folder-plus',label:'新建文件夹',action:()=>createChild(ROOT,'folder')},
      null,
      {icon:'refresh-cw',label:'刷新',action:()=>render()},
      {icon:'chevrons-down-up',label:'折叠',action:()=>{ROOT.children.forEach(c=>{if(c.type==='folder')c.expanded=false});render()}}
    ]);
  });
  document.addEventListener('mousedown',e=>{if(!e.target.closest('.ctx-menu'))closeMenu()});
  document.addEventListener('keydown',e=>{if(e.key==='Escape'){closeMenu();closeModal()}});
  window.addEventListener('resize',closeMenu);

  // ===== 终端：多会话标签 =====
  const tabsBar=document.querySelector('.terminal-tabs');
  const termBody=document.querySelector('[data-bottom-logs]');
  let termCount=1;
  const sessions=[{id:1}];
  let activeTerm=1;
  const promptLine=()=>{
    const div=document.createElement('div');div.className='terminal-line';
    div.innerHTML='<span class="t-prompt-user">hehejie@hehejie</span><span class="t-colon">:</span><span class="t-path">~</span><span class="t-colon">$</span><span class="t-cursor"></span>';
    return div;
  };
  const showTerm=id=>{
    activeTerm=id;
    termBody.innerHTML='';termBody.append(promptLine());
    document.querySelectorAll('.terminal-tab').forEach(t=>t.classList.toggle('active',Number(t.dataset.termId)===id));
  };
  const bindClose=(tab,id)=>{
    tab.querySelector('.terminal-tab-close').addEventListener('click',ev=>{
      ev.stopPropagation();
      if(sessions.length<=1)return;
      const idx=sessions.findIndex(s=>s.id===id);sessions.splice(idx,1);tab.remove();
      showTerm(sessions[Math.max(0,idx-1)].id);
    });
  };
  const addTab=id=>{
    const tab=document.createElement('div');
    tab.className='terminal-tab';tab.dataset.termId=id;
    tab.innerHTML=`<i data-icon="terminal"></i><span>ssh ${id}</span><button class="terminal-tab-close" title="关闭终端标签" aria-label="关闭终端标签"><i data-icon="x"></i></button>`;
    tab.addEventListener('click',()=>showTerm(id));
    bindClose(tab,id);
    tabsBar.querySelector('.terminal-add').before(tab);
  };
  const firstTab=tabsBar.querySelector('.terminal-tab');firstTab.dataset.termId='1';
  firstTab.addEventListener('click',()=>showTerm(1));
  bindClose(firstTab,1);
  tabsBar.querySelector('.terminal-add').addEventListener('click',()=>{
    termCount+=1;sessions.push({id:termCount});
    addTab(termCount);showTerm(termCount);
    window.lucide?.createIcons({attrs:{'stroke-width':2,'aria-hidden':'true'}});
  });
})();
