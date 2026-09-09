/* NoteMeld Design System — small behavior layer for the static HTML reference. */
(() => {
  const root = document.documentElement;
  const notify = (message, tone = 'info') => {
    let toast = document.querySelector('[data-nm-toast-node]');
    if (!toast) {
      toast = document.createElement('div');
      toast.dataset.nmToastNode = '';
      toast.setAttribute('role', 'status');
      document.body.append(toast);
    }
    toast.textContent = message;
    toast.dataset.tone = tone;
    toast.classList.add('is-visible');
    clearTimeout(toast._hideTimer);
    toast._hideTimer = setTimeout(() => toast.classList.remove('is-visible'), 2400);
  };

  const markLegacyPrimitives = () => {
    document.querySelectorAll('.primary-button, .secondary-button, .button').forEach(node => {
      node.dataset.nmPrimitive = 'button';
      node.classList.add('nm-button');
      if (node.classList.contains('primary-button') || node.classList.contains('primary')) node.dataset.variant = 'primary';
      else if (node.classList.contains('secondary-button')) node.dataset.variant = 'secondary';
    });
    document.querySelectorAll('.icon-button, .icon-only, .round-button').forEach(node => {
      node.dataset.nmPrimitive = 'icon-button';
      node.classList.add('nm-icon-button');
    });
    document.querySelectorAll('.status-badge, .doc-badge, .tag').forEach(node => {
      node.dataset.nmPrimitive = 'badge';
      node.classList.add('nm-badge');
      if (node.classList.contains('running')) node.dataset.status = 'running';
      else if (node.classList.contains('approval') || node.classList.contains('warn')) node.dataset.status = 'waiting';
      else if (node.classList.contains('failed') || node.classList.contains('danger')) node.dataset.status = 'failed';
      else if (node.classList.contains('completed') || node.classList.contains('success')) node.dataset.status = 'completed';
    });
    document.querySelectorAll('.field, .search-field, .select-field').forEach(node => {
      node.dataset.nmPrimitive = 'field';
      node.classList.add('nm-field');
    });
    document.querySelectorAll('.empty-state, .empty-cloud-state, .error-state, .loading-state').forEach(node => {
      node.dataset.nmPrimitive = 'state';
      node.classList.add('nm-state');
      if (node.classList.contains('error-state')) node.dataset.state = 'error';
    });
    document.querySelectorAll('.modal-backdrop, dialog, .mobile-sheet').forEach(node => {
      node.dataset.nmPrimitive = 'dialog';
    });
  };

  const bindPrimitiveActions = () => {
    document.querySelectorAll('[data-nm-toast]').forEach(node => {
      if (node.dataset.nmBound) return;
      node.dataset.nmBound = 'true';
      node.addEventListener('click', () => notify(node.dataset.nmToast || node.textContent.trim()));
    });
    document.querySelectorAll('[data-nm-busy-form]').forEach(form => {
      if (form.dataset.nmBound) return;
      form.dataset.nmBound = 'true';
      form.addEventListener('submit', () => {
        const button = form.querySelector('button[type="submit"]');
        if (!button) return;
        button.disabled = true;
        button.dataset.nmPreviousLabel = button.textContent;
        button.textContent = button.dataset.busyLabel || '处理中…';
      });
    });
  };

  root.dataset.nmDesignSystem = '1';
  window.NoteMeldDesignSystem = { version: '0.2.0', notify, markLegacyPrimitives, bindPrimitiveActions };
  markLegacyPrimitives();
  bindPrimitiveActions();
})();
