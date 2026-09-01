"""Local Web Dashboard, AI Pair Programmer, and Time-Travel Visualizer for SBpy."""

from __future__ import annotations

import http.server
import json
import os
import socketserver
import threading
import urllib.parse
import webbrowser
from typing import Any

from .config import get_config
from .console import get_console
from .git_ops import snapshot
from .shortcuts import SHORTCUTS

DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>SBpy Live Dashboard</title>
  <link rel="icon" type="image/jpeg" href="/assets/icon.jpg">
  <style>
    :root {
      --bg: #0d1117;
      --card: #161b22;
      --border: #30363d;
      --text: #c9d1d9;
      --heading: #f0f6fc;
      --accent: #58a6ff;
      --green: #3fb950;
      --yellow: #d29922;
      --red: #f85149;
      --purple: #bc8cff;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
    body { background-color: var(--bg); color: var(--text); padding: 24px; line-height: 1.5; }
    header { display: flex; justify-content: space-between; align-items: center; padding-bottom: 20px; border-bottom: 1px solid var(--border); margin-bottom: 20px; }
    .logo { font-size: 24px; font-weight: bold; color: var(--accent); display: flex; align-items: center; gap: 10px; }
    .badge { background: #1f6feb22; color: var(--accent); border: 1px solid var(--accent); padding: 2px 8px; border-radius: 12px; font-size: 12px; }
    
    .nav-tabs { display: flex; gap: 8px; margin-bottom: 20px; border-bottom: 1px solid var(--border); padding-bottom: 10px; }
    .tab-btn { background: transparent; color: var(--text); border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer; font-weight: 600; }
    .tab-btn.active { background: #21262d; color: var(--accent); border: 1px solid var(--border); }
    
    .tab-content { display: none; }
    .tab-content.active { display: block; }

    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 16px; margin-bottom: 24px; }
    .card { background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 20px; margin-bottom: 20px; }
    .card-title { font-size: 14px; text-transform: uppercase; letter-spacing: 0.5px; color: #8b949e; margin-bottom: 12px; }
    .metric { font-size: 30px; font-weight: bold; color: var(--heading); margin-bottom: 4px; }
    .submetric { font-size: 13px; color: #8b949e; }
    .status-ok { color: var(--green); }
    .status-warn { color: var(--yellow); }
    .status-err { color: var(--red); }
    
    button { background: #238636; color: white; border: none; padding: 8px 16px; border-radius: 6px; font-weight: 600; cursor: pointer; transition: 0.2s; }
    button:hover { background: #2ea043; }
    .btn-secondary { background: #21262d; color: var(--text); border: 1px solid var(--border); }
    .btn-secondary:hover { background: #30363d; }
    .btn-pro { background: #8957e5; color: white; }
    .btn-pro:hover { background: #a371f7; }
    
    .code-box { background: #000; padding: 12px; border-radius: 6px; font-family: monospace; font-size: 13px; color: #79c0ff; overflow-x: auto; margin-top: 10px; position: relative; }
    .apply-btn { position: absolute; top: 8px; right: 8px; background: #238636; font-size: 11px; padding: 4px 10px; border-radius: 4px; }
    
    /* Chat UI */
    .chat-box { height: 380px; overflow-y: auto; background: #010409; border: 1px solid var(--border); border-radius: 6px; padding: 16px; margin-bottom: 12px; display: flex; flex-direction: column; gap: 12px; }
    .chat-msg { padding: 10px 14px; border-radius: 8px; max-width: 85%; font-size: 14px; }
    .msg-user { background: #1f6feb33; border: 1px solid var(--accent); align-self: flex-end; color: #f0f6fc; }
    .msg-ai { background: #21262d; border: 1px solid var(--border); align-self: flex-start; color: var(--text); }
    .chat-input-row { display: flex; gap: 8px; }
    .chat-input { flex: 1; background: #000; border: 1px solid var(--border); color: #f0f6fc; padding: 10px 14px; border-radius: 6px; font-size: 14px; }
    
    /* Timeline Visualizer */
    .timeline-step { padding: 10px; border-left: 3px solid var(--accent); background: #010409; margin-bottom: 8px; border-radius: 0 6px 6px 0; }
    .timeline-step.crash { border-left-color: var(--red); }
  </style>
</head>
<body>
  <header>
    <div class="logo">
      <img src="/assets/icon.jpg" alt="SBpy Logo" style="width: 32px; height: 32px; border-radius: 6px; object-fit: cover; vertical-align: middle;" onerror="this.style.display='none'">
      <span>SBpy Live Platform</span>
      <span class="badge" id="version">v0.1.0</span>
      <span class="badge" style="background:#23863622; color:var(--green); border-color:var(--green);" id="backend-badge">Gemini</span>
    </div>
    <div>
      <button class="btn-secondary" onclick="refreshData()">🔄 Refresh</button>
      <button onclick="runShortcut('FIX')">⚡ Auto-Fix All</button>
    </div>
  </header>

  <div class="nav-tabs">
    <button class="tab-btn active" onclick="switchTab('tab-overview')">📊 Overview</button>
    <button class="tab-btn" onclick="switchTab('tab-chat')">🤖 AI Pair Programmer (Chat & 1-Click Patch)</button>
    <button class="tab-btn" onclick="switchTab('tab-search')">🔍 Semantic Search</button>
    <button class="tab-btn" onclick="switchTab('tab-trace')">⏳ Time-Travel Crash Replayer</button>
    <button class="tab-btn" onclick="switchTab('tab-graph')">🌐 Architecture Topology</button>
  </div>

  <!-- TAB 1: OVERVIEW -->
  <div id="tab-overview" class="tab-content active">
    <div class="grid">
      <div class="card">
        <div class="card-title">Project Health Score</div>
        <div class="metric" id="health-score">100%</div>
        <div class="submetric status-ok" id="health-text">✓ Ready for Production</div>
      </div>
      <div class="card">
        <div class="card-title">Active AI Provider & Model</div>
        <div class="metric" id="provider-name">Gemini</div>
        <div class="submetric" id="model-name">gemini-3.6-flash</div>
      </div>
      <div class="card">
        <div class="card-title">Token Usage & Budget</div>
        <div class="metric" id="tokens-count">0</div>
        <div class="submetric" id="cost-estimate">Cost: ~$0.0000 · 0 Calls</div>
      </div>
      <div class="card">
        <div class="card-title">Project Index</div>
        <div class="metric" id="files-count">0 Files</div>
        <div class="submetric" id="symbols-count">0 Indexed Symbols</div>
      </div>
    </div>

    <div class="card">
      <div class="card-title">Quick Actions</div>
      <div style="display: flex; gap: 10px; flex-wrap: wrap;" id="shortcuts-bar">
        <button class="btn-secondary" onclick="runShortcut('SFB')">🔍 /SFB (Bug Scan)</button>
        <button class="btn-secondary" onclick="runShortcut('SEC')">🛡️ /SEC (Security)</button>
        <button class="btn-secondary" onclick="runShortcut('OPT')">⚡ /OPT (Optimize)</button>
        <button class="btn-secondary" onclick="runShortcut('CLEAN')">🧹 /CLEAN (Cleanup)</button>
        <button class="btn-secondary" onclick="runShortcut('REVIEW')">📝 /REVIEW (Full Review)</button>
        <button class="btn-secondary" onclick="runShortcut('TST')">🧪 /TST (Generate Tests)</button>
      </div>
      <div id="action-output" class="code-box" style="display:none;"></div>
    </div>
  </div>

  <!-- TAB 2: AI CHAT & 1-CLICK PATCH -->
  <div id="tab-chat" class="tab-content">
    <div class="card">
      <div class="card-title">🤖 Interactive AI Code Assistant (RAG-Aware with 1-Click Patching)</div>
      <div class="chat-box" id="chat-history">
        <div class="chat-msg msg-ai">Hello! I am your SBpy AI developer assistant. I have full context on your codebase and symbols. How can I help you write, refactor, or fix code today?</div>
      </div>
      <div class="chat-input-row">
        <input type="text" id="chat-input" class="chat-input" placeholder="Ask a question or request a code change (e.g. 'Add input validation to user function in app.py')..." onkeydown="if(event.key==='Enter') sendChatMessage()">
        <button onclick="sendChatMessage()">Send 🚀</button>
      </div>
    </div>
  </div>

  <!-- TAB 3: SEMANTIC SEARCH -->
  <div id="tab-search" class="tab-content">
    <div class="card">
      <div class="card-title">🔍 Semantic Code Search</div>
      <div style="font-size:13px; color:#8b949e; margin-bottom: 10px;">Search functions, classes, and logic by meaning rather than exact keywords:</div>
      <div class="chat-input-row" style="margin-bottom: 16px;">
        <input type="text" id="search-query-input" class="chat-input" placeholder="e.g. 'Where do we handle token budgets and usage limits?'" onkeydown="if(event.key==='Enter') runSemanticSearch()">
        <button onclick="runSemanticSearch()">Search 🔍</button>
      </div>
      <div id="search-results-box"></div>
    </div>
  </div>

  <!-- TAB 4: TIME-TRAVEL CRASH REPLAYER -->
  <div id="tab-trace" class="tab-content">
    <div class="card">
      <div class="card-title">⏳ Time-Travel Crash Replayer & State Inspector</div>
      <div style="font-size:13px; color:#8b949e; margin-bottom: 12px;">Step-by-step timeline of variables and execution steps captured during script crashes:</div>
      <div id="trace-timeline-box" style="display: flex; flex-direction: column; gap: 8px;">
        <div style="color:#8b949e; text-align:center; padding: 20px;">No recent crash snapshot detected. Run <code>sbpy trace &lt;script.py&gt;</code> to capture live execution frames.</div>
      </div>
    </div>
  </div>

  <!-- TAB 5: ARCHITECTURE TOPOLOGY -->
  <div id="tab-graph" class="tab-content">
    <div class="card">
      <div class="card-title">🌐 Interactive Project Architecture & Dependency Map</div>
      <div style="font-size:13px; color:#8b949e; margin-bottom: 12px;">Visual module imports and dependencies. Click on any node to inspect & diagnose:</div>
      <div id="graph-container" style="width: 100%; height: 350px; background: #010409; border: 1px solid var(--border); border-radius: 6px; overflow: hidden; position: relative;">
        <svg id="dep-svg" width="100%" height="100%"></svg>
      </div>
    </div>
  </div>

  <script>
    function switchTab(tabId) {
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
      event.target.classList.add('active');
      document.getElementById(tabId).classList.add('active');
    }

    async function refreshData() {
      try {
        const res = await fetch('/api/status');
        const data = await res.json();
        document.getElementById('version').textContent = 'v' + data.version;
        document.getElementById('provider-name').textContent = data.backend.toUpperCase();
        document.getElementById('backend-badge').textContent = data.backend;
        document.getElementById('model-name').textContent = data.models.command;
        document.getElementById('tokens-count').textContent = (data.budget.tokens_total || 0).toLocaleString();
        document.getElementById('cost-estimate').textContent = `Cost: ~$${(data.budget.cost_usd || 0).toFixed(4)} · ${data.budget.calls_today || 0} Calls`;
        document.getElementById('files-count').textContent = (data.index.files || 0) + ' Files';
        document.getElementById('symbols-count').textContent = (data.index.symbols || 0) + ' Symbols';
        loadGraph();
        loadTrace();
      } catch (e) {
        console.error(e);
      }
    }

    async function loadGraph() {
      try {
        const res = await fetch('/api/graph');
        const data = await res.json();
        const svg = document.getElementById('dep-svg');
        svg.innerHTML = '';
        const nodes = data.nodes || [];
        const edges = data.edges || [];
        const width = svg.clientWidth || 800;
        const height = 350;
        const count = nodes.length || 1;
        const radius = Math.min(width, height) / 2 - 40;
        const cx = width / 2;
        const cy = height / 2;

        const nodePos = {};
        nodes.forEach((n, i) => {
          const angle = (i / count) * 2 * Math.PI;
          const x = cx + radius * Math.cos(angle);
          const y = cy + radius * Math.sin(angle);
          nodePos[n.id] = {x, y, name: n.name};
        });

        edges.forEach(e => {
          const p1 = nodePos[e.source];
          const p2 = nodePos[e.target];
          if (p1 && p2) {
            const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
            line.setAttribute('x1', p1.x);
            line.setAttribute('y1', p1.y);
            line.setAttribute('x2', p2.x);
            line.setAttribute('y2', p2.y);
            line.setAttribute('stroke', '#30363d');
            line.setAttribute('stroke-width', '1.5');
            svg.appendChild(line);
          }
        });

        nodes.forEach((n) => {
          const p = nodePos[n.id];
          if (!p) return;
          const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
          g.style.cursor = 'pointer';
          g.onclick = () => {
            switchTab('tab-overview');
            const box = document.getElementById('action-output');
            box.style.display = 'block';
            box.textContent = `Running /SFB on ${n.id}...`;
            fetch('/api/run', {
              method: 'POST',
              headers: {'Content-Type': 'application/json'},
              body: JSON.stringify({code: 'SFB', target: n.id})
            }).then(r => r.json()).then(d => {
              box.textContent = JSON.stringify(d, null, 2);
            });
          };

          const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
          circle.setAttribute('cx', p.x);
          circle.setAttribute('cy', p.y);
          circle.setAttribute('r', '12');
          circle.setAttribute('fill', n.status === 'error' ? '#f85149' : '#238636');
          circle.setAttribute('stroke', '#ffffff');
          circle.setAttribute('stroke-width', '1.5');

          const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
          text.setAttribute('x', p.x);
          text.setAttribute('y', p.y + 20);
          text.setAttribute('text-anchor', 'middle');
          text.setAttribute('fill', '#c9d1d9');
          text.setAttribute('font-size', '10px');
          text.textContent = p.name.length > 14 ? p.name.slice(0, 12) + '..' : p.name;

          g.appendChild(circle);
          g.appendChild(text);
          svg.appendChild(g);
        });
      } catch (e) {
        console.error(e);
      }
    }

    async function sendChatMessage() {
      const input = document.getElementById('chat-input');
      const text = input.value.trim();
      if (!text) return;

      const historyBox = document.getElementById('chat-history');
      const userMsg = document.createElement('div');
      userMsg.className = 'chat-msg msg-user';
      userMsg.textContent = text;
      historyBox.appendChild(userMsg);
      input.value = '';

      const aiMsg = document.createElement('div');
      aiMsg.className = 'chat-msg msg-ai';
      aiMsg.textContent = 'Thinking...';
      historyBox.appendChild(aiMsg);
      historyBox.scrollTop = historyBox.scrollHeight;

      try {
        const res = await fetch('/api/chat', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({message: text})
        });
        const data = await res.json();
        aiMsg.innerHTML = formatAiResponse(data.reply || 'No response from AI.');
      } catch (e) {
        aiMsg.textContent = 'Error: ' + e;
      }
      historyBox.scrollTop = historyBox.scrollHeight;
    }

    function formatAiResponse(text) {
      // Look for code blocks and add 1-click patch buttons
      const regex = /```(?:python)?\s*\n([\s\S]*?)\n```/g;
      return text.replace(regex, function(match, code) {
        const escaped = encodeURIComponent(code);
        return `<div class="code-box"><button class="apply-btn" onclick="applyCodePatch(decodeURIComponent('${escaped}'))">⚡ 1-Click Apply to File</button><pre>${code}</pre></div>`;
      }).replace(/\\n/g, '<br>');
    }

    async function applyCodePatch(code) {
      const targetFile = prompt('Enter the relative target file path to apply this code:', 'app.py');
      if (!targetFile) return;

      try {
        const res = await fetch('/api/patch', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({file: targetFile, code: code})
        });
        const data = await res.json();
        if (data.ok) {
          alert('✓ Successfully applied patch to ' + targetFile + ' with automatic undo backup!');
        } else {
          alert('Error: ' + (data.error || 'Failed to patch file'));
        }
      } catch (e) {
        alert('Patch failed: ' + e);
      }
    }

    async function runSemanticSearch() {
      const input = document.getElementById('search-query-input');
      const q = input.value.trim();
      if (!q) return;

      const box = document.getElementById('search-results-box');
      box.innerHTML = '<div style="color:#8b949e;">Searching AST & semantic meaning...</div>';

      try {
        const res = await fetch('/api/search', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({query: q})
        });
        const results = await res.json();
        if (!results || results.length === 0) {
          box.innerHTML = '<div style="color:#d29922;">No matching symbols found.</div>';
          return;
        }

        let html = '';
        results.forEach((r, idx) => {
          html += `
            <div style="background:#010409; border:1px solid var(--border); border-radius:6px; padding:12px; margin-bottom:10px;">
              <div style="display:flex; justify-content:space-between; align-items:center;">
                <span style="color:#58a6ff; font-weight:bold; font-size:15px;">[${idx+1}] ${r.symbol} <span style="font-size:12px; color:#8b949e;">(${r.kind})</span></span>
                <span class="badge" style="color:var(--green); border-color:var(--green);">${Math.round(r.score*100)}% Match</span>
              </div>
              <div style="font-size:12px; color:#8b949e; margin-top:2px;">${r.file}:${r.line}</div>
              ${r.reason ? `<div style="font-size:13px; color:#f0f6fc; margin: 6px 0;">💡 ${r.reason}</div>` : ''}
              <div class="code-box" style="margin-top:6px; font-size:12px;">${r.snippet}</div>
            </div>
          `;
        });
        box.innerHTML = html;
      } catch (e) {
        box.innerHTML = '<div style="color:#f85149;">Error: ' + e + '</div>';
      }
    }

    async function loadTrace() {
      try {
        const res = await fetch('/api/trace');
        const data = await res.json();
        const box = document.getElementById('trace-timeline-box');
        if (!data || !data.timeline || data.timeline.length === 0) return;

        let html = `<div style="color:var(--red); font-weight:bold; margin-bottom:12px;">💥 Exception: ${data.exc_type}: ${data.exc_value}</div>`;
        data.timeline.forEach((f, idx) => {
          const isLast = idx === data.timeline.length - 1;
          const localsStr = Object.entries(f.locals || {}).map(([k, v]) => `<code>${k} = ${v}</code>`).join(' · ') || 'None';
          html += `
            <div class="timeline-step ${isLast ? 'crash' : ''}">
              <div style="display:flex; justify-content:space-between; font-size:13px;">
                <span style="color:${isLast ? 'var(--red)' : 'var(--accent)'}; font-weight:bold;">Step ${idx+1}: ${f.func_name}() in ${f.file}:${f.line}</span>
              </div>
              <div style="font-family:monospace; color:#79c0ff; font-size:13px; margin:4px 0;">${f.code}</div>
              <div style="font-size:12px; color:#8b949e;">Variables: ${localsStr}</div>
            </div>
          `;
        });
        box.innerHTML = html;
      } catch (e) {
        console.error(e);
      }
    }

    async function runShortcut(code) {
      const box = document.getElementById('action-output');
      box.style.display = 'block';
      box.textContent = `Running /${code}...`;
      try {
        const res = await fetch('/api/run', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({code: code, target: '.'})
        });
        const data = await res.json();
        box.textContent = JSON.stringify(data, null, 2);
      } catch (e) {
        box.textContent = 'Error: ' + e;
      }
    }

    refreshData();
  </script>
</body>
</html>
"""


class DashboardHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        pass  # Quiet logging

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/" or parsed.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(DASHBOARD_HTML.encode("utf-8"))
            return

        if parsed.path.startswith("/assets/"):
            rel_path = parsed.path.lstrip("/")
            if os.path.exists(rel_path):
                self.send_response(200)
                if rel_path.endswith((".jpg", ".jpeg")):
                    self.send_header("Content-Type", "image/jpeg")
                elif rel_path.endswith(".png"):
                    self.send_header("Content-Type", "image/png")
                self.end_headers()
                with open(rel_path, "rb") as f:
                    self.wfile.write(f.read())
                return
            self.send_response(404)
            self.end_headers()
            return

        if parsed.path == "/api/status":
            from . import budget, index

            config = get_config()
            stats = {
                "version": "0.1.0",
                "backend": config.backend,
                "offline": config.offline,
                "custom_instructions": config.custom_instructions,
                "models": {
                    "auto": config.model_auto,
                    "command": config.model_command,
                    "pro": config.model_pro,
                },
                "budget": budget.summary(config),
                "index": index.describe(config),
            }
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(stats).encode("utf-8"))
            return

        if parsed.path == "/api/shortcuts":
            config = get_config()
            rows = []
            for code, sc in sorted(SHORTCUTS.items()):
                rows.append({
                    "code": code,
                    "title": sc.title_en,
                    "escalate": sc.escalate,
                    "tier": sc.tier,
                })
            for name, target in sorted(config.custom_shortcuts.items()):
                rows.append({
                    "code": name,
                    "title": f"Custom alias -> {target}",
                    "escalate": "custom",
                    "tier": "custom",
                })
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(rows).encode("utf-8"))
            return

        if parsed.path == "/api/graph":
            from .graph import build_file_dependency_graph

            graph_data = build_file_dependency_graph(".")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(graph_data).encode("utf-8"))
            return

        if parsed.path == "/api/trace":
            from .trace import get_latest_crash_snapshot

            snap = get_latest_crash_snapshot()
            data = snap.to_dict() if snap else {}
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(data).encode("utf-8"))
            return

        self.send_response(404)
        self.end_headers()

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")
        data = json.loads(body) if body else {}

        if parsed.path == "/api/run":
            code = data.get("code", "SFB").upper()
            target = data.get("target", ".")
            from .shortcuts import run as run_sc

            res = run_sc(code, target if os.path.exists(target) else None)
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(res.to_dict()).encode("utf-8"))
            return

        if parsed.path == "/api/chat":
            message = data.get("message", "")
            from .gemini import get_engine
            from .config import TIER_COMMAND

            config = get_config()
            if config.offline:
                reply = "Offline mode is active. Please configure an API key to enable live AI chat."
            else:
                prompt = f"""You are SBpy AI Pair Programmer.
Answer the user request with high accuracy, explaining concisely and providing complete runnable Python code blocks where helpful.
USER MESSAGE:
{message}
"""
                engine = get_engine(config)
                resp = engine.generate(prompt, tier=TIER_COMMAND)
                reply = resp.text if resp.ok else f"AI Error: {resp.error}"

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"reply": reply}).encode("utf-8"))
            return

        if parsed.path == "/api/patch":
            file_path = data.get("file", "")
            code_content = data.get("code", "")
            if not file_path:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(json.dumps({"ok": False, "error": "Missing file path"}).encode("utf-8"))
                return

            try:
                if os.path.exists(file_path):
                    snapshot([file_path])
                dir_name = os.path.dirname(os.path.abspath(file_path))
                if dir_name:
                    os.makedirs(dir_name, exist_ok=True)
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(code_content)
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": True, "file": file_path}).encode("utf-8"))
            except Exception as e:  # sbpy: ignore=silent-except
                self.send_response(500)
                self.end_headers()
                self.wfile.write(json.dumps({"ok": False, "error": str(e)}).encode("utf-8"))
            return

        if parsed.path == "/api/search":
            query = data.get("query", "")
            from .search import semantic_code_search

            results = semantic_code_search(query, ".")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps([r.to_dict() for r in results]).encode("utf-8"))
            return

        if parsed.path == "/api/instructions":
            from .config import set_config_value

            instructions = data.get("instructions", "")
            set_config_value("custom_instructions", instructions)
            get_config().custom_instructions = instructions
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True}).encode("utf-8"))
            return

        self.send_response(404)
        self.end_headers()


def start_dashboard_server(
    port: int = 8080,
    open_browser: bool = True,
    console: Any = None,
) -> None:
    """Starts the SBpy local web UI dashboard."""
    console = console or get_console()

    # Find free port if 8080 is busy
    server = None
    for p in range(port, port + 20):
        try:
            server = socketserver.TCPServer(("", p), DashboardHandler)
            port = p
            break
        except OSError:
            continue

    if server is None:
        console.write(console.paint(f"  ! Could not bind to port {port}", "red"))
        return

    url = f"http://localhost:{port}"
    console.write(console.paint(f"\n  🚀 SBpy Web Dashboard running at: {url}", "green", bold=True))
    console.write(console.paint("  Press Ctrl+C to stop the dashboard server.\n", "grey"))

    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        console.write(console.paint("\n  Dashboard server stopped.", "yellow"))
    finally:
        server.server_close()
