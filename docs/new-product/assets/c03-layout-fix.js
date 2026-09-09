(()=>{
  if(document.body.dataset.page!=='C03')return;
  const header=document.querySelector('.cloud-session-header'),layout=document.querySelector('.session-layout'),thread=document.querySelector('.session-thread');
  if(header&&layout&&thread){thread.prepend(header);layout.style.gridTemplateColumns='220px minmax(0,1fr) 290px';layout.style.height='calc(100vh - 64px)';header.style.gridColumn='1 / -1';header.style.height='64px';header.style.padding='0 28px';header.querySelector('.eyebrow')?.setAttribute('hidden','true');header.querySelector('[data-session-meta]')?.setAttribute('hidden','true');header.querySelector('h1')?.style.setProperty('font-size','16px')}
})();
