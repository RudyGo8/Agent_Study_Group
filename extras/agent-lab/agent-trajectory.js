/**
 * <agent-trajectory> — a self-contained Web Component that replays an
 * Agent's ReAct loop step by step. Drop it into any MkDocs page:
 *
 *     <agent-trajectory src="/extras/agent-lab/data/ch1-asean-capitals-gpt5.json" />
 *
 * Data format: see extras/agent-lab/SCHEMA.md. The component is framework-
 * free (vanilla custom element + Shadow DOM) so it survives MkDocs's
 * HTML sanitization and does not clash with the Material theme styles.
 */
(function () {
  const TEMPLATE = document.createElement('template');
  TEMPLATE.innerHTML = `
    <style>
      :host {
        display: block;
        --bg:        #f7f8fa;
        --card:      #ffffff;
        --border:    #e3e6eb;
        --ink:       #1f2328;
        --ink-soft:  #57606a;
        --accent:    #6f42c1;   /* indigo, matches the book's palette */
        --thought:   #6f42c1;
        --action:    #0969da;
        --obs:       #1a7f37;
        --answer:    #bf3989;
        --warn:      #9a6700;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
                     "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
        font-size: 14px;
        line-height: 1.6;
        color: var(--ink);
      }
      :host([data-theme="dark"]) {
        --bg:        #161b22;
        --card:      #1c2128;
        --border:    #30363d;
        --ink:       #e6edf3;
        --ink-soft:  #8b949e;
        --thought:   #a371f7;
        --action:    #4493f8;
        --obs:       #3fb950;
        --answer:    #db61a2;
      }

      .wrap {
        background: var(--bg);
        border: 1px solid var(--border);
        border-radius: 10px;
        padding: 14px 16px 16px;
      }

      header.meta {
        display: flex;
        flex-wrap: wrap;
        align-items: baseline;
        gap: 8px 14px;
        padding-bottom: 10px;
        margin-bottom: 12px;
        border-bottom: 1px dashed var(--border);
      }
      .meta h3 {
        margin: 0;
        font-size: 15px;
        font-weight: 600;
        color: var(--ink);
      }
      .meta .pill {
        font-size: 11px;
        padding: 2px 8px;
        border-radius: 999px;
        background: var(--card);
        border: 1px solid var(--border);
        color: var(--ink-soft);
      }
      .meta .task {
        flex-basis: 100%;
        font-size: 13px;
        color: var(--ink-soft);
      }
      .meta .task b { color: var(--ink); font-weight: 500; }

      .toolbar {
        display: flex;
        align-items: center;
        gap: 8px;
        margin-bottom: 12px;
        font-size: 12px;
        color: var(--ink-soft);
      }
      .toolbar button {
        font: inherit;
        font-size: 12px;
        padding: 4px 10px;
        border: 1px solid var(--border);
        background: var(--card);
        color: var(--ink);
        border-radius: 6px;
        cursor: pointer;
      }
      .toolbar button:hover { border-color: var(--accent); }
      .toolbar .spacer { flex: 1; }
      .toolbar .progress {
        flex: 1;
        height: 4px;
        background: var(--border);
        border-radius: 2px;
        overflow: hidden;
        max-width: 240px;
      }
      .toolbar .progress > i {
        display: block;
        height: 100%;
        width: 0;
        background: var(--accent);
        transition: width .25s ease;
      }

      ol.timeline {
        list-style: none;
        margin: 0;
        padding: 0 0 0 22px;
        position: relative;
      }
      ol.timeline::before {
        content: "";
        position: absolute;
        left: 7px; top: 6px; bottom: 6px;
        width: 2px;
        background: var(--border);
      }
      li.step {
        position: relative;
        margin-bottom: 10px;
        opacity: 0.4;
        transition: opacity .2s;
      }
      li.step.shown { opacity: 1; }

      li.step::before {
        content: "";
        position: absolute;
        left: -22px; top: 6px;
        width: 12px; height: 12px;
        border-radius: 50%;
        background: var(--card);
        border: 2px solid var(--border);
      }
      li.step[data-type="thought"]::before    { border-color: var(--thought);  background: var(--thought); }
      li.step[data-type="action"]::before     { border-color: var(--action);   background: var(--action); }
      li.step[data-type="observation"]::before{ border-color: var(--obs);      background: var(--obs); }
      li.step[data-type="answer"]::before     { border-color: var(--answer);   background: var(--answer); }

      .step .head {
        display: flex;
        align-items: center;
        gap: 8px;
        font-size: 12px;
        color: var(--ink-soft);
        margin-bottom: 4px;
      }
      .step .head .badge {
        font-size: 11px;
        padding: 1px 7px;
        border-radius: 4px;
        color: #fff;
      }
      .step[data-type="thought"]    .badge { background: var(--thought); }
      .step[data-type="action"]     .badge { background: var(--action); }
      .step[data-type="observation"] .badge { background: var(--obs); }
      .step[data-type="answer"]     .badge { background: var(--answer); }
      .step .head .iter { opacity: .8; }
      .step .head .tool { font-family: ui-monospace, SFMono-Regular, monospace; }

      .step .body {
        background: var(--card);
        border: 1px solid var(--border);
        border-radius: 6px;
        padding: 8px 10px;
        font-size: 13px;
        white-space: pre-wrap;
        word-break: break-word;
      }
      .step[data-type="thought"] .body { border-left: 3px solid var(--thought); }
      .step[data-type="action"]  .body { border-left: 3px solid var(--action);  }
      .step[data-type="observation"] .body { border-left: 3px solid var(--obs); }
      .step[data-type="answer"]  .body { border-left: 3px solid var(--answer); }

      .step .body.collapsed {
        max-height: 6.5em;
        overflow: hidden;
        position: relative;
      }
      .step .body.collapsed::after {
        content: "";
        position: absolute; inset: auto 0 0 0; height: 2.5em;
        background: linear-gradient(transparent, var(--card));
      }

      .step .args, .step .raw {
        margin-top: 6px;
        font-family: ui-monospace, SFMono-Regular, monospace;
        font-size: 12px;
        background: var(--bg);
        border: 1px solid var(--border);
        border-radius: 4px;
        padding: 6px 8px;
        white-space: pre;
        overflow-x: auto;
      }

      .step .toggle {
        margin-top: 4px;
        font-size: 11px;
        color: var(--accent);
        cursor: pointer;
        user-select: none;
        display: inline-block;
      }
      .step .toggle:hover { text-decoration: underline; }

      .error {
        padding: 10px;
        color: var(--warn);
        background: var(--card);
        border: 1px solid var(--border);
        border-radius: 6px;
      }

      @media (max-width: 540px) {
        :host { font-size: 13px; }
        .toolbar .progress { max-width: 120px; }
      }
    </style>

    <article class="wrap" hidden>
      <header class="meta">
        <h3 id="t-title"></h3>
        <span class="pill" id="t-model"></span>
        <span class="pill" id="t-outcome"></span>
        <span class="pill" id="t-iter"></span>
        <div class="task" id="t-task"></div>
      </header>
      <div class="toolbar">
        <button id="btn-play">▶ 自动播放</button>
        <button id="btn-next">下一步 ⏭</button>
        <button id="btn-reset">重置</button>
        <div class="progress"><i id="bar"></i></div>
        <span id="counter">0 / 0</span>
      </div>
      <ol class="timeline" id="timeline"></ol>
    </article>
    <div class="error" id="loading" hidden>加载轨迹中……</div>
  `;

  const TYPE_LABEL = {
    thought:     '思考',
    action:      '行动',
    observation: '观察',
    answer:      '答案',
  };

  class AgentTrajectory extends HTMLElement {
    constructor() {
      super();
      const root = this.attachShadow({ mode: 'open' });
      root.appendChild(TEMPLATE.content.cloneNode(true));
      this._shown = 0;
      this._timer = null;
    }

    connectedCallback() {
      this._applyTheme();
      this._wire();
      const src = this.getAttribute('src');
      if (!src) {
        this._fail('未指定 src 属性');
        return;
      }
      this._load(src);
      // Re-apply theme if the document changes light/dark.
      new MutationObserver(() => this._applyTheme())
        .observe(document.documentElement, { attributes: true, attributeFilter: ['data-md-color-scheme', 'data-theme'] });
    }

    _applyTheme() {
      const scheme = document.documentElement.getAttribute('data-md-color-scheme');
      this.setAttribute('data-theme', scheme === 'slate' ? 'dark' : 'light');
    }

    _wire() {
      const $ = (id) => this.shadowRoot.getElementById(id);
      $('btn-play').addEventListener('click', () => this._togglePlay());
      $('btn-next').addEventListener('click', () => this._step());
      $('btn-reset').addEventListener('click', () => this._reset());
    }

    async _load(src) {
      this.shadowRoot.getElementById('loading').hidden = false;
      try {
        const res = await fetch(src);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        this._render(data);
      } catch (e) {
        this._fail(`无法加载轨迹：${e.message}`);
      }
    }

    _fail(msg) {
      const el = this.shadowRoot.getElementById('loading');
      el.hidden = false;
      el.textContent = msg;
    }

    _render(data) {
      const $ = (id) => this.shadowRoot.getElementById(id);
      $('loading').hidden = true;

      $('t-title').textContent   = data.title || data.experiment || 'Agent 轨迹';
      $('t-model').textContent   = '🤖 ' + (data.model || 'unknown');
      $('t-outcome').textContent = '结果：' + this._outcomeLabel(data.outcome);
      $('t-iter').textContent    = (data.steps || []).length + ' 步';
      $('t-task').innerHTML      = data.task ? `任务：<b>${this._escape(data.task)}</b>` : '';

      const ol = $('timeline');
      ol.innerHTML = '';
      (data.steps || []).forEach((s, i) => {
        const li = document.createElement('li');
        li.className = 'step';
        li.dataset.type = s.type;
        li.dataset.index = i;

        const head = document.createElement('div');
        head.className = 'head';
        const badge = document.createElement('span');
        badge.className = 'badge';
        badge.textContent = TYPE_LABEL[s.type] || s.type;
        const iter = document.createElement('span');
        iter.className = 'iter';
        iter.textContent = `第 ${s.iteration} 轮迭代`;
        head.append(badge, iter);
        if (s.tool) {
          const t = document.createElement('span');
          t.className = 'tool';
          t.textContent = '🔧 ' + s.tool;
          head.appendChild(t);
        }
        li.appendChild(head);

        if (s.content != null) {
          const body = document.createElement('div');
          body.className = 'body';
          body.textContent = s.content;
          li.appendChild(body);
          if (s.content.length > 220) this._makeCollapsible(body);
        }
        if (s.args != null) {
          const args = document.createElement('div');
          args.className = 'args';
          args.textContent = 'args: ' + this._prettify(s.args);
          li.appendChild(args);
        }
        ol.appendChild(li);
      });

      this._wrapEl = this.shadowRoot.querySelector('.wrap');
      this._wrapEl.hidden = false;
      this._steps = ol.children;
      this._total = this._steps.length;
      this._shown = 0;
      this._update();
    }

    _makeCollapsible(body) {
      body.classList.add('collapsed');
      const toggle = document.createElement('span');
      toggle.className = 'toggle';
      toggle.textContent = '展开 ▾';
      toggle.addEventListener('click', () => {
        const collapsed = body.classList.toggle('collapsed');
        toggle.textContent = collapsed ? '展开 ▾' : '收起 ▴';
      });
      body.parentElement.insertBefore(toggle, body.nextSibling);
    }

    _togglePlay() {
      if (this._timer) {
        clearInterval(this._timer);
        this._timer = null;
        this.shadowRoot.getElementById('btn-play').textContent = '▶ 自动播放';
      } else {
        this.shadowRoot.getElementById('btn-play').textContent = '⏸ 暂停';
        this._timer = setInterval(() => {
          if (this._shown >= this._total) {
            clearInterval(this._timer);
            this._timer = null;
            this.shadowRoot.getElementById('btn-play').textContent = '▶ 自动播放';
            return;
          }
          this._step();
        }, 1200);
      }
    }

    _step() {
      if (this._shown >= this._total) return;
      this._shown++;
      this._update();
    }

    _reset() {
      if (this._timer) {
        clearInterval(this._timer);
        this._timer = null;
        this.shadowRoot.getElementById('btn-play').textContent = '▶ 自动播放';
      }
      this._shown = 0;
      this._update();
    }

    _update() {
      for (let i = 0; i < this._steps.length; i++) {
        this._steps[i].classList.toggle('shown', i < this._shown);
      }
      const bar = this.shadowRoot.getElementById('bar');
      const counter = this.shadowRoot.getElementById('counter');
      const pct = this._total ? (this._shown / this._total) * 100 : 0;
      bar.style.width = pct + '%';
      counter.textContent = `${this._shown} / ${this._total}`;
      if (this._shown > 0) {
        const last = this._steps[this._shown - 1];
        last.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      }
    }

    _outcomeLabel(o) {
      return ({ success: '✅ 成功', failure: '❌ 失败',
                loop: '🔁 死循环', timeout: '⏱️ 超时' })[o] || (o || '未知');
    }

    _escape(s) {
      return String(s).replace(/[&<>"]/g, c =>
        ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
    }
    _prettify(v) {
      try { return typeof v === 'string' ? v : JSON.stringify(v, null, 2); }
      catch { return String(v); }
    }
  }

  customElements.define('agent-trajectory', AgentTrajectory);
})();
