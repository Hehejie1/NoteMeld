const settingsTabs=[...document.querySelectorAll('[data-setting-tab]')],settingsViews=[...document.querySelectorAll('[data-setting-view]')];
settingsTabs.forEach(tab=>tab.addEventListener('click',()=>{settingsTabs.forEach(item=>item.classList.toggle('active',item===tab));settingsViews.forEach(view=>view.classList.toggle('active',view.dataset.settingView===tab.dataset.settingTab))}));
/* 添加模型弹窗由 desktop-model-settings.js 接管（厂商选择 + 统一表单 + 分享/导入） */
