(() => {
  const source = document.getElementById('chart-data');
  if (!source) return;

  const containers = document.querySelectorAll('.chart');
  if (typeof window.echarts === 'undefined') {
    containers.forEach((node) => {
      node.innerHTML = '<p class="chart-error">圖表元件無法載入，請使用下方數據表查看內容。</p>';
    });
    return;
  }

  let data;
  try {
    data = JSON.parse(source.textContent);
    if (typeof data === 'string') data = JSON.parse(data);
  } catch (_) {
    containers.forEach((node) => {
      node.innerHTML = '<p class="chart-error">圖表資料格式錯誤，請使用下方數據表查看內容。</p>';
    });
    return;
  }

  const css = getComputedStyle(document.documentElement);
  const colors = {
    text: css.getPropertyValue('--text').trim(),
    muted: css.getPropertyValue('--muted').trim(),
    grid: css.getPropertyValue('--border').trim(),
    green: css.getPropertyValue('--green').trim(),
    blue: css.getPropertyValue('--blue').trim(),
    amber: css.getPropertyValue('--amber').trim(),
    purple: css.getPropertyValue('--purple').trim(),
  };
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const charts = [];
  const distanceNode = document.getElementById('distanceChart');
  if (distanceNode) {
    distanceNode.replaceChildren();
    const chart = window.echarts.init(distanceNode);
    chart.setOption({
      animation: !reducedMotion,
      tooltip: { trigger: 'axis', valueFormatter: (value) => `${value} km` },
      grid: { left: 44, right: 18, top: 24, bottom: 30 },
      xAxis: { type: 'category', boundaryGap: false, data: data.labels || [], axisLine: { lineStyle: { color: colors.grid } }, axisLabel: { color: colors.muted, formatter: (value) => value.slice(5) } },
      yAxis: { type: 'value', axisLabel: { color: colors.muted }, splitLine: { lineStyle: { color: colors.grid, opacity: .65 } } },
      series: [{
        name: '跑量', type: 'line', smooth: true, symbolSize: 8, data: data.distance || [],
        lineStyle: { width: 3, color: colors.green }, itemStyle: { color: colors.green, borderWidth: 3, borderColor: '#0d1726' },
        areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: 'rgba(61, 214, 140, .28)' }, { offset: 1, color: 'rgba(61, 214, 140, 0)' }] } },
      }],
    });
    charts.push(chart);
  }

  const classNode = document.getElementById('classChart');
  if (classNode) {
    classNode.replaceChildren();
    const chart = window.echarts.init(classNode);
    const labelMap = { easy: '輕鬆跑', recovery: '恢復跑', long: '長跑', tempo_threshold: '節奏／閾值', tempo: '節奏跑', threshold: '閾值跑', fartlek: '法特雷克', interval: '間歇', progression: '漸速跑', race: '比賽', unknown: '待判定' };
    chart.setOption({
      animation: !reducedMotion,
      tooltip: { trigger: 'item', formatter: '{b}<br>{c} 次 · {d}%' },
      color: [colors.green, colors.blue, colors.amber, colors.purple, '#f472b6', '#38bdf8', '#a3e635'],
      series: [{
        type: 'pie', radius: ['52%', '76%'], center: ['50%', '47%'], avoidLabelOverlap: true,
        itemStyle: { borderColor: '#101b2a', borderWidth: 3, borderRadius: 4 },
        label: { color: colors.muted, fontSize: 12, formatter: '{b}\n{c} 次' },
        data: (data.classes || []).map((name, index) => ({ name: labelMap[name] || name, value: (data.classValues || [])[index] })),
      }],
      graphic: [{ type: 'text', left: 'center', top: '42%', style: { text: `${(data.classValues || []).reduce((sum, value) => sum + value, 0)}\n次跑步`, textAlign: 'center', fill: colors.text, fontSize: 16, fontWeight: 700, lineHeight: 22 } }],
    });
    charts.push(chart);
  }

  let resizeFrame;
  window.addEventListener('resize', () => {
    cancelAnimationFrame(resizeFrame);
    resizeFrame = requestAnimationFrame(() => charts.forEach((chart) => chart.resize()));
  });
})();
