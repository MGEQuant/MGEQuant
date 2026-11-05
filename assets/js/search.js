/* MGEQuant · assets/js/search.js
   Site search (palette, hero box, search.html) and the research list filters (research.html).
   Vanilla JS, no dependencies, no network except one same-site fetch of search-index.json.
   Stores nothing in the browser (no cookies, no localStorage, no sessionStorage). */
(function () {
  'use strict';

  var script = document.currentScript || document.querySelector('script[src*="search.js"]');
  var ROOT = script && script.src ? script.src.replace(/assets\/js\/search\.js.*$/, '') : '/';
  var SUGGESTED = ['no edge', 'forward test', 'backtest', 'walk-forward', 'FlowEdge', 'MarketCoach', 'bug', 'prop firm calculator', 'MGE Labs pricing', 'Rithmic'];
  var STOP = { the: 1, a: 1, an: 1, of: 1, and: 1, to: 1, is: 1, in: 1, for: 1, on: 1, it: 1, we: 1, do: 1, i: 1, what: 1, are: 1, how: 1, does: 1, my: 1, can: 1, which: 1 };
  var TYPES = ['Research log', 'Note', 'Tool', 'Page', 'FAQ'];
  var TYPE_CLASS = { 'Research log': 'log', 'Note': 'note', 'Tool': 'tool', 'Page': 'page', 'FAQ': 'faq' };

  /* ------------------------------------------------------------------ helpers */
  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }
  function tokens(s) { return (String(s).toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').match(/[a-z0-9]+/g) || []); }
  function qs(name) { try { return new URLSearchParams(location.search).get(name) || ''; } catch (e) { return ''; } }
  function urlFor(doc) {
    if (!doc.u) return ROOT + 'search.html?q=' + encodeURIComponent(doc.ti) + '&type=FAQ';
    return /^https?:/.test(doc.u) ? doc.u : ROOT + doc.u;
  }
  function isExternal(doc) { return /^https?:/.test(doc.u || ''); }
  function fmtDate(d) {
    if (!d) return '';
    var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(d);
    if (!m) return d;
    return ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][+m[2] - 1] + ' ' + (+m[3]) + ', ' + m[1];
  }

  // Optimal-string-alignment distance with an early exit.
  function osa(a, b, max) {
    var la = a.length, lb = b.length;
    if (Math.abs(la - lb) > max) return max + 1;
    var prev2 = null, prev = [], cur = [], i, j;
    for (j = 0; j <= lb; j++) prev[j] = j;
    for (i = 1; i <= la; i++) {
      cur = [i];
      var rowMin = i;
      for (j = 1; j <= lb; j++) {
        var cost = a.charCodeAt(i - 1) === b.charCodeAt(j - 1) ? 0 : 1;
        var v = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost);
        if (prev2 && i > 1 && j > 1 && a.charCodeAt(i - 1) === b.charCodeAt(j - 2) && a.charCodeAt(i - 2) === b.charCodeAt(j - 1)) v = Math.min(v, prev2[j - 2] + 1);
        cur[j] = v;
        if (v < rowMin) rowMin = v;
      }
      if (rowMin > max) return max + 1;
      prev2 = prev; prev = cur;
    }
    return prev[lb];
  }

  /* ------------------------------------------------------------------ engine */
  var Engine = { ready: false, failed: false, docs: [], vocab: {}, vocabList: [], types: TYPES, tools: [], waiters: [] };

  function build(data) {
    Engine.docs = data.docs;
    Engine.types = data.types || TYPES;
    Engine.tools = data.tools || [];
    var vocab = Engine.vocab;
    data.docs.forEach(function (d) {
      var fields = [[d.ti, 6], [(d.tools || []).join(' '), 5], [(d.cat || '') + ' ' + (d.w || '') + ' ' + (d.st || []).join(' '), 2], [d.s, 2.5], [d.x, 1]];
      var seen = {};
      fields.forEach(function (f) {
        var tk = tokens(f[0] || '');
        tk.forEach(function (t) {
          if (!seen[t] || seen[t] < f[1]) seen[t] = f[1];
        });
        if (f[1] >= 5) { // "walk-forward" is also found as "walkforward"
          for (var j = 0; j + 1 < tk.length; j++) {
            var jn = tk[j] + tk[j + 1];
            if (!seen[jn] || seen[jn] < f[1] * 0.9) seen[jn] = f[1] * 0.9;
          }
        }
      });
      d._tt = tokens(d.ti);
      for (var t in seen) {
        if (!vocab[t]) vocab[t] = [];
        vocab[t].push([d.id, seen[t]]);
      }
    });
    Engine.vocabList = Object.keys(vocab);
    Engine.ready = true;
    Engine.waiters.splice(0).forEach(function (fn) { fn(); });
  }

  function load(cb) {
    if (Engine.ready) return cb();
    Engine.waiters.push(cb);
    if (Engine.loading) return;
    Engine.loading = true;
    fetch(ROOT + 'search-index.json').then(function (r) {
      if (!r.ok) throw new Error('index');
      return r.json();
    }).then(build).catch(function () {
      Engine.failed = true;
      Engine.waiters.splice(0).forEach(function (fn) { fn(); });
    });
  }

  // Expand one query term to {vocabToken: quality}.
  function expand(term, isLast) {
    var out = {}, list = Engine.vocabList, i, t;
    if (Engine.vocab[term]) out[term] = 1;
    if (term.length >= 2) {
      for (i = 0; i < list.length; i++) {
        t = list[i];
        if (out[t]) continue;
        if (t.length > term.length && t.indexOf(term) === 0) out[t] = 0.85;
      }
    }
    if (term.length >= 3) {
      for (i = 0; i < list.length; i++) {
        t = list[i];
        if (out[t]) continue;
        if (t.length > term.length + 1 && t.indexOf(term) > 0) out[t] = 0.35;
      }
    }
    var d = term.length >= 8 ? 2 : term.length >= 4 ? 1 : (term.length === 3 && !Engine.vocab[term] ? 1 : 0);
    if (Engine.vocab[term] && term.length < 8) d = 0; // an exact word exists: do not add look-alikes
    if (d) {
      for (i = 0; i < list.length; i++) {
        t = list[i];
        if (out[t]) continue;
        if (term.length === 3 && t.charAt(0) !== term.charAt(0)) continue;
        if (osa(term, t, d) <= d) out[t] = 0.55;
        else if (isLast && t.length > term.length && osa(term, t.slice(0, term.length), d) <= d) out[t] = 0.4;
      }
    }
    return out;
  }

  // Returns {hits:[{doc,score}], terms:[...], matched:{token:1}, partial:bool}
  function searchOne(query) {
    var raw = tokens(query);
    var terms = raw.filter(function (t) { return !STOP[t]; });
    if (!terms.length) terms = raw;
    if (!terms.length) return { hits: [], terms: [], matched: {}, partial: false };
    var per = terms.map(function (t, i) { return expand(t, i === terms.length - 1); });
    var matched = {};
    var scores = {}; // docId -> {sum, n}
    per.forEach(function (ex, ti) {
      var best = {};
      for (var tok in ex) {
        matched[tok] = 1;
        Engine.vocab[tok].forEach(function (p) {
          var s = p[1] * ex[tok];
          if (!best[p[0]] || best[p[0]] < s) best[p[0]] = s;
        });
      }
      for (var id in best) {
        var o = scores[id] || (scores[id] = { sum: 0, n: 0 });
        o.sum += best[id]; o.n++;
      }
    });
    var phrase = terms.join(' ');
    function collect(need) {
      var hits = [];
      for (var id in scores) {
        if (scores[id].n < need) continue;
        var d = Engine.docs[id], s = scores[id].sum;
        var ttj = ' ' + d._tt.join(' ') + ' ', pp = ' ' + phrase + ' ';
        if (ttj.indexOf(pp) >= 0) s += (terms.length > 1 ? 8 : 0) + 24 / d._tt.length; // the whole phrase is in the title; shorter titles are more specific
        if (ttj.indexOf(pp) === 0) s += 4;
        hits.push({ doc: d, score: s });
      }
      return hits;
    }
    var hits = collect(terms.length), partial = false;
    if (!hits.length && terms.length > 1) { hits = collect(1); partial = true; }
    hits.sort(function (a, b) { return b.score - a.score || (b.doc.d || '').localeCompare(a.doc.d || '') || a.doc.id - b.doc.id; });
    return { hits: hits, terms: terms, matched: matched, partial: partial };
  }

  // "back test" also finds "backtest", "walk forward" also finds "walkforward".
  function search(query) {
    var res = searchOne(query);
    var raw = tokens(query).filter(function (t) { return !STOP[t]; });
    for (var i = 0; i + 1 < raw.length; i++) {
      var joined = raw[i] + raw[i + 1];
      if (!Engine.vocab[joined]) continue;
      var alt = searchOne(raw.slice(0, i).concat([joined], raw.slice(i + 2)).join(' '));
      var best = {};
      res.hits.forEach(function (h) { best[h.doc.id] = h; });
      alt.hits.forEach(function (h) { if (!best[h.doc.id] || best[h.doc.id].score < h.score) best[h.doc.id] = h; });
      res.hits = Object.keys(best).map(function (k) { return best[k]; });
      res.hits.sort(function (a, b) { return b.score - a.score || (b.doc.d || '').localeCompare(a.doc.d || '') || a.doc.id - b.doc.id; });
      for (var m in alt.matched) res.matched[m] = 1;
      res.partial = res.partial && !alt.hits.length;
    }
    return res;
  }

  /* ------------------------------------------------------------------ rendering */
  function highlightInto(node, text, matched) {
    var re = /[A-Za-z0-9]+/g, last = 0, m;
    while ((m = re.exec(text))) {
      var w = m[0].toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
      if (matched[w]) {
        if (m.index > last) node.appendChild(document.createTextNode(text.slice(last, m.index)));
        node.appendChild(el('mark', null, m[0]));
        last = m.index + m[0].length;
      }
    }
    if (last < text.length) node.appendChild(document.createTextNode(text.slice(last)));
  }

  function snippet(doc, matched) {
    var s = doc.s || '', x = doc.x || '';
    function has(t) { return tokens(t).some(function (w) { return matched[w]; }); }
    if (!has(s) && x && has(x)) {
      var re = /[A-Za-z0-9]+/g, m, at = -1;
      while ((m = re.exec(x))) { if (matched[m[0].toLowerCase()]) { at = m.index; break; } }
      if (at >= 0) {
        var from = Math.max(0, at - 70), to = Math.min(x.length, at + 170);
        if (from > 0) from = x.indexOf(' ', from) + 1 || from;
        return (from > 0 ? '… ' : '') + x.slice(from, to).trim() + (to < x.length ? ' …' : '');
      }
    }
    return s;
  }

  function resultItem(hit, matched, mode, idPrefix, idx) {
    var d = hit.doc;
    var li = el('li', 'sr-item sr-' + TYPE_CLASS[d.t]);
    li.setAttribute('role', 'presentation');
    var a = el('a', 'sr-link');
    a.setAttribute('role', 'option');
    a.id = idPrefix + idx;
    a.setAttribute('aria-selected', 'false');
    a.href = urlFor(d);
    if (isExternal(d)) { a.target = '_blank'; a.rel = 'noopener noreferrer'; }
    a.tabIndex = -1;
    var top = el('span', 'sr-top');
    top.appendChild(el('span', 'sr-type sr-type-' + TYPE_CLASS[d.t], d.t));
    var title = el('span', 'sr-title');
    highlightInto(title, d.ti, matched);
    top.appendChild(title);
    a.appendChild(top);
    var where = [d.w, fmtDate(d.d)].filter(Boolean).join(' · ');
    if (where) a.appendChild(el('span', 'sr-where', where));
    if (mode === 'full') {
      var sn = el('span', 'sr-snippet');
      highlightInto(sn, snippet(d, matched), matched);
      a.appendChild(sn);
      if (d.tools && d.tools.length) {
        var tg = el('span', 'sr-tools');
        d.tools.slice(0, 5).forEach(function (t) { tg.appendChild(el('span', 'sr-chip', t)); });
        a.appendChild(tg);
      }
    }
    li.appendChild(a);
    return li;
  }

  /* ------------------------------------------------------------------ combo (input + listbox) */
  function Combo(input, list, opts) {
    var self = this, active = -1, items = [];
    opts = opts || {};
    input.setAttribute('role', 'combobox');
    input.setAttribute('aria-autocomplete', 'list');
    input.setAttribute('aria-expanded', 'false');
    input.setAttribute('aria-controls', list.id);
    function opt(li) { return li.querySelector('a'); }
    function setActive(i) {
      if (items[active]) { opt(items[active]).setAttribute('aria-selected', 'false'); items[active].classList.remove('is-active'); }
      active = i;
      if (items[active]) {
        opt(items[active]).setAttribute('aria-selected', 'true');
        items[active].classList.add('is-active');
        input.setAttribute('aria-activedescendant', opt(items[active]).id);
        if (items[active].scrollIntoView) items[active].scrollIntoView({ block: 'nearest' });
      } else input.removeAttribute('aria-activedescendant');
    }
    function render() {
      var q = input.value.trim();
      list.textContent = '';
      items = []; active = -1;
      input.removeAttribute('aria-activedescendant');
      if (!q) {
        if (opts.showSuggested) {
          var h = el('li', 'sr-head', 'Try searching for'); h.setAttribute('role', 'presentation'); list.appendChild(h);
          SUGGESTED.forEach(function (s, i) {
            var li = el('li', 'sr-item sr-suggest'); li.setAttribute('role', 'presentation');
            var a = el('a', 'sr-link', s); a.href = ROOT + 'search.html?q=' + encodeURIComponent(s); a.tabIndex = -1;
            a.setAttribute('role', 'option'); a.id = list.id + '-s' + i; a.setAttribute('aria-selected', 'false');
            li.appendChild(a); list.appendChild(li); items.push(li);
          });
        }
        input.setAttribute('aria-expanded', items.length ? 'true' : 'false');
        list.hidden = !items.length;
        if (opts.status) opts.status('');
        return;
      }
      if (Engine.failed) {
        var f = el('li', 'sr-empty', 'Search needs the site to be served over http(s). Open the research index instead.'); f.setAttribute('role', 'presentation');
        list.appendChild(f); list.hidden = false; return;
      }
      var res = search(q);
      var max = opts.max || 8, shown = {}, n = 0;
      res.hits.forEach(function (h) {
        if (n >= max) return;
        var key = h.doc.t + '|' + h.doc.ti;
        if (shown[key]) return;
        shown[key] = 1;
        var li = resultItem(h, res.matched, 'compact', list.id + '-r', n++);
        list.appendChild(li); items.push(li);
      });
      if (!res.hits.length) {
        var e = el('li', 'sr-empty'); e.setAttribute('role', 'presentation');
        e.appendChild(document.createTextNode('No matches for “' + q + '”. Try fewer letters, one word, or a tool name. For example: '));
        ['no edge', 'forward test', 'FlowEdge'].forEach(function (sx, k) {
          if (k) e.appendChild(document.createTextNode(', '));
          var ea = el('a', null, sx); ea.href = ROOT + 'search.html?q=' + encodeURIComponent(sx); e.appendChild(ea);
        });
        e.appendChild(document.createTextNode('. Or '));
        var eb = el('a', null, 'browse all research'); eb.href = ROOT + 'research.html'; e.appendChild(eb);
        e.appendChild(document.createTextNode('.'));
        list.appendChild(e);
      } else if (res.hits.length > max || opts.alwaysAll) {
        var more = el('li', 'sr-item sr-all'); more.setAttribute('role', 'presentation');
        var ma = el('a', 'sr-link', 'See all ' + res.hits.length + ' result' + (res.hits.length === 1 ? '' : 's') + ' for “' + q + '” →');
        ma.href = ROOT + 'search.html?q=' + encodeURIComponent(q); ma.tabIndex = -1;
        ma.setAttribute('role', 'option'); ma.id = list.id + '-all'; ma.setAttribute('aria-selected', 'false');
        more.appendChild(ma); list.appendChild(more); items.push(more);
      }
      list.hidden = false;
      input.setAttribute('aria-expanded', 'true');
      if (items.length && res.hits.length) setActive(0);
      if (opts.status) opts.status(res.hits.length + (res.hits.length === 1 ? ' result' : ' results') + (res.partial ? ' (partial matches)' : ''));
    }
    self.refresh = function () { load(render); };
    input.addEventListener('input', self.refresh);
    input.addEventListener('focus', function () { if (opts.openOnFocus) self.refresh(); });
    input.addEventListener('keydown', function (e) {
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        if (list.hidden) { self.refresh(); }
        if (!items.length) return;
        e.preventDefault();
        var n = active + (e.key === 'ArrowDown' ? 1 : -1);
        if (n < 0) n = items.length - 1;
        if (n >= items.length) n = 0;
        setActive(n);
      } else if (e.key === 'Enter') {
        if (active >= 0 && items[active] && !list.hidden) {
          e.preventDefault();
          var a = items[active].querySelector('a');
          if (a) { if (a.target === '_blank') window.open(a.href, '_blank', 'noopener'); else location.href = a.href; }
        } else if (opts.enterGoes !== false && input.value.trim()) {
          e.preventDefault();
          location.href = ROOT + 'search.html?q=' + encodeURIComponent(input.value.trim());
        }
      } else if (e.key === 'Escape' && opts.closeOnEsc && !list.hidden) {
        e.preventDefault(); list.hidden = true; input.setAttribute('aria-expanded', 'false');
      }
    });
    list.addEventListener('mousemove', function (e) {
      var li = e.target.closest && e.target.closest('.sr-item');
      var i = items.indexOf(li);
      if (i >= 0 && i !== active) setActive(i);
    });
    self.close = function () { list.hidden = true; input.setAttribute('aria-expanded', 'false'); };
    self.items = function () { return items; };
  }

  /* ------------------------------------------------------------------ palette (Ctrl/Cmd+K) */
  var palette = null, lastFocus = null;
  function buildPalette() {
    var dlg = el('dialog', 'sp');
    dlg.setAttribute('aria-label', 'Search the site');
    var form = el('form', 'sp-form'); form.setAttribute('role', 'search'); form.method = 'get'; form.action = ROOT + 'search.html';
    var label = el('label', 'sp-label', 'Search research logs, notes, tools and pages'); label.htmlFor = 'sp-input';
    var row = el('div', 'sp-row');
    var input = el('input', 'sp-input'); input.type = 'search'; input.id = 'sp-input'; input.name = 'q'; input.autocomplete = 'off'; input.spellcheck = false;
    input.placeholder = 'Search: try “no edge”, “FlowEdge”, “forward test”…';
    var close = el('button', 'sp-close', 'Esc'); close.type = 'button'; close.setAttribute('aria-label', 'Esc, close search');
    row.appendChild(input); row.appendChild(close);
    var list = el('ul', 'sp-list'); list.id = 'sp-list'; list.setAttribute('role', 'listbox'); list.setAttribute('aria-label', 'Results'); list.hidden = true;
    var status = el('p', 'sp-status'); status.setAttribute('aria-live', 'polite'); status.setAttribute('role', 'status');
    var hints = el('p', 'sp-hints');
    hints.innerHTML = '<span><kbd>↑</kbd><kbd>↓</kbd> move</span><span><kbd>Enter</kbd> open</span><span><kbd>Esc</kbd> close</span><a href="' + ROOT + 'search.html">Advanced search &amp; filters</a>';
    form.appendChild(label); form.appendChild(row); form.appendChild(list); form.appendChild(status); form.appendChild(hints);
    dlg.appendChild(form);
    document.body.appendChild(dlg);
    var combo = new Combo(input, list, { max: 8, showSuggested: true, status: function (t) { status.textContent = t; } });
    input.addEventListener('keydown', function (e) { if (e.key === 'Escape') { e.preventDefault(); dlg.close(); } });
    close.addEventListener('click', function () { dlg.close(); });
    dlg.addEventListener('click', function (e) { if (e.target === dlg) dlg.close(); });
    dlg.addEventListener('close', function () {
      document.documentElement.classList.remove('sp-open');
      if (lastFocus && lastFocus.focus) lastFocus.focus();
    });
    form.addEventListener('submit', function (e) { if (!input.value.trim()) e.preventDefault(); });
    return { dlg: dlg, input: input, combo: combo };
  }
  function openPalette() {
    if (!document.createElement('dialog').showModal) { location.href = ROOT + 'search.html'; return; }
    if (!palette) palette = buildPalette();
    if (palette.dlg.open) { palette.input.focus(); palette.input.select(); return; }
    lastFocus = document.activeElement;
    document.documentElement.classList.add('sp-open');
    palette.dlg.showModal();
    palette.input.focus();
    load(function () { palette.combo.refresh(); });
  }
  document.addEventListener('keydown', function (e) {
    if ((e.ctrlKey || e.metaKey) && !e.altKey && !e.shiftKey && (e.key === 'k' || e.key === 'K')) {
      e.preventDefault();
      openPalette();
    }
  });
  document.addEventListener('click', function (e) {
    var t = e.target.closest && e.target.closest('[data-open-search]');
    if (t && !(e.metaKey || e.ctrlKey || e.shiftKey || e.button)) { e.preventDefault(); openPalette(); }
  });

  // Show the right shortcut hint for this platform.
  var isMac = /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent || '');
  Array.prototype.forEach.call(document.querySelectorAll('[data-kbd]'), function (k) { k.textContent = isMac ? '⌘K' : 'Ctrl K'; });

  /* ------------------------------------------------------------------ hero / inline box */
  Array.prototype.forEach.call(document.querySelectorAll('[data-search-box]'), function (box, n) {
    var input = box.querySelector('input[type="search"]');
    var list = box.querySelector('[role="listbox"]');
    if (!input || !list) return;
    list.id = list.id || 'sb-list-' + n;
    var status = box.querySelector('[data-status]');
    var combo = new Combo(input, list, { max: 5, closeOnEsc: true, status: function (t) { if (status) status.textContent = t; } });
    document.addEventListener('click', function (e) { if (!box.contains(e.target)) combo.close(); });
  });

  /* ------------------------------------------------------------------ search.html */
  var page = document.getElementById('sr-root');
  if (page) {
    var form = page.querySelector('form');
    var input = page.querySelector('#sr-q');
    var out = page.querySelector('#sr-results');
    var typeBox = page.querySelector('#sr-types');
    var toolBox = page.querySelector('#sr-tools');
    var sortSel = page.querySelector('#sr-sort');
    var count = page.querySelector('#sr-count');
    var sugg = page.querySelector('#sr-suggest');
    var state = { q: qs('q'), type: qs('type'), tool: qs('tool'), sort: qs('sort') || 'rel' };
    input.value = state.q;
    if (sortSel) sortSel.value = state.sort;
    page.classList.add('is-js');

    function pushState() {
      var p = [];
      if (state.q) p.push('q=' + encodeURIComponent(state.q));
      if (state.type) p.push('type=' + encodeURIComponent(state.type));
      if (state.tool) p.push('tool=' + encodeURIComponent(state.tool));
      if (state.sort && state.sort !== 'rel') p.push('sort=' + state.sort);
      try { history.replaceState(null, '', location.pathname + (p.length ? '?' + p.join('&') : '')); } catch (e) { /* file: or sandboxed */ }
    }
    function chip(label, n, pressed, on) {
      var b = el('button', 'chip'); b.type = 'button'; b.setAttribute('aria-pressed', pressed ? 'true' : 'false');
      b.appendChild(document.createTextNode(label));
      if (n != null) b.appendChild(el('span', 'chip-n', String(n)));
      b.addEventListener('click', on);
      return b;
    }
    function run() {
      document.title = (state.q ? '“' + state.q + '” · ' : '') + 'Search | MGEQuant';
      var res, base;
      if (state.q) { res = search(state.q); base = res.hits; }
      else {
        res = { matched: {}, terms: [], partial: false };
        base = Engine.docs.map(function (d) { return { doc: d, score: 0 }; });
      }
      var browse = !state.q && (state.type || state.tool);
      // counts ignore their own facet
      var byType = {}, byTool = {};
      base.forEach(function (h) {
        if (!state.tool || (h.doc.tools || []).indexOf(state.tool) >= 0) byType[h.doc.t] = (byType[h.doc.t] || 0) + 1;
        if (!state.type || h.doc.t === state.type) (h.doc.tools || []).forEach(function (t) { byTool[t] = (byTool[t] || 0) + 1; });
      });
      var hits = base.filter(function (h) {
        return (!state.type || h.doc.t === state.type) && (!state.tool || (h.doc.tools || []).indexOf(state.tool) >= 0);
      });
      if (state.sort === 'new' || (!state.q && browse)) hits.sort(function (a, b) { return (b.doc.d || '').localeCompare(a.doc.d || '') || a.doc.id - b.doc.id; });
      typeBox.textContent = '';
      typeBox.appendChild(chip('All types', Object.keys(byType).reduce(function (s, k) { return s + byType[k]; }, 0), !state.type, function () { state.type = ''; pushState(); run(); }));
      Engine.types.forEach(function (t) {
        if (!byType[t] && state.type !== t) return;
        typeBox.appendChild(chip(t, byType[t] || 0, state.type === t, function () { state.type = state.type === t ? '' : t; pushState(); run(); }));
      });
      toolBox.textContent = '';
      Engine.tools.forEach(function (t) {
        if (!byTool[t] && state.tool !== t) return;
        toolBox.appendChild(chip(t, byTool[t] || 0, state.tool === t, function () { state.tool = state.tool === t ? '' : t; pushState(); run(); }));
      });
      out.textContent = '';
      sugg.hidden = !!(state.q || browse);
      var msg;
      if (!state.q && !browse) msg = 'Type to search ' + Engine.docs.length + ' items, or pick a suggestion.';
      else msg = hits.length + (hits.length === 1 ? ' result' : ' results') + (state.q ? ' for “' + state.q + '”' : '') + (res.partial ? ' (no item has every word, so these match some of them)' : '');
      count.textContent = msg;
      if (!state.q && !browse) return;
      if (!hits.length) {
        var none = el('li', 'sr-empty'); none.appendChild(document.createTextNode('Nothing matched. Try fewer letters (partial words work), one word instead of two, or a tool name. Popular searches: '));
        SUGGESTED.slice(0, 5).forEach(function (sx, k) {
          if (k) none.appendChild(document.createTextNode(', '));
          var sa = el('a', null, sx); sa.href = ROOT + 'search.html?q=' + encodeURIComponent(sx); none.appendChild(sa);
        });
        if (state.type || state.tool) {
          none.appendChild(document.createTextNode('. A filter is on: '));
          var ca = el('a', null, 'clear filters'); ca.href = ROOT + 'search.html?q=' + encodeURIComponent(state.q); none.appendChild(ca);
        }
        none.appendChild(document.createTextNode('. Or '));
        var a1 = el('a', null, 'browse all research'); a1.href = ROOT + 'research.html'; none.appendChild(a1); none.appendChild(document.createTextNode('.'));
        out.appendChild(none); return;
      }
      hits.slice(0, 80).forEach(function (h, i) {
        var li = resultItem(h, res.matched, 'full', 'r', i);
        li.removeAttribute('role');
        var la = li.querySelector('a');
        la.removeAttribute('role'); la.removeAttribute('aria-selected'); la.removeAttribute('id');
        la.tabIndex = 0;
        out.appendChild(li);
      });
      if (hits.length > 80) out.appendChild(el('li', 'sr-empty', 'Showing the first 80. Narrow with the filters above.'));
    }

    sugg.querySelector('ul').addEventListener('click', function (e) {
      var a = e.target.closest('a'); if (!a) return;
      e.preventDefault(); state.q = a.getAttribute('data-q'); input.value = state.q; pushState(); run();
    });
    form.addEventListener('submit', function (e) { e.preventDefault(); state.q = input.value.trim(); pushState(); load(run); input.blur(); });
    var t = null;
    input.addEventListener('input', function () { clearTimeout(t); t = setTimeout(function () { state.q = input.value.trim(); pushState(); load(run); }, 120); });
    if (sortSel) sortSel.addEventListener('change', function () { state.sort = sortSel.value; pushState(); run(); });
    page.querySelector('#sr-clear').addEventListener('click', function () { state.q = state.type = state.tool = ''; state.sort = 'rel'; input.value = ''; if (sortSel) sortSel.value = 'rel'; pushState(); run(); input.focus(); });
    load(function () {
      if (Engine.failed) { count.textContent = 'Search could not load its index. If you opened this file directly, serve the folder over http(s). The research list still works.'; return; }
      run();
      if (!state.q) input.focus();
    });
  }

  /* ------------------------------------------------------------------ research.html */
  var rx = document.getElementById('rx-root');
  if (rx) {
    var items = Array.prototype.slice.call(rx.querySelectorAll('.rx-item'));
    var listEl = rx.querySelector('#rx-list');
    var panel = rx.querySelector('#rx-filters');
    var cnt = rx.querySelector('#rx-count');
    var qIn = rx.querySelector('#rx-q');
    var sort = rx.querySelector('#rx-sort');
    var groups = [
      { key: 'area', label: 'Area', attr: 'area', multi: false },
      { key: 'tool', label: 'Tool', attr: 'tools', multi: true },
      { key: 'year', label: 'Year', attr: 'year', multi: false },
      { key: 'word', label: 'Words in the entry', attr: 'status', multi: true }
    ];
    var sel = { area: {}, tool: {}, year: {}, word: {} };
    // restore from URL
    groups.forEach(function (g) { var v = qs(g.key); if (v) v.split('|').forEach(function (x) { if (x) sel[g.key][x] = 1; }); });
    qIn.value = qs('q'); if (qs('sort')) sort.value = qs('sort');
    function vals(it, g) { var v = it.getAttribute('data-' + g.attr) || ''; return v ? v.split('|') : []; }
    var facets = {};
    groups.forEach(function (g) {
      var c = {};
      items.forEach(function (it) { vals(it, g).forEach(function (v) { c[v] = (c[v] || 0) + 1; }); });
      facets[g.key] = Object.keys(c).sort(function (a, b) { return g.key === 'year' ? b.localeCompare(a) : (c[b] - c[a]) || a.localeCompare(b); }).map(function (k) { return [k, c[k]]; });
    });
    var chipEls = {};
    groups.forEach(function (g) {
      var fs = el('fieldset', 'rx-group');
      fs.appendChild(el('legend', null, g.label));
      var wrap = el('div', 'rx-chips');
      chipEls[g.key] = {};
      facets[g.key].forEach(function (f) {
        var b = el('button', 'chip'); b.type = 'button'; b.setAttribute('aria-pressed', 'false');
        b.appendChild(document.createTextNode(f[0])); b.appendChild(el('span', 'chip-n', String(f[1])));
        b.addEventListener('click', function () {
          if (sel[g.key][f[0]]) delete sel[g.key][f[0]];
          else { if (!g.multi) sel[g.key] = {}; sel[g.key][f[0]] = 1; }
          apply();
        });
        chipEls[g.key][f[0]] = b; wrap.appendChild(b);
      });
      fs.appendChild(wrap); panel.appendChild(fs);
    });
    function apply() {
      var q = tokens(qIn.value);
      var shown = 0, order = items.slice();
      var mode = sort.value;
      order.sort(function (a, b) {
        var da = a.getAttribute('data-date'), db = b.getAttribute('data-date');
        if (mode === 'old') return da.localeCompare(db);
        if (mode === 'az') return a.getAttribute('data-title').localeCompare(b.getAttribute('data-title'));
        if (mode === 'area') return a.getAttribute('data-area').localeCompare(b.getAttribute('data-area')) || db.localeCompare(da);
        return db.localeCompare(da);
      });
      order.forEach(function (it) {
        var ok = groups.every(function (g) {
          var keys = Object.keys(sel[g.key]);
          if (!keys.length) return true;
          var v = vals(it, g);
          return keys.some(function (k) { return v.indexOf(k) >= 0; });
        });
        if (ok && q.length) {
          var hay = tokens(it.textContent + ' ' + it.getAttribute('data-title'));
          ok = q.every(function (t) { return hay.some(function (w) { return w.indexOf(t) === 0 || (t.length > 3 && osa(t, w, 1) <= 1); }); });
        }
        it.hidden = !ok;
        if (ok) shown++;
        listEl.appendChild(it);
      });
      groups.forEach(function (g) { for (var k in chipEls[g.key]) chipEls[g.key][k].setAttribute('aria-pressed', sel[g.key][k] ? 'true' : 'false'); });
      cnt.textContent = 'Showing ' + shown + ' of ' + items.length + ' entries';
      var p = [];
      groups.forEach(function (g) { var k = Object.keys(sel[g.key]); if (k.length) p.push(g.key + '=' + encodeURIComponent(k.join('|'))); });
      if (qIn.value.trim()) p.push('q=' + encodeURIComponent(qIn.value.trim()));
      if (mode !== 'new') p.push('sort=' + mode);
      try { history.replaceState(null, '', location.pathname + (p.length ? '?' + p.join('&') : '')); } catch (e) { /* ignore */ }
      rx.querySelector('#rx-empty').hidden = shown > 0;
    }
    qIn.addEventListener('input', apply);
    sort.addEventListener('change', apply);
    rx.querySelector('#rx-reset').addEventListener('click', function () { sel = { area: {}, tool: {}, year: {}, word: {} }; qIn.value = ''; sort.value = 'new'; apply(); });
    rx.classList.add('is-js');
    apply();
  }
})();
