/* MGEQuant · Option A · assets/js/hero-bars.js
   "Read a chart bar by bar": 16 SAMPLE bars (not market data). Step with the buttons, the arrow keys,
   or tap a bar. "Play" steps through automatically (never starts by itself, and is off under reduced motion). */
(function () {
  'use strict';
  var root = document.getElementById('hx'); if (!root) return;
  var svg = root.querySelector('.hx-svg'), box = root.querySelector('.hx-explain'), counter = root.querySelector('.hx-counter'), playBtn = root.querySelector('[data-a="play"]');
  var B = [[100,104,98,102],[102,106,101,105],[105,107,103,104],[104,106,104,105],[105,105.5,103.5,104],[104,108,102,107],[107,109,106,108],[108,108.5,106.5,107],
           [107,107.5,104.5,105],[105,106,104,104.5],[104.5,105.5,104.2,105.2],[105.2,108,105,107.8],[107.8,109.5,107,109],[109,110,106.5,107],[107,108,106,106.5],[106.5,108.5,106.2,108]];
  var N = B.length, W = 640, H = 330, padL = 12, padR = 12, top = 30, bottom = 22, lo = 96, hi = 112;
  var step = (W - padL - padR) / N, bw = step * 0.5;
  var COL = { '1': '#f2c14e', '2U': '#34d399', '2D': '#f87171', '3': '#4da3ff' };
  var WHY = { '1': 'Inside bar: it stayed inside the previous bar’s range.',
              '2U': 'It went above the previous bar’s high, but not below its low.',
              '2D': 'It went below the previous bar’s low, but not above its high.',
              '3': 'It went above the previous high and below the previous low.' };
  var sel = 1, nums = true, timer = null;
  function y(v) { return top + (hi - v) * (H - top - bottom) / (hi - lo); }
  function x(i) { return padL + step * i + step / 2; }
  function kind(i) { if (i < 1) return null; var p = B[i - 1], b = B[i], up = b[1] > p[1], dn = b[2] < p[2]; return up && dn ? '3' : up ? '2U' : dn ? '2D' : '1'; }
  function f(v) { return v.toFixed(1); }
  function draw() {
    var s = '';
    for (var g = 0; g < 4; g++) { var gy = top + g * (H - top - bottom) / 3; s += '<line x1="0" x2="' + W + '" y1="' + gy + '" y2="' + gy + '" stroke="#ffffff" stroke-opacity="0.05"/>'; }
    if (sel >= 1) {
      var p = B[sel - 1];
      s += '<rect x="' + (x(sel) - step / 2) + '" y="0" width="' + step + '" height="' + H + '" fill="#ffffff" fill-opacity="0.07"/>';
      s += '<line x1="' + x(sel - 1) + '" x2="' + (x(sel) + step) + '" y1="' + y(p[1]) + '" y2="' + y(p[1]) + '" stroke="#9aa0ab" stroke-dasharray="4 3"/><text x="' + (W - 8) + '" y="' + (y(p[1]) - 4) + '" text-anchor="end" font-size="12" fill="#d3d8e2" stroke="#090b0f" stroke-width="3" paint-order="stroke">previous high</text>';
      s += '<line x1="' + x(sel - 1) + '" x2="' + (x(sel) + step) + '" y1="' + y(p[2]) + '" y2="' + y(p[2]) + '" stroke="#9aa0ab" stroke-dasharray="4 3"/><text x="' + (W - 8) + '" y="' + (y(p[2]) + 14) + '" text-anchor="end" font-size="12" fill="#d3d8e2" stroke="#090b0f" stroke-width="3" paint-order="stroke">previous low</text>';
    }
    for (var i = 0; i < N; i++) {
      var b = B[i], c = b[3] >= b[0] ? '#34d399' : '#f87171', k = kind(i), yt = y(Math.max(b[0], b[3])), yb = y(Math.min(b[0], b[3]));
      s += '<line x1="' + x(i) + '" x2="' + x(i) + '" y1="' + y(b[1]) + '" y2="' + y(b[2]) + '" stroke="' + c + '" stroke-width="1.6"/>';
      s += '<rect x="' + (x(i) - bw / 2) + '" y="' + yt + '" width="' + bw + '" height="' + Math.max(2, yb - yt) + '" fill="' + c + '" rx="1.5"' + (i === sel ? ' stroke="#ffffff" stroke-width="1.6"' : '') + '/>';
      if (nums && k) s += '<text x="' + x(i) + '" y="' + (k === '2D' ? y(b[2]) + 15 : y(b[1]) - 6) + '" text-anchor="middle" font-size="13" font-weight="700" fill="' + COL[k] + '">' + k + '</text>';
      s += '<rect data-i="' + i + '" x="' + (x(i) - step / 2) + '" y="0" width="' + step + '" height="' + H + '" fill="transparent"/>';
    }
    svg.innerHTML = s;
    var k2 = kind(sel), b2 = B[sel];
    counter.textContent = 'Bar ' + (sel + 1) + ' of ' + N;
    if (!k2) { box.innerHTML = '<b>Bar 1</b> has nothing before it to compare with. Press next, or tap any later bar.'; return; }
    var p2 = B[sel - 1];
    box.innerHTML = '<span class="hx-chip" style="background:' + COL[k2] + '">' + k2 + '</span><b>Bar ' + (sel + 1) + '.</b> ' + WHY[k2] +
      '<span class="hx-dim">High ' + f(b2[1]) + ' vs ' + f(p2[1]) + ' before: ' + (b2[1] > p2[1] ? 'broke it' : 'did not break it') + '. Low ' + f(b2[2]) + ' vs ' + f(p2[2]) + ' before: ' + (b2[2] < p2[2] ? 'broke it' : 'did not break it') + '.</span>';
  }
  function stop() { if (timer) { clearInterval(timer); timer = null; } playBtn.textContent = '▶ Play'; playBtn.setAttribute('aria-pressed', 'false'); }
  function go(n) { stop(); sel = Math.max(0, Math.min(N - 1, n)); draw(); }
  function play() {
    if (timer) { stop(); return; }
    if (sel >= N - 1) sel = 0; draw();
    playBtn.textContent = '❚❚ Pause'; playBtn.setAttribute('aria-pressed', 'true');
    timer = setInterval(function () { if (sel >= N - 1) { stop(); return; } sel++; draw(); }, 1100);
  }
  svg.addEventListener('click', function (e) { var t = e.target.closest('[data-i]'); if (t) go(+t.getAttribute('data-i')); });
  svg.addEventListener('mouseover', function (e) { var t = e.target.closest('[data-i]'); if (t && !timer) { var i = +t.getAttribute('data-i'); if (i !== sel) { sel = i; draw(); } } });
  svg.addEventListener('keydown', function (e) { if (e.key === 'ArrowRight') { go(sel + 1); e.preventDefault(); } if (e.key === 'ArrowLeft') { go(sel - 1); e.preventDefault(); } });
  root.querySelector('.hx-controls').addEventListener('click', function (e) {
    var el = e.target.closest('[data-a]'); if (!el) return; var a = el.getAttribute('data-a');
    if (a === 'next') go(sel + 1); else if (a === 'prev') go(sel - 1); else if (a === 'play') play();
    else if (a === 'nums') { nums = el.checked; draw(); }
  });
  draw();
})();
