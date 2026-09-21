(() => {
  let currentVersion = '';

  const check = async () => {
    try {
      const response = await fetch(`/__new_product_version?t=${Date.now()}`, { cache: 'no-store' });
      if (!response.ok) return;
      const { version } = await response.json();
      if (currentVersion && version !== currentVersion) {
        window.location.reload();
        return;
      }
      currentVersion = version;
    } catch {
      // The preview server may be restarting; retry on the next interval.
    } finally {
      window.setTimeout(check, 800);
    }
  };

  check();
})();
