let chart = null;

async function fetchJSON(url) {
  const res = await fetch(url);
  return res.json();
}

function formatChange(pct) {
  const sign = pct >= 0 ? '+' : '';
  const cls = pct >= 0 ? 'change-positive' : 'change-negative';
  return `<span class="${cls}">${sign}${pct.toFixed(1)}%</span>`;
}

function formatTime(ts) {
  if (!ts) return '';
  return new Date(ts * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function platformBadge(platform) {
  return `<span class="platform-badge platform-${platform}">${platform}</span>`;
}

async function loadStats() {
  const stats = await fetchJSON('/api/stats');
  document.getElementById('stat-markets').textContent = stats.total_markets;
  document.getElementById('stat-snapshots').textContent = stats.total_snapshots;
  document.getElementById('stat-signals').textContent = stats.total_signals;
  const mins = Math.floor(stats.uptime_seconds / 60);
  const secs = stats.uptime_seconds % 60;
  document.getElementById('stat-uptime').textContent = mins > 0 ? `${mins}m ${secs}s` : `${secs}s`;
}

async function loadSignals() {
  const signals = await fetchJSON('/api/signals?limit=20');
  const container = document.getElementById('signals-list');

  if (signals.length === 0) {
    container.innerHTML = '<div class="empty-state">No signals yet. Waiting for price movements > 5% to correlate with news...</div>';
    return;
  }

  container.innerHTML = signals.map(s => `
    <div class="signal-card">
      <div class="market">${s.market_title || s.market_id}</div>
      <div class="news">${s.news_title ? `<a href="${s.news_url}" target="_blank" style="color:#888;text-decoration:none;">${s.news_title}</a>` : 'No news matched'}</div>
      <div class="meta">
        ${formatChange(s.price_change)}
        <span>Score: ${(s.correlation_score || 0).toFixed(2)}</span>
        <span>${formatTime(s.timestamp)}</span>
      </div>
    </div>
  `).join('');
}

async function loadMarkets() {
  const markets = await fetchJSON('/api/markets');
  const tbody = document.getElementById('markets-body');

  if (markets.length === 0) {
    tbody.innerHTML = '<tr><td colspan="4" class="empty-state">No markets yet. Poller starting...</td></tr>';
    return;
  }

  // Sort by absolute 1h change descending
  markets.sort((a, b) => Math.abs(b.price_change_1h) - Math.abs(a.price_change_1h));

  tbody.innerHTML = markets.slice(0, 50).map(m => `
    <tr data-id="${m.id}" style="cursor:pointer" onclick="loadChart('${m.id}','${m.title.replace(/'/g, "\\'")}')">
      <td>${platformBadge(m.platform)}</td>
      <td>${m.title.substring(0, 60)}</td>
      <td>${m.last_price ? '$' + m.last_price.toFixed(2) : '-'}</td>
      <td>${m.price_change_1h ? formatChange(m.price_change_1h) : '-'}</td>
    </tr>
  `).join('');
}

async function loadChart(marketId, title) {
  document.getElementById('chart-hint').textContent = title;
  const data = await fetchJSON(`/api/markets/${encodeURIComponent(marketId)}/history?hours=24`);

  const prices = data.prices || [];
  const events = data.events || [];

  if (chart) chart.destroy();

  const ctx = document.getElementById('price-chart').getContext('2d');

  const labels = prices.map(p => new Date(p.timestamp * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }));
  const values = prices.map(p => p.price);

  // Create event annotations
  const annotations = {};
  events.forEach((e, i) => {
    annotations[`event${i}`] = {
      type: 'line',
      xMin: new Date(e.timestamp * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      xMax: new Date(e.timestamp * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      borderColor: '#F93C31',
      borderWidth: 1,
      borderDash: [4, 4],
    };
  });

  chart = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label: 'Price',
        data: values,
        borderColor: '#1E93FF',
        backgroundColor: 'rgba(30, 147, 255, 0.1)',
        fill: true,
        tension: 0.2,
        pointRadius: 1,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: { ticks: { color: '#555', maxTicksLimit: 10 }, grid: { color: '#1e1e28' } },
        y: { ticks: { color: '#555' }, grid: { color: '#1e1e28' } },
      },
      plugins: {
        legend: { display: false },
      },
    },
  });
}

async function refresh() {
  try {
    await Promise.all([loadStats(), loadSignals(), loadMarkets()]);
  } catch (e) {
    console.error('Refresh error:', e);
  }
}

// Initial load + auto-refresh
refresh();
setInterval(refresh, 30000);
