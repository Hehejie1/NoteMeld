const settingsTabs=[...document.querySelectorAll('[data-setting-tab]')],settingsViews=[...document.querySelectorAll('[data-setting-view]')],modelDialog=document.querySelector('[data-model-dialog]');
settingsTabs.forEach(tab=>tab.addEventListener('click',()=>{settingsTabs.forEach(item=>item.classList.toggle('active',item===tab));settingsViews.forEach(view=>view.classList.toggle('active',view.dataset.settingView===tab.dataset.settingTab))}));
document.querySelector('[data-model-add]')?.addEventListener('click',()=>modelDialog.showModal());
