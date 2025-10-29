from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

from cryptobot.monitor.state import state


app = FastAPI(title="CryptoBot Monitor")


@app.get("/api/state")
async def get_state():
    return JSONResponse(state.snapshot())


@app.get("/")
async def index():
    html = """
    <!doctype html>
    <html>
    <head>
      <meta charset=\"utf-8\" />
      <title>CryptoBot Monitor</title>
      <style>
        body { font-family: sans-serif; margin: 20px; }
        #chart { width: 100%; height: 300px; }
        table { border-collapse: collapse; width: 100%; }
        th, td { border: 1px solid #ddd; padding: 8px; }
        th { background: #f0f0f0; }
      </style>
    </head>
    <body>
      <h1>CryptoBot Monitor</h1>
      <div>
        <strong>LLM multiplier:</strong> <span id=\"mult\">-</span>
      </div>
      <h2>Equity</h2>
      <canvas id=\"chart\"></canvas>
      <h2>Positions</h2>
      <table id=\"pos\">
        <thead><tr><th>Symbol</th><th>Qty</th><th>Avg Price</th></tr></thead>
        <tbody></tbody>
      </table>
      <h2>Events (latest 50)</h2>
      <ul id=\"events\"></ul>
      <script>
        async function fetchState() {
          const res = await fetch('/api/state');
          return await res.json();
        }
        const ctx = document.getElementById('chart').getContext('2d');
        let chart;
        async function render() {
          const s = await fetchState();
          document.getElementById('mult').textContent = s.last_llm_multiplier ?? '-';
          // positions
          const tbody = document.querySelector('#pos tbody');
          tbody.innerHTML = '';
          Object.values(s.positions).forEach(p => {
            const tr = document.createElement('tr');
            tr.innerHTML = `<td>${p.symbol}</td><td>${p.qty.toFixed(6)}</td><td>${p.avg_price.toFixed(2)}</td>`;
            tbody.appendChild(tr);
          });
          // events
          const ev = document.getElementById('events');
          ev.innerHTML = '';
          (s.events || []).slice(-50).reverse().forEach(e => {
            const li = document.createElement('li');
            li.textContent = JSON.stringify(e);
            ev.appendChild(li);
          });
          // chart
          const labels = s.equity_curve.map(x => new Date(x.timestamp).toLocaleTimeString());
          const data = s.equity_curve.map(x => x.equity);
          if (!chart) {
            chart = new Chart(ctx, {
              type: 'line',
              data: { labels, datasets: [{ label: 'Equity', data, borderColor: 'blue', fill: false }] },
              options: { responsive: true, scales: { y: { beginAtZero: false } } }
            });
          } else {
            chart.data.labels = labels;
            chart.data.datasets[0].data = data;
            chart.update();
          }
        }
        setInterval(render, 3000);
      </script>
      <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    </body>
    </html>
    """
    return HTMLResponse(html)
