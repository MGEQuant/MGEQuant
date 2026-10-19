/* ======================================================================
   MGEQuant · assets/js/site.js
   Scroll reveals only. Sections already on screen at load are never hidden;
   sections further down fade in as they scroll into view. Without this
   script (or with reduced motion) everything simply shows. No dependencies.
   ====================================================================== */

(function () {
  'use strict';
  if (!('IntersectionObserver' in window)) return;
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

  var fold = window.innerHeight || document.documentElement.clientHeight;
  var pending = [];
  document.querySelectorAll('.reveal').forEach(function (el) {
    if (el.getBoundingClientRect().top > fold) { el.classList.add('reveal-pending'); pending.push(el); }
  });
  if (!pending.length) return;

  var io = new IntersectionObserver(function (entries) {
    entries.forEach(function (entry) {
      if (entry.isIntersecting) { entry.target.classList.remove('reveal-pending'); io.unobserve(entry.target); }
    });
  }, { rootMargin: '0% 0% -10% 0%', threshold: 0.05 });
  pending.forEach(function (el) { io.observe(el); });

  // Safety net: nothing stays hidden (printing, odd browsers, jump links).
  setTimeout(function () { pending.forEach(function (el) { el.classList.remove('reveal-pending'); }); }, 6000);
})();
