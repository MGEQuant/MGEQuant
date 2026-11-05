/* MGEQuant option H: clickable pipeline + tool filters (from option C). Built only from text already on the page. No storage, no network. */
(function () {
  'use strict';
  function $(s, r) { return (r || document).querySelector(s); }
  function $$(s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); }
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  function key(s) { return s.toLowerCase().replace(/[^a-z0-9]/g, ''); }

  /* ------------------------------------------------------ 2. pipeline explorer */
  var STAGES = ['Idea', 'Hypothesis', 'Prototype', 'Backtest', 'Forward test', 'Break / refine', 'Document'];
  var pipe = $('#pipe-ex'), out = $('#pipe-panel');
  if (pipe && out) {
    // Captions the site already prints under each tool card, matched to the status rows by name.
    var caps = {};
    $$('#gallery figure').forEach(function (f) {
      var b = $('figcaption b', f); if (!b) return;
      var fired = $('figcaption .fired', f), c = $('figcaption', f).cloneNode(true);
      $$('.fired, b', c).forEach(function (n) { n.remove(); });
      caps[key(b.textContent)] = { tag: fired ? fired.textContent.replace(/^[●\s]+/, '') : '', text: c.textContent.trim() };
    });
    var rows = $$('#status .stages li[data-stage]').map(function (li) {
      var a = $('a', li), lbl = $('.lbl', li);
      return { stage: +li.getAttribute('data-stage'), name: a.textContent, href: a.getAttribute('href'), label: lbl.textContent.replace(/^\d+\s*/, ''), li: li, cap: caps[key(a.textContent)] };
    });
    var btns = [];
    $$('li > a', pipe).forEach(function (a, i) {
      var n = rows.filter(function (r) { return r.stage === i + 1; }).length;
      var b = document.createElement('button');
      b.type = 'button'; b.setAttribute('aria-pressed', 'false'); b.setAttribute('aria-controls', 'pipe-panel'); b.setAttribute('data-stage', i + 1);
      b.innerHTML = esc(STAGES[i]) + (n ? '<span class="cnt">' + n + (n === 1 ? ' tool' : ' tools') + '</span>' : '');
      a.parentNode.replaceChild(b, a);
      btns.push(b);
      b.addEventListener('click', function () { show(i + 1, true); });
      b.addEventListener('keydown', function (e) {
        var t = -1;
        if (e.key === 'ArrowRight') t = (i + 1) % 7; else if (e.key === 'ArrowLeft') t = (i + 6) % 7;
        if (t >= 0) { e.preventDefault(); btns[t].focus(); }
      });
    });
    function show(n, fromClick) {
      var same = btns[n - 1].getAttribute('aria-pressed') === 'true' && fromClick;
      btns.forEach(function (b, i) { b.setAttribute('aria-pressed', 'false'); b.parentNode.classList.remove('is-on'); });
      rows.forEach(function (r) { r.li.classList.remove('is-hl'); });
      if (same) { out.hidden = true; return; }
      btns[n - 1].setAttribute('aria-pressed', 'true'); btns[n - 1].parentNode.classList.add('is-on');
      var here = rows.filter(function (r) { return r.stage === n; });
      here.forEach(function (r) { r.li.classList.add('is-hl'); });
      var h = '<h3>Stage ' + n + ': ' + esc(STAGES[n - 1]) + '</h3>';
      if (here.length) {
        h += '<p class="pp-lead">' + here.length + (here.length === 1 ? ' tool or idea is' : ' tools or ideas are') + ' at this stage on the research status board. This shows how far each idea has got, not how well it did. It is not a result.</p><ul class="pp-list">';
        here.forEach(function (r) {
          h += '<li class="pp-item"><span class="pp-name"><a href="' + esc(r.href) + '">' + esc(r.name) + '</a></span><span class="pp-status">' + esc(r.label) + '</span>';
          if (r.cap) h += '<p class="pp-cap"><b>' + esc(r.cap.tag) + '.</b> ' + esc(r.cap.text) + '</p>';
          h += '<a class="sec-link pp-more" href="' + esc(r.href) + '">Read the write-up &rarr;</a></li>';
        });
        h += '</ul>';
      } else {
        h += '<p class="pp-empty">Nothing on the research status board sits at this stage right now. Most ideas don’t survive the pipeline; that is the point of it. <a href="DevelopmentLogs/">Read the write-ups &rarr;</a></p>';
      }
      out.innerHTML = h; out.hidden = false;
      if (fromClick && history.replaceState) history.replaceState(null, '', '#stage-' + n);
    }
    function fromHash() {
      var m = /^#stage-([1-7])$/.exec(location.hash);
      if (!m) return;
      show(+m[1], false);
      var sec = document.getElementById('pipeline'); // there is no element with id "stage-N", so scroll to the pipeline ourselves
      if (sec && sec.scrollIntoView) sec.scrollIntoView({ block: 'start' });
    }
    fromHash();
    window.addEventListener('hashchange', fromHash);
  }

  /* ---------------------------------------------------------- 3. tool filters */
  var bar = $('#tool-filter'), gal = $('#gallery');
  if (bar && gal) {
    var figs = $$('figure[data-tags]', gal);
    var CH = [['', 'All'], ['indicator', 'Indicator'], ['strategy', 'Strategy'], ['forward', 'Forward test'], ['noedge', 'No edge found']];
    var note = document.createElement('p'); note.className = 'tool-status'; note.setAttribute('aria-live', 'polite');
    bar.parentNode.insertBefore(note, gal);
    CH.forEach(function (c) {
      var n = c[0] ? figs.filter(function (f) { return f.getAttribute('data-tags').split(' ').indexOf(c[0]) >= 0; }).length : figs.length;
      if (c[0] && !n) return;
      var b = document.createElement('button');
      b.type = 'button'; b.setAttribute('aria-pressed', c[0] === '' ? 'true' : 'false');
      b.innerHTML = esc(c[1]) + '<span class="tf-count">(' + n + ')</span>';
      b.addEventListener('click', function () {
        $$('button', bar).forEach(function (x) { x.setAttribute('aria-pressed', x === b ? 'true' : 'false'); });
        var shown = 0;
        figs.forEach(function (f) { var on = !c[0] || f.getAttribute('data-tags').split(' ').indexOf(c[0]) >= 0; f.hidden = !on; if (on) shown++; });
        gal.scrollLeft = 0;
        note.textContent = c[0] ? 'Showing ' + shown + ' of ' + figs.length + ' tool cards: ' + c[1] + '.' : '';
      });
      bar.appendChild(b);
    });
    bar.hidden = false;
  }
})();

