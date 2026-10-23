/* MGE Labs page: the journal card that opens as you scroll, six small demos, and a quiet grid background.
   Every number on this page is made up for illustration. It is not a result and not a recommendation. */
(function () {
  'use strict';
  var track = document.getElementById('lx-track');
  if (!track) return;
  var section = document.getElementById('journal');
  var card = document.getElementById('lx-card');
  var pill = document.getElementById('lx-pill');
  var inner = document.getElementById('lx-inner');
  var rail = document.getElementById('lx-rail');
  var pane = document.getElementById('lx-pane');
  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var openAmt = 0;

  function money(n) { return (n < 0 ? '−$' : '$') + Math.abs(Math.round(n)).toLocaleString('en-US'); }
  function rfmt(r) { return (r > 0 ? '+' : r < 0 ? '−' : '') + Math.abs(r).toFixed(2) + 'R'; }
  var toastEl = document.createElement('div');
  toastEl.className = 'lx-toast'; toastEl.setAttribute('role', 'status');
  document.body.appendChild(toastEl);
  var toastTimer;
  function toast(m) { toastEl.textContent = m; toastEl.classList.add('show'); clearTimeout(toastTimer); toastTimer = setTimeout(function () { toastEl.classList.remove('show'); }, 2300); }

  var TR = [
    { t: '9:31', s: 'Setup A', pc: 'Desktop', pnl: 240 },
    { t: '9:48', s: 'Setup B', pc: 'Laptop', pnl: -200 },
    { t: '10:12', s: 'Hand trade', pc: 'Desktop', pnl: 120 },
    { t: '10:40', s: 'Setup A', pc: 'Laptop', pnl: -80 }
  ];
  var S = {
    journal: { pc: 'All', risk: 200, open: -1 }, edge: { n: 12 }, payout: { bal: 99200, loss: 300, view: 'one', f: 'ACT', q: '' },
    ledger: { fees: 550, pay: 380 },
    pcs: { list: [{ n: 'Desktop', on: true }, { n: 'Laptop', on: true }, { n: 'Office PC', on: false }], code: null },
    data: { two: true }
  };
  var seen = {};

  function bullets(i) { return '<ul class="lx-det">' + i.det.map(function (d) { return '<li>' + d + '</li>'; }).join('') + '</ul>'; }
  function focusKeep(el, id) { var x = el.querySelector(id); if (x) x.focus(); }

  var ITEMS = [
    { tag: 'JOURNAL', title: 'Every trade, every PC, without typing',
      why: 'You trade on more than one PC or account. This gives you one record that fills itself in.',
      det: ["Each closed trade syncs seconds after it closes, from NinjaTrader's own data.", 'Journals any strategy and any indicator you trade by hand, each scored separately.', 'Label hand trades with your own setup names to compare them.'],
      tip: 'Change the risk and watch every R value recompute. Click a trade.',
      mount: function (el) {
        var self = this, s = S.journal;
        var rows = TR.filter(function (t) { return s.pc === 'All' || t.pc === s.pc; });
        var net = rows.reduce(function (a, t) { return a + t.pnl / s.risk; }, 0);
        el.innerHTML = '<div class="lx-cap"><span>TODAY &middot; <span class="lx-try">TRY IT</span></span><span>SAMPLE DATA</span></div>' +
          '<div class="lx-seg" id="jpc">' + ['All', 'Desktop', 'Laptop'].map(function (p) { return '<button type="button" class="' + (p === s.pc ? 'on' : '') + '" data-p="' + p + '">' + p + '</button>'; }).join('') + '</div>' +
          '<div class="lx-lab"><span>Risk you set per trade</span><b>' + money(s.risk) + '</b></div><input type="range" id="jr" aria-label="Risk per trade" min="50" max="500" step="10" value="' + s.risk + '">' +
          rows.map(function (t, i) { return '<div class="lx-row ' + (s.open === i ? 'exp' : '') + '" data-i="' + i + '"><span>' + t.t + '</span><span>' + t.s + ' <span class="lx-chip">' + t.pc + '</span></span><b class="' + (t.pnl > 0 ? 'lx-win' : 'lx-loss') + '">' + rfmt(t.pnl / s.risk) + '</b>' + (s.open === i ? '<div class="lx-detail">' + money(t.pnl) + ' result &divide; ' + money(s.risk) + ' risk = ' + rfmt(t.pnl / s.risk) + '</div>' : '') + '</div>'; }).join('') +
          '<div class="lx-lab"><span>Net for the day</span><b class="' + (net >= 0 ? 'lx-win' : 'lx-loss') + '">' + rfmt(net) + '</b></div>';
        [].forEach.call(el.querySelectorAll('#jpc button'), function (b) { b.onclick = function () { s.pc = b.getAttribute('data-p'); s.open = -1; self.mount(el); }; });
        el.querySelector('#jr').oninput = function (e) { s.risk = +e.target.value; self.mount(el); focusKeep(el, '#jr'); };
        [].forEach.call(el.querySelectorAll('.lx-row'), function (r) { r.onclick = function () { var i = +r.getAttribute('data-i'); s.open = s.open === i ? -1 : i; self.mount(el); }; });
      } },
    { tag: 'EDGE CHECK', title: 'Know whether a setup is doing anything',
      why: "A good week doesn't tell you if a setup works. Edge check compares each one with random entries taken at the same moments.",
      det: ["Measured about an hour after each trade, from NinjaTrader's own data on your PC.", 'Shown in R after commissions, never a win rate on its own.', 'A setup that is no better than random is flagged, so you decide with the facts.'],
      tip: 'Drag the slider to add measured trades. Nothing is judged before 30.',
      mount: function (el) {
        var self = this, n = S.edge.n, ok = n >= 30;
        function line(name, mine, rnd, good) {
          return '<div style="margin-top:10px"><b>' + name + '</b> <span class="lx-chip ' + (ok ? (good ? 'lx-win' : 'lx-warn') : '') + '">' + (ok ? (good ? 'ahead of random so far' : 'no better than random') : 'measuring ' + n + ' of 30') + '</span><div class="lx-bar"><i style="width:' + Math.min(100, n / 30 * 100) + '%;' + (ok && !good ? 'background:var(--lx-loss)' : '') + '"></i></div><small class="lx-fine">' + (ok ? mine + ' vs random ' + rnd : 'needs 30 measured trades before it says anything') + '</small></div>';
        }
        el.innerHTML = '<div class="lx-cap"><span>SETUPS VS RANDOM &middot; <span class="lx-try">TRY IT</span></span><span>SAMPLE DATA</span></div>' +
          '<div class="lx-lab"><span>Trades measured</span><b>' + n + '</b></div><input type="range" id="en" aria-label="Trades measured" min="0" max="40" value="' + n + '">' +
          line('Setup A', '+0.12R', '+0.04R', true) + line('Setup B', '−0.05R', '+0.03R', false) +
          '<p class="lx-fine" style="margin-top:10px">Random entries are taken at the same moments, with the same stop and holding time, using NinjaTrader\'s own data on your PC.</p>';
        el.querySelector('#en').oninput = function (e) { S.edge.n = +e.target.value; self.mount(el); focusKeep(el, '#en'); };
      } },
    { tag: 'PAYOUT GUARD', title: 'See your prop-firm rules before they cost you',
      why: 'Drawdown, consistency and payout rules are easy to lose track of across accounts. It tracks them and tells you when to stop and request a payout, even with dozens of accounts.',
      det: ['One searchable list of every account on every PC, those that need you first.', 'Warns when a rule you set is about to be broken. It never places or cancels orders.', 'Counts payouts per cycle, for example payout 2 of 6.'],
      tip: 'Move the balance, then open all accounts.',
      pgSeg: function () {
        var v = S.payout.view;
        return '<div class="lx-seg" id="pgv" style="margin-bottom:10px"><button type="button" class="' + (v === 'one' ? 'on' : '') + '" data-v="one">One account</button><button type="button" class="' + (v === 'all' ? 'on' : '') + '" data-v="all">All accounts</button></div>';
      },
      pgWire: function (el) {
        var self = this;
        [].forEach.call(el.querySelectorAll('#pgv button'), function (b) { b.onclick = function () { S.payout.view = b.getAttribute('data-v'); self.mount(el); }; });
      },
      mountAll: function (el) {
        var self = this, p = S.payout;
        var kinds = { READY: ['PAYOUT READY', 'win', 0], PASSED: ['PASSED', 'win', 1], BREACHED: ['BREACHED', 'loss', 2], BUILDING: ['BUILDING', '', 3] };
        var A = [];
        for (var i = 0; i < 36; i++) {
          var k = i % 9 === 0 ? 'READY' : i % 13 === 5 ? 'PASSED' : i === 17 ? 'BREACHED' : 'BUILDING';
          A.push({ n: (i % 2 ? '100K-' : '50K-') + String(i + 1).padStart(2, '0'), k: k, room: k === 'BREACHED' ? 0 : 450 + ((i * 197) % 3300), pc: i % 3 ? 'Desktop' : 'Laptop' });
        }
        var need = function (a) { return a.k !== 'BUILDING'; };
        var list = A.filter(function (a) { return (p.f === 'ALL' || need(a)) && (!p.q || (a.n + ' ' + a.pc).toLowerCase().indexOf(p.q) > -1); })
          .sort(function (a, b) { return kinds[a.k][2] - kinds[b.k][2] || a.room - b.room; });
        var nn = A.filter(need).length;
        el.innerHTML = '<div class="lx-cap"><span>EVERY ACCOUNT &middot; <span class="lx-try">TRY IT</span></span><span>SAMPLE DATA</span></div>' + this.pgSeg() +
          '<div class="lx-seg" id="pgf" style="margin-left:8px"><button type="button" class="' + (p.f === 'ACT' ? 'on' : '') + '" data-f="ACT">Needs action ' + nn + '</button><button type="button" class="' + (p.f === 'ALL' ? 'on' : '') + '" data-f="ALL">All ' + A.length + '</button></div>' +
          '<input id="pgq" type="search" placeholder="Search account" aria-label="Search accounts" autocomplete="off" value="' + p.q + '" style="margin-top:8px;width:100%;padding:6px 10px;border-radius:8px;border:1px solid var(--border);background:var(--bg-panel);color:var(--text);font:inherit">' +
          '<div style="margin-top:8px">' + list.slice(0, 4).map(function (a) {
            var kd = kinds[a.k];
            return '<div class="lx-row" style="grid-template-columns:1fr auto auto;cursor:default"><span><b>' + a.n + '</b> <span class="lx-chip">' + a.pc + '</span></span><span class="' + (kd[1] ? 'lx-' + kd[1] : '') + '" style="font-size:11px;font-weight:700">' + kd[0] + '</span><span class="' + (a.room < 800 && a.k !== 'BREACHED' ? 'lx-warn' : '') + '">' + money(a.room) + '</span></div>';
          }).join('') + (list.length ? '' : '<p class="lx-fine">Nothing matches.</p>') + '</div>' +
          '<p class="lx-fine" style="margin-top:8px">' + (list.length > 4 ? 'Top 4 of ' + list.length + ' matches shown here, type to narrow.' : list.length + ' of ' + A.length + ' accounts. ')+ '</p>';
        this.pgWire(el);
        [].forEach.call(el.querySelectorAll('#pgf button'), function (b) { b.onclick = function () { p.f = b.getAttribute('data-f'); self.mount(el); }; });
        el.querySelector('#pgq').oninput = function (e) { p.q = e.target.value.trim().toLowerCase(); self.mount(el); var q = el.querySelector('#pgq'); q.focus(); q.setSelectionRange(q.value.length, q.value.length); };
      },
      mount: function (el) {
        var self = this, p = S.payout, floor = 97000, lim = 750, room = p.bal - floor, pct = Math.round(p.loss / lim * 100);
        if (p.view === 'all') { return this.mountAll(el); }
        var st = room <= 0 ? ['BELOW THE FLOOR', 'loss'] : room < 600 ? ['CLOSE TO THE FLOOR', 'warn'] : ['ROOM TO TRADE', 'win'];
        var dl = pct >= 100 ? ['Daily loss limit reached: warning (the decision stays yours)', 'loss'] : pct >= 75 ? ['Daily loss at ' + pct + '%: warning', 'warn'] : ['Daily loss at ' + pct + '%', 'win'];
        el.innerHTML = '<div class="lx-cap"><span>ACCOUNT 100K-A &middot; <span class="lx-try">TRY IT</span></span><span>SAMPLE DATA</span></div>' + this.pgSeg() +
          '<b class="lx-' + st[1] + '">' + st[0] + '</b> <span class="lx-chip">floor ' + money(floor) + '</span>' +
          '<div class="lx-lab"><span>Balance</span><b>' + money(p.bal) + '</b></div><input type="range" id="pb" aria-label="Balance" min="96500" max="103000" step="50" value="' + p.bal + '">' +
          '<div class="lx-lab"><span>Room above the floor</span><b class="lx-' + st[1] + '">' + money(room) + '</b></div>' +
          '<div class="lx-lab" style="margin-top:14px"><span>Today\'s loss (limit ' + money(lim) + ')</span><b>' + money(p.loss) + '</b></div><input type="range" id="pl" aria-label="Today\'s loss" min="0" max="900" step="10" value="' + p.loss + '">' +
          '<div class="lx-bar"><i style="width:' + Math.min(100, pct) + '%;background:var(--lx-' + dl[1] + ')"></i></div><small class="lx-' + dl[1] + '">' + dl[0] + '</small>' +
          '<p class="lx-fine" style="margin-top:10px">Warn mode only: it never places or cancels orders.</p>';
        this.pgWire(el);
        el.querySelector('#pb').oninput = function (e) { p.bal = +e.target.value; self.mount(el); focusKeep(el, '#pb'); };
        el.querySelector('#pl').oninput = function (e) { p.loss = +e.target.value; self.mount(el); focusKeep(el, '#pl'); };
      } },
    { tag: 'PROP LEDGER', title: 'What your accounts actually cost and paid',
      why: 'Fees, resets and payouts in one place, so you can see where you really stand.',
      det: ['Enter fees and payouts, or use what Payout Guard already saw.', 'Totals by period, including history from before you started.'],
      tip: 'Add a fee or a payout and watch the net.',
      mount: function (el) {
        var self = this, l = S.ledger, net = l.pay - l.fees, mx = Math.max(l.fees, l.pay, 1);
        el.innerHTML = '<div class="lx-cap"><span>THIS PERIOD &middot; <span class="lx-try">TRY IT</span></span><span>SAMPLE DATA</span></div>' +
          '<div class="lx-lab"><span>Fees</span><b class="lx-loss">' + money(l.fees) + '</b></div><div class="lx-bar"><i style="width:' + l.fees / mx * 100 + '%;background:var(--lx-loss)"></i></div>' +
          '<div class="lx-lab"><span>Payouts</span><b class="lx-win">' + money(l.pay) + '</b></div><div class="lx-bar"><i style="width:' + l.pay / mx * 100 + '%;background:var(--lx-win)"></i></div>' +
          '<div class="lx-lab" style="margin-top:12px"><span>Net after fees</span><b class="' + (net >= 0 ? 'lx-win' : 'lx-loss') + '">' + money(net) + '</b></div>' +
          '<div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:12px"><button type="button" class="lx-btn" id="lf">+ fee $150</button><button type="button" class="lx-btn" id="lp">+ payout $300</button><button type="button" class="lx-btn" id="lr">Reset</button></div>';
        el.querySelector('#lf').onclick = function () { l.fees += 150; self.mount(el); };
        el.querySelector('#lp').onclick = function () { l.pay += 300; self.mount(el); };
        el.querySelector('#lr').onclick = function () { S.ledger = { fees: 550, pay: 380 }; self.mount(el); };
      } },
    { tag: 'YOUR PCs', title: 'Pair a PC once, then forget it',
      why: 'It keeps syncing while NinjaTrader is open. The journal runs on our servers, so you never keep a browser open.',
      det: ['Pair with a one-time code; closed trades sync from then on.', 'Phone, tablet or PC: install it as an app, with an app lock.', 'Light and dark themes.'],
      tip: 'Pair a sample PC, or switch one on and off.',
      mount: function (el) {
        var self = this, p = S.pcs;
        el.innerHTML = '<div class="lx-cap"><span>MY PCs &middot; <span class="lx-try">TRY IT</span></span><span>SAMPLE DATA</span></div>' +
          p.list.map(function (x, i) { return '<div class="lx-pcr"><span><i class="lx-dot ' + (x.on ? '' : 'off') + '"></i>' + x.n + '</span><span><span class="lx-chip">' + (x.on ? 'online' : 'offline') + '</span> <button type="button" class="lx-sw ' + (x.on ? 'on' : '') + '" data-i="' + i + '" aria-label="Switch ' + x.n + '"></button></span></div>'; }).join('') +
          (p.code ? '<div class="lx-code">' + p.code + '</div><p class="lx-fine">Type this one-time code in the NinjaTrader window.</p><button type="button" class="lx-btn pri" id="pd">I typed it</button>'
            : '<div style="margin-top:12px"><button type="button" class="lx-btn pri" id="pn"' + (p.list.length >= 5 ? ' disabled' : '') + '>Pair a new PC</button></div>');
        [].forEach.call(el.querySelectorAll('.lx-sw'), function (b) { b.onclick = function () { var i = +b.getAttribute('data-i'); p.list[i].on = !p.list[i].on; self.mount(el); }; });
        var pn = el.querySelector('#pn'); if (pn) pn.onclick = function () { p.code = 'ABCD-' + Math.floor(1000 + Math.random() * 9000); self.mount(el); };
        var pd = el.querySelector('#pd'); if (pd) pd.onclick = function () { p.list.push({ n: 'New PC', on: true }); p.code = null; toast('Paired. Closed trades from this PC now sync.'); self.mount(el); };
      } },
    { tag: 'YOUR DATA', title: 'Yours to keep',
      why: 'Two-step sign-in and recovery codes protect the account. Take everything with you whenever you want.',
      det: ['Export every trade as a CSV file at any time, including after you cancel.', 'Your journal stays readable after cancelling.'],
      tip: 'Switch two-step on and off. Download the sample CSV.',
      mount: function (el) {
        var self = this, d = S.data;
        el.innerHTML = '<div class="lx-cap"><span>ACCOUNT &middot; <span class="lx-try">TRY IT</span></span><span>SAMPLE</span></div>' +
          '<div class="lx-pcr"><span>Two-step sign-in</span><button type="button" class="lx-sw ' + (d.two ? 'on' : '') + '" id="tw" aria-label="Two-step sign-in"></button></div>' +
          '<div class="lx-pcr"><span>Recovery codes</span><span class="lx-chip ' + (d.two ? 'lx-win' : '') + '">' + (d.two ? '10 saved' : 'off') + '</span></div>' +
          '<p class="lx-fine" style="margin:10px 0">' + (d.two ? 'Each recovery code signs you in once if you lose your phone.' : 'Without two-step sign-in a password is the only protection.') + '</p>' +
          '<button type="button" class="lx-btn pri" id="ex">Download sample CSV</button><p class="lx-fine" style="margin-top:8px">Real exports include every trade, also after you cancel.</p>';
        el.querySelector('#tw').onclick = function () { d.two = !d.two; self.mount(el); };
        el.querySelector('#ex').onclick = function () {
          var rows = ['time,setup,pc,result_usd,risk_usd,r'].concat(TR.map(function (t) { return [t.t, t.s, t.pc, t.pnl, 200, (t.pnl / 200).toFixed(2)].join(','); }));
          var a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([rows.join('\n')], { type: 'text/csv' })); a.download = 'mge-labs-sample.csv'; document.body.appendChild(a); a.click(); a.remove();
          toast('Sample file downloaded (made-up data).');
        };
      } }
  ];
  var N = ITEMS.length, cur = -1;
  rail.innerHTML = ITEMS.map(function (i, k) { return '<button type="button" data-k="' + k + '">' + i.tag + '</button>'; }).join('') + '<div class="lx-prog"><i></i></div><div class="lx-kb">Tabs, or the left and right arrow keys.</div>';

  function show(k) {
    if (k === cur) return; cur = k; seen[k] = 1;
    [].forEach.call(rail.querySelectorAll('button'), function (b, x) { b.classList.toggle('on', x === k); b.classList.toggle('done', !!seen[x] && x !== k); });
    var i = ITEMS[k];
    pane.innerHTML = '<span class="lx-tag">' + i.tag + '</span><h3 class="lx-title">' + i.title + '</h3><p class="lx-why">' + i.why + '</p><div class="lx-grid"><div>' + bullets(i) + '<p class="lx-fine lx-try">' + i.tip + '</p>' +
      (k < N - 1 ? '<button type="button" class="lx-btn lx-next" data-go="' + (k + 1) + '">Next: ' + ITEMS[k + 1].tag.toLowerCase() + ' &rarr;</button>' : '') + '</div><div class="lx-vis" id="lx-vis"></div></div>';
    i.mount(pane.querySelector('#lx-vis'));
    var nb = pane.querySelector('.lx-next'); if (nb) nb.onclick = function () { goTo(k + 1); };
  }
  /* No scroll-jacking: the card sits in the normal page flow. It opens once, when it scrolls into view (or when
     clicked), with a short animation; after that it is an ordinary tabbed panel and the page scrolls as usual. */
  var dirty = true, isOpen = false, tween = 0;
  var compact = reduce || window.innerWidth <= 820;   // phones and reduced motion: the card is simply open, at its natural height, with no inner scrolling
  function setOpen(e) {
    var W = Math.min(980, window.innerWidth - 36), H = Math.min(Math.max(window.innerHeight - 80, 480), 560);
    var st = card.parentNode;   // the vars live on the stage so it grows with the card
    st.style.setProperty('--w', (260 + (W - 260) * e) + 'px'); st.style.setProperty('--h', (86 + (H - 86) * e) + 'px'); st.style.setProperty('--r', (43 - 25 * e) + 'px');
    st.style.setProperty('--po', String(1 - Math.min(1, e * 2.2))); inner.style.setProperty('--io', String(Math.max(0, (e - 0.55) / 0.45)));
    card.classList.toggle('lx-isopen', e > 0.5);
    if (Math.abs(e - openAmt) > 0.004) dirty = true;
    openAmt = e;
  }
  function open() {
    if (isOpen) return; isOpen = true;
    if (compact) { setOpen(1); return; }
    var t0 = performance.now(), D = 650;
    (function step(now) { var o = Math.min(1, (now - t0) / D); setOpen(o * o * (3 - 2 * o)); if (o < 1) tween = requestAnimationFrame(step); })(t0);
  }
  function goTo(k) {
    k = Math.max(0, Math.min(N - 1, k));
    open(); show(k); rail.style.setProperty('--pp', (((k + 1) / N) * 100) + '%');
  }
  rail.addEventListener('click', function (e) { var b = e.target.closest ? e.target.closest('button') : null; if (b) goTo(+b.getAttribute('data-k')); });
  pill.addEventListener('click', function () { goTo(0); });
  document.addEventListener('keydown', function (e) {
    if (!isOpen || e.metaKey || e.ctrlKey || e.altKey) return;
    var r = card.getBoundingClientRect(); if (r.bottom < 0 || r.top > window.innerHeight) return;
    var tg = document.activeElement && document.activeElement.tagName; if (tg === 'INPUT' || tg === 'TEXTAREA' || tg === 'SELECT') return;
    if (!card.contains(document.activeElement)) return;   // arrows only steer the card when focus is inside it: the page keeps its own arrow scrolling
    if (e.key === 'ArrowRight') { e.preventDefault(); goTo(cur + 1); }
    if (e.key === 'ArrowLeft') { e.preventDefault(); goTo(cur - 1); }
  });
  window.addEventListener('resize', function () { if (isOpen) setOpen(1); });
  track.hidden = false; section.classList.add('lx-on', 'lx-flow');
  if (compact) section.classList.add('lx-reduce');
  show(0); rail.style.setProperty('--pp', (100 / N) + '%');
  if ('IntersectionObserver' in window && !compact) {
    new IntersectionObserver(function (en, ob) { if (en[0].isIntersecting) { open(); ob.disconnect(); } }, { threshold: 0.6, rootMargin: '0px 0px -30% 0px' }).observe(card);
  } else { open(); }

  /* quiet grid background: dots on the page's own grid lines swell near the cursor; a click sends a ripple */
  var cv = document.createElement('canvas'); cv.id = 'lx-bg'; cv.setAttribute('aria-hidden', 'true'); document.body.insertBefore(cv, document.body.firstChild);
  var cx = cv.getContext('2d'), W2 = 0, H2 = 0, mx = -9999, my = -9999, col = {}, ripples = [], last = 0;
  function colors() { var c = getComputedStyle(document.documentElement); col.dim = c.getPropertyValue('--text-dim').trim() || '#7d8390'; col.hi = c.getPropertyValue('--blue-hi').trim() || '#8cc6ff'; }
  function size() { var d = 1; dirty = true; W2 = window.innerWidth; H2 = window.innerHeight; cv.width = W2 * d; cv.height = H2 * d; cx.setTransform(d, 0, 0, d, 0, 0); }
  function draw(t) {
    var o = openAmt, sp = 46, al = 1 - o * 0.75;
    ripples = ripples.filter(function (r) { return t - r.t < 1.6; });
    cx.clearRect(0, 0, W2, H2);
    for (var x = 0; x <= W2; x += sp) for (var y = 0; y <= H2; y += sp) {
      var k = 0, px = x, py = y;
      if (!reduce) {
        var dx = x - mx, dy = y - my, d = Math.sqrt(dx * dx + dy * dy);
        if (d < 150) { k = 1 - d / 150; if (d > 0) { px += dx / d * k * 10; py += dy / d * k * 10; } }
        for (var i = 0; i < ripples.length; i++) { var r = ripples[i], rad = (t - r.t) * 420, dd = Math.abs(Math.sqrt((x - r.x) * (x - r.x) + (y - r.y) * (y - r.y)) - rad); if (dd < 46) k = Math.max(k, (1 - dd / 46) * (1 - (t - r.t) / 1.6)); }
      }
      cx.globalAlpha = (0.16 + 0.6 * k) * al; cx.fillStyle = k > 0.15 ? col.hi : col.dim;
      cx.beginPath(); cx.arc(px, py, 1.1 + 2.4 * k, 0, 6.283); cx.fill();
    }
    cx.globalAlpha = 1;
  }
  function frame(ts) { var t = ts / 1000; if (!document.hidden && (dirty || ripples.length) && (t - last > 0.033)) { last = t; dirty = false; draw(t); } requestAnimationFrame(frame); }
  window.addEventListener('pointermove', function (e) { mx = e.clientX; my = e.clientY; dirty = true; }, { passive: true });
  document.addEventListener('pointerleave', function () { mx = my = -9999; dirty = true; });
  window.addEventListener('pointerdown', function (e) { var tg = e.target; if (!reduce && !(tg.closest && tg.closest('button,input,a,.lx-card,.panel,details,nav,footer'))) ripples.push({ x: e.clientX, y: e.clientY, t: performance.now() / 1000 }); });
  window.addEventListener('resize', size);
  colors(); size();
  try { new MutationObserver(function () { setTimeout(function () { colors(); dirty = true; }, 30); }).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] }); } catch (e) { }
  requestAnimationFrame(frame);
})();
