/* Minimal, safe Markdown renderer (no raw HTML passthrough).
   Supports: frontmatter skip, ATX headings (with slug ids), fenced code, $$ math blocks,
   blockquotes, nested lists, GFM tables, hr, images, links, autolinks, **bold**, *em*,
   ~~del~~, `code`, $inline math$, [[wikilinks]], [E1] evidence markers.
   opts.link(href) -> rewritten href; opts.img(src) -> url; opts.wiki(id,label) -> html; opts.ev(id) -> html */
(function () {
  const esc = s => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const slug = s => String(s).trim().toLowerCase().replace(/[\s]+/g, '-').replace(/[^\p{L}\p{N}\-_]/gu, '');

  function inline(src, o) {
    const stash = [];
    const keep = h => '\u0000' + (stash.push(h) - 1) + '\u0000';
    let s = src;
    s = s.replace(/`([^`]+)`/g, (_, c) => keep('<code>' + esc(c) + '</code>'));
    s = s.replace(/\$([^$\n]+?)\$/g, (_, m) => keep('<span class="math">' + esc(m) + '</span>'));
    s = s.replace(/!\[([^\]]*)\]\(([^)\s]+)(?:\s+"[^"]*")?\)/g, (_, alt, src) =>
      keep('<img alt="' + esc(alt) + '" src="' + esc(o.img ? o.img(src) : src) + '">'));
    s = s.replace(/\[\[([^\]|]+)(?:\|([^\]]+))?\]\]/g, (_, id, label) =>
      keep(o.wiki ? o.wiki(id.trim(), (label || id).trim()) : esc(label || id)));
    s = s.replace(/\[([^\]]+)\]\(([^)\s]+)(?:\s+"[^"]*")?\)/g, (_, text, href) => {
      const h = o.link ? o.link(href) : href;
      const safe = /^(javascript|data|vbscript):/i.test(h) ? '#' : h;
      const ext = /^https?:/i.test(safe) ? ' target="_blank" rel="noopener"' : '';
      return keep('<a href="' + esc(safe) + '"' + ext + '>' + inline(text, o) + '</a>');
    });
    s = s.replace(/\[(E\d+)\]/g, (_, id) => keep(o.ev ? o.ev(id) : '<sup>[' + id + ']</sup>'));
    s = s.replace(/<(https?:\/\/[^>\s]+)>/g, (_, u) => keep('<a href="' + esc(u) + '" target="_blank" rel="noopener">' + esc(u) + '</a>'));
    s = esc(s);
    s = s.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>').replace(/__([^_]+)__/g, '<strong>$1</strong>')
         .replace(/(^|[^*])\*([^*\s][^*]*)\*/g, '$1<em>$2</em>').replace(/~~([^~]+)~~/g, '<del>$1</del>');
    return s.replace(/\u0000(\d+)\u0000/g, (_, i) => stash[+i]);
  }

  function render(text, o = {}) {
    let lines = String(text).replace(/\r\n?/g, '\n').split('\n');
    if (lines[0] && /^---\s*$/.test(lines[0])) {
      const end = lines.findIndex((l, i) => i > 0 && /^---\s*$/.test(l));
      if (end > 0) lines = lines.slice(end + 1);
    }
    const out = [];
    const seen = {};
    let i = 0;
    const para = [];
    const flush = () => { if (para.length) { out.push('<p>' + inline(para.join(' '), o) + '</p>'); para.length = 0; } };
    while (i < lines.length) {
      const l = lines[i];
      let m;
      if ((m = l.match(/^(\s*)(```+|~~~+)\s*([\w+-]*)/))) {
        flush(); const fence = m[2]; const buf = []; i++;
        while (i < lines.length && !lines[i].trim().startsWith(fence)) buf.push(lines[i++]);
        i++; out.push('<pre><code class="lang-' + esc(m[3]) + '">' + esc(buf.join('\n')) + '</code></pre>'); continue;
      }
      if (/^\s*\$\$/.test(l)) {
        flush(); const buf = [l.replace(/^\s*\$\$/, '')];
        if (!/\$\$\s*$/.test(buf[0]) || buf[0].trim() === '') {
          i++; while (i < lines.length && !/\$\$\s*$/.test(lines[i])) buf.push(lines[i++]);
          if (i < lines.length) buf.push(lines[i].replace(/\$\$\s*$/, ''));
        } else buf[0] = buf[0].replace(/\$\$\s*$/, '');
        i++; out.push('<div class="math block">' + esc(buf.join('\n').trim()) + '</div>'); continue;
      }
      if ((m = l.match(/^(#{1,6})\s+(.*?)\s*#*\s*$/))) {
        flush(); let id = slug(m[2]); if (seen[id] !== undefined) id += '-' + (++seen[id]); else seen[id] = 0;
        out.push('<h' + m[1].length + ' id="' + esc(id) + '">' + inline(m[2], o) + '</h' + m[1].length + '>'); i++; continue;
      }
      if (/^\s*([-*_])(\s*\1){2,}\s*$/.test(l)) { flush(); out.push('<hr>'); i++; continue; }
      if (/^\s*>/.test(l)) {
        flush(); const buf = [];
        while (i < lines.length && /^\s*>/.test(lines[i])) buf.push(lines[i++].replace(/^\s*>\s?/, ''));
        out.push('<blockquote>' + render(buf.join('\n'), o) + '</blockquote>'); continue;
      }
      if (/^\s*\|.*\|\s*$/.test(l) && i + 1 < lines.length && /^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$/.test(lines[i + 1])) {
        flush();
        const cells = r => r.trim().replace(/^\||\|$/g, '').split('|').map(c => c.trim());
        const hdr = cells(l); i += 2; const rows = [];
        while (i < lines.length && /^\s*\|/.test(lines[i])) rows.push(cells(lines[i++]));
        out.push('<table><thead><tr>' + hdr.map(h => '<th>' + inline(h, o) + '</th>').join('') + '</tr></thead><tbody>' +
          rows.map(r => '<tr>' + r.map(c => '<td>' + inline(c, o) + '</td>').join('') + '</tr>').join('') + '</tbody></table>');
        continue;
      }
      if (/^\s*([-*+]|\d+[.)])\s+/.test(l)) {
        flush(); const buf = [];
        while (i < lines.length && (lines[i].trim() === '' ? (i + 1 < lines.length && /^\s+\S|^\s*([-*+]|\d+[.)])\s+/.test(lines[i + 1])) : /^\s*([-*+]|\d+[.)])\s+|^\s{2,}\S/.test(lines[i]))) buf.push(lines[i++]);
        out.push(list(buf, o)); continue;
      }
      if (l.trim() === '') { flush(); i++; continue; }
      para.push(l.trim()); i++;
    }
    flush();
    return out.join('\n');
  }

  function list(buf, o) {
    const base = buf[0].match(/^\s*/)[0].length;
    const ordered = /^\s*\d+[.)]/.test(buf[0]);
    const items = [];
    for (const l of buf) {
      const ind = l.match(/^\s*/)[0].length;
      const m = l.match(/^\s*([-*+]|\d+[.)])\s+(.*)$/);
      if (m && ind <= base + 1) items.push([m[2]]);
      else if (items.length) items[items.length - 1].push(l.slice(Math.min(ind, base + 2)));
    }
    return (ordered ? '<ol>' : '<ul>') + items.map(it => {
      const [first, ...rest] = it;
      const task = first.match(/^\[( |x)\]\s+(.*)/i);
      const head = task ? '<input type="checkbox" disabled' + (task[1] !== ' ' ? ' checked' : '') + '> ' + inline(task[2], o) : inline(first, o);
      const sub = rest.filter(x => x.trim()).length ? render(rest.join('\n'), o) : '';
      return '<li>' + head + sub + '</li>';
    }).join('') + (ordered ? '</ol>' : '</ul>');
  }

  window.MD = { render, esc, slug };
})();
