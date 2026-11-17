(function () {
  var box = document.querySelector('.beta-cta');
  if (!box) return;
  var ADDRESS = 'support@mgequant.com';
  var QUESTIONS = [
    '1. Windows and NinjaTrader 8 versions:',
    '2. What I trade:',
    '3. About how many trades a week:',
    '4. Own account, prop-firm account or Sim (please do not send account names, numbers or screenshots):',
    '5. One PC or more:'
  ].join('\n');
  var note = box.querySelector('.beta-copied');
  function say(msg) { if (note) { note.textContent = msg; window.setTimeout(function () { note.textContent = ''; }, 3000); } }
  function copy(text) {
    if (navigator.clipboard && window.isSecureContext) {
      return navigator.clipboard.writeText(text).then(function () { say('Copied'); }, function () { fallback(text); });
    }
    fallback(text);
  }
  function fallback(text) {
    var ta = document.createElement('textarea');
    ta.value = text; ta.setAttribute('readonly', ''); ta.style.position = 'fixed'; ta.style.opacity = '0';
    document.body.appendChild(ta); ta.select();
    var ok = false;
    try { ok = document.execCommand('copy'); } catch (e) {}
    document.body.removeChild(ta);
    say(ok ? 'Copied' : 'Press Ctrl+C to copy the text shown above');
  }
  box.addEventListener('click', function (e) {
    var b = e.target.closest ? e.target.closest('[data-copy]') : null;
    if (!b) return;
    copy(b.getAttribute('data-copy') === 'address' ? ADDRESS : QUESTIONS);
  });
})();
