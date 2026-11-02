/* HTML PPT Studio runtime — no dependencies.
   Keys: ←/→/Space/PgUp/PgDn navigate · Home/End · F fullscreen · O overview · T next theme (Shift+T previous)
         N speaker notes · ? help · P print mode hint. Touch swipe works too. Hash (#3) deep-links a slide. */
(function () {
  'use strict';
  var deck = document.querySelector('.deck');
  var slides = Array.prototype.slice.call(document.querySelectorAll('.deck > .slide'));
  if (!deck || !slides.length) return;
  var cur = 0, W = 1920, H = 1080, overview = false;
  var THEMES = (document.body.getAttribute('data-themes') || '').split(',').filter(Boolean);
  if (!deck.getAttribute('data-transition')) deck.setAttribute('data-transition', 'fade');

  function el(cls, html) { var d = document.createElement('div'); d.className = cls; if (html) d.innerHTML = html; document.body.appendChild(d); return d; }
  var bar = el('hud-progress'), count = el('hud-count'), notes = el('hud-notes'), toast = el('hud-toast');
  var help = el('hud-help',
    '<div><b>HTML PPT Studio</b><br><kbd>←</kbd><kbd>→</kbd> / <kbd>Space</kbd> navigate<br><kbd>Home</kbd><kbd>End</kbd> first / last' +
    '<br><kbd>F</kbd> fullscreen<br><kbd>O</kbd> overview<br><kbd>T</kbd> switch theme<br><kbd>N</kbd> speaker notes<br><kbd>?</kbd> this help</div>');
  var toastTimer;
  function say(msg) { toast.textContent = msg; toast.classList.add('on'); clearTimeout(toastTimer); toastTimer = setTimeout(function () { toast.classList.remove('on'); }, 1400); }

  function fit() {
    var s = Math.min(innerWidth / W, innerHeight / H);
    slides.forEach(function (sl) { sl.style.setProperty('--s', s); });
    if (overview) layoutOverview();
  }

  // Stagger: <div data-anim-stagger="fade-up"> children inherit the animation with increasing delay.
  slides.forEach(function (sl) {
    sl.querySelectorAll('[data-anim-stagger]').forEach(function (p) {
      var kind = p.getAttribute('data-anim-stagger') || 'fade-up';
      var step = parseFloat(p.getAttribute('data-stagger') || '0.12');
      var base = parseFloat(p.style.getPropertyValue('--d')) || 0;
      Array.prototype.forEach.call(p.children, function (c, i) {
        if (!c.hasAttribute('data-anim')) c.setAttribute('data-anim', kind);
        c.style.setProperty('--d', (base + i * step).toFixed(2) + 's');
      });
    });
  });

  function countUp(sl) {
    sl.querySelectorAll('[data-count]').forEach(function (n) {
      var target = parseFloat(n.getAttribute('data-count')), dec = (n.getAttribute('data-count').split('.')[1] || '').length;
      var pre = n.getAttribute('data-prefix') || '', suf = n.getAttribute('data-suffix') || '';
      var dur = 1400, t0 = null;
      function step(ts) {
        if (t0 === null) t0 = ts;
        var p = Math.min((ts - t0) / dur, 1), e = 1 - Math.pow(1 - p, 3);
        n.textContent = pre + (target * e).toLocaleString(undefined, { minimumFractionDigits: dec, maximumFractionDigits: dec }) + suf;
        if (p < 1) requestAnimationFrame(step);
      }
      n.textContent = pre + (0).toFixed(dec) + suf;
      requestAnimationFrame(step);
    });
  }

  function go(i, silent) {
    i = Math.max(0, Math.min(slides.length - 1, i));
    cur = i;
    slides.forEach(function (sl, k) {
      sl.classList.toggle('is-active', k === i);
      sl.classList.toggle('is-prev', k < i);
      sl.classList.toggle('is-next', k > i);
    });
    bar.style.width = ((i + 1) / slides.length * 100) + '%';
    count.textContent = (i + 1) + ' / ' + slides.length;
    notes.textContent = slides[i].getAttribute('data-notes') || '';
    if (!silent) history.replaceState(null, '', '#' + (i + 1));
    if (!overview) countUp(slides[i]);
  }

  function layoutOverview() {
    var cols = Math.ceil(Math.sqrt(slides.length * 16 / 9)), gap = 24;
    var tw = (innerWidth - gap * (cols + 1)) / cols, s = tw / W;
    slides.forEach(function (sl, k) {
      var r = Math.floor(k / cols), c = k % cols;
      sl.style.left = (gap + c * (tw + gap)) + 'px';
      sl.style.top = (gap + r * (H * s + gap)) + 'px';
      sl.style.transform = 'scale(' + s + ')';
    });
  }
  function toggleOverview(on) {
    overview = on === undefined ? !overview : on;
    document.body.classList.toggle('overview', overview);
    slides.forEach(function (sl) { sl.style.left = sl.style.top = sl.style.transform = ''; });
    if (overview) layoutOverview(); else fit();
  }
  deck.addEventListener('click', function (e) {
    if (!overview) return;
    var sl = e.target.closest('.slide'); if (!sl) return;
    go(slides.indexOf(sl)); toggleOverview(false);
  });

  function setTheme(name) {
    document.body.setAttribute('data-theme', name);
    try { localStorage.setItem('ppt-theme', name); } catch (e) {}
    say('Theme: ' + name);
  }
  function cycleTheme(dir) {
    if (!THEMES.length) return;
    var k = THEMES.indexOf(document.body.getAttribute('data-theme'));
    setTheme(THEMES[(k + dir + THEMES.length) % THEMES.length]);
  }

  document.addEventListener('keydown', function (e) {
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    var k = e.key;
    if (k === 'ArrowRight' || k === 'ArrowDown' || k === 'PageDown' || k === ' ' || k === 'Enter') { e.preventDefault(); go(cur + 1); }
    else if (k === 'ArrowLeft' || k === 'ArrowUp' || k === 'PageUp' || k === 'Backspace') { e.preventDefault(); go(cur - 1); }
    else if (k === 'Home') go(0);
    else if (k === 'End') go(slides.length - 1);
    else if (k === 'f' || k === 'F') { document.fullscreenElement ? document.exitFullscreen() : document.documentElement.requestFullscreen && document.documentElement.requestFullscreen(); }
    else if (k === 'o' || k === 'O' || k === 'Escape') { if (k === 'Escape' && !overview) { document.body.classList.remove('show-help'); return; } toggleOverview(); }
    else if (k === 't') cycleTheme(1);
    else if (k === 'T') cycleTheme(-1);
    else if (k === 'n' || k === 'N') document.body.classList.toggle('show-notes');
    else if (k === '?') document.body.classList.toggle('show-help');
  });
  var x0 = null;
  document.addEventListener('touchstart', function (e) { x0 = e.touches[0].clientX; }, { passive: true });
  document.addEventListener('touchend', function (e) {
    if (x0 === null || overview) return;
    var dx = e.changedTouches[0].clientX - x0; x0 = null;
    if (Math.abs(dx) > 50) go(cur + (dx < 0 ? 1 : -1));
  });
  addEventListener('resize', fit);
  addEventListener('hashchange', function () { var n = parseInt(location.hash.slice(1), 10); if (n) go(n - 1, true); });

  try { var saved = localStorage.getItem('ppt-theme'); if (saved && THEMES.indexOf(saved) > -1 && !document.body.hasAttribute('data-theme-locked')) document.body.setAttribute('data-theme', saved); } catch (e) {}
  fit();
  var start = parseInt(location.hash.slice(1), 10);
  go(start ? start - 1 : 0, true);
  window.PPT = { go: go, next: function () { go(cur + 1); }, prev: function () { go(cur - 1); }, setTheme: setTheme, overview: toggleOverview };
})();
