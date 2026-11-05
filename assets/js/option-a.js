/* MGEQuant · Option A · assets/js/option-a.js
   Search dialog (Ctrl/Cmd+K), glossary tooltips, ticker pause. Vanilla JS, no storage, no network
   except one same-site fetch of search-index.json when search is opened. */
(function () {
  'use strict';
  var script = document.currentScript;
  var INDEX_URL = script ? new URL('../../search-index.json', script.src).href : '/search-index.json';
  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ---------------- ticker pause ---------------- */
  var ticker = document.querySelector('.ticker');
  if (ticker) {
    var wrap = ticker.parentNode;
    if (!wrap.classList.contains('ticker-wrap')) { wrap = document.createElement('div'); wrap.className = 'ticker-wrap'; ticker.parentNode.insertBefore(wrap, ticker); wrap.appendChild(ticker); }
    var pb = document.createElement('button');
    pb.type = 'button'; pb.className = 'ticker-pause'; pb.setAttribute('aria-pressed', 'false');
    pb.textContent = 'Pause banner';
    function setPaused(p) { wrap.classList.toggle('paused', p); pb.setAttribute('aria-pressed', p ? 'true' : 'false'); pb.textContent = p ? 'Play banner' : 'Pause banner'; }
    pb.addEventListener('click', function () { setPaused(!wrap.classList.contains('paused')); });
    wrap.appendChild(pb);
    if (reduce) setPaused(true);
  }

  /* ---------------- glossary tooltips ---------------- */
  var GL = {
    r: ['R', 'One unit of risk: the amount you are prepared to lose on a single trade. A trade that makes twice that amount is +2R; one that loses it is −1R.'],
    edge: ['Edge', 'A repeatable advantage: a rule that does better than chance would, after costs. Most ideas turn out to have none, which is why we test them.'],
    backtest: ['Backtest', 'Running a fixed set of rules over old data to see what they would have done. It tests one version of a rule, and passing it is not proof.'],
    oos: ['Out-of-sample', 'Data the rules never saw while they were being built. A result that only works on the data it was tuned on is usually luck.'],
    forward: ['Forward test', 'Running the rules on new data as it arrives, on a simulation account, to find out whether the backtest holds up.'],
    control: ['Random-entry control', 'The same test with entries taken at random, using the same stops, targets and timing. If the rule cannot beat it, it has shown nothing beyond chance.']
  };
  var pop = null, popFor = null, popHow = '';
  function closePop() { if (pop) { pop.remove(); pop = null; } if (popFor) { popFor.removeAttribute('aria-describedby'); popFor = null; } }
  function openPop(a) {
    var d = GL[a.getAttribute('data-term')]; if (!d) return;
    if (popFor === a) return;
    closePop();
    pop = document.createElement('div'); pop.className = 'gl-pop'; pop.id = 'gl-pop'; pop.setAttribute('role', 'tooltip');
    pop.innerHTML = '<b></b><span></span> <a href="#g-' + a.getAttribute('data-term') + '">In the glossary</a>';
    pop.firstChild.textContent = d[0]; pop.children[1].textContent = d[1];
    document.body.appendChild(pop);
    var r = a.getBoundingClientRect(), pw = pop.offsetWidth;
    var left = Math.max(12 + window.scrollX, Math.min(window.scrollX + r.left, window.scrollX + document.documentElement.clientWidth - pw - 12));
    pop.style.left = left + 'px'; pop.style.top = (window.scrollY + r.bottom + 8) + 'px';
    a.setAttribute('aria-describedby', 'gl-pop'); popFor = a;
  }
  document.addEventListener('click', function (e) {
    var a = e.target.closest && e.target.closest('a.gl');
    if (a) { e.preventDefault(); if (popFor === a && popHow === 'click') closePop(); else { openPop(a); popHow = 'click'; } return; }
    if (pop && !e.target.closest('.gl-pop')) closePop();
  });
  document.addEventListener('mouseover', function (e) { var a = e.target.closest && e.target.closest('a.gl'); if (a && window.matchMedia('(hover: hover)').matches && popFor !== a) { openPop(a); popHow = 'hover'; } });
  document.addEventListener('mouseout', function (e) { var a = e.target.closest && e.target.closest('a.gl'); if (a && popFor === a && popHow !== 'click' && !(e.relatedTarget && e.relatedTarget.closest && e.relatedTarget.closest('.gl-pop'))) closePop(); });
  document.addEventListener('focusin', function (e) { var a = e.target.closest && e.target.closest('a.gl'); if (a) openPop(a); else if (pop && !e.target.closest('.gl-pop')) closePop(); });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && pop) { closePop(); } });
  window.addEventListener('scroll', function () { if (pop && popFor) { var r = popFor.getBoundingClientRect(); if (r.bottom < 0 || r.top > window.innerHeight) closePop(); } }, { passive: true });

})();
