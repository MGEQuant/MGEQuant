/* MGEQuant · option H2 · assets/js/h2.js
   Phone menu button and chat-button behaviour. No storage, no network. Without JavaScript the full menu stays visible. */
(function () {
  'use strict';
  var nav = document.querySelector('nav.site-nav');
  var links = nav && nav.querySelector('.links');
  if (nav && links) {
    links.id = links.id || 'site-links';
    // phone-only copies of the two small MGE Labs strip links
    var strip = document.querySelector('.labs-strip');
    if (strip) {
      Array.prototype.forEach.call(strip.querySelectorAll('a.labs-strip-notes'), function (a) {
        var c = a.cloneNode(true);
        c.className = 'menu-only-phone';
        links.appendChild(c);
      });
    }
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'nav-menu-btn';
    btn.setAttribute('aria-expanded', 'false');
    btn.setAttribute('aria-controls', links.id);
    btn.innerHTML = '<span class="nm-ic" aria-hidden="true"></span><span class="nm-t">Menu</span>';
    var tt = nav.querySelector('.theme-toggle');
    nav.insertBefore(btn, tt ? tt.nextSibling : links);
    document.documentElement.classList.add('nav-js');
    function setOpen(o) {
      links.classList.toggle('is-open', o);
      btn.setAttribute('aria-expanded', o ? 'true' : 'false');
    }
    btn.addEventListener('click', function () { setOpen(btn.getAttribute('aria-expanded') !== 'true'); });
    nav.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && btn.getAttribute('aria-expanded') === 'true') { setOpen(false); btn.focus(); }
    });
    links.addEventListener('click', function (e) { if (e.target.closest('a')) setOpen(false); });
  }

  // On phones the help-chat button fades out while the page is scrolling, so it does not sit on top of the text being read.
  var phone = window.matchMedia && window.matchMedia('(max-width: 640px)');
  var timer = null;
  window.addEventListener('scroll', function () {
    if (!phone || !phone.matches) return;
    var b = document.querySelector('.mge-chat-btn');
    if (!b) return;
    b.classList.add('is-away');
    clearTimeout(timer);
    timer = setTimeout(function () { b.classList.remove('is-away'); }, 900);
  }, { passive: true });
})();
