#!/usr/bin/env python3
"""
dashboard.py — MoneyBot PC Kitchen Dashboard
Live web UI showing regime, pipeline, candidates, positions, and log tail.

Usage:
  python dashboard.py

Opens http://localhost:8878 automatically in your browser.
Auto-refreshes every 30 seconds. Start/stop the bot from the browser.
"""

import os, sys, json, subprocess, threading, webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import date, datetime
from pathlib import Path

PORT    = 8878
BOT_DIR = Path(__file__).parent

bot_process = None
bot_lock    = threading.Lock()


# ── Bot helpers ───────────────────────────────────────────────────────────────

def bot_running():
    with bot_lock:
        return bot_process is not None and bot_process.poll() is None

def start_bot(dry_run=False):
    global bot_process
    log_path = BOT_DIR / "dashboard_run.log"
    with open(log_path, "a") as log:
        with bot_lock:
            cmd = [sys.executable, str(BOT_DIR / "auto_daily.py")]
            if dry_run:
                cmd.append("--dry-run")
            bot_process = subprocess.Popen(cmd, stdout=log, stderr=log, cwd=str(BOT_DIR))

def stop_bot():
    global bot_process
    with bot_lock:
        if bot_process and bot_process.poll() is None:
            bot_process.terminate()
            try:
                bot_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                bot_process.kill()
            bot_process = None


# ── Kitchen data ──────────────────────────────────────────────────────────────

def get_kitchen_data():
    data = {"generated": datetime.now().strftime("%H:%M:%S"), "bot_running": bot_running()}

    ops_path = BOT_DIR / f"ops_log_{date.today()}.json"
    if ops_path.exists():
        try:
            data["ops"] = json.loads(ops_path.read_text(encoding="utf-8"))
        except Exception as e:
            data["ops"] = None
            data["ops_error"] = str(e)
    else:
        data["ops"] = None
        data["ops_missing"] = f"No ops log yet for today ({ops_path.name}). Run the bot first."

    state_path = BOT_DIR / "execution_state.json"
    data["state"] = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}

    summary_path = BOT_DIR / "daily_summary.json"
    if summary_path.exists():
        try:
            data["recent_summaries"] = json.loads(summary_path.read_text(encoding="utf-8"))[-5:]
        except Exception:
            data["recent_summaries"] = []
    else:
        data["recent_summaries"] = []

    log_file = BOT_DIR / "auto_daily.log"
    if log_file.exists():
        try:
            lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
            data["log_tail"] = lines[-50:]
        except Exception:
            data["log_tail"] = []
    else:
        data["log_tail"] = []

    return data


# ── HTML ──────────────────────────────────────────────────────────────────────

HTML = r"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>MoneyBot Dashboard</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, 'Segoe UI', sans-serif; background: #0d0d0d; color: #e0e0e0; }
.topbar {
  background: #141414; border-bottom: 1px solid #222;
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 24px; position: sticky; top: 0; z-index: 10;
}
.topbar h1 { font-size: 16px; font-weight: 600; color: #fff; }
.topbar .meta { font-size: 12px; color: #555; margin-top: 2px; }
.controls { display: flex; gap: 8px; }
.btn {
  padding: 8px 16px; border: none; border-radius: 8px;
  font-size: 13px; font-weight: 600; cursor: pointer;
}
.btn-start   { background: #4a9eff; color: #fff; }
.btn-dry     { background: #1e1e1e; color: #aaa; border: 1px solid #333; }
.btn-stop    { background: #ff4a4a; color: #fff; }
.btn-refresh { background: #1e1e1e; color: #888; border: 1px solid #2a2a2a; }
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 16px; padding: 20px;
}
.panel {
  background: #1a1a1a; border: 1px solid #252525;
  border-radius: 12px; padding: 18px 20px;
}
.panel-title {
  font-size: 10px; color: #555; letter-spacing: 1.2px;
  text-transform: uppercase; margin-bottom: 14px;
  display: flex; justify-content: space-between; align-items: center;
}
.regime-badge {
  display: inline-block; padding: 4px 14px; border-radius: 20px;
  font-size: 13px; font-weight: 700; letter-spacing: 1px; margin-bottom: 12px;
}
.BEAR { background: #2a1010; color: #ff6b6b; border: 1px solid #4a1e1e; }
.BULL { background: #102a10; color: #4cff72; border: 1px solid #1e4a1e; }
.FLAT { background: #2a2a10; color: #ffd93d; border: 1px solid #4a4a1e; }
.UNKNOWN { background: #1e1e1e; color: #666; border: 1px solid #333; }
.krow {
  display: flex; justify-content: space-between; padding: 6px 0;
  border-bottom: 1px solid #1e1e1e; font-size: 13px;
}
.krow:last-child { border-bottom: none; }
.kl { color: #555; }
.kv { color: #ccc; font-variant-numeric: tabular-nums; }
.good { color: #4cff72 !important; }
.bad  { color: #ff6b6b !important; }
.warn { color: #ffd93d !important; }
.pipe {
  display: flex; justify-content: space-between;
  padding: 6px 0; border-bottom: 1px solid #1a1a1a; font-size: 12px;
}
.pipe:last-child { border-bottom: none; }
.pl { color: #666; }
table.cands { width: 100%; border-collapse: collapse; font-size: 11px; }
table.cands th {
  color: #444; font-weight: 500; text-align: right;
  padding: 4px 6px; border-bottom: 1px solid #222;
}
table.cands th:first-child, table.cands td:first-child { text-align: left; }
table.cands td {
  padding: 5px 6px; text-align: right; color: #999;
  border-bottom: 1px solid #1a1a1a;
}
table.cands td:first-child { color: #ddd; font-weight: 500; }
.log-box {
  background: #111; border-radius: 6px; padding: 10px;
  font-family: 'Cascadia Code', 'Consolas', monospace; font-size: 10px;
  color: #555; max-height: 260px; overflow-y: auto; line-height: 1.6;
}
.log-box .e { color: #ff6b6b; }
.log-box .w { color: #ffd93d; }
.log-box .g { color: #4cff72; }
.hist td { padding: 5px 8px; font-size: 12px; border-bottom: 1px solid #1a1a1a; color: #888; }
.hist td:first-child { color: #555; }
.dot {
  display: inline-block; width: 8px; height: 8px;
  border-radius: 50%; margin-right: 6px; vertical-align: middle;
}
.dot.live { background: #4cff72; box-shadow: 0 0 6px #4cff72; animation: p 1.5s infinite; }
.dot.off  { background: #333; }
@keyframes p { 0%,100%{opacity:1} 50%{opacity:.3} }
.empty { color: #444; font-size: 13px; padding: 4px 0; }
.loading { text-align: center; color: #333; padding: 60px; font-size: 14px; }
.full-width { grid-column: 1 / -1; }
</style>
</head>
<body>
<div class="topbar">
  <div>
    <h1>📈 MoneyBot
      <span id="botDot" style="font-size:12px;font-weight:400;margin-left:8px"></span>
    </h1>
    <div class="meta">v1.3.1 &nbsp;·&nbsp; RS60/EP40 &nbsp;·&nbsp; Policy-C &nbsp;·&nbsp; Top-10 &nbsp;·&nbsp; 10% SL &nbsp;·&nbsp; <span id="refreshLabel">—</span></div>
  </div>
  <div class="controls">
    <button class="btn btn-refresh" onclick="load()">↻ Refresh</button>
    <button class="btn btn-dry"    onclick="runBot(true)">Dry Run</button>
    <button class="btn btn-start"  id="btnStart" onclick="runBot(false)" style="display:none">▶ Start Bot</button>
    <button class="btn btn-stop"   id="btnStop"  onclick="stopBot()"    style="display:none">⏹ Stop Bot</button>
  </div>
</div>

<div id="main" class="loading">Opening kitchen…</div>

<script>
function fmt(n) {
  if (n == null || n === '') return '—';
  return Number(n).toLocaleString('en-IN', {maximumFractionDigits:2});
}
function row(l, v) {
  return '<div class="krow"><span class="kl">'+l+'</span><span class="kv">'+v+'</span></div>';
}
function pipe(l, v, cls) {
  return '<div class="pipe"><span class="pl">'+l+'</span><span class="'+cls+'">'+v+'</span></div>';
}

function load() {
  fetch('/kitchen')
    .then(r => r.json())
    .then(render)
    .catch(e => {
      document.getElementById('main').innerHTML =
        '<div style="color:#ff6b6b;padding:40px">Error loading data: '+e+'</div>';
    });
}

function runBot(dry) {
  fetch('/start' + (dry ? '?dry=1' : ''), {method:'POST'}).then(() => setTimeout(load, 1000));
}
function stopBot() {
  fetch('/stop', {method:'POST'}).then(() => setTimeout(load, 500));
}

function render(d) {
  const ops   = d.ops   || {};
  const state = d.state || {};
  const running = d.bot_running;

  document.getElementById('botDot').innerHTML =
    '<span class="dot '+(running?'live':'off')+'"></span>' +
    (running ? '<span class="good">Running</span>' : '<span style="color:#444">Idle</span>');
  document.getElementById('btnStart').style.display = running ? 'none' : '';
  document.getElementById('btnStop').style.display  = running ? ''     : 'none';
  document.getElementById('refreshLabel').textContent = 'Updated ' + d.generated;

  const regime   = ops.regime || 'UNKNOWN';
  const tradeable = ops.tradeable;
  const gap = (ops.nifty && ops.dma200) ? (ops.nifty - ops.dma200) : null;
  const candidates = ops.candidates || [];
  const buys = ops.buys || [];
  const rebalDue = ops.rebalance_due;
  const positions = state.positions || {};
  const posKeys = Object.keys(positions);
  const pnl = state.pnl || 0;

  let g = '';

  // ── REGIME ──────────────────────────────────────────────────────────────
  g += '<div class="panel">';
  g += '<div class="panel-title">📊 Regime<span>'+(ops.data_date||'')+'</span></div>';
  g += '<span class="regime-badge '+(regime||'UNKNOWN')+'">'+regime+'</span>';
  if (tradeable === false)
    g += ' <span class="bad" style="font-size:12px">Buying BLOCKED — 100% cash</span>';
  else if (tradeable === true)
    g += ' <span class="good" style="font-size:12px">Buying ALLOWED</span>';
  g += row('Nifty Close', ops.nifty  ? '₹'+fmt(ops.nifty)  : '—');
  g += row('50-DMA',      ops.dma50  ? '₹'+fmt(ops.dma50)  : '—');
  g += row('200-DMA',     ops.dma200 ? '₹'+fmt(ops.dma200) : '—');
  if (gap !== null) {
    const gc = gap >= 0 ? 'good' : 'bad';
    g += row('Gap to 200-DMA',
      '<span class="'+gc+'">'+(gap>=0?'+':'')+fmt(gap)+' pts ('+(gap>=0?'+':'')+
      (gap/ops.dma200*100).toFixed(1)+'%)</span>');
    if (gap < 0)
      g += row('Re-entry trigger', '₹'+fmt(ops.dma200)+' (Nifty must close above this)');
  }
  g += '</div>';

  // ── PIPELINE ────────────────────────────────────────────────────────────
  g += '<div class="panel">';
  g += '<div class="panel-title">🔍 Decision Pipeline</div>';
  g += pipe('Universe tracked',        '136 stocks',                           'kv');
  g += pipe('Candidates scored',       candidates.length > 0
              ? candidates.length+' stocks scored'
              : (regime==='BEAR' ? 'Skipped — BEAR regime' : 'No data yet'),   'kv');
  g += pipe('50-DMA stock filter',     candidates.length > 0 ? 'Applied ✓' : '—', 'kv');
  g += pipe('Regime gate (Policy-C)',  tradeable
              ? '✓ PASSED — '+regime
              : '✗ BLOCKED — '+regime+' regime (hold cash)',                    tradeable?'good':'bad');
  g += pipe('Rebalance gate (10d)',    rebalDue
              ? '✓ PASSED — rebalance due'
              : '✗ Not due today (monitoring only)',                             rebalDue?'good':'warn');
  g += pipe('BUY orders in plan',      buys.length > 0 ? buys.length : '0',    buys.length>0?'good':'warn');
  const zeroQ = buys.filter(b => b.qty===0).length;
  if (zeroQ > 0)
    g += pipe('Rejected (qty=0, price > ₹1,150)', zeroQ,                       'bad');
  const validB = buys.filter(b => (b.qty||0) > 0).length;
  g += pipe('Orders submitted to broker', validB > 0 ? validB : '0',           validB>0?'good':'kv');
  g += '</div>';

  // ── CANDIDATES ──────────────────────────────────────────────────────────
  g += '<div class="panel">';
  g += '<div class="panel-title">🏆 Top-10 Candidates (RS60/EP40 + 50-DMA filter)</div>';
  if (candidates.length === 0) {
    g += '<div class="empty">'+(regime==='BEAR'
      ? 'Not generated — BEAR regime. Bot holds cash until Nifty reclaims 200-DMA.'
      : 'No data yet. Run the bot to populate this.')+'</div>';
  } else {
    g += '<table class="cands"><thead><tr><th>#</th><th>Symbol</th><th>Price</th>' +
         '<th>RS%</th><th>EP%</th><th>Score</th></tr></thead><tbody>';
    candidates.forEach((c,i) => {
      g += '<tr><td style="color:#444">'+(i+1)+'</td><td>'+c.symbol+
           '</td><td>₹'+fmt(c.price)+'</td><td>'+
           (c.rs_pct||'—')+'</td><td>'+(c.ep_pct||'—')+
           '</td><td style="color:#4a9eff">'+(c.composite||'—')+'</td></tr>';
    });
    g += '</tbody></table>';
  }
  g += '</div>';

  // ── POSITIONS ───────────────────────────────────────────────────────────
  g += '<div class="panel">';
  g += '<div class="panel-title">💼 Positions <span>'+posKeys.length+' open</span></div>';
  if (posKeys.length === 0) {
    g += '<div class="empty">No open positions — 100% cash</div>';
  } else {
    posKeys.forEach(inst => {
      const p = positions[inst];
      g += row(p.plain || inst.split('|')[1] || inst,
        'Qty '+p.qty+' @ ₹'+fmt(p.entry)+' &nbsp;·&nbsp; SL ₹'+fmt(p.sl_price));
    });
  }
  const pnlClass = pnl >= 0 ? 'good' : 'bad';
  g += row('Cumulative P&L',
    '<span class="'+pnlClass+'">'+(pnl>=0?'+':'')+' ₹'+fmt(Math.abs(pnl))+'</span>');
  g += row('Completed trades', (state.trades||[]).length);
  g += row('Last ops date', state.last_ops_date || '—');
  g += '</div>';

  // ── HISTORY ─────────────────────────────────────────────────────────────
  const summaries = d.recent_summaries || [];
  g += '<div class="panel">';
  g += '<div class="panel-title">📅 Recent Daily Summaries</div>';
  if (summaries.length === 0) {
    g += '<div class="empty">No daily summaries yet.</div>';
  } else {
    g += '<table class="hist" style="width:100%"><thead><tr>' +
         '<td>Date</td><td>Status</td><td>Regime</td><td>Errors</td><td>Runtime</td>' +
         '</tr></thead><tbody>';
    [...summaries].reverse().forEach(s => {
      const sc = s.status==='PASS' ? 'good' : s.status==='WEEKEND' ? '' : 'bad';
      g += '<tr><td>'+s.date+'</td><td class="'+sc+'">'+s.status+'</td>' +
           '<td>'+(s.regime||'—')+'</td><td>'+(s.errors||0)+'</td>' +
           '<td>'+(s.runtime_seconds ? s.runtime_seconds+'s' : '—')+'</td></tr>';
    });
    g += '</tbody></table>';
  }
  g += '</div>';

  // ── LOG TAIL ─────────────────────────────────────────────────────────────
  const logLines = d.log_tail || [];
  g += '<div class="panel full-width">';
  g += '<div class="panel-title">📋 Log Tail <span>last 50 lines of auto_daily.log</span></div>';
  if (logLines.length === 0) {
    g += '<div class="empty">No log file yet. The bot hasn\'t run today.</div>';
  } else {
    g += '<div class="log-box">';
    logLines.forEach(line => {
      let cls = '';
      if (/ERROR|FAILED|CRITICAL|crash/i.test(line)) cls = 'e';
      else if (/WARNING|WARN/i.test(line)) cls = 'w';
      else if (/PASS|Done\.|BOUGHT|SOLD|filled|Lock acquired/i.test(line)) cls = 'g';
      const safe = line.replace(/</g,'&lt;').replace(/>/g,'&gt;');
      g += '<div class="'+cls+'">'+safe+'</div>';
    });
    g += '</div>';
  }
  g += '</div>';

  if (d.ops_missing) {
    g += '<div class="panel full-width" style="border-color:#333">' +
         '<div class="empty">⏳ '+d.ops_missing+'</div></div>';
  }

  document.getElementById('main').innerHTML = '<div class="grid">'+g+'</div>';
}

load();
setInterval(load, 30000);
</script>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass

    def do_GET(self):
        if self.path == "/kitchen":
            data = get_kitchen_data()
            self._json(json.dumps(data, default=str).encode())
        else:
            self._html(HTML.encode())

    def do_POST(self):
        if self.path.startswith("/start"):
            dry = "dry=1" in self.path
            threading.Thread(target=start_bot, args=(dry,), daemon=True).start()
            self._json(b'{"ok":true}')
        elif self.path == "/stop":
            stop_bot()
            self._json(b'{"ok":true}')
        else:
            self._json(b'{"ok":false}')

    def _html(self, body):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, body):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    server = HTTPServer(("127.0.0.1", PORT), Handler)
    url = f"http://localhost:{PORT}"
    print(f"MoneyBot Dashboard → {url}")
    print("Auto-refreshes every 30 seconds. Press Ctrl+C to stop.")
    webbrowser.open(url)
    server.serve_forever()
