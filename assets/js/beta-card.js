/* MGE Labs beta: slide-in card (all pages) + 3-tap "Is it for you?" (Labs page #beta).
   No tracking, no cookies: the only thing kept is the visitor's own "closed" choice in their browser. */
(function () {
  var KEY = 'mge_beta_card_closed_v1';
  var ADDRESS = 'support@mgequant.com';
  var css = [
    '.mbc{position:fixed;right:18px;bottom:18px;z-index:9000;width:min(380px,calc(100vw - 36px));background:#1a1d22;color:#eceff3;border:1px solid #2a2e35;border-radius:14px;padding:18px 18px 16px;box-shadow:0 24px 50px -20px rgba(0,0,0,.75);font:16px/1.5 system-ui,Segoe UI,Arial,sans-serif;transform:translateY(130%);opacity:0;transition:transform .5s cubic-bezier(.2,.8,.2,1),opacity .5s}',
    '.mbc.on{transform:none;opacity:1}',
    '.mbc-top{display:flex;justify-content:space-between;font-size:.72rem;letter-spacing:.12em;font-weight:700;padding-right:22px}',
    '.mbc-top b{color:#c9a25e;font-weight:700}.mbc-top span{color:#a3abb7}',
    '.mbc h3{font-size:1.15rem;line-height:1.3;margin:.55em 0 .35em;color:#eceff3}',
    '.mbc p{margin:0 0 .9em;color:#a3abb7;font-size:.94rem}',
    '.mbc-cta{display:inline-block;font-weight:700;border-radius:9px;padding:10px 16px;background:#c9a25e;color:#1b1408 !important;text-decoration:none}',
    '.mbc-cta:hover,.mbc-cta:focus{background:#d8b373}',
    '.mbc-later{font:inherit;background:none;border:0;color:#a3abb7;margin-left:10px;cursor:pointer;text-decoration:underline}',
    '.mbc-x{position:absolute;top:10px;right:12px;background:none;border:0;color:#a3abb7;font-size:22px;cursor:pointer;line-height:1}',
    '.mbc-fine{font-size:.76rem !important;margin:.8em 0 0 !important}',
    '@media (max-width:520px){.mbc{right:10px;left:10px;bottom:10px;width:auto}}',
    '@media (prefers-reduced-motion:reduce){.mbc{transition:none}}',
    '.mbq{margin-top:18px;border:1px solid #2a2e35;border-radius:14px;padding:18px;background:rgba(201,162,94,.06)}',
    '.mbq-k{font-size:.72rem;letter-spacing:.12em;font-weight:700;color:#c9a25e}',
    '.mbq h4{margin:.3em 0 .2em;font-size:1.1rem}',
    '.mbq-steps{display:flex;gap:6px;margin:10px 0 14px}.mbq-steps i{flex:1;height:5px;border-radius:3px;background:#2a2e35}.mbq-steps i.on{background:#c9a25e}',
    '.mbq-q{font-weight:700;margin-bottom:10px}.mbq-o{display:flex;flex-wrap:wrap;gap:8px}',
    '.mbq-o button{font:inherit;border:1px solid #2a2e35;background:transparent;color:inherit;border-radius:10px;padding:9px 14px;cursor:pointer}',
    '.mbq-o button:hover,.mbq-o button:focus{border-color:#c9a25e}',
    '.mbq-fit{color:#c9a25e;font-weight:800;margin:0 0 .3em}',
    '.mbq-go{display:inline-block;font-weight:700;border-radius:9px;padding:10px 16px;background:#c9a25e;color:#1b1408 !important;text-decoration:none;margin-right:10px}',
    '.mbq-again{font:inherit;background:none;border:0;color:inherit;opacity:.75;cursor:pointer;text-decoration:underline}'
  ].join('\n');
  var st = document.createElement('style'); st.textContent = css; document.head.appendChild(st);

  function closed() { try { return localStorage.getItem(KEY) === '1'; } catch (e) { return false; } }
  function remember() { try { localStorage.setItem(KEY, '1'); } catch (e) {} }

  /* ---- 3-tap quiz on the Labs page ---- */
  var host = document.getElementById('beta-quiz');
  if (host) {
    var Q = [
      { q: 'Do you trade on NinjaTrader 8 on Windows?', o: ['Yes', 'Not yet'] },
      { q: 'What do you trade?', o: ['Futures', 'Prop-firm accounts', 'Both'] },
      { q: 'Which accounts?', o: ['Own account', 'Prop-firm', 'Sim only'] }
    ];
    var A = [], i = 0;
    host.innerHTML = '<div class="mbq"><span class="mbq-k">30 DAYS FREE &middot; NO CARD</span><h4>Is MGE Labs for you? Three taps.</h4>' +
      '<div class="mbq-steps"><i class="on"></i><i></i><i></i></div><div class="mbq-body" aria-live="polite"></div></div>';
    var body = host.querySelector('.mbq-body'), bars = host.querySelectorAll('.mbq-steps i');
    function setBars() { for (var k = 0; k < bars.length; k++) bars[k].className = k <= Math.min(i, 2) ? 'on' : ''; }
    function draw() {
      setBars();
      if (i >= Q.length) return done();
      body.innerHTML = '<div class="mbq-q">' + Q[i].q + '</div><div class="mbq-o">' +
        Q[i].o.map(function (o) { return '<button type="button">' + o + '</button>'; }).join('') + '</div>';
      var bs = body.querySelectorAll('button');
      for (var k = 0; k < bs.length; k++) bs[k].addEventListener('click', function (e) { A.push(e.currentTarget.textContent); i++; draw(); });
    }
    function done() {
      if (A[0] === 'Yes') {
        var text = 'Hi MGEQuant,\n\nI would like to test MGE Labs.\nNinjaTrader 8 on Windows: ' + A[0] + '\nI trade: ' + A[1] +
          '\nAccounts: ' + A[2] + '\n\n(I will not add account names, numbers or screenshots.)';
        body.innerHTML = '<p class="mbq-fit">Looks like a fit.</p><p>30 days free, no card. Your answers are already in the e-mail; just press send. If we invite you, we reply with your sign-up link.</p>' +
          '<a class="mbq-go" href="mailto:' + ADDRESS + '?subject=beta&body=' + encodeURIComponent(text) + '">Open my e-mail to join</a>' +
          '<button type="button" class="mbq-again">Start over</button>';
      } else {
        body.innerHTML = '<p><b>MGE Labs runs inside NinjaTrader 8 on Windows.</b> When you are set up, you are welcome to come back.</p>' +
          '<button type="button" class="mbq-again">Start over</button>';
      }
      body.querySelector('.mbq-again').addEventListener('click', function () { A = []; i = 0; draw(); });
    }
    draw();
  }

  /* ---- slide-in card on every page ---- */
  var force = /[?&]betacard=1/.test(location.search);
  if (closed() && !force) return;
  var onLabs = /labs(\.html)?$/.test(location.pathname.replace(/\/$/, ''));
  var card = document.createElement('div');
  card.className = 'mbc'; card.setAttribute('role', 'dialog'); card.setAttribute('aria-label', 'MGE Labs beta program');
  card.innerHTML = '<button type="button" class="mbc-x" aria-label="Close">&times;</button>' +
    '<div class="mbc-top"><b>MGE LABS</b><span>BETA PROGRAM</span></div>' +
    '<h3>A better way to understand your trading workflow.</h3>' +
    '<p>We\'re inviting NinjaTrader 8 and prop firm traders to help us develop MGE Labs. 30 days free, no card.</p>' +
    '<a class="mbc-cta" href="' + (onLabs ? '#beta' : '/labs.html#beta') + '">Explore Beta Access &rarr;</a>' +
    '<button type="button" class="mbc-later">Not now</button>' +
    '<p class="mbc-fine">Software only. No signals, no investment advice.</p>';
  document.body.appendChild(card);
  function hide() { card.classList.remove('on'); remember(); }
  card.querySelector('.mbc-x').addEventListener('click', hide);
  card.querySelector('.mbc-later').addEventListener('click', hide);
  card.querySelector('.mbc-cta').addEventListener('click', function () { remember(); card.classList.remove('on'); });
  var shown = false;
  function maybe() {
    if (shown) return;
    var h = document.documentElement.scrollHeight - window.innerHeight;
    if (force || h <= 0 || window.scrollY / h >= 0.33) {
      shown = true; window.removeEventListener('scroll', maybe);
      setTimeout(function () { card.classList.add('on'); }, force ? 300 : 0);
    }
  }
  window.addEventListener('scroll', maybe, { passive: true });
  maybe();
})();
