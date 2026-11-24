(() => {
  const timeline = document.getElementById('history-timeline');
  const count = document.getElementById('history-count');
  const range = document.getElementById('history-range');
  const empty = document.getElementById('history-empty');
  if (!timeline || !count || !range || !empty) return;

  const today = new Date();
  today.setHours(23, 59, 59, 999);
  const cutoff = new Date(today);
  cutoff.setMonth(cutoff.getMonth() - 3);
  cutoff.setHours(0, 0, 0, 0);

  const formatter = new Intl.DateTimeFormat('zh-TW', { year: 'numeric', month: '2-digit', day: '2-digit' });
  range.textContent = `${formatter.format(cutoff)} — ${formatter.format(today)}`;

  let visible = 0;
  timeline.querySelectorAll('[data-week-start]').forEach((card) => {
    const start = new Date(`${card.dataset.weekStart}T00:00:00`);
    const inRange = !Number.isNaN(start.getTime()) && start >= cutoff && start <= today;
    card.hidden = !inRange;
    if (inRange) visible += 1;
  });

  count.textContent = `${visible} 份報告`;
  empty.hidden = visible !== 0;
  timeline.hidden = visible === 0;
})();
