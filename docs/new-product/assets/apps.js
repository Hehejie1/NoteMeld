document.querySelectorAll('[data-app-tab]').forEach(button=>button.addEventListener('click',()=>{
  const target=button.dataset.appTab;
  document.querySelectorAll('[data-app-tab]').forEach(item=>item.classList.toggle('active',item===button));
  document.querySelectorAll('[data-app-view]').forEach(view=>view.classList.toggle('active',view.dataset.appView===target));
}));
document.querySelectorAll('[data-app-search]').forEach(input=>input.addEventListener('input',()=>{
  const query=input.value.trim().toLowerCase();
  document.querySelectorAll('[data-app-item]').forEach(item=>item.classList.toggle('is-filtered',Boolean(query&&!item.textContent.toLowerCase().includes(query))));
}));
