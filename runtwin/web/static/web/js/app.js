(() => {
  const header = document.querySelector('.site-header');
  const updateHeader = () => header?.classList.toggle('is-scrolled', window.scrollY > 8);
  updateHeader();
  window.addEventListener('scroll', updateHeader, { passive: true });

  document.querySelectorAll('details').forEach((details) => {
    details.addEventListener('toggle', () => details.classList.toggle('is-open', details.open));
  });
})();
