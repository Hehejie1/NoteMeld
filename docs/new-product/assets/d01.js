const composer=document.querySelector('[data-composer]');
const popups=[...document.querySelectorAll('[data-popup]')];
function closePopups(){popups.forEach(p=>p.classList.remove('is-open'))}
document.querySelectorAll('[data-popup-toggle]').forEach(button=>button.addEventListener('click',()=>{const popup=document.querySelector(`[data-popup="${button.dataset.popupToggle}"]`);const open=popup.classList.contains('is-open');closePopups();if(!open)popup.classList.add('is-open')}));
document.querySelectorAll('[data-popup-close]').forEach(button=>button.addEventListener('click',closePopups));
document.addEventListener('click',event=>{if(composer&&!composer.contains(event.target))closePopups()});
const workspace=document.querySelector('.agent-workspace');
document.querySelectorAll('[data-panel-toggle]').forEach(button=>button.addEventListener('click',()=>{const panel=document.querySelector(`[data-panel="${button.dataset.panelToggle}"]`);if(!panel)return;const open=!panel.classList.contains('is-open');panel.classList.toggle('is-open',open);workspace?.classList.toggle(`panel-${button.dataset.panelToggle}-open`,open)}));
document.querySelectorAll('[data-panel-close]').forEach(button=>button.addEventListener('click',event=>{const panel=event.currentTarget.closest('[data-panel]');if(!panel)return;panel.classList.remove('is-open');workspace?.classList.remove(`panel-${panel.dataset.panel}-open`)}));
const themeButton=document.querySelector('[data-theme-toggle]');
try{if(localStorage.getItem('notemeld-theme')==='dark')document.body.classList.add('theme-dark')}catch{}
function syncThemeLabel(){const dark=document.body.classList.contains('theme-dark');if(themeButton)themeButton.querySelector('b').textContent=dark?'深色':'浅色';document.querySelector('.new-conversation-body h1')?.style.setProperty('color',dark?'#f2f5fc':'#202533','important');document.querySelector('.new-conversation-body p')?.style.setProperty('color',dark?'#b5bfd1':'#8791a5','important')}
syncThemeLabel();
themeButton?.addEventListener('click',()=>{const dark=document.body.classList.toggle('theme-dark');syncThemeLabel();try{localStorage.setItem('notemeld-theme',dark?'dark':'light')}catch{}});
const textarea=document.querySelector('textarea');const limit=document.querySelector('.limit');
textarea?.addEventListener('input',()=>{if(limit)limit.textContent=`${textarea.value.length} / ${textarea.maxLength}`;const last=textarea.value.slice(-1);if(last==='/'||last==='@'){closePopups();document.querySelector(`[data-popup="${last==='/'?'slash':'mention'}"]`)?.classList.add('is-open')}});
document.querySelectorAll('.starter-grid button').forEach(button=>button.addEventListener('click',()=>{
  if(!textarea)return;
  textarea.value=button.textContent.trim();
  textarea.dispatchEvent(new Event('input',{bubbles:true}));
  textarea.focus();
}));
document.querySelector('.send-button')?.addEventListener('click',()=>{
  if(!textarea?.value.trim()){textarea?.focus();return;}
  const button=document.querySelector('.send-button');
  button?.setAttribute('aria-label','已发送');
  button?.classList.add('sent');
  if(limit)limit.textContent='已准备提交';
});
document.addEventListener('keydown',event=>{if(event.key==='Escape')closePopups()});
