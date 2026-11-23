/* LithoKB single-page UI. No framework, no build step. */
(function () {
'use strict';
const $ = s => document.querySelector(s);
const esc = MD.esc;
const S = { me: null, token: localStorage.getItem('lkb_token') || '', site: '', srcCache: {}, titles: {} };
const RANK = { anonymous: 0, reader: 1, reviewer: 2, admin: 3 };
const ROLE_LABEL = { reader: 'Reader', reviewer: 'Reviewer', admin: 'Admin' };
const can = r => RANK[S.me ? S.me.role : 'anonymous'] >= RANK[r];
const TYPE_LABEL = { topic:'Topic', summary:'Document summary', synthesis:'Q&A synthesis', concept:'Concept', method:'Method', model:'Model', algorithm:'Algorithm', parameter:'Parameter', metric:'Metric',
  process:'Process', tool:'Tool', material:'Material', equipment:'Equipment', issue:'Issue', result:'Result', person_or_org:'Person / org' };
const ST_LABEL = { draft:'Draft', in_review:'In review', changes_requested:'Changes requested', approved:'Approved', rejected:'Rejected', published:'Published',
  withdrawn:'Withdrawn', superseded:'Superseded', active:'Active', exact:'Exact match', moved:'Moved in source', elided:'Elided match', card:'Cited from card', fuzzy:'Fuzzy match', missing:'Not found in source',
  no_source:'Source missing', approve:'Approve', request_changes:'Request changes', reject:'Reject', comment:'Comment', submit:'Submit for review', publish:'Publish',
  return:'Send back', reopen:'Reopen review', extracted:'Extracted', inferred:'Inferred', ambiguous:'Ambiguous', withdraw:'Withdraw', restore:'Restore', supersede:'Supersede with', done:'Done', failed:'Failed', running:'Running', queued:'Queued' };
const stLabel = k => ST_LABEL[k] || k;
const badge = (k, txt) => `<span class="badge b-${esc(k)}">${esc(txt || stLabel(k))}</span>`;
const TYPE_COLORS = { summary:'#9aa5b1', synthesis:'#b0417a', topic:'#2f5d8a', concept:'#3c8d6e', method:'#b5651d', model:'#7b4fa0', algorithm:'#c0392b', parameter:'#5d6d7e',
  metric:'#16a085', process:'#8e6e3c', tool:'#2c7fb8', material:'#a0522d', equipment:'#566573', issue:'#d35400', result:'#27ae60', person_or_org:'#7f8c8d' };

// ---------------------------------------------------------------- API
async function api(method, path, body) {
  const opt = { method, headers: {} };
  if (S.token) opt.headers.Authorization = 'Bearer ' + S.token;
  if (body !== undefined) { opt.headers['Content-Type'] = 'application/json'; opt.body = JSON.stringify(body); }
  const r = await fetch('/api/' + path, opt);
  const data = await r.json().catch(() => ({ error: r.statusText }));
  if (!r.ok) { const e = new Error(data.error || r.statusText); e.status = r.status; throw e; }
  if (data && data.source_titles) Object.assign(S.titles, data.source_titles);
  return data;
}
const get = p => api('GET', p);
function toast(msg, ms = 3500) { const d = document.createElement('div'); d.textContent = msg; $('#toast').appendChild(d); setTimeout(() => d.remove(), ms); }
const fmtTime = t => t ? String(t).replace('T', ' ').slice(0, 16) : '';
const set = html => { $('#main').innerHTML = html; };

// ---------------------------------------------------------------- shell
function renderShell(route) {
  const links = [['#/', 'Home'], ['#/wiki', 'Knowledge'], ['#/src', 'Sources']];
  if (S.me) links.push(['#/ask', 'Ask']);
  const rev = [['#/review', 'Review'], ['#/issues', 'Issues'], ['#/traces', 'LLM traces'], ['#/schema', 'Schema'], ['#/lint', 'Health']];
  const adm = [['#/publish', 'Publish'], ['#/compile', 'Compile'], ['#/users', 'Users'], ['#/log', 'Audit log']];
  const viewRoutes = ['k', 'wiki', 'tree', 'entity', 'graph', 'mindmap', 'timeline', 'facts'];
  const a = (l, cls = '') => `<a href="${l[0]}" class="${cls} ${('#/' + route[0]) === l[0] || (route[0] === '' && l[0] === '#/') || (l[0] === '#/wiki' && viewRoutes.includes(route[0])) ? 'on' : ''}">${l[1]}</a>`;
  let nav = links.map(l => a(l)).join('');
  if (can('reviewer')) nav += '<span class="sep"></span>' + rev.map(l => a(l, 'role-reviewer')).join('');
  if (can('admin')) nav += adm.map(l => a(l, 'role-admin')).join('');
  $('#nav').innerHTML = nav;
  $('#who').innerHTML = S.me
    ? `<span>${esc(S.me.display || S.me.name)} · ${esc(ROLE_LABEL[S.me.role] || S.me.role)}</span><button id="logout">Log out</button>`
    : `<a href="#/login">Log in</a>`;
  if (S.me) $('#logout').onclick = async () => { await api('POST', 'logout').catch(() => {}); S.token = ''; localStorage.removeItem('lkb_token'); S.me = null; location.hash = '#/'; boot(); };
}

// ---------------------------------------------------------------- router
const routes = {};
async function route() {
  const raw = location.hash.replace(/^#\/?/, '');
  const [pathPart, query] = raw.split('?');
  const parts = pathPart.split('/').map(decodeURIComponent);
  const q = Object.fromEntries(new URLSearchParams(query || ''));
  renderShell(parts);
  const fn = routes[parts[0] || ''] || routes['404'];
  try { await fn(parts.slice(1), q); }
  catch (e) {
    if (e.status === 401) { location.hash = '#/login'; return; }
    set(`<div class="panel"><h1>Something went wrong</h1><p class="muted">${esc(e.message)}</p></div>`);
  }
}
window.addEventListener('hashchange', route);
$('#qform').onsubmit = e => { e.preventDefault(); location.hash = '#/search?q=' + encodeURIComponent($('#q').value); };

// ---------------------------------------------------------------- shared renderers
function cardHref(id) { return '#/k/' + encodeURIComponent(id); }
function srcHref(path, q) { return '#/src/' + path.split('/').map(encodeURIComponent).join('/') + (q ? '?' + q : ''); }

const docTitle = p => S.titles[p] || p.split('/').pop().replace(/\.(md|markdown|mdx)$/i, '');
const docLink = (p, q, label) => `<a href="${srcHref(p, q)}" title="${esc(p)}">“${esc(docTitle(p))}”${label ? ' ' + label : ''}</a>`;
function renderCardBody(card, known) {
  // legacy bodies carry a Chinese "Addendum (from path.md)" heading, newer ones the English form: show the document title, linked to the original
  const body = (card.body || '').replace(/\u8865\u5145\uff08\u6765\u81ea ([^\uff09\[\]]+?\.(?:md|markdown|mdx))\uff09|Addendum \(from ([^)\[\]]+?\.(?:md|markdown|mdx))\)/g,
    (_, p1, p2) => { const p = p1 || p2; return `Addendum (from [“${docTitle(p)}”](src:${p}))`; });
  return MD.render(body, {
    wiki: (id, label) => {
      const k = MD.slug(id).replace(/[^a-z0-9-]/g, '');
      const miss = known && !known.has(k);
      const shown = (label === id && S.cardTitles && S.cardTitles[k]) ? S.cardTitles[k] : label;  // [[id]] → the page title
      return `<a href="${cardHref(k)}" class="${miss ? 'muted' : ''}" title="${miss ? 'Not published / does not exist' : esc(k)}">${esc(shown)}</a>`;
    },
    ev: id => `<a class="ev" data-ev="${esc(id)}" href="javascript:void 0">${esc(id)}</a>`,
    link: h => h.startsWith('src:') ? srcHref(h.slice(4)) : h, img: s => s,
  });
}

function evidenceList(card, withLines) {
  if (!card.evidence || !card.evidence.length) return '<p class="muted">No evidence cited.</p>';
  return '<ol class="evlist">' + card.evidence.map(e => {
    const ln = e.found_lines || e.lines;
    if (e.card) return `<li id="ev-${esc(e.id)}"><b>${esc(e.id)}</b> ${badge(e.check === 'card' ? 'exact' : 'missing', stLabel(e.check))}
      <a href="${cardHref(e.card)}">Card ${esc(e.card)}</a><div class="quote">${esc(e.quote)}</div></li>`;
    return `<li id="ev-${esc(e.id)}"><b>${esc(e.id)}</b> ${badge(e.check || 'missing')}${e.not_read ? ' <span class="badge b-warn">Not in reading plan</span>' : ''}
      ${docLink(e.path, 'L=' + encodeURIComponent(ln), '· L' + esc(ln))}
      ${e.found_lines && e.found_lines !== e.lines ? `<span class="small muted">(model claimed L${esc(e.lines)})</span>` : ''}
      <div class="quote">${esc(e.quote)}</div>${withLines ? `<details ${['exact', 'moved'].includes(e.check) ? '' : 'open'}><summary class="small muted">Source context${['exact', 'moved'].includes(e.check) ? '' : ' (needs human check)'}</summary><div class="srclines" data-path="${esc(e.path)}" data-lines="${esc(ln)}"></div></details>` : ''}</li>`;
  }).join('') + '</ol>';
}

async function fillSourceLines(root) {
  for (const el of root.querySelectorAll('.srclines')) {
    const path = el.dataset.path;
    try {
      if (!S.srcCache[path]) S.srcCache[path] = (await get('sources/file?path=' + encodeURIComponent(path))).text || '';
      const lines = S.srcCache[path].split('\n');
      const [a, b] = el.dataset.lines.split('-').map(Number);
      const from = Math.max(1, a - 2), to = Math.min(lines.length, (b || a) + 2);
      let h = '';
      for (let i = from; i <= to; i++) h += `<div class="ln ${i >= a && i <= (b || a) ? 'hl' : ''}"><i>${i}</i><span>${esc(lines[i - 1])}</span></div>`;
      el.innerHTML = `<div class="srcview small">${h}</div>`;
    } catch (e) { el.innerHTML = `<span class="muted small">Cannot read source: ${esc(e.message)}</span>`; }
  }
}

function bindEvidence(root) {
  root.querySelectorAll('a.ev').forEach(a => a.onclick = () => {
    const t = document.getElementById('ev-' + a.dataset.ev);
    if (t) { t.scrollIntoView({ behavior: 'smooth', block: 'center' }); t.style.outline = '2px solid var(--warn)'; setTimeout(() => t.style.outline = '', 1500); }
  });
}

function basisBadge(r) {
  const b = r.basis || 'inferred';
  const cls = b === 'extracted' ? 'exact' : b === 'ambiguous' ? 'request_changes' : 'comment';
  const conf = r.confidence != null && b !== 'extracted' ? ' ' + Math.round(r.confidence * 100) + '%' : '';
  return ` <span class="badge b-${cls}" title="Epistemic status: ${stLabel(b)}${r.evidence ? ', evidence ' + esc(r.evidence) : ''}">${stLabel(b)}${conf}${r.evidence ? ' · ' + esc(r.evidence) : ''}</span>`;
}
function basisSummary(rels) {
  const c = { extracted: 0, inferred: 0, ambiguous: 0 };
  (rels || []).forEach(r => c[r.basis || 'inferred']++);
  return `<span class="small muted">Extracted ${c.extracted} · Inferred ${c.inferred} </span>${c.ambiguous ? badge('request_changes', 'Ambiguous ' + c.ambiguous) : ''}`;
}
function relationsBlock(card, backlinks) {
  const rels = card.relations || [];
  let h = '';
  if (rels.length) {
    const g = {};
    rels.forEach(r => (g[r.rel] = g[r.rel] || []).push(r));
    h += '<h3>Relations</h3><ul>' + Object.entries(g).map(([rel, rs]) =>
      `<li><span class="badge">${esc(rel)}</span> ${rs.map(r => `<a href="${cardHref(r.target)}">${esc(r.target)}</a>${basisBadge(r)}${r.note ? ` <span class="muted small">${esc(r.note)}</span>` : ''}`).join(', ')}</li>`).join('') + '</ul>';
  }
  if (backlinks && backlinks.length) h += '<h3>Referenced by</h3><p>' + backlinks.map(b => `<a href="${cardHref(b.id)}">${esc(b.title)}</a>`).join(' · ') + '</p>';
  return h;
}

function topicTree(allCards, current) {
  const cards = allCards.filter(c => c.type !== 'summary');
  const byParent = {};
  const ids = new Set(cards.map(c => c.id));
  cards.forEach(c => { const p = ids.has(c.parent) ? c.parent : ''; (byParent[p] = byParent[p] || []).push(c); });
  const walk = (pid, seen) => {
    const kids = (byParent[pid] || []).filter(c => !seen.has(c.id)).sort((a, b) => (a.type !== 'topic') - (b.type !== 'topic') || a.title.localeCompare(b.title, 'zh'));
    if (!kids.length) return '';
    return '<ul>' + kids.map(c => {
      seen.add(c.id);
      const sub = walk(c.id, seen);
      const link = `<a href="${cardHref(c.id)}" class="${c.id === current ? 'on' : ''}" title="${esc(c.summary || '')}">${esc(c.title)}</a>`;
      return sub ? `<li class="dir"><span data-toggle>${esc(c.title)}</span>${link.replace('">', '" style="font-size:12px;color:var(--muted)">· overview ')}${sub}</li>` : `<li>${link}</li>`;
    }).join('') + '</ul>';
  };
  return '<div class="tree">' + walk('', new Set()) + '</div>';
}
function bindTree(root) { root.querySelectorAll('[data-toggle]').forEach(s => s.onclick = () => s.parentElement.classList.toggle('closed')); }

// ---------------------------------------------------------------- views: reader
routes[''] = async () => {
  const st = await get('stats');
  const cards = await get('cards');
  set(`<div class="stats">
      <div class="stat"><b>${st.published}</b><span>Published knowledge cards</span></div>
      <div class="stat"><b>${st.sources}</b><span>Source documents</span></div>
      ${can('reviewer') ? `<div class="stat"><b>${st.cards}</b><span>All cards (incl. unpublished)</span></div>
      <div class="stat"><b>${(st.by_status.in_review || 0)}</b><span>Awaiting review</span></div>
      <div class="stat"><b>${(st.by_status.approved || 0)}</b><span>Awaiting publication</span></div>` : ''}
    </div>
    <div class="cols"><aside class="panel side"><h3 style="margin-top:0">Knowledge structure</h3>${topicTree(cards.filter(c => can('reviewer') ? c.published_rev : true))}</aside>
    <section class="panel"><h2 style="margin-top:0">Recently published</h2><div class="cardlist">${st.recent.map(c =>
      `<a class="item" href="${cardHref(c.id)}"><b>${esc(c.title)}</b> <span class="muted small">${fmtTime(c.at)}</span><br><span class="muted small">${esc(c.summary)}</span></a>`).join('') || '<p class="muted">No published knowledge yet.</p>'}</div>
    <p class="small muted" style="margin-top:16px">Two layers: <a href="#/src">source documents</a> (layer 1: stored verbatim, with uploader and version history) → LLM-compiled <a href="#/k">knowledge cards</a> (layer 2: published after human review; every claim cites source evidence that is verified automatically).</p></section></div>`);
  bindTree($('#main'));
};

routes.k = async ([id], q) => {
  const all = await get(id ? 'cards' : withCond('cards'));
  S.cardTitles = Object.assign(S.cardTitles || {}, Object.fromEntries(all.map(c => [c.id, c.title])));
  if (!S.dims) S.dims = await get('dims').catch(() => ({}));
  const visible = can('reviewer') ? all.filter(c => c.published_rev || q.all) : all;
  if (!id) {
    const byType = {};
    visible.filter(c => c.type !== 'summary').forEach(c => (byType[c.type] = byType[c.type] || []).push(c));
    const sums = visible.filter(c => c.type === 'summary');
    const bar = await condBar();
    set(`<div class="panel" style="margin-bottom:16px">${viewTabs('#/k')}${bar}</div><div class="cols"><aside class="panel side">${topicTree(visible)}</aside><section class="panel"><h1>Knowledge cards</h1>
      <p class="muted small">${visible.length} ${can('reviewer') ? 'published cards (for cards under review see <a href="#/review">Review</a>)' : 'cards'}${condQS() ?
        ` · filtered by applicability conditions: <b>${visible.filter(c => c.applies === 'yes').length}</b> explicitly match, ${visible.filter(c => c.applies === 'general').length} general (source states no conditions); non-matching cards excluded` : ''}</p>
      ${Object.entries(byType).map(([t, cs]) => `<h3>${esc(TYPE_LABEL[t] || t)} <span class="muted small">${cs.length}</span></h3><div class="cardlist">` +
        cs.map(c => `<a class="item" href="${cardHref(c.id)}"><b>${esc(c.title)}</b> ${appliesBadge(c.applies)} ${condChips(c.conditions)}<br><span class="muted small">${esc(c.summary || '')}</span></a>`).join('') + '</div>').join('')}
      <h2>Document summaries <span class="muted small">${sums.length} · one summary card per source document, pointing to the knowledge it contributed</span></h2><div class="cardlist">${sums.map(c =>
        `<a class="item" href="${cardHref(c.id)}"><b>${esc(c.title)}</b> <span class="mono small muted">${(c.sources || []).map(x => esc(x.path)).join(', ')}</span><br><span class="muted small">${esc(c.summary || '')}</span></a>`).join('') || '<p class="muted">None</p>'}</div></section></div>`);
    bindCond();
    return bindTree($('#main'));
  }
  const d = await get('cards/' + encodeURIComponent(id));
  if (d.lifecycle === 'superseded') {
    return set(`<div class="panel"><h1>${esc(d.title)}</h1><div class="banner warn">This card has been superseded by <a href="${cardHref(d.replaced_by)}">${esc(d.replaced_by)}</a>.</div></div>`);
  }
  const showHead = can('reviewer') && (q.view === 'head' || !d.published);
  const card = showHead ? d.head : d.published;
  const known = new Set(all.map(c => c.id));
  const head = d.head;
  let banners = '';
  if (can('reviewer')) {
    if (head.lifecycle !== 'active') banners += `<div class="banner bad">Card status: ${stLabel(head.lifecycle)}${head.replaced_by ? ' → ' + esc(head.replaced_by) : ''} (hidden from readers)</div>`;
    if (d.published && head.rev !== head.published_rev)
      banners += `<div class="banner info">New revision r${head.rev} (${stLabel(head.status)}) is not yet published. Viewing: ${showHead ? 'latest revision r' + head.rev : 'published r' + head.published_rev}.
        <a href="${cardHref(id)}?view=${showHead ? 'published' : 'head'}">Switch</a> · <a href="#/review/${encodeURIComponent(id)}">Go to review</a></div>`;
    if (!d.published) banners += `<div class="banner warn">Not yet published (${stLabel(head.status)}); hidden from readers. <a href="#/review/${encodeURIComponent(id)}">Go to review</a></div>`;
  }
  if ((d.issues || []).some(i => i.kind === 'contradiction')) banners += `<div class="banner bad">This card is involved in an unresolved contradiction; see “Known disagreements and open questions” at the end.</div>`;
  if ((head.stale_sources || []).length) banners += `<div class="banner warn">Source document updated; this card may be stale: ${head.stale_sources.map(esc).join(', ')}</div>`;
  set(`<div class="cols"><aside class="panel side">${topicTree(visible, id)}</aside>
    <article class="panel doc"><div class="row">${badge('t', TYPE_LABEL[card.type] || card.type)}${can('reviewer') ? badge(head.status) : ''}
      <span class="small muted">r${card.rev} · evidence verified ${Math.round((card.grounding || {}).score * 100 || 0)}% · ${originLabel(card.origin, false)}${card.published_by ? ' · published by ' + esc(card.published_by) + ' at ' + fmtTime(card.published_at) : ''}</span></div>
    ${banners}<h1>${esc(card.title)}</h1>${(card.aliases || []).length ? `<p class="muted small">Aliases: ${card.aliases.map(esc).join(', ')}</p>` : ''}
    <p><i>${esc(card.summary || '')}</i></p>${renderCardBody(card, known)}
    ${relationsBlock(card, d.backlinks)}${(card.relations || []).length ? '<p>' + basisSummary(card.relations) + '</p>' : ''}
    ${facetsBlock(card)}
    <h3>Evidence (source quotes, verified automatically)</h3>${evidenceList(card, false)}
    <p class="small muted">Sources: ${(card.sources || []).map(s => `${docLink(s.path)} <span title="Version">v${s.version}</span>`).join(', ')}
    ${can('reviewer') && card.origin && card.origin.run ? ` · <a href="#/traces/${esc(card.origin.run)}">View compile trace</a>` : ''}</p>
    ${issuesBlock(d.issues, id)}</article></div>`);
  bindTree($('#main')); bindEvidence($('#main')); bindReport();
};

routes.src = async (parts, q) => {
  const path = parts.join('/');
  const tree = await get('sources');
  const treeHtml = n => '<ul>' + n.children.filter(c => !(c.type === 'file' && c.path === n.index && n.path)).map(c => c.type === 'dir'
    ? `<li class="dir ${path.startsWith(c.path + '/') ? '' : 'closed'}"><span data-toggle>${esc(c.title || c.name)}</span>${c.index ? `<a href="${srcHref(c.index)}" class="${c.index === path ? 'on' : ''}" style="font-size:12px;color:var(--muted)">· index page</a>` : ''}${treeHtml(c)}</li>`
    : `<li><a href="${c.name.match(/\.(md|markdown|mdx)$/i) ? srcHref(c.path) : '/raw/' + c.path}" class="${c.path === path ? 'on' : ''}" title="${esc(c.path)}">${esc(c.title || c.name)}</a></li>`).join('') + '</ul>';
  const up = can('reviewer') ? `<details style="margin-top:12px"><summary>Upload Markdown / HTML files or folders</summary>
      <div class="row"><input type="file" id="upfiles" multiple accept=".md,.markdown,.mdx,.html,.htm,.png,.jpg,.jpeg,.gif,.svg,.webp,.pdf,.csv,.txt,.json,.yaml,.yml"></div>
      <div class="row"><input type="file" id="updir" webkitdirectory multiple></div>
      <div class="row"><input id="upprefix" placeholder="Target folder (optional)" style="width:100%"></div>
      <div class="row"><input id="upnote" placeholder="Upload note (optional)" style="width:100%"></div>
      <div class="row"><button class="primary" id="upgo">Upload</button></div><div id="upres" class="small"></div></details>` : '';
  let mainHtml = `<h1>Source documents</h1><p class="muted">Layer 1: Markdown documents stored verbatim, preserving the authors' folder structure, index order and cross-links.</p>`;
  if (path) {
    const d = await get('sources/file?path=' + encodeURIComponent(path) + (q.v ? '&v=' + q.v : ''));
    const dir = path.includes('/') ? path.slice(0, path.lastIndexOf('/')) : '';
    const resolve = href => {
      if (/^[a-z]+:/i.test(href) || href.startsWith('//')) return href;
      let [file, frag] = href.split('#');
      if (!file) return srcHref(path, 'h=' + encodeURIComponent(frag || ''));
      const segs = (file.startsWith('/') ? [] : dir ? dir.split('/') : []);
      for (const s of file.replace(/^\//, '').split('/')) { if (s === '..') segs.pop(); else if (s && s !== '.') segs.push(s); }
      const target = segs.join('/');
      return /\.(md|markdown|mdx)$/i.test(target) ? srcHref(target, frag ? 'h=' + encodeURIComponent(frag) : '') : '/raw/' + target;
    };
    const img = s => resolve(s).startsWith('#') ? s : resolve(s);
    const raw = q.L || q.raw;
    const meta = d.meta;
    let body;
    if (raw) {
      const [a, b] = (q.L || '0-0').split('-').map(Number);
      body = '<div class="srcview">' + d.text.split('\n').map((l, i) => `<div class="ln ${i + 1 >= a && i + 1 <= (b || a) ? 'hl' : ''}" id="L${i + 1}"><i>${i + 1}</i><span>${esc(l) || ' '}</span></div>`).join('') + '</div>';
    } else body = '<div class="doc">' + MD.render(d.text, { link: resolve, img }) + '</div>';
    const outlineHtml = (nodes) => !nodes || !nodes.length ? '' : '<ul>' + nodes.map(n =>
      `<li><a href="${srcHref(path, 'L=' + n.start + '-' + n.end + (q.v ? '&v=' + q.v : ''))}" title="${esc(n.gist || '')}">${esc(n.title)} <span class="muted small">L${n.start}–${n.end}</span></a>${outlineHtml(n.children)}</li>`).join('') + '</ul>';
    const sumCard = d.derived_cards.find(c => c.id.startsWith('summary-'));
    mainHtml = `<div class="row small muted"><span class="mono">${esc(path)}</span> · v${q.v || meta.version}${q.v && +q.v !== meta.version ? ' <span class="badge b-warn">Old version</span>' : ''}
        · uploaded: ${esc(meta.by)} ${fmtTime(meta.at)} · first: ${esc(meta.first_by)} ${fmtTime(meta.first_at)}
        · <a href="${srcHref(path, raw ? (q.v ? 'v=' + q.v : '') : 'raw=1' + (q.v ? '&v=' + q.v : ''))}">${raw ? 'Rendered view' : 'Original (line numbers)'}</a>
        · <a href="/raw/${esc(path)}${q.v ? '?v=' + q.v : ''}" target="_blank">Download</a></div>
      ${meta.derived_from ? `<div class="banner warn">This document was converted automatically from an HTML original (${esc(meta.converter)}). The original is always kept:<a href="/raw/${esc(meta.derived_from)}" target="_blank">View original HTML</a> · <a href="/raw/${esc(meta.derived_from)}" download>Download</a></div>` : ''}
      ${sumCard ? `<div class="banner info">Document summary card: <a href="${cardHref(sumCard.id)}${sumCard.public ? '' : '?view=head'}">${esc(sumCard.title)}</a> ${can('reviewer') ? badge(sumCard.status) : ''}</div>` : ''}
      ${d.tree && d.tree.nodes.length ? `<details class="tree" ${raw ? 'open' : ''} style="margin:8px 0"><summary class="small">Document outline (${d.tree.lines} lines · built from the headings; used for Ask navigation and section-by-section compilation of long documents)</summary>${outlineHtml(d.tree.nodes)}</details>` : ''}
      ${body}
      <details style="margin-top:16px"><summary class="small">Version history (${meta.history.length})</summary><table class="grid"><tr><th>Version</th><th>Uploaded by</th><th>Time</th><th>sha256</th><th>Note</th></tr>
        ${meta.history.slice().reverse().map(h => `<tr><td><a href="${srcHref(path, 'v=' + h.version)}">v${h.version}</a></td><td>${esc(h.by)}</td><td>${fmtTime(h.at)}</td><td class="mono">${esc(h.sha256.slice(0, 12))}</td><td>${esc(h.note || '')}</td></tr>`).join('')}</table></details>
      ${d.derived_cards.length ? `<h3>Knowledge compiled from this document</h3><p>${d.derived_cards.map(c => `<a href="${cardHref(c.id)}">${esc(c.title)}</a> ${can('reviewer') ? badge(c.status) : ''}${c.stale ? badge('stale', 'Needs update') : ''}`).join(' · ')}</p>` : ''}
      ${can('admin') ? `<p><button class="bad small" id="retire">Retire this document</button></p>` : ''}`;
  }
  set(`<div class="cols"><aside class="panel side"><div class="tree">${treeHtml(tree)}</div>${up}</aside><section class="panel">${mainHtml}</section></div>`);
  bindTree($('#main'));
  if (q.L) { const el = document.getElementById('L' + q.L.split('-')[0]); if (el) el.scrollIntoView({ block: 'center' }); }
  if (q.h) { const el = document.getElementById(q.h) || document.getElementById(MD.slug(q.h)); if (el) el.scrollIntoView(); }
  const rb = $('#retire'); if (rb) rb.onclick = async () => { if (!confirm('Retiring archives the document in its history and marks cards that cite it as stale. Continue?')) return; await api('DELETE', 'sources/file?path=' + encodeURIComponent(path)); toast('Retired'); location.hash = '#/src'; };
  const go = $('#upgo'); if (go) go.onclick = () => upload();
};

async function upload() {
  const files = [...$('#upfiles').files, ...$('#updir').files];
  if (!files.length) return toast('Select files or a folder');
  const items = await Promise.all(files.map(f => new Promise(res => {
    const r = new FileReader();
    const rel = f.webkitRelativePath || f.name;
    if (/\.(md|markdown|mdx|txt|csv|json|ya?ml|svg|html?)$/i.test(f.name)) { r.onload = () => res({ path: rel, text: r.result }); r.readAsText(f); }
    else { r.onload = () => res({ path: rel, b64: String(r.result).split(',')[1] || '' }); r.readAsDataURL(f); }
  })));
  const d = await api('POST', 'sources/upload', { files: items, prefix: $('#upprefix').value.trim(), note: $('#upnote').value.trim() });
  $('#upres').innerHTML = d.results.map(r => `${badge(r.status === 'skipped' ? 'warn' : 'published', r.status)} ${esc(r.path)} ${r.reason ? esc(r.reason) : ''}`).join('<br>');
  toast(`Upload complete: ${d.results.filter(r => r.status === 'added' || r.status === 'updated').length} file(s) changed`);
  setTimeout(route, 800);
}

routes.search = async (_, q) => {
  $('#q').value = q.q || '';
  const d = await get('search?q=' + encodeURIComponent(q.q || ''));
  set(`<div class="panel"><h1>Search: ${esc(q.q || '')}</h1><h3>Knowledge cards (${d.cards.length})</h3><div class="cardlist">${d.cards.map(c =>
    `<a class="item" href="${cardHref(c.id)}"><b>${esc(c.title)}</b> ${can('reviewer') ? badge(c.status) : ''}<br><span class="muted small">${esc(c.summary)}</span></a>`).join('') || '<p class="muted">None</p>'}</div>
    <h3>Source document sections (${d.sources.length})</h3><div class="cardlist">${d.sources.map(s =>
    `<a class="item" href="${srcHref(s.path, 'L=' + s.line)}"><b>“${esc(docTitle(s.path))}” · ${esc(s.title || '')}</b> <span class="muted small">L${s.line}-${s.end || ''}</span><br><span class="muted small">${esc(s.snippet)}</span></a>`).join('') || '<p class="muted">None</p>'}</div></div>`);
};

// ---------------------------------------------------------------- graph
routes.graph = async (_, q) => {
  const g0 = await get(withCond('graph' + (q.all ? '?all=1' : '')));
  const bar = await condBar();
  const keep = new Set(g0.nodes.filter(n => q.sum || n.type !== 'summary').map(n => n.id));
  const g = { nodes: g0.nodes.filter(n => keep.has(n.id)), edges: g0.edges.filter(e => keep.has(e.s) && keep.has(e.t)) };
  const types = [...new Set(g.nodes.map(n => n.type))];
  set(`<div class="panel" style="margin-bottom:10px">${viewTabs('#/graph')}${bar}</div><div class="row"><b>Knowledge graph</b><span class="muted small">${g.nodes.length} nodes · ${g.edges.length} relations · scroll to zoom, drag to pan, click to open</span>
      ${can('reviewer') ? `<label class="small"><input type="checkbox" id="gall" ${q.all ? 'checked' : ''}> Include unpublished</label>` : ''}
      <input id="gfilter" placeholder="Highlight…" style="width:160px"></div>
    <div class="legend row">${types.map(t => `<span><i style="background:${TYPE_COLORS[t] || '#888'}"></i>${esc(TYPE_LABEL[t] || t)}</span>`).join('')}
      <span class="small muted">Edges: solid = extracted · dashed = inferred · orange dotted = ambiguous · red = contradiction</span>
      <label class="small"><input type="checkbox" id="gsum"> Show document summary nodes</label></div>
    ${await pathFinder(g.nodes)}
    <canvas id="graph"></canvas>`);
  bindPathFinder(g.nodes);
  const gnav = () => { const p = []; if ($('#gall') && $('#gall').checked) p.push('all=1'); if ($('#gsum').checked) p.push('sum=1'); location.hash = '#/graph' + (p.length ? '?' + p.join('&') : ''); };
  if ($('#gall')) $('#gall').onchange = gnav; $('#gsum').checked = !!q.sum; $('#gsum').onchange = gnav;
  bindCond();
  drawGraph($('#graph'), g);
};

function drawGraph(cv, g) {
  const dpr = window.devicePixelRatio || 1;
  const W = cv.clientWidth, H = cv.clientHeight;
  cv.width = W * dpr; cv.height = H * dpr;
  const ctx = cv.getContext('2d'); ctx.scale(dpr, dpr);
  const idx = {};
  const N = g.nodes.map((n, i) => (idx[n.id] = { ...n, x: W / 2 + Math.cos(i) * 200 * Math.random(), y: H / 2 + Math.sin(i) * 200 * Math.random(), vx: 0, vy: 0, deg: 0 }));
  const E = g.edges.filter(e => idx[e.s] && idx[e.t]).map(e => { idx[e.s].deg++; idx[e.t].deg++; return { ...e, s: idx[e.s], t: idx[e.t] }; });
  let view = { x: 0, y: 0, k: 1 }, alpha = 1, hover = null, filter = '';
  const ink = getComputedStyle(document.body).color;
  function tick() {
    const k = 60;
    for (let i = 0; i < N.length; i++) for (let j = i + 1; j < N.length; j++) {
      const a = N[i], b = N[j]; let dx = a.x - b.x, dy = a.y - b.y; let d2 = dx * dx + dy * dy || 0.01;
      if (d2 > 250000) continue; const f = (k * k) / d2 * alpha; a.vx += dx * f * 0.05; a.vy += dy * f * 0.05; b.vx -= dx * f * 0.05; b.vy -= dy * f * 0.05;
    }
    for (const e of E) { const dx = e.t.x - e.s.x, dy = e.t.y - e.s.y, d = Math.sqrt(dx * dx + dy * dy) || 1; const f = (d - k * 1.3) / d * 0.04 * alpha;
      e.s.vx += dx * f; e.s.vy += dy * f; e.t.vx -= dx * f; e.t.vy -= dy * f; }
    for (const n of N) { n.vx += (W / 2 - n.x) * 0.002 * alpha; n.vy += (H / 2 - n.y) * 0.002 * alpha; n.x += n.vx; n.y += n.vy; n.vx *= 0.6; n.vy *= 0.6; }
    alpha *= 0.985;
  }
  function draw() {
    ctx.clearRect(0, 0, W, H); ctx.save(); ctx.translate(view.x, view.y); ctx.scale(view.k, view.k);
    ctx.lineWidth = 1 / view.k;
    for (const e of E) { ctx.strokeStyle = e.rel === 'contradicts' ? 'rgba(200,60,50,.8)' : e.basis === 'ambiguous' ? 'rgba(210,130,0,.8)' : e.rel === 'subtopic_of' ? 'rgba(120,130,140,.55)' : 'rgba(120,130,140,.35)';
      ctx.setLineDash(e.basis === 'inferred' ? [4 / view.k, 3 / view.k] : e.basis === 'ambiguous' ? [1.5 / view.k, 2.5 / view.k] : []);
      ctx.beginPath(); ctx.moveTo(e.s.x, e.s.y); ctx.lineTo(e.t.x, e.t.y); ctx.stroke(); }
    ctx.setLineDash([]);
    for (const n of N) {
      const r = 4 + Math.min(10, Math.sqrt(n.deg) * 2) + (n.type === 'topic' ? 3 : 0);
      const dim = filter && !(n.title + n.id).toLowerCase().includes(filter);
      ctx.globalAlpha = dim ? 0.15 : (n.status === 'published' || n.lifecycle !== 'active' ? 1 : 0.55);
      ctx.fillStyle = TYPE_COLORS[n.type] || '#888'; ctx.beginPath(); ctx.arc(n.x, n.y, r, 0, 7); ctx.fill();
      if (n.status !== 'published') { ctx.strokeStyle = '#a66a00'; ctx.setLineDash([2, 2]); ctx.stroke(); ctx.setLineDash([]); }
      if (view.k > 0.7 || n === hover || n.type === 'topic' || (filter && !dim)) { ctx.fillStyle = ink; ctx.font = `${12 / Math.max(view.k, .7)}px sans-serif`; ctx.fillText(n.title, n.x + r + 2, n.y + 4); }
      ctx.globalAlpha = 1;
    }
    ctx.restore();
    if (hover) { ctx.fillStyle = ink; ctx.font = '13px sans-serif'; ctx.fillText(`${hover.title}  [${TYPE_LABEL[hover.type] || hover.type} · ${stLabel(hover.status)}]`, 10, H - 12); }
  }
  let fitted = false;
  function fit() {
    if (!N.length) return; let x0 = 1e9, y0 = 1e9, x1 = -1e9, y1 = -1e9;
    for (const n of N) { x0 = Math.min(x0, n.x); y0 = Math.min(y0, n.y); x1 = Math.max(x1, n.x); y1 = Math.max(y1, n.y); }
    const k = Math.min(2, 0.85 * Math.min(W / Math.max(1, x1 - x0 + 120), H / Math.max(1, y1 - y0 + 60)));
    view = { k, x: W / 2 - k * (x0 + x1) / 2, y: H / 2 - k * (y0 + y1) / 2 };
  }
  let touched = false;
  for (let i = 0; i < 120 && N.length < 400; i++) tick();  // pre-settle off-screen for small graphs
  fit();
  function loop() { if (!document.body.contains(cv)) return; if (alpha > 0.02) tick(); else if (!fitted) { if (!touched) fit(); fitted = true; } draw(); requestAnimationFrame(loop); }
  loop();
  const at = ev => { const r = cv.getBoundingClientRect(); const x = (ev.clientX - r.left - view.x) / view.k, y = (ev.clientY - r.top - view.y) / view.k;
    let best = null, bd = 144 / view.k / view.k; for (const n of N) { const d = (n.x - x) ** 2 + (n.y - y) ** 2; if (d < bd) { bd = d; best = n; } } return best; };
  let drag = null, moved = false;
  cv.onmousedown = ev => { touched = true; drag = { x: ev.clientX, y: ev.clientY, vx: view.x, vy: view.y }; moved = false; };
  window.onmouseup = ev => { if (drag && !moved) { const n = at(ev); if (n) location.hash = cardHref(n.id) + (n.status !== 'published' ? '?view=head' : ''); } drag = null; };
  cv.onmousemove = ev => { if (drag) { const dx = ev.clientX - drag.x, dy = ev.clientY - drag.y; if (Math.abs(dx) + Math.abs(dy) > 3) moved = true; view.x = drag.vx + dx; view.y = drag.vy + dy; } else hover = at(ev); };
  cv.onwheel = ev => { ev.preventDefault(); touched = true; const r = cv.getBoundingClientRect(); const mx = ev.clientX - r.left, my = ev.clientY - r.top; const f = ev.deltaY < 0 ? 1.15 : 1 / 1.15;
    view.x = mx - (mx - view.x) * f; view.y = my - (my - view.y) * f; view.k *= f; };
  $('#gfilter').oninput = e => { filter = e.target.value.toLowerCase(); };
}

// ---------------------------------------------------------------- reviewer
const RISK_LABEL = { low: 'Low risk', medium: 'Medium risk', high: 'High risk' };
const riskBadge = r => r ? `<span class="badge b-${r.level === 'low' ? 'exact' : r.level === 'medium' ? 'request_changes' : 'missing'}" title="${esc((r.reasons || []).join('\n') || 'All evidence matches the source exactly; no ambiguous/contradicting relations; single source; granularity OK')}">${RISK_LABEL[r.level]}</span>` : '';
const sizeBadge = g => g ? `<span class="small muted" title="Reading units: CJK characters or English words">${g.units} words · ${g.minutes} min</span>${(g.issues || []).map(i => ' ' + badge(i === 'long' ? 'comment' : 'warn', { thin: 'Too thin', long: 'Long', too_long: 'Too long', fragmented: 'Many addenda', broad: 'Too much evidence' }[i] || i)).join('')}` : '';
routes.review = async ([id], q) => {
  if (id) return reviewWorkspace(id, q);
  const cards = await get('cards');
  const tab = q.s || 'in_review';
  const risk = q.r || '';
  const tabs = ['in_review', 'changes_requested', 'approved', 'rejected', 'draft', 'published'];
  const order = { high: 0, medium: 1, low: 2 };
  let rows = cards.filter(c => c.status === tab);
  const counts = { high: 0, medium: 0, low: 0 };
  rows.forEach(c => c.risk && counts[c.risk.level]++);
  if (risk) rows = rows.filter(c => c.risk && c.risk.level === risk);
  rows.sort((a, b) => order[(a.risk || {}).level] - order[(b.risk || {}).level] || (a.type === 'topic') - (b.type === 'topic'));
  const batchable = tab === 'in_review';
  set(`<div class="panel"><h1>Review queue</h1><div class="tabs">${tabs.map(t => `<a href="#/review?s=${t}" class="${t === tab ? 'on' : ''}">${stLabel(t)} (${cards.filter(c => c.status === t).length})</a>`).join('')}</div>
    <div class="row small">By risk: ${['', 'high', 'medium', 'low'].map(r => `<a href="#/review?s=${tab}${r ? '&r=' + r : ''}" class="badge ${r === risk ? 'b-in_review' : ''}">${r ? RISK_LABEL[r] + ' ' + counts[r] : 'All ' + (counts.high + counts.medium + counts.low)}</a>`).join(' ')}
      <span class="muted">· High- and medium-risk cards must be reviewed one by one; only low-risk cards can be batch-approved (enforced by the server), and a batch needs a comment and leaves an audit record.</span></div>
    ${batchable && counts.low ? `<details class="panel" style="margin:8px 0;padding:10px 14px" ${risk === 'low' ? 'open' : ''}><summary><b>Batch-approve low-risk cards</b> <span class="small muted">(<span id="bsel">0</span> selected)</span></summary>
      <p class="small muted">Low risk means: every evidence quote matches the source verbatim (exact / moved); no ambiguous or contradicting relations; single source; not a human edit and not an update to published content; confidence ≥ 0.7; granularity OK. After a batch approval each card gets its own review record (with the batch id), and the audit log records the batch and the criteria.</p>
      <div class="row"><button id="bsall">Select all low-risk on this page</button><button id="bsnone">Clear</button></div>
      <textarea id="bcomment" placeholder="Comment (required, at least 10 characters): explain why you are batch-approving and how you checked, e.g. “Spot-checked 5 cards against the source, all consistent; the rest rely on all-exact evidence matches”"></textarea>
      <div class="row"><button class="primary" id="bgo">Approve selected</button><span id="bres" class="small"></span></div></details>` : ''}
    <table class="grid"><tr>${batchable ? '<th></th>' : ''}<th>Card</th><th>Risk</th><th>Type</th><th>Length</th><th>Sources</th><th>Verification</th><th>Relations</th><th>Origin</th></tr>
    ${rows.map(c => `<tr>${batchable ? `<td>${c.risk && c.risk.level === 'low' ? `<input type="checkbox" class="bsel" value="${esc(c.id)}">` : ''}</td>` : ''}
      <td><a href="#/review/${encodeURIComponent(c.id)}"><b>${esc(c.title)}</b></a><br><span class="mono muted">${esc(c.id)}</span>
        ${c.lifecycle !== 'active' ? badge(c.lifecycle) : ''}${(c.stale_sources || []).length ? badge('stale', 'Source changed') : ''}${c.published_rev ? badge('published', 'live r' + c.published_rev) : ''}</td>
      <td>${riskBadge(c.risk)}${c.risk && c.risk.reasons.length ? `<div class="small muted" style="max-width:260px">${c.risk.reasons.slice(0, 2).map(esc).join('; ')}${c.risk.reasons.length > 2 ? '…' : ''}</div>` : ''}</td>
      <td>${esc(TYPE_LABEL[c.type] || c.type)} <span class="small muted">r${c.rev}</span></td><td>${sizeBadge(c.risk && c.risk.granularity)}</td>
      <td class="small">${(c.sources || []).map(s => docLink(s.path)).join('<br>')}</td>
      <td>${gbadge(c.grounding, c)}</td><td>${basisSummary(c.relations)}</td><td class="small">${originLabel(c.origin)}</td></tr>`).join('') || '<tr><td colspan="9" class="muted">Empty</td></tr>'}</table></div>`);
  const boxes = () => [...document.querySelectorAll('.bsel')];
  const upd = () => { const el = $('#bsel'); if (el) el.textContent = boxes().filter(b => b.checked).length; };
  boxes().forEach(b => b.onchange = upd);
  if ($('#bsall')) $('#bsall').onclick = () => { boxes().forEach(b => b.checked = true); upd(); };
  if ($('#bsnone')) $('#bsnone').onclick = () => { boxes().forEach(b => b.checked = false); upd(); };
  if ($('#bgo')) $('#bgo').onclick = async () => {
    const ids = boxes().filter(b => b.checked).map(b => b.value), comment = $('#bcomment').value.trim();
    if (!ids.length) return toast('No cards selected');
    if (comment.length < 10) return toast('Batch actions require a comment (at least 10 characters)');
    if (!confirm(`Batch-approve ${ids.length} low-risk card(s)? Your comment and the batch id are recorded on each card.`)) return;
    try {
      const r = await api('POST', 'cards/_batch', { ids, action: 'approve', comment });
      toast(`${r.batch}: approved ${r.done.length}${r.skipped.length ? ', skipped ' + r.skipped.length : ''}`, 6000);
      if (r.skipped.length) alert('These cards failed the batch check and need individual review:\n' + r.skipped.map(x => x.id + ': ' + x.reason).join('\n'));
      route();
    } catch (e) { toast(e.message); }
  };
};
const FIELD_LABEL = { title: 'Title', type: 'Type', parent: 'Parent topic', summary: 'Summary', aliases: 'Aliases', confidence: 'Confidence' };
function semanticDiff(sd) {
  if (!sd) return '';
  const val = v => Array.isArray(v) ? v.map(esc).join(', ') || '(empty)' : (v === null || v === undefined || v === '' ? '(empty)' : esc(String(v)));
  const rel = r => `<span class="badge">${esc(r.rel)}</span> ${esc(r.target)}${basisBadge(r)}`;
  const ev = e => `<b>${esc(e.id)}</b> ${docLink(e.path, 'L=' + encodeURIComponent(e.lines), '· L' + esc(e.lines))} <span class="small">${esc((e.quote || '').slice(0, 120))}</span>`;
  const sec = (title, items, cls) => items.length ? `<h4 style="margin:12px 0 4px">${title} (${items.length})</h4><ul class="small">${items.map(x => `<li class="${cls || ''}">${x}</li>`).join('')}</ul>` : '';
  const nothing = !sd.fields.length && !sd.relations_added.length && !sd.relations_removed.length && !sd.relations_changed.length &&
    !sd.evidence_added.length && !sd.evidence_removed.length && !sd.body;
  return `<div class="banner info small">r${sd.a || '(empty)'} → r${sd.b} · ${originLabel(sd.origin, false)}${sd.change_note ? ' · ' + esc(sd.change_note) : ''}</div>
    ${nothing ? '<p class="muted">The two revisions are identical.</p>' : ''}
    ${sec('Field changes', sd.fields.map(f => `<b>${esc(FIELD_LABEL[f.field] || f.field)}</b>: <span class="diff"><span class="d">${val(f.before)}</span> → <span class="a">${val(f.after)}</span></span>`))}
    ${sec('Relations added', sd.relations_added.map(rel), 'a')}${sec('Relations removed', sd.relations_removed.map(rel), 'd')}
    ${sec('Relation status changes', sd.relations_changed.map(c => `${rel(c.before)} → ${basisBadge(c.after)}`))}
    ${sec('Evidence added', sd.evidence_added.map(ev), 'a')}
    ${(sd.evidence_moved || []).length ? (() => { const by = {}; sd.evidence_moved.forEach(e => e.moved_to.forEach(t => (by[t] = by[t] || []).push(e)));
      return `<h4 style="margin:12px 0 4px">Evidence moved to other cards (${sd.evidence_moved.length}, not lost)</h4><ul class="small">${Object.entries(by).map(([t, es]) =>
        `<li>→ <a href="#/review/${encodeURIComponent(t)}">${esc(t)}</a>: ${es.length} (${es.map(e => esc(e.id)).join(', ')})</li>`).join('')}</ul>`; })() : ''}
    ${sec('Evidence removed (no longer in any card)', sd.evidence_removed.map(ev), 'd')}
    ${sd.evidence_renumbered ? `<p class="small muted">${sd.evidence_renumbered} evidence item(s) only renumbered</p>` : ''}
    ${sd.body ? `<h4 style="margin:12px 0 4px">Body changes</h4><div class="diff">${sd.body.split('\n').slice(2).map(l => `<div class="${l.startsWith('+') ? 'a' : l.startsWith('-') ? 'd' : l.startsWith('@') ? 'h' : ''}">${esc(l) || ' '}</div>`).join('')}</div>` : '<p class="small muted">Body unchanged.</p>'}`;
}
function originLabel(o, link = true) {
  o = o || {};
  if (o.kind === 'llm') return link && o.run ? `<a href="#/traces/${esc(o.run)}">LLM ${esc(o.model || '')}</a>` : 'LLM compile ' + esc(o.model || '');
  if (o.kind === 'query') return link && o.run ? `<a href="#/ask/${esc(o.run)}">Filed from Ask ${esc(o.user || '')}</a>` : 'Filed from Ask ' + esc(o.user || '');
  if (o.kind === 'schema') return 'Schema topic skeleton' + (o.schema ? ' v' + esc(o.schema) : '');
  if (o.kind === 'human') return 'Human edit ' + esc(o.user || '');
  return esc(o.kind || '—');
}
function gbadge(g, card) {
  g = g || {};
  if (!g.total) return card && card.type === 'topic' ? '<span class="small muted">Topic card, no evidence needed</span>' : badge('missing', 'No evidence');
  const s = Math.round((g.score || 0) * 100);
  return `${badge(s >= 90 ? 'exact' : s >= 60 ? 'fuzzy' : 'missing', s + '%')}<span class="small muted">${(g.exact || 0) + (g.moved || 0) + (g.elided || 0) + (g.card || 0)}/${g.total || 0} verifiable${g.missing ? ', ' + g.missing + ' not found' : ''}</span>`;
}

async function reviewWorkspace(id, q) {
  const d = await get('cards/' + encodeURIComponent(id));
  const all = await get('cards');
  const h = d.head;
  const known = new Set(all.map(c => c.id));
  let trace = null;
  if (h.origin && h.origin.run) trace = await get('traces/' + h.origin.run).catch(() => null);
  const findings = trace ? (trace.run.findings || []).filter(f => f.card === id) : [];
  const tab = q.tab || 'card';
  const prev = h.rev > 1 ? h.rev - 1 : 0;
  const diffBase = q.base !== undefined ? +q.base : (h.published_rev && h.published_rev !== h.rev ? h.published_rev : prev);
  let tabBody = '';
  if (tab === 'card') tabBody = `<div class="doc"><h1>${esc(h.title)}</h1><p><i>${esc(h.summary)}</i></p>${renderCardBody(h, known)}${relationsBlock(h, d.backlinks)}</div>`;
  if (tab === 'diff') {
    const df = await get(`cards/${encodeURIComponent(id)}/diff?a=${diffBase}&b=${h.rev}`);
    tabBody = `<div class="row small">Compare: <select id="dbase">${[0, ...d.revisions.filter(r => r !== h.rev)].map(r => `<option value="${r}" ${r === diffBase ? 'selected' : ''}>${r ? 'r' + r + (r === h.published_rev ? ' (published)' : '') : '(empty)'}</option>`).join('')}</select> → r${h.rev}</div>
      ${semanticDiff(df.semantic)}
      <details style="margin-top:12px"><summary class="small muted">Raw text diff (frontmatter + body)</summary><div class="diff">${df.diff.split('\n').map(l => `<div class="${l.startsWith('+') ? 'a' : l.startsWith('-') ? 'd' : l.startsWith('@') ? 'h' : ''}">${esc(l) || ' '}</div>`).join('')}</div></details>`;
  }
  if (tab === 'edit') tabBody = `<p class="small muted">A manual edit creates a new revision (attributed to you) that goes back into review.</p>
      <div class="row"><label style="width:60px">Title</label><input id="e_title" value="${esc(h.title)}" style="flex:1"></div>
      <div class="row"><label style="width:60px">Type</label><select id="e_type">${Object.keys(TYPE_LABEL).map(t => `<option ${t === h.type ? 'selected' : ''} value="${t}">${esc(TYPE_LABEL[t])}</option>`).join('')}</select>
        <label>Parent topic</label><input id="e_parent" value="${esc(h.parent || '')}" list="cardids"><datalist id="cardids">${all.map(c => `<option value="${esc(c.id)}">${esc(c.title)}</option>`).join('')}</datalist></div>
      <div class="row"><label style="width:60px">Aliases</label><input id="e_aliases" value="${esc((h.aliases || []).join(', '))}" style="flex:1"></div>
      <div class="row"><label style="width:60px">Summary</label><input id="e_summary" value="${esc(h.summary || '')}" style="flex:1"></div>
      <label class="small">Body (Markdown; [[card-id]] links, [E1] evidence markers)</label><textarea id="e_body" class="code">${esc(h.body)}</textarea>
      <label class="small">Relations (JSON)</label><textarea id="e_rel" class="code" style="min-height:90px">${esc(JSON.stringify(h.relations || [], null, 1))}</textarea>
      <label class="small">Evidence (JSON: id, path, lines, quote — re-verified automatically on save)</label><textarea id="e_ev" class="code" style="min-height:140px">${esc(JSON.stringify((h.evidence || []).map(e => ({ id: e.id, path: e.path, lines: e.lines, quote: e.quote })), null, 1))}</textarea>
      <div class="row"><input id="e_note" placeholder="Change note" style="flex:1"><button class="primary" id="e_save">Save as new revision</button></div>`;
  if (tab === 'history') tabBody = `<table class="grid"><tr><th>Time</th><th>Who</th><th>Action</th><th>Revision</th><th>Note</th></tr>${(d.review_log || []).slice().reverse().map(r =>
      `<tr><td class="small">${fmtTime(r.ts)}</td><td>${esc(r.user)} <span class="muted small">${esc(r.role)}</span></td><td>${badge(r.verdict)}${r.target ? ' → ' + esc(r.target) : ''}</td><td>r${r.rev}</td><td>${esc(r.comment || '')}${r.anchor ? ` <span class="muted small">@${esc(r.anchor)}</span>` : ''}</td></tr>`).join('') || '<tr><td colspan=5 class="muted">No review records yet</td></tr>'}</table>
    <h3>Revisions</h3><p>${d.revisions.map(r => `<a href="#/review/${encodeURIComponent(id)}?tab=rev&r=${r}">r${r}</a>${r === h.published_rev ? ' (published)' : ''}`).join(' · ')}</p>
    <h3>Events</h3><table class="grid">${(d.events || []).slice().reverse().map(e => `<tr><td class="small">${fmtTime(e.ts)}</td><td>${esc(e.actor)}</td><td class="mono">${esc(e.action)}</td><td class="small mono">${esc(JSON.stringify(e.detail || {}))}</td></tr>`).join('')}</table>`;
  if (tab === 'rev') {
    const r = await get(`cards/${encodeURIComponent(id)}/rev/${+q.r}`);
    tabBody = `<p class="small muted">Revision r${r.rev} · ${fmtTime(r.created)} · ${originLabel(r.origin, false)} · ${esc(r.change_note || '')}</p><div class="doc"><h1>${esc(r.title)}</h1>${renderCardBody(r, known)}</div>${evidenceList(r)}`;
  }
  const v = d.reviews.votes;
  const isAdmin = can('admin');
  const adminBtns = isAdmin ? `<div class="row"><b class="small">Admin decision:</b>
      ${h.status === 'approved' ? '<button class="primary" data-act="publish">Publish</button>' : ''}
      ${['approved', 'in_review', 'rejected'].includes(h.status) ? '<button class="warn" data-act="return">Send back for changes</button>' : ''}
      ${h.status !== 'rejected' && h.status !== 'published' ? '<button class="bad" data-act="reject">Reject</button>' : ''}
      ${['rejected', 'changes_requested'].includes(h.status) ? '<button data-act="reopen">Reopen review</button>' : ''}
      ${h.published_rev && h.lifecycle === 'active' ? '<button class="bad" data-act="withdraw">Withdraw</button><button data-act="supersede">Supersede…</button>' : ''}
      ${h.lifecycle !== 'active' ? '<button class="ok" data-act="restore">Restore</button>' : ''}</div>` : '';
  set(`<div class="row"><a href="#/review?s=${h.status}">← Review queue</a> <span class="mono muted">${esc(id)}</span> ${badge(h.status)} ${badge(h.lifecycle)}
      <span class="small muted">r${h.rev}${h.published_rev ? ' · published r' + h.published_rev : ''} · ${originLabel(h.origin, false)} · <a href="${cardHref(id)}?view=head">Reader view</a></span></div>
    ${h.change_note ? `<div class="banner info">Change note: ${esc(h.change_note)}</div>` : ''}
    ${(h.stale_sources || []).length ? `<div class="banner warn">Source changed after compilation: ${h.stale_sources.map(esc).join(', ')} — recompile recommended</div>` : ''}
    <div class="cols3"><section class="panel"><div class="tabs">${[['card', 'Card'], ['diff', 'Diff'], ['edit', 'Edit'], ['history', 'Review history']].map(([t, n]) =>
      `<a href="#/review/${encodeURIComponent(id)}?tab=${t}" class="${t === tab ? 'on' : ''}">${n}</a>`).join('')}</div>${tabBody}</section>
    <aside class="panel side" style="max-height:none;position:static">
      <h3 style="margin-top:0">Review decision</h3>
      <p class="small">Votes on r${h.rev}: ${badge('approve', 'Approve ' + v.approve)}${badge('request_changes', 'Request changes ' + v.request_changes)}${badge('reject', 'Reject ' + v.reject)}</p>
      <textarea id="rv_comment" placeholder="Comment (required to request changes, reject or send back)"></textarea>
      <div class="row"><input id="rv_anchor" placeholder="Anchor, e.g. E2 or a paragraph (optional)" style="flex:1"></div>
      <div class="row"><button class="ok" data-act="approve">Approve</button><button class="warn" data-act="request_changes">Request changes</button><button class="bad" data-act="reject">Reject</button><button data-act="comment">Comment only</button>
        ${['draft', 'changes_requested'].includes(h.status) ? '<button data-act="submit">Submit for review</button>' : ''}</div>
      ${adminBtns}
      ${d.risk ? `<h3>Review risk ${riskBadge(d.risk)}</h3>${d.risk.reasons.length ? `<ul class="small">${d.risk.reasons.map(r => `<li>${esc(r)}</li>`).join('')}</ul>` : '<p class="small muted">All evidence matches the source exactly; no ambiguous relations; single source; granularity OK.</p>'}
        <p class="small">Length: ${sizeBadge(d.risk.granularity)}${d.risk.granularity.needs_consolidation ? ` <button id="consolidate" class="warn">Consolidate / split</button>` : ''}
        ${can('admin') && (d.risk.granularity.issues || []).includes('thin') ? ` <button id="mergeinto">Merge into another card…</button>` : ''}</p>` : ''}
      <h3>Epistemic status of relations</h3><p>${basisSummary(h.relations)}</p>
      <h3>Evidence verification ${gbadge(h.grounding, h)}</h3>
      <p class="small muted">Every quote the model gives is checked verbatim against the source lines. Context for exact matches is collapsed by default; items that need human confirmation are expanded.</p>
      ${evidenceList(h, true)}
      ${findings.length ? `<h3>Compiler validation findings</h3><ul class="small">${findings.map(f => `<li>${badge(f.level === 'error' ? 'error' : 'warn', f.level)} ${esc(f.msg)}</li>`).join('')}</ul>` : ''}
      ${h.origin.kind === 'query' ? `<div class="banner info">This card was filed back from Ask: <a href="#/ask/${esc(h.origin.run)}">View the original question and reading plan</a></div>` : ''}
      ${trace && trace.run.kind !== 'query' ? `<h3>LLM compile trace</h3><div class="kv"><div>Run</div><div><a href="#/traces/${esc(trace.run.id)}">${esc(trace.run.id)}</a></div><div>Model</div><div>${esc(trace.run.model)}</div>
        <div>Latency</div><div>${trace.run.latency_s}s</div><div>Confidence</div><div>${h.confidence ?? '—'}</div>
        <div>Schema</div><div>${trace.run.schema ? `<a href="#/schema?v=${trace.run.schema.version}">v${trace.run.schema.version}</a>` : '—'}</div>
        ${(trace.run.sections || []).length ? `<div>Section compile</div><div class="small">${trace.run.sections.map(x => esc(x.path + ' §' + x.part + ' L' + x.lines)).join('<br>')}</div>` : ''}</div>
        ${trace.run.notes ? `<p class="small"><b>Compiler notes:</b>${esc(trace.run.notes)}</p>` : ''}
        <details><summary class="small">Model thinking summary</summary><pre class="box">${esc(trace['thinking.md'] || '')}</pre></details>` : ''}
    </aside></div>`);
  bindEvidence($('#main'));
  fillSourceLines($('#main'));
  const db = $('#dbase'); if (db) db.onchange = () => { location.hash = `#/review/${encodeURIComponent(id)}?tab=diff&base=${db.value}`; };
  document.querySelectorAll('[data-act]').forEach(b => b.onclick = async () => {
    const act = b.dataset.act;
    const comment = $('#rv_comment').value.trim();
    if (['request_changes', 'reject', 'return'].includes(act) && !comment) return toast('Please enter a comment');
    let target = '';
    if (act === 'supersede') { target = prompt('Supersede with which card (id)?') || ''; if (!target) return; }
    if (['publish', 'withdraw', 'reject'].includes(act) && !confirm(`Confirm: ${stLabel(act)}?`)) return;
    try { await api('POST', `cards/${encodeURIComponent(id)}/action`, { action: act, comment, target, anchor: $('#rv_anchor').value.trim() }); toast(stLabel(act) + ' ✓'); route(); }
    catch (e) { toast(e.message); }
  });
  const cb = $('#consolidate'); if (cb) cb.onclick = async () => {
    if (!confirm('Have the LLM consolidate and rewrite this card (splitting it into sub-concept cards if needed)? Only the card\'s existing verified evidence is used; the result enters review as a new revision.')) return;
    cb.disabled = true; cb.textContent = 'Consolidating…';
    try { const r = await api('POST', `cards/${encodeURIComponent(id)}/consolidate`, {});
      if (r.status !== 'done') throw new Error(r.error || 'Failed');
      toast(`Consolidated: ${r.before.units} → ${r.after.units} words; wrote ${r.written.length} card revision(s)`, 6000);
      location.hash = `#/review/${encodeURIComponent(id)}?tab=diff`; route();
    } catch (e) { toast('Consolidation failed: ' + e.message); cb.disabled = false; cb.textContent = 'Consolidate / split'; }
  };
  const mb = $('#mergeinto'); if (mb) mb.onclick = async () => {
    const into = prompt('Merge this card into which card (id)? This card will be marked as superseded.'); if (!into) return;
    try { const r = await api('POST', `cards/${encodeURIComponent(id)}/merge`, { into }); toast('Merged into ' + into + ' (r' + r.rev + ', awaiting review)'); location.hash = '#/review/' + encodeURIComponent(into) + '?tab=diff'; }
    catch (e) { toast(e.message); }
  };
  const sv = $('#e_save'); if (sv) sv.onclick = async () => {
    try {
      const body = { title: $('#e_title').value, type: $('#e_type').value, parent: $('#e_parent').value.trim(), summary: $('#e_summary').value,
        aliases: $('#e_aliases').value.split(',').map(s => s.trim()).filter(Boolean), body: $('#e_body').value,
        relations: JSON.parse($('#e_rel').value || '[]'), evidence: JSON.parse($('#e_ev').value || '[]'), change_note: $('#e_note').value || 'Manual edit' };
      const r = await api('PUT', 'cards/' + encodeURIComponent(id), body); toast('Saved as r' + r.rev); location.hash = `#/review/${encodeURIComponent(id)}?tab=diff`;
    } catch (e) { toast('Save failed: ' + e.message); }
  };
}

// ---------------------------------------------------------------- LLM observability
routes.traces = async ([rid], q) => {
  if (rid) return traceView(rid, q);
  const [runs, st] = await Promise.all([get('traces'), get('traces/stats')]);
  const g = st.grounding;
  set(`<h1>LLM traces</h1><p class="muted">A full record of every knowledge-compile call: prompts, raw model output, thinking summary, usage, latency, validation and evidence-verification results.</p>
    <div class="stats"><div class="stat"><b>${st.runs}</b><span>Calls (${st.failed || 0} failed)</span></div>
      <div class="stat"><b>${(st.input_tokens / 1000).toFixed(1)}k / ${(st.output_tokens / 1000).toFixed(1)}k</b><span>Input / output tokens</span></div>
      <div class="stat"><b>$${st.cost_usd}</b><span>Estimated cost</span></div><div class="stat"><b>${st.runs ? (st.latency_s / st.runs).toFixed(1) : 0}s</b><span>Avg latency</span></div>
      <div class="stat"><b>${st.cards_written}</b><span>Card revisions written</span></div>
      <div class="stat"><b>${g.total ? Math.round((g.exact + g.moved) / g.total * 100) : 0}%</b><span>Quotes verifiable in source (${g.exact + g.moved}/${g.total})</span></div></div>
    <div class="cols3"><section class="panel"><table class="grid"><tr><th>Run</th><th>Type</th><th>Status</th><th>Sources / question</th><th>Model</th><th>Latency</th><th>Cards</th><th>Verification</th><th>Findings</th></tr>
      ${runs.map(r => `<tr><td><a href="#/traces/${esc(r.id)}" class="mono">${esc(r.id)}</a><br><span class="small muted">${esc(r.by)}</span></td><td>${r.kind === 'query' ? badge('comment', 'Ask') : badge('t', 'Compile')}${(r.sections || []).length ? badge('t', 'Section ' + r.sections[0].part) : ''}</td><td>${badge(r.status)}</td>
        <td class="small">${r.kind === 'query' ? esc((r.question || '').slice(0, 60)) : r.sources.map(esc).join('<br>')}</td>
        <td class="small">${esc(r.model || '')}</td><td>${r.latency_s ?? ''}s</td><td>${(r.written || []).length}</td><td>${r.grounding ? gbadge(r.grounding) : ''}</td><td>${(r.findings || []).length}</td></tr>`).join('')}</table></section>
    <aside class="panel"><h3 style="margin-top:0">Common validation findings</h3><table class="grid">${Object.entries(st.findings).sort((a, b) => b[1] - a[1]).map(([k, n]) => `<tr><td class="small">${esc(k)}</td><td>${n}</td></tr>`).join('') || '<tr><td class="muted">None</td></tr>'}</table>
      <h3>Relation epistemic status (cumulative)</h3><p>${Object.entries(st.bases).map(([b, n]) => badge(b === 'extracted' ? 'exact' : b === 'ambiguous' ? 'request_changes' : 'comment', stLabel(b) + ' ' + n)).join(' ')}</p>
      <h3>By schema version</h3><table class="grid">${Object.entries(st.by_schema).map(([v, x]) => `<tr><td><a href="#/schema?v=${v.slice(1)}">${esc(v)}</a></td><td>${x.runs} runs</td><td>verifiable ${x.total ? Math.round(x.exact / x.total * 100) : 0}%</td></tr>`).join('') || '<tr><td class="muted">None</td></tr>'}</table>
      <h3>By model</h3><table class="grid">${Object.entries(st.by_model).map(([m, x]) => `<tr><td class="small">${esc(m)}</td><td>${x.runs} runs</td><td>${(x.latency_s / x.runs).toFixed(1)}s</td></tr>`).join('')}</table></aside></div>`);
};

async function traceView(rid, q) {
  const t = await get('traces/' + encodeURIComponent(rid));
  const r = t.run;
  const tab = q.tab || 'overview';
  const NAMES = { 'thinking.md': 'Thinking summary', 'prompt.md': 'User prompt', 'system.md': 'System prompt', 'response.md': 'Raw output', 'parsed.json': 'Parsed result', 'error.txt': 'Error' };
  const order = ['thinking.md', 'prompt.md', 'system.md', 'response.md', 'parsed.json', 'error.txt'];
  const files = Object.keys(t).filter(k => k !== 'run');
  // file prefixes: nav- / nav2- … (navigation rounds), idx- (index), ans- (answer), retryN- / ans-retryN- (corrective retries)
  const pre = f => (f.match(/^((?:nav\d*|ans|idx)-)?(retry\d+-)?/) || [''])[0];
  const stage = f => { const m = f.match(/^(nav(\d*)|ans|idx)-/); return !m ? 'Compile' : m[1] === 'ans' ? 'Answer' : m[1] === 'idx' ? 'Index' : 'Navigate' + (m[2] ? ' round ' + m[2] : ''); };
  const rank = f => { const m = f.match(/^nav(\d*)-/); return f.startsWith('ans-') ? 100 : m ? (+m[2 - 1] || 1) : 0; };
  const label = f => { const p = pre(f); const r = (p.match(/retry(\d+)-/) || [])[1];
    return (p ? stage(f) + (r ? ' · retry ' + r : '') + ' · ' : '') + (NAMES[f.slice(p.length)] || f); };
  files.sort((a, b) => rank(a) - rank(b) || pre(a).localeCompare(pre(b)) || order.indexOf(a.slice(pre(a).length)) - order.indexOf(b.slice(pre(b).length)));
  const tabs = [['overview', 'Overview'], ...files.map(f => [f, label(f)])];
  const u = r.usage || {};
  let body = '';
  if (tab === 'overview' && r.kind === 'query') body = `<div class="kv"><div>Question</div><div><b>${esc(r.question)}</b></div><div>Status</div><div>${badge(r.status)} ${esc(r.error || '')}</div>
      <div>Asked by</div><div>${esc(r.by)} · scope: ${r.scope === 'all' ? 'incl. unpublished' : 'published only'}</div><div>Backend / model</div><div>${esc(r.backend)} / ${esc(r.model)}</div>
      <div>Latency / cost</div><div>${r.latency_s}s ${r.cost_usd !== undefined ? '· $' + r.cost_usd : ''}</div><div>Quote verification</div><div>${r.grounding ? gbadge(r.grounding) : ''}</div></div>
      <p><a href="#/ask/${esc(r.id)}">View the answer and reading plan in Ask →</a></p>
      <h3>LLM calls <span class="muted small">(each runs the LangGraph CALL graph)</span></h3><table class="grid"><tr><th>Step</th><th>Model</th><th>Latency</th><th>Usage</th><th>Prompt</th><th>Graph path</th></tr>${(r.calls || []).map(c => `<tr><td>${esc(c.step)}</td><td class="small">${esc(c.model)}</td><td>${c.latency_s}s</td><td class="small mono">${esc(JSON.stringify(c.usage))}</td><td class="small">${(c.prompt_chars / 1000).toFixed(1)}k chars</td><td class="small mono">${esc((c.graph_path || []).join(' → '))}${c.watchdog_aborts ? ' <span class="badge b-request_changes">watchdog step-down ×' + c.watchdog_aborts.length + '</span>' : ''}${c.transient_retries ? ' <span class="badge">retried ×' + c.transient_retries + '</span>' : ''}</td></tr>`).join('')}</table>
      ${(r.graph || []).length ? `<h3>Pipeline graph <span class="muted small">(LangGraph node visits, in order)</span></h3><p class="small mono">${r.graph.map(g => `<span title="${esc(JSON.stringify(Object.fromEntries(Object.entries(g).filter(([k]) => !['graph', 'node'].includes(k)))))}">${esc(g.graph)}.${esc(g.node)}</span>`).join(' → ')}</p>` : ''}
      <h3>Timeline</h3><ul class="timeline">${(r.timeline || []).map(s => `<li><span class="mono">${fmtTime(s.ts).slice(11)}</span> ${esc(s.step)} <span class="muted">${esc(JSON.stringify(Object.fromEntries(Object.entries(s).filter(([k]) => !['ts', 'step'].includes(k)))))}</span></li>`).join('')}</ul>`;
  else if (tab === 'overview') body = `<div class="kv"><div>Status</div><div>${badge(r.status)} ${esc(r.error || '')}</div><div>Started by</div><div>${esc(r.by)}</div>
      <div>Backend / model</div><div>${esc(r.backend)} / ${esc(r.model)} ${r.effort ? '· effort ' + esc(r.effort) : ''}</div><div>Prompt version</div><div class="mono">${esc(r.prompt_version)}</div>
      <div>Schema</div><div>${r.schema ? `<a href="#/schema?v=${r.schema.version}">SCHEMA.md v${r.schema.version}</a> <span class="mono small muted">${esc(r.schema.sha)}</span>` : '—'}</div>
      ${(r.sections || []).length ? `<div>Section compile</div><div class="small">${r.sections.map(x => `${esc(x.path)} §${esc(x.part)} L${esc(x.lines)}: ${x.titles.map(esc).join(', ')}`).join('<br>')}</div>` : ''}
      <div>Relation status</div><div>${r.bases ? Object.entries(r.bases).map(([b, n]) => stLabel(b) + ' ' + n).join(' · ') : '—'}</div>
      <div>Source documents</div><div>${r.sources.map(s => `<a href="${srcHref(s)}">${esc(s)}</a> <span class="mono small muted">${esc((r.source_shas[s] || '').slice(0, 10))}</span>`).join('<br>')}</div>
      <div>Context</div><div class="small">${r.context ? `index of ${r.context.index_cards} cards · ${r.context.related_cards.length} related cards in full · prompt ${(r.context.prompt_chars / 1000).toFixed(1)}k chars` : ''}</div>
      <div>Usage</div><div class="small mono">${esc(JSON.stringify(u))}</div><div>Latency / cost</div><div>${r.latency_s}s ${r.cost_usd !== undefined ? '· $' + r.cost_usd : ''} · stop=${esc(r.stop_reason || '')}${r.attempts > 1 ? ' · ' + badge('warn', 'retried ' + (r.attempts - 1) + '×') : ''}</div>
      ${(r.attempt_errors || []).length ? `<div>Invalid outputs</div><div class="small">${r.attempt_errors.map(esc).join('<br>')}</div>` : ''}
      <div>Evidence verification</div><div>${r.grounding ? gbadge(r.grounding) : ''}</div></div>
    ${r.notes ? `<h3>Compiler notes (for reviewers)</h3><div class="banner info">${esc(r.notes)}</div>` : ''}
    <h3>Card revisions written</h3><table class="grid">${(r.written || []).map(w => `<tr><td><a href="#/review/${encodeURIComponent(w.id)}">${esc(w.id)}</a></td><td>${w.action === 'create' ? 'Created' : 'Updated'}</td><td>r${w.rev}</td><td>${gbadge(w.grounding)}</td></tr>`).join('') || '<tr><td class="muted">None</td></tr>'}</table>
    <h3>Validation findings (${(r.findings || []).length})</h3><table class="grid">${(r.findings || []).map(f => `<tr><td>${badge(f.level === 'error' ? 'error' : f.level === 'info' ? 'comment' : 'warn', f.level)}</td><td class="mono small">${esc(f.card)}</td><td class="small">${esc(f.msg)}</td></tr>`).join('') || '<tr><td class="muted">None</td></tr>'}</table>
    <h3>Timeline</h3><ul class="timeline">${(r.timeline || []).map(s => `<li><span class="mono">${fmtTime(s.ts).slice(11)}</span> ${esc(s.step)} <span class="muted">${esc(JSON.stringify(Object.fromEntries(Object.entries(s).filter(([k]) => !['ts', 'step'].includes(k)))))}</span></li>`).join('')}</ul>`;
  else {
    const key = tab;
    body = `<p class="small muted">${(t[key] || '').length} chars · exactly as sent to / received from the model, unmodified.</p><pre class="box">${esc(t[key] || '(none)')}</pre>`;
  }
  set(`<div class="row"><a href="#/traces">← LLM traces</a><span class="mono">${esc(rid)}</span></div><div class="panel"><div class="tabs">${tabs.map(([k, n]) => `<a href="#/traces/${esc(rid)}?tab=${encodeURIComponent(k)}" class="${k === tab ? 'on' : ''}">${n}</a>`).join('')}</div>${body}</div>`);
}

routes.lint = async () => {
  const issues = await get('lint');
  const KIND = { dangling_relation: 'Relation points to a missing card', dangling_wikilink: 'Body link points to a missing card', dangling_parent: 'Parent topic does not exist', stale_source: 'Source updated (recompile needed)',
    ungrounded_evidence: 'Quote not found in source', no_evidence: 'No evidence', dangling_replacement: 'Replacement target does not exist',
    ambiguous_relation: 'Has “ambiguous” relations awaiting human judgement', missing_summary: 'Document has no summary card (recompile needed)', duplicate_source: 'Source documents largely duplicate each other',
    granularity_thin: 'Too thin (single fact; merge into a related card)', granularity_too_long: 'Too long (consolidate or split)',
    granularity_fragmented: 'Too many addenda (consolidate and rewrite)', granularity_broad: 'Too much evidence (may cover several concepts)' };
  set(`<div class="panel"><h1>Knowledge base health check</h1><p class="muted">${issues.length} issue(s)</p><table class="grid"><tr><th>Card</th><th>Issue</th><th>Detail</th></tr>${issues.map(i =>
    `<tr><td><a href="#/review/${encodeURIComponent(i.card)}">${esc(i.card)}</a></td><td>${esc(KIND[i.kind] || i.kind)}</td><td class="small">${esc(i.detail)}</td></tr>`).join('')}</table></div>`);
};

// ---------------------------------------------------------------- admin
routes.publish = async () => {
  const cards = await get('cards');
  const appr = cards.filter(c => c.status === 'approved');
  const pub = cards.filter(c => c.published_rev);
  set(`<div class="panel"><h1>Publishing desk</h1><h3>Approved, awaiting publication (${appr.length})</h3>
    ${appr.length > 1 ? `<details style="margin:6px 0"><summary class="small"><b>Batch publish</b> (<span id="psel">0</span> selected; a comment is required and recorded in the audit log)</summary>
      <div class="row"><button id="psall">Select all</button></div><textarea id="pcomment" placeholder="Publish comment (required, at least 10 characters), e.g. “Cards for lecture 14, each approved by two reviewers”"></textarea>
      <div class="row"><button class="primary" id="pgo">Publish selected</button></div></details>` : ''}
    <table class="grid"><tr><th></th><th>Card</th><th>Revision</th><th>Verification</th><th>Currently live</th><th></th></tr>${appr.map(c => `<tr><td><input type="checkbox" class="psel" value="${esc(c.id)}"></td><td><a href="#/review/${encodeURIComponent(c.id)}">${esc(c.title)}</a></td><td>r${c.rev}</td><td>${gbadge(c.grounding, c)}</td>
      <td>${c.published_rev ? 'r' + c.published_rev : '—'}</td><td><button class="primary" data-pub="${esc(c.id)}">Publish</button> <button class="warn" data-ret="${esc(c.id)}">Send back</button></td></tr>`).join('') || '<tr><td colspan=6 class="muted">None</td></tr>'}</table>
    <h3>Published content (${pub.length})</h3><table class="grid"><tr><th>Card</th><th>Live revision</th><th>Status</th><th>Published</th><th></th></tr>${pub.map(c => `<tr><td><a href="${cardHref(c.id)}">${esc(c.title)}</a></td><td>r${c.published_rev}${c.rev !== c.published_rev ? ` <span class="small muted">(new revision r${c.rev} ${stLabel(c.status)})</span>` : ''}</td>
      <td>${badge(c.lifecycle)}${c.replaced_by ? ' → ' + esc(c.replaced_by) : ''}${(c.stale_sources || []).length ? badge('stale', 'Source changed') : ''}</td><td class="small">${esc(c.published_by || '')} ${fmtTime(c.published_at)}</td>
      <td>${c.lifecycle === 'active' ? `<button class="bad" data-wd="${esc(c.id)}">Withdraw</button> <button data-sup="${esc(c.id)}">Supersede…</button>` : `<button class="ok" data-rs="${esc(c.id)}">Restore</button>`}</td></tr>`).join('')}</table></div>`);
  const act = async (id, action, extra = {}) => { try { await api('POST', `cards/${encodeURIComponent(id)}/action`, { action, ...extra }); toast(stLabel(action) + ' ✓'); route(); } catch (e) { toast(e.message); } };
  document.querySelectorAll('[data-pub]').forEach(b => b.onclick = () => act(b.dataset.pub, 'publish'));
  const pboxes = () => [...document.querySelectorAll('.psel')];
  const pupd = () => { const el = $('#psel'); if (el) el.textContent = pboxes().filter(b => b.checked).length; };
  pboxes().forEach(b => b.onchange = pupd);
  if ($('#psall')) $('#psall').onclick = () => { pboxes().forEach(b => b.checked = true); pupd(); };
  if ($('#pgo')) $('#pgo').onclick = async () => {
    const ids = pboxes().filter(b => b.checked).map(b => b.value), comment = $('#pcomment').value.trim();
    if (!ids.length) return toast('No cards selected');
    if (comment.length < 10) return toast('Batch publishing requires a comment (at least 10 characters)');
    if (!confirm(`Publish ${ids.length} card(s)? They will become visible to readers.`)) return;
    try { const r = await api('POST', 'cards/_batch', { ids, action: 'publish', comment }); toast(`${r.batch}: published ${r.done.length}`); route(); }
    catch (e) { toast(e.message); }
  };
  document.querySelectorAll('[data-ret]').forEach(b => b.onclick = () => { const c = prompt('Reason for sending back:'); if (c) act(b.dataset.ret, 'return', { comment: c }); });
  document.querySelectorAll('[data-wd]').forEach(b => b.onclick = () => { const c = prompt('Reason for withdrawal:'); if (c !== null) act(b.dataset.wd, 'withdraw', { comment: c }); });
  document.querySelectorAll('[data-rs]').forEach(b => b.onclick = () => act(b.dataset.rs, 'restore'));
  document.querySelectorAll('[data-sup]').forEach(b => b.onclick = () => { const t = prompt('Supersede with which card (id)?'); if (t) act(b.dataset.sup, 'supersede', { target: t, comment: prompt('Note:') || '' }); });
};

routes.compile = async () => {
  const [plan, jobs, tree] = await Promise.all([get('compile/plan'), get('compile/jobs'), get('compile/plan?all=1')]);
  const changed = new Set(plan.paths);
  set(`<div class="cols3"><section class="panel"><h1>Knowledge compilation</h1>
    <p class="muted small">Whole documents go to the LLM (no chunking, no embeddings), together with the index of all cards and the full text of cards already compiled from these documents, so the model updates rather than duplicates. All output goes to the review queue.</p>
    <div class="row"><button id="selchg">Select changed (${plan.paths.length})</button><button id="selall">Select all</button><button id="selnone">Clear</button></div>
    <div style="max-height:360px;overflow:auto;border:1px solid var(--line);border-radius:6px;padding:6px 10px">${tree.paths.map(p =>
      `<label class="row" style="margin:2px 0"><input type="checkbox" class="cp" value="${esc(p)}" ${changed.has(p) ? 'checked' : ''}><span class="mono">${esc(p)}</span>${changed.has(p) ? badge('warn', 'New / changed') : ''}</label>`).join('')}</div>
    <div class="row"><label>Backend</label><select id="cbackend">${['mock', 'openrouter', 'anthropic', 'command'].map(b => `<option ${b === plan.backend ? 'selected' : ''}>${b}</option>`).join('')}</select>
      <span class="small muted">Default model ${esc(plan.model)} (config.json)</span><label>Docs per call</label><input id="cfpc" type="number" min="1" value="1" style="width:60px"></div>
    <textarea id="cinst" placeholder="Extra instructions for the compiler (optional), e.g. focus on model parameters and typical values"></textarea>
    <div class="row"><button class="primary" id="cgo">Start compile</button></div></section>
    <aside class="panel"><h3 style="margin-top:0">Jobs</h3>${jobs.map(j => `<div style="border-bottom:1px solid var(--line);padding:6px 0"><span class="mono">${esc(j.id)}</span> ${badge(j.status)} ${j.done}/${j.total}<br>
      <span class="small muted">${esc(j.by)} · ${fmtTime(j.at)} · ${esc(j.backend)}</span><br>${j.runs.map(r => `<a class="mono small" href="#/traces/${esc(r)}">${esc(r)}</a>`).join('<br>')}</div>`).join('') || '<p class="muted">No jobs since the server started</p>'}</aside></div>`);
  const boxes = () => [...document.querySelectorAll('.cp')];
  $('#selchg').onclick = () => boxes().forEach(b => b.checked = changed.has(b.value));
  $('#selall').onclick = () => boxes().forEach(b => b.checked = true);
  $('#selnone').onclick = () => boxes().forEach(b => b.checked = false);
  $('#cgo').onclick = async () => {
    const paths = boxes().filter(b => b.checked).map(b => b.value);
    if (!paths.length) return toast('No documents selected');
    try {
      const j = await api('POST', 'compile', { paths, backend: $('#cbackend').value, instructions: $('#cinst').value, files_per_call: +$('#cfpc').value || 1 });
      toast('Started ' + j.id); poll(j.id);
    } catch (e) { toast(e.message); }
  };
  const running = jobs.find(j => j.status === 'running' || j.status === 'queued'); if (running) poll(running.id);
}
function poll(jid) {
  const t = setInterval(async () => {
    if (!location.hash.startsWith('#/compile')) return clearInterval(t);
    const jobs = await get('compile/jobs').catch(() => []);
    const j = jobs.find(x => x.id === jid);
    if (!j || j.status === 'done') { clearInterval(t); toast('Compile finished'); route(); }
  }, 1500);
}

routes.users = async () => {
  const users = await get('users');
  const roles = ['reader', 'reviewer', 'admin'], RZ = ROLE_LABEL;
  set(`<div class="panel"><h1>Users and roles</h1><table class="grid"><tr><th>User</th><th>Display name</th><th>Role</th><th>Status</th><th>Created</th><th></th></tr>
    ${users.map(u => `<tr><td class="mono">${esc(u.name)}</td><td>${esc(u.display)}</td><td><select data-role="${esc(u.name)}">${roles.map(r => `<option value="${r}" ${r === u.role ? 'selected' : ''}>${RZ[r]}</option>`).join('')}</select></td>
      <td>${u.active ? badge('active', 'Active') : badge('withdrawn', 'Disabled')}</td><td class="small">${fmtTime(u.created)}</td>
      <td><button data-toggle-user="${esc(u.name)}" data-active="${u.active}">${u.active ? 'Disable' : 'Enable'}</button> <button data-pw="${esc(u.name)}">Reset password</button></td></tr>`).join('')}</table>
    <h3>Add user</h3><div class="row"><input id="nu" placeholder="Username"><input id="nd" placeholder="Display name"><input id="np" type="password" placeholder="Initial password">
      <select id="nr">${roles.map(r => `<option value="${r}">${RZ[r]}</option>`).join('')}</select><button class="primary" id="nadd">Add</button></div></div>`);
  const upd = async (n, b) => { try { await api('PUT', 'users/' + encodeURIComponent(n), b); toast('Updated'); route(); } catch (e) { toast(e.message); route(); } };
  document.querySelectorAll('[data-role]').forEach(s => s.onchange = () => upd(s.dataset.role, { role: s.value }));
  document.querySelectorAll('[data-toggle-user]').forEach(b => b.onclick = () => upd(b.dataset.toggleUser, { active: b.dataset.active !== 'true' }));
  document.querySelectorAll('[data-pw]').forEach(b => b.onclick = () => { const p = prompt('New password:'); if (p) upd(b.dataset.pw, { password: p }); });
  $('#nadd').onclick = async () => { try { await api('POST', 'users', { name: $('#nu').value.trim(), display: $('#nd').value.trim(), password: $('#np').value, role: $('#nr').value }); toast('Added'); route(); } catch (e) { toast(e.message); } };
};

routes.log = async (_, q) => {
  const evs = await get('events?limit=500' + (q.target ? '&target=' + encodeURIComponent(q.target) : ''));
  set(`<div class="panel"><h1>Audit log</h1><p class="muted small">Every upload, compile, review, publish and user-management action (log/events.jsonl, append-only).</p>
    <div class="row"><input id="lf" placeholder="Filter…" style="width:260px"></div>
    <table class="grid" id="lt"><tr><th>Time</th><th>Who</th><th>Action</th><th>Target</th><th>Detail</th></tr>${evs.map(e => `<tr><td class="small">${fmtTime(e.ts)}</td><td>${esc(e.actor)}</td><td class="mono">${esc(e.action)}</td>
      <td class="small"><a href="#/log?target=${encodeURIComponent(e.target)}">${esc(e.target)}</a></td><td class="small mono">${esc(JSON.stringify(e.detail || {})).slice(0, 300)}</td></tr>`).join('')}</table></div>`);
  $('#lf').oninput = ev => { const f = ev.target.value.toLowerCase(); document.querySelectorAll('#lt tr').forEach((tr, i) => { if (i) tr.style.display = tr.textContent.toLowerCase().includes(f) ? '' : 'none'; }); };
};

// ---------------------------------------------------------------- ask (navigate → read → answer → file back)
routes.ask = async ([rid]) => {
  if (!S.me) { location.hash = '#/login'; return; }
  const hist = await get('queries?limit=30').catch(() => []);
  let run = null;
  if (rid) run = await get('queries/' + encodeURIComponent(rid));
  const all = await get('cards');
  const known = new Set(all.map(c => c.id));
  const histHtml = `<h3 style="margin-top:0">${can('reviewer') ? 'Recent questions' : 'My questions'}</h3>${hist.map(h =>
    `<div style="border-bottom:1px solid var(--line);padding:5px 0"><a href="#/ask/${esc(h.id)}" class="${h.id === rid ? 'on' : ''}">${esc((h.question || '').slice(0, 60))}</a><br>
     <span class="small muted">${esc(h.by)} · ${fmtTime(h.started)} ${h.status !== 'done' ? badge(h.status) : ''}${h.filed_as ? ' · filed as ' + esc(h.filed_as) : ''}</span></div>`).join('') || '<p class="muted small">None yet</p>'}`;
  let res = '';
  if (run) {
    const n = run.navigation || {}, a = run.answer || {};
    const evRender = (a.evidence || []).map(e => ({ ...e }));
    res = `<div class="row small muted">Question · ${esc(run.by)} · ${fmtTime(run.started)} · scope: ${run.scope === 'all' ? 'incl. unpublished' : 'published only'} ·
        ${run.latency_s}s · ${can('reviewer') ? `<a href="#/traces/${esc(run.id)}">Full LLM trace</a>` : ''}</div><h2 style="margin-top:4px">${esc(run.question)}</h2>
      ${run.status !== 'done' ? `<div class="banner bad">Failed: ${esc(run.error || '')}</div>` : `
      <details open><summary><b>① Reading plan</b> <span class="small muted">The model first looks at the knowledge tree and document outlines to decide what to read (no vector search)</span></summary>
        <div class="banner info">${esc(n.reasoning || '')}</div>
        <div class="small"><b>Cards read (${(n.cards || []).length}):</b>${(n.cards || []).map(c => `<a href="${cardHref(c)}">${esc(c)}</a>`).join(' · ') || '—'}</div>
        <div class="small"><b>Source sections read (${(n.sections || []).length}):</b><ul>${(n.sections || []).map(s => `<li><a href="${srcHref(s.path, 'L=' + s.lines)}">${esc(s.path)} › ${esc(s.title)}</a> <span class="muted">L${esc(s.lines)}</span> ${s.why ? '<span class="muted">— ' + esc(s.why) + '</span>' : ''}</li>`).join('') || '<li class="muted">None</li>'}</ul></div>
      </details>
      <h3>② Answer ${gbadge(run.grounding)} ${a.confidence != null ? `<span class="small muted">confidence ${a.confidence}</span>` : ''}</h3>
      <div class="doc">${renderCardBody({ body: a.answer_md }, known)}</div>
      ${a.gaps ? `<div class="banner warn">Gaps in sources: ${esc(a.gaps)}</div>` : ''}
      <h3>③ Quote verification</h3>${evidenceList({ evidence: evRender }, true)}
      ${can('reviewer') ? (run.filed_as ? `<div class="banner info">Filed as knowledge card <a href="#/review/${esc(run.filed_as)}">${esc(run.filed_as)}</a> (in review)</div>` :
        `<h3>④ File back as knowledge</h3><p class="small muted">A good answer becomes a “Q&amp;A synthesis” card in the review queue; once published it is part of the knowledge base — knowledge grows through use.</p>
        <div class="row"><input id="fb_title" placeholder="Card title (defaults to the question)" style="flex:1"><input id="fb_parent" placeholder="Parent topic id (optional)" list="cardids2"><datalist id="cardids2">${all.filter(c => c.type === 'topic').map(c => `<option value="${esc(c.id)}">${esc(c.title)}</option>`).join('')}</datalist>
        <button class="primary" id="fb_go">Submit as knowledge card</button></div>`) : ''}`}`;
  }
  set(`<div class="cols3"><section class="panel"><h1>Ask</h1>
      <p class="muted small">Answers come from the knowledge base: the model first reasons over the knowledge tree and document outlines to build a reading plan, then reads the selected cards and source sections closely. Every source quote in the answer is verified automatically.</p>
      <textarea id="qq" placeholder="e.g. What are the limits of the Hopkins model under EUV conditions? How does ILT differ from OPC?" style="min-height:70px"></textarea>
      ${await condBar()}
      <div class="row"><button class="primary" id="qgo">Ask</button>${can('reviewer') ? '<label class="small"><input type="checkbox" id="qall"> Include unpublished (in-review) cards</label>' : ''}<span id="qwait" class="small muted"></span></div>
      ${res}</section><aside class="panel">${histHtml}</aside></div>`);
  bindEvidence($('#main')); fillSourceLines($('#main')); bindCond();
  $('#qgo').onclick = async () => {
    const question = $('#qq').value.trim(); if (!question) return;
    document.querySelectorAll('[data-cond]').forEach(i => { S.cond[i.dataset.cond] = i.value.trim(); });
    try { localStorage.setItem('lkb_cond', JSON.stringify(S.cond)); } catch (e) {}
    $('#qgo').disabled = true; $('#qwait').textContent = 'The model is reading and answering…';
    try { const r = await api('POST', 'ask', { question, include_unpublished: !!($('#qall') && $('#qall').checked), cond: condQS() }); location.hash = '#/ask/' + r.id; }
    catch (e) { toast(e.message); $('#qgo').disabled = false; $('#qwait').textContent = ''; }
  };
  const fb = $('#fb_go'); if (fb) fb.onclick = async () => {
    try { const h = await api('POST', `queries/${encodeURIComponent(run.id)}/file`, { title: $('#fb_title').value.trim(), parent: $('#fb_parent').value.trim() });
      toast('Submitted as ' + h.id); location.hash = '#/review/' + encodeURIComponent(h.id); } catch (e) { toast(e.message); }
  };
};

// ---------------------------------------------------------------- schema (the compiler's "source code")
routes.schema = async (_, q) => {
  const sc = await get('schema');
  const v = q.v ? +q.v : sc.version;
  const text = v === sc.version ? sc.text : (await get('schema/v/' + v)).text;
  const prev = sc.history.filter(h => h.version < v).map(h => h.version).pop() || 0;
  const df = q.diff ? (await get(`schema/diff?a=${prev}&b=${v}`)).diff : '';
  const editable = can('admin') && v === sc.version;
  set(`<div class="cols3"><section class="panel"><h1>Schema: SCHEMA.md <span class="small muted">v${v}${v !== sc.version ? ' (old version)' : ' (current)'}</span></h1>
      <p class="small muted">The knowledge compiler reads this schema in full on every compile: domain ontology, topic skeleton, how to use card types, naming and writing conventions, what relations mean, and what not to compile.
      Editing it changes how knowledge is compiled, with no code changes; every compile trace records the version used, so results can be compared across versions. The fixed evidence / epistemic-label / output-format protocol lives in code and cannot be changed here.</p>
      <div class="tabs"><a href="#/schema?v=${v}" class="${!q.diff ? 'on' : ''}">${editable ? 'Edit' : 'View'}</a><a href="#/schema?v=${v}&diff=1" class="${q.diff ? 'on' : ''}">Diff vs previous</a></div>
      ${q.diff ? `<div class="diff">${df.split('\n').map(l => `<div class="${l.startsWith('+') ? 'a' : l.startsWith('-') ? 'd' : l.startsWith('@') ? 'h' : ''}">${esc(l) || ' '}</div>`).join('')}</div>` :
        editable ? `<textarea id="sc_text" class="code" style="min-height:60vh">${esc(text)}</textarea>
          <div class="row"><input id="sc_note" placeholder="Change note (required)" style="flex:1"><button class="primary" id="sc_save">Save as new version</button></div>`
        : `<div class="doc">${MD.render(text)}</div>`}</section>
    <aside class="panel"><h3 style="margin-top:0">Version history</h3><table class="grid">${sc.history.slice().reverse().map(h =>
      `<tr><td><a href="#/schema?v=${h.version}">v${h.version}</a></td><td class="small">${esc(h.by)}<br>${fmtTime(h.at)}</td><td class="small">${esc(h.note || '')}</td></tr>`).join('')}</table>
      <p class="small muted">In LLM traces you can compare quote-verification rates by schema version.</p></aside></div>`);
  const sv = $('#sc_save'); if (sv) sv.onclick = async () => {
    const note = $('#sc_note').value.trim(); if (!note) return toast('Please enter a change note');
    try { const e = await api('PUT', 'schema', { text: $('#sc_text').value, note }); toast('Saved as v' + e.version); location.hash = '#/schema?v=' + e.version; route(); }
    catch (e) { toast(e.message); }
  };
};

// ---------------------------------------------------------------- applicability filter (shared by all views)
const DIM_LABEL = { node: 'Process node', wavelength: 'Wavelength', na: 'NA', layer: 'Layer', mask: 'Mask', application: 'Application' };
S.cond = (() => { try { return JSON.parse(localStorage.getItem('lkb_cond') || '{}'); } catch (e) { return {}; } })();
const condQS = () => Object.entries(S.cond).filter(([, v]) => v).map(([k, v]) => `${k}:${v}`).join(',');
const withCond = path => { const c = condQS(); return c ? path + (path.includes('?') ? '&' : '?') + 'cond=' + encodeURIComponent(c) : path; };
async function condBar() {
  if (!S.dims) S.dims = await get('dims').catch(() => ({}));
  const dims = Object.keys(S.dims);
  if (!dims.length) return '';
  return `<div class="row small condbar"><b>Applicability conditions</b>${dims.map(d => `<label>${esc((S.dims[d] || [DIM_LABEL[d] || d])[0])}
      <input data-cond="${esc(d)}" value="${esc(S.cond[d] || '')}" placeholder="e.g. ${esc(((S.dims[d] || [])[1] || '').split(/[\u3001,]/)[0].replace(/^(?:\u5982|e\.g\.)\s*/i, ''))}" style="width:120px"></label>`).join('')}
    <button id="condgo">Filter</button>${condQS() ? '<button id="condclr">Clear</button>' : ''}
    <span class="muted">Knowledge with no stated conditions is treated as general and always shown (marked “General”).</span></div>`;
}
function bindCond() {
  const go = () => { document.querySelectorAll('[data-cond]').forEach(i => { S.cond[i.dataset.cond] = i.value.trim(); });
    try { localStorage.setItem('lkb_cond', JSON.stringify(S.cond)); } catch (e) {} route(); };
  if ($('#condgo')) $('#condgo').onclick = go;
  document.querySelectorAll('[data-cond]').forEach(i => i.onkeydown = e => { if (e.key === 'Enter') go(); });
  if ($('#condclr')) $('#condclr').onclick = () => { S.cond = {}; try { localStorage.removeItem('lkb_cond'); } catch (e) {} route(); };
}
const condChips = (conds, evLink) => (conds || []).map(c => `<span class="badge b-comment" title="Evidence ${esc(c.evidence || '')}">${esc((S.dims && S.dims[c.dim] ? S.dims[c.dim][0] : DIM_LABEL[c.dim]) || c.dim)}: ${esc(c.value)}${evLink && c.evidence ? ' · ' + esc(c.evidence) : ''}</span>`).join(' ');
const appliesBadge = a => a === 'general' ? '<span class="badge" title="Source states no applicability conditions">General</span>' : a === 'yes' ? '<span class="badge b-exact">Matches conditions</span>' : '';

// view switcher shared by the knowledge views
const VIEWS = [['#/wiki', 'Wiki'], ['#/k', 'Cards'], ['#/tree', 'Index tree'], ['#/graph', 'Graph'], ['#/mindmap', 'Mind map'], ['#/timeline', 'Timeline'], ['#/facts', 'Comparison table'], ['#/src', 'Document outlines']];
const viewTabs = cur => `<div class="tabs" style="margin-top:0">${VIEWS.map(([h, n]) => `<a href="${h}" class="${h === cur ? 'on' : ''}">${n}</a>`).join('')}</div>`;

// ---------------------------------------------------------------- mind map: one topic at the centre
routes.mindmap = async ([id], q) => {
  const all = await get(withCond('cards'));
  const cards = all.filter(c => c.type !== 'summary' && (can('reviewer') ? (c.published_rev || q.all) : true));
  const byId = Object.fromEntries(cards.map(c => [c.id, c]));
  const kids = p => cards.filter(c => c.parent === p);
  const roots = cards.filter(c => c.type === 'topic' && !byId[c.parent]);
  const center = byId[id] || roots.find(r => kids(r.id).length) || roots[0] || cards[0];
  const bar = await condBar();
  if (!center) { set(`<div class="panel">${viewTabs('#/mindmap')}${bar}<p class="muted">No knowledge to show yet.</p></div>`); return bindCond(); }
  const ring1 = kids(center.id);
  const relIds = [...new Set([...(center.relations || []).map(r => r.target), ...cards.filter(c => (c.relations || []).some(r => r.target === center.id)).map(c => c.id)])]
    .filter(x => byId[x] && x !== center.id && !ring1.some(k => k.id === x) && x !== center.parent).slice(0, 10);
  const parent = byId[center.parent];
  const W = 1200, H = 860, cx = W / 2, cy = H / 2;
  const nodes = [], links = [];
  const place = (list, r, a0, a1, kind) => list.forEach((c, i) => {
    const a = list.length === 1 ? (a0 + a1) / 2 : a0 + (a1 - a0) * (i + 0.5) / list.length;
    nodes.push({ c, x: cx + r * Math.cos(a), y: cy + r * Math.sin(a), kind, a });
  });
  // each box needs ~170px of arc; related concepts sit on an outer arc at the bottom, staggered on two radii
  const relN = relIds.length, rRel = 340, relArc = Math.min(Math.PI * 1.1, relN * 170 / (rRel + 30) / 1.6);
  const span = relN ? [Math.PI / 2 + relArc / 2 + 0.3, Math.PI / 2 - relArc / 2 - 0.3 + 2 * Math.PI] : [-Math.PI, Math.PI];
  place(ring1, Math.max(250, Math.min(330, ring1.length * 170 / Math.max(0.5, span[1] - span[0]))), span[0], span[1], 'child');
  place(relIds.map(x => byId[x]), rRel, Math.PI / 2 - relArc / 2, Math.PI / 2 + relArc / 2, 'related');
  nodes.filter(n => n.kind === 'related').forEach((n, i) => { if (i % 2) { n.x = cx + (rRel - 95) * Math.cos(n.a); n.y = cy + (rRel - 95) * Math.sin(n.a); } });
  // collision relaxation: overlapping boxes push each other apart (centre ellipse stays fixed)
  const BW = 156, BH = 62, boxes = nodes.filter(n => n.kind !== 'grand');
  for (let it = 0; it < 200; it++) {
    let moved = false;
    for (let i = 0; i < boxes.length; i++) for (let j = i + 1; j < boxes.length; j++) {
      const A = boxes[i], B = boxes[j], dx = B.x - A.x, dy = B.y - A.y;
      const ox = BW - Math.abs(dx), oy = BH - Math.abs(dy);
      if (ox > 0 && oy > 0) {
        moved = true;
        if (ox < oy) { const m = (ox / 2 + 1) * Math.sign(dx || 1); A.x -= m; B.x += m; }
        else { const m = (oy / 2 + 1) * Math.sign(dy || 1); A.y -= m; B.y += m; }
      }
    }
    for (const n of boxes) {  // keep clear of the centre ellipse
      const ex = (n.x - cx) / (105 + BW / 2), ey = (n.y - cy) / (48 + BH / 2), d = Math.hypot(ex, ey);
      if (d < 1) { n.x = cx + (n.x - cx) / Math.max(d, 0.01); n.y = cy + (n.y - cy) / Math.max(d, 0.01); moved = true; }
      n.a = Math.atan2(n.y - cy, n.x - cx);
    }
    if (!moved) break;
  }
  nodes.filter(n => n.kind === 'child').forEach(n => {
    const g = kids(n.c.id).slice(0, 6);
    g.forEach((c, i) => nodes.push({ c, x: n.x + 120 * Math.cos(n.a + (i - (g.length - 1) / 2) * 0.32), y: n.y + 120 * Math.sin(n.a + (i - (g.length - 1) / 2) * 0.32), kind: 'grand', from: n }));
  });
  const wrap = (t, n) => {
    const s = String(t).replace(/\s*[\uff08(][^)\uff09]*[)\uff09]\s*$/, '') || String(t); const out = [];
    if (/\s/.test(s) && !/[\u4e00-\u9fff]/.test(s)) {  // Latin text: wrap at word boundaries (~1.7× chars per line)
      const w = Math.round(n * 1.7); let cur = '';
      for (const word of s.split(/\s+/)) { if (cur && (cur + ' ' + word).length > w) { out.push(cur); cur = word; } else cur = cur ? cur + ' ' + word : word; }
      if (cur) out.push(cur);
      return out.length > 3 ? [...out.slice(0, 2), out.slice(2).join(' ').slice(0, w - 1) + '…'] : out;
    }
    for (let i = 0; i < s.length && out.length < 3; i += n) out.push(s.slice(i, i + n)); return out; };
  const label = (n, size, fill, w) => wrap(n.c.title, w).map((ln, i, arr) => `<text x="${n.x}" y="${n.y + (i - (arr.length - 1) / 2) * (size + 3) + size / 3}" text-anchor="middle" font-size="${size}" fill="${fill}">${esc(ln)}</text>`).join('');
  let svg = '';
  nodes.forEach(n => { const p = n.from || { x: cx, y: cy }; svg += `<path d="M${p.x},${p.y} Q${(p.x + n.x) / 2 + (n.kind === 'related' ? 0 : 0)},${(p.y + n.y) / 2} ${n.x},${n.y}" fill="none" stroke="${n.kind === 'related' ? 'var(--warn)' : 'var(--line)'}" stroke-width="${n.kind === 'grand' ? 1 : 2}" ${n.kind === 'related' ? 'stroke-dasharray="5 4"' : ''}/>`; });
  nodes.forEach(n => {
    const col = TYPE_COLORS[n.c.type] || '#888', has = kids(n.c.id).length;
    const href = has ? `#/mindmap/${encodeURIComponent(n.c.id)}` : cardHref(n.c.id);
    if (n.kind === 'grand') svg += `<a href="${href}"><circle cx="${n.x}" cy="${n.y}" r="5" fill="${col}"/><text x="${n.x}" y="${n.y + 16}" text-anchor="middle" font-size="11" fill="var(--muted)">${esc(wrap(n.c.title, 9)[0])}</text></a>`;
    else svg += `<a href="${href}"><rect x="${n.x - 72}" y="${n.y - 26}" width="144" height="52" rx="12" fill="var(--panel)" stroke="${col}" stroke-width="2"/>${label(n, 12, 'var(--ink)', 11)}${has ? `<text x="${n.x + 66}" y="${n.y - 14}" font-size="10" text-anchor="end" fill="${col}">+${has}</text>` : ''}</a>`;
  });
  svg += `<a href="${cardHref(center.id)}"><ellipse cx="${cx}" cy="${cy}" rx="105" ry="48" fill="${TYPE_COLORS[center.type] || '#2f5d8a'}"/>${label({ x: cx, y: cy, c: center }, 15, '#fff', 12)}</a>`;
  set(`<div class="panel">${viewTabs('#/mindmap')}${bar}
    <div class="row small"><b>Center:</b><a href="${cardHref(center.id)}">${esc(center.title)}</a>${parent ? ` · up: <a href="#/mindmap/${encodeURIComponent(parent.id)}">${esc(parent.title)}</a>` : ''}
      <span class="muted">· solid: sub-concepts (+N expands further) · orange dashed: related concepts</span>
      <select id="mmtopic" style="margin-left:auto"><option value="">Switch topic…</option>${cards.filter(c => kids(c.id).length).map(c => `<option value="${esc(c.id)}" ${c.id === center.id ? 'selected' : ''}>${esc(c.title)} (${kids(c.id).length})</option>`).join('')}</select></div>
    <svg viewBox="0 0 ${W} ${H}" style="width:100%;height:auto;max-height:76vh">${svg}</svg>
    ${ring1.length || relIds.length ? '' : '<p class="muted">This node has no sub-concepts or related concepts.</p>'}</div>`);
  bindCond();
  $('#mmtopic').onchange = e => { if (e.target.value) location.hash = '#/mindmap/' + encodeURIComponent(e.target.value); };
};

// ---------------------------------------------------------------- timeline: dated events from the cards' evidence
routes.timeline = async (_, q) => {
  const d = await get(withCond('timeline' + (q.all ? '?all=1' : '')));
  const bar = await condBar();
  const nodeOf = w => { const m = String(w).match(/(\d+(?:\.\d+)?)\s*nm/i); return m ? +m[1] : null; };
  const dated = d.rows.filter(r => r.year);
  const eras = d.rows.filter(r => !r.year && nodeOf(r.when) !== null).sort((a, b) => nodeOf(b.when) - nodeOf(a.when));
  const undated = d.rows.filter(r => !r.year && nodeOf(r.when) === null);
  const groups = {};
  dated.forEach(r => { const k = Math.floor(r.year); (groups[k] = groups[k] || []).push(r); });
  const item = r => `<div class="tl-item"><div class="tl-when">${esc(r.when)}</div><div class="tl-what">${esc(r.what)}
      <div class="small muted">${badge('t', TYPE_LABEL[r.card_type] || r.card_type)}<a href="${cardHref(r.card)}">${esc(r.card_title)}</a> · ${r.path ? docLink(r.path, 'L=' + encodeURIComponent(r.lines), '· L' + esc(r.lines)) : ''} ${r.check ? badge(r.check) : ''}</div></div></div>`;
  set(`<div class="panel">${viewTabs('#/timeline')}${bar}
    <p class="small muted">The timeline is built from dated events in the cards (each event cites verified source evidence).${can('reviewer') ? ` <a href="#/timeline${q.all ? '' : '?all=1'}">${q.all ? 'Published only' : 'Include unpublished'}</a>` : ''}</p>
    ${dated.length ? `<h3>By year</h3><div class="timeline-v">${Object.keys(groups).sort((a, b) => a - b).map(y => `<div class="tl-year"><span>${y}</span></div>${groups[y].map(item).join('')}`).join('')}</div>` : (eras.length ? '' : '<p class="muted">No dated events yet.</p>')}
    ${eras.length ? `<h3>By process node <span class="small muted">(larger to smaller node ≈ earlier to later)</span></h3><div class="timeline-v">${eras.map(r => `<div class="tl-year"><span>${nodeOf(r.when)}nm</span></div>${item(r)}`).join('')}</div>` : ''}
    ${undated.length ? `<h3>Other periods</h3>${undated.map(item).join('')}` : ''}</div>`);
  bindCond();
};

// ---------------------------------------------------------------- comparison table: structured facts across cards
routes.facts = async (_, q) => {
  const d = await get(withCond('facts' + (q.all ? '?all=1' : '')));
  const bar = await condBar();
  const f = (q.f || '').toLowerCase();
  const rows = d.rows.filter(r => !f || (r.name + ' ' + r.card_title + ' ' + r.value).toLowerCase().includes(f));
  const groups = {};
  rows.forEach(r => (groups[r.name] = groups[r.name] || []).push(r));
  const condTxt = r => Object.entries(r.conditions || {}).map(([k, v]) => `${(S.dims[k] || [DIM_LABEL[k] || k])[0]}: ${v}`).concat((r.card_conditions || []).map(c => `${(S.dims[c.dim] || [DIM_LABEL[c.dim] || c.dim])[0]}: ${c.value}`));
  set(`<div class="panel">${viewTabs('#/facts')}${bar}
    <div class="row small"><input id="ff" placeholder="Filter parameters / metrics / cards…" value="${esc(q.f || '')}" style="width:260px">
      <span class="muted">${rows.length} facts · ${Object.keys(groups).length} parameters/metrics · same-name parameters side by side; every value links to the source.</span>
      ${can('reviewer') ? `<a href="#/facts${q.all ? '' : '?all=1'}">${q.all ? 'Published only' : 'Include unpublished'}</a>` : ''}</div>
    <table class="grid"><tr><th>Parameter / metric</th><th>Value</th><th>Applicability conditions</th><th>Card</th><th>Source</th></tr>
    ${Object.entries(groups).map(([name, rs]) => rs.map((r, i) => `<tr>${i === 0 ? `<td rowspan="${rs.length}"><b>${esc(name)}</b>${rs.length > 1 ? `<br><span class="small muted">${rs.length} entries</span>` : ''}</td>` : ''}
      <td><b>${esc(r.value)}</b> ${esc(r.unit || '')}</td><td class="small">${condTxt(r).map(esc).join('<br>') || '<span class="muted">General</span>'}</td>
      <td class="small"><a href="${cardHref(r.card)}">${esc(r.card_title)}</a></td>
      <td class="small">${r.path ? docLink(r.path, 'L=' + encodeURIComponent(r.lines), '· L' + esc(r.lines)) : ''} ${r.check ? badge(r.check) : ''}<div class="muted" title="${esc(r.quote)}">${esc((r.quote || '').slice(0, 60))}…</div></td></tr>`).join('')).join('') || '<tr><td colspan="5" class="muted">No structured facts yet.</td></tr>'}</table></div>`);
  bindCond();
  $('#ff').onkeydown = e => { if (e.key === 'Enter') location.hash = '#/facts?f=' + encodeURIComponent(e.target.value) + (q.all ? '&all=1' : ''); };
};

// ---------------------------------------------------------------- issue register
const ISSUE_LABEL = { contradiction: 'Contradiction', open_question: 'Open question', gap: 'Knowledge gap', report: 'Reader report' };
const ISSUE_CLS = { contradiction: 'reject', open_question: 'request_changes', gap: 'comment', report: 'warn' };
routes.issues = async ([iid], q) => {
  if (iid) return issueView(iid);
  const d = await get('issues' + (q.status !== 'all' ? '?status=' + (q.status || 'open') : '') + (q.kind ? (q.status === 'all' ? '?' : '&') + 'kind=' + q.kind : ''));
  const st = d.stats || {};
  set(`<div class="panel"><h1>${can('reviewer') ? 'Issue register' : 'My reports'}</h1>
    <p class="small muted">Contradictions, open questions, knowledge gaps and reader reports. The knowledge base does not hide contradictions: unresolved contradictions and open questions are shown on the affected cards to all readers; gaps tell admins which sources to add next.</p>
    ${can('reviewer') ? `<div class="row small">${['', 'contradiction', 'open_question', 'gap', 'report'].map(k => `<a class="badge ${(q.kind || '') === k ? 'b-in_review' : ''}" href="#/issues?kind=${k}&status=${q.status || 'open'}">${k ? ISSUE_LABEL[k] + ' ' + ((st.by_kind || {})[k] || 0) : 'All open ' + (st.open || 0)}</a>`).join(' ')}
      · Status: ${['open', 'resolved', 'wontfix', 'all'].map(s => `<a href="#/issues?status=${s}${q.kind ? '&kind=' + q.kind : ''}" class="badge ${(q.status || 'open') === s ? 'b-in_review' : ''}">${{ open: 'Open', resolved: 'Resolved', wontfix: 'Won’t fix', all: 'All' }[s]}</a>`).join(' ')}</div>` : ''}
    <table class="grid"><tr><th>Type</th><th>Issue</th><th>Related cards</th><th>Origin</th><th>Status</th><th>Updated</th></tr>
    ${d.items.map(i => `<tr><td>${badge(ISSUE_CLS[i.kind], ISSUE_LABEL[i.kind])}${i.seen > 1 ? `<br><span class="small muted">seen ${i.seen}×</span>` : ''}</td>
      <td><a href="#/issues/${esc(i.id)}"><b>${esc(i.title)}</b></a><div class="small muted">${esc((i.detail || '').slice(0, 120))}</div></td>
      <td class="small">${i.cards.map(c => `<a href="#/review/${encodeURIComponent(c)}">${esc(c)}</a>`).join('<br>')}</td>
      <td class="small">${esc((i.origin || {}).kind || '')}${(i.origin || {}).run ? `<br><a href="#/${i.origin.kind === 'query' ? 'ask' : 'traces'}/${esc(i.origin.run)}">trace</a>` : ''}</td>
      <td>${badge(i.status === 'open' ? 'in_review' : i.status === 'resolved' ? 'published' : 'rejected', { open: 'Open', resolved: 'Resolved', wontfix: 'Won’t fix' }[i.status])}</td><td class="small">${fmtTime(i.updated)}</td></tr>`).join('') || '<tr><td colspan="6" class="muted">None</td></tr>'}</table></div>`);
};
async function issueView(iid) {
  const i = await get('issues/' + encodeURIComponent(iid));
  set(`<div class="row"><a href="#/issues">← Issue register</a></div><div class="panel"><div class="row">${badge(ISSUE_CLS[i.kind], ISSUE_LABEL[i.kind])}
      ${badge(i.status === 'open' ? 'in_review' : 'published', { open: 'Open', resolved: 'Resolved', wontfix: 'Won’t fix' }[i.status])}<span class="small muted">raised by ${esc(i.by)} at ${fmtTime(i.created)} · seen ${i.seen || 1}×</span></div>
    <h1>${esc(i.title)}</h1><p>${esc(i.detail || '')}</p>
    ${i.cards.length ? `<p class="small">Related cards: ${i.cards.map(c => `<a href="${cardHref(c)}">${esc(c)}</a>`).join(', ')}</p>` : ''}
    ${(i.evidence || []).length ? `<h3>Source evidence</h3>${evidenceList({ evidence: i.evidence }, false)}` : ''}
    ${i.resolution ? `<div class="banner info">Resolution: ${esc(i.resolution)}</div>` : ''}
    <h3>History</h3><table class="grid">${i.history.map(h => `<tr><td class="small">${fmtTime(h.ts)}</td><td>${esc(h.user)}</td><td>${esc({ open: 'Raised', seen_again: 'Seen again', comment: 'Comment', resolve: 'Resolved', wontfix: 'Won’t fix', reopen: 'Reopened' }[h.action] || h.action)}</td><td class="small">${esc(h.comment || '')}</td></tr>`).join('')}</table>
    ${S.me ? `<textarea id="ic" placeholder="Comment / resolution note (required to resolve or mark won’t fix)"></textarea><div class="row"><button data-ia="comment">Comment</button>
      ${can('reviewer') ? (i.status === 'open' ? '<button class="ok" data-ia="resolve">Mark resolved</button><button data-ia="wontfix">Won’t fix</button>' : '<button data-ia="reopen">Reopen</button>') : ''}</div>` : ''}</div>`);
  document.querySelectorAll('[data-ia]').forEach(b => b.onclick = async () => {
    try { await api('POST', `issues/${encodeURIComponent(iid)}/action`, { action: b.dataset.ia, comment: $('#ic').value.trim() }); toast('Recorded'); route(); }
    catch (e) { toast(e.message); }
  });
}
function facetsBlock(card) {
  const ev = Object.fromEntries((card.evidence || []).map(e => [e.id, e]));
  const reviewer = can('reviewer');
  const keep = items => (items || []).filter(x => x.supported !== false || reviewer);  // readers only see supported facets
  card = { ...card, conditions: keep(card.conditions), facts: keep(card.facts), events: keep(card.events) };
  const ref = (id, x) => (ev[id] ? `<a class="ev" data-ev="${esc(id)}" href="javascript:void 0">${esc(id)}</a>` : '') +
    (x && x.supported === false ? ' <span class="badge b-missing" title="The cited source does not state this value explicitly">Not supported by source</span>' : '');
  let h = '';
  if ((card.conditions || []).length) h += `<h3>Applicability conditions</h3><p>${(card.conditions).map(c => `${condChips([c])} ${ref(c.evidence, c)}`).join(' &nbsp; ')}</p>`;
  else h += `<p class="small muted">Applicability conditions: not stated in source (treated as general).</p>`;
  if ((card.facts || []).length) h += `<h3>Key parameters and metrics</h3><table class="grid"><tr><th>Name</th><th>Value</th><th>Conditions</th><th>Evidence</th></tr>${card.facts.map(f => `<tr><td>${esc(f.name)}</td><td><b>${esc(f.value)}</b> ${esc(f.unit || '')}</td><td class="small">${Object.entries(f.conditions || {}).map(([k, v]) => esc(((S.dims || {})[k] || [DIM_LABEL[k] || k])[0] + ': ' + v)).join(', ') || '—'}</td><td>${ref(f.evidence, f)}</td></tr>`).join('')}</table>`;
  if ((card.events || []).length) h += `<h3>Milestones</h3><ul>${card.events.map(e => `<li><b>${esc(e.when)}</b> ${esc(e.what)} ${ref(e.evidence, e)}</li>`).join('')}</ul>`;
  return h;
}
function issuesBlock(issues, cid) {
  const list = (issues || []);
  return `${list.length ? `<div class="banner warn"><b>Known disagreements and open questions (${list.length})</b><ul class="small" style="margin:4px 0">${list.map(i => `<li>${badge(ISSUE_CLS[i.kind], ISSUE_LABEL[i.kind])} ${can('reviewer') || i.kind === 'contradiction' || i.kind === 'open_question' ? `<a href="#/issues/${esc(i.id)}">${esc(i.title)}</a>` : esc(i.title)}</li>`).join('')}</ul></div>` : ''}
    ${S.me ? `<details style="margin-top:12px"><summary class="small">Found an error or something unclear? Report an issue</summary><input id="rp_t" placeholder="Issue title (e.g. the value quoted in E3 does not match the source)" style="width:100%;margin:6px 0">
      <textarea id="rp_d" placeholder="Details (optional)"></textarea><div class="row"><button id="rp_go" data-card="${esc(cid)}">Submit report</button></div></details>` : ''}`;
}
function bindReport() {
  const b = $('#rp_go'); if (!b) return;
  b.onclick = async () => { const title = $('#rp_t').value.trim(); if (title.length < 4) return toast('Please enter an issue title');
    try { await api('POST', 'issues', { kind: 'report', card: b.dataset.card, title, detail: $('#rp_d').value.trim() }); toast('Submitted; a reviewer will follow up'); route(); } catch (e) { toast(e.message); } };
}

// ---------------------------------------------------------------- wiki: every page a navigation hub
const wikiHref = id => '#/wiki/' + encodeURIComponent(id);
const entHref = id => '#/entity/' + encodeURIComponent(String(id).replace(/^e:/, ''));
const REL_LABEL = { is_a:'is a', part_of:'part of', uses:'uses', depends_on:'depends on', implements:'implements', improves:'improves', alternative_to:'alternative to',
  contrasts_with:'contrasts with', causes:'causes', mitigates:'mitigates', measured_by:'measured by', parameter_of:'parameter of', input_to:'input to', output_of:'output of',
  example_of:'example of', contradicts:'contradicts', covers:'covers', related_to:'related to' };
const ENT_LABEL = { tool:'Software / tool', equipment:'Equipment', organization:'Organization', material:'Material', standard:'Format / standard', person:'Person', product:'Product' };
function wikiSide(cards, cur) {
  return `<aside class="panel side"><h3 style="margin-top:0"><a href="#/wiki">Wiki home</a></h3>${topicTree(cards, cur).replace(/#\/k\//g, '#/wiki/')}</aside>`;
}
routes.wiki = async ([id], q) => {
  const view = q.view === 'head' && can('reviewer') ? '?view=head' : '';
  const cards = await get('cards');
  S.cardTitles = Object.fromEntries(cards.map(c => [c.id, c.title]));
  const side = wikiSide(cards.filter(c => can('reviewer') ? c.published_rev : true), id);
  if (!id) {
    const h = await get('wiki' + view);
    set(`<div class="panel" style="margin-bottom:10px">${viewTabs('#/wiki')}</div><div class="cols">${side}<section class="panel">
      <h1 style="margin-top:0">Knowledge base wiki</h1>
      <p class="muted small">${h.pages} pages · graph ${Object.values(h.graph.nodes).reduce((a, b) => a + b, 0)} nodes / ${Object.values(h.graph.edges).reduce((a, b) => a + b, 0)} edges
        (reviewed relations ${h.graph.edges.reviewed || 0} · concept mentions ${h.graph.edges.linked || 0} · entities ${h.graph.edges.indexed || 0})</p>
      <h3>Topics</h3><div class="grid2">${h.topics.map(t => `<a class="item tile" href="${wikiHref(t.id)}"><b>${esc(t.title)}</b>
        <span class="muted small">${t.children} subpages ${t.has_overview ? '' : '· <i>no overview yet</i>'}</span><br><span class="small">${esc(t.summary || '')}</span></a>`).join('')}</div>
      <h3>Core concepts <span class="muted small">(by graph centrality)</span></h3><p>${h.central.map(c => `<a class="chip" href="${wikiHref(c.id)}">${esc(c.title)}</a>`).join(' ')}</p>
      ${h.entities.length ? `<h3>Entities <span class="muted small">(tools, equipment, organizations…, detected by the index and verified verbatim)</span></h3><p>${h.entities.map(e =>
        `<a class="chip" href="${entHref(e.id)}">${esc(e.title)} <span class="muted">${esc(ENT_LABEL[e.type] || '')}</span></a>`).join(' ')}</p>` : ''}
      <h3>Recently updated</h3><div class="cardlist">${h.recent.map(c => `<a class="item" href="${wikiHref(c.id)}"><b>${esc(c.title)}</b> <span class="muted small">${esc(TYPE_LABEL[c.type] || c.type)} · ${fmtTime(c.at)}</span></a>`).join('')}</div>
      ${can('reviewer') && h.hub_gaps.length ? `<h3>Wiki structure gaps</h3><ul class="small">${h.hub_gaps.map(g => g.kind === 'topic_without_overview'
        ? `<li>Topic <a href="${wikiHref(g.id)}">${esc(g.title)}</a> has ${g.children} subpages but no overview</li>`
        : `<li>A tightly connected group of cards spans different topics (${g.parents.map(esc).join(', ')}): ${g.titles.map(esc).join(', ')} — may need a shared topic</li>`).join('')}</ul>` : ''}
    </section></div>`);
    bindTree($('#main'));
    return;
  }
  const p = await get('wiki/' + encodeURIComponent(id) + view);
  const known = new Set(cards.map(c => c.id));
  const body = renderCardBody({ body: (p.body || '').replace(/^\s*#\s+[^\n]*\n/, '') }, known).replace(/href="#\/k\//g, 'href="#/wiki/')
    .replace(/<a class="ev" data-ev="([^"]+)"[^>]*>/g, (_, e) => `<a class="ev" href="${cardHref(p.id)}?ev=${e}" title="${esc(((p.evidence || []).find(x => x.id === e) || {}).quote || '')}">`);
  const relGroup = (arr, dirIn) => {
    const g = {};
    arr.forEach(r => (g[r.rel] = g[r.rel] || []).push(r));
    return Object.entries(g).map(([rel, xs]) => `<li><b>${dirIn ? '← ' : ''}${esc(REL_LABEL[rel] || rel)}</b>:${xs.map(r =>
      `<a href="${wikiHref(r.id)}">${esc(r.title)}</a>${r.basis && r.basis !== 'extracted' ? ' <span class="muted small">(' + stLabel(r.basis) + ')</span>' : ''}`).join(', ')}</li>`).join('');
  };
  set(`<div class="panel" style="margin-bottom:10px">${viewTabs('#/wiki')}</div><div class="cols">${side}<section class="panel doc">
    <div class="small muted crumbs"><a href="#/wiki">Wiki</a>${p.breadcrumbs.map(b => ` › <a href="${wikiHref(b.id)}">${esc(b.title)}</a>`).join('')}</div>
    <h1 style="margin:6px 0">${esc(p.title)}</h1>
    <p class="small">${badge('comment', TYPE_LABEL[p.type] || p.type)} ${p.aliases.length ? '<span class="muted">also known as ' + p.aliases.map(esc).join(', ') + '</span>' : ''}
      ${condChips(p.conditions)} · <a href="${cardHref(p.id)}">Evidence and review history →</a></p>
    <p><i>${esc(p.summary)}</i></p>
    ${body}
    ${p.type === 'topic' && can('reviewer') ? `<p><button id="hubgo">${(p.body || '').trim().length > 40 ? 'Regenerate' : 'Generate'} topic overview (LLM, goes to review)</button></p>` : ''}
    ${p.children.length ? `<h2>Subpages</h2><div class="cardlist">${p.children.map(c => `<a class="item" href="${wikiHref(c.id)}"><b>${esc(c.title)}</b>
      <span class="muted small">${esc(TYPE_LABEL[c.type] || c.type)}</span> ${c.conditions.map(x => `<span class="badge b-comment">${esc(x)}</span>`).join(' ')}<br><span class="small muted">${esc(c.summary)}</span></a>`).join('')}</div>` : ''}
    ${p.relations_out.length || p.relations_in.length ? `<h2>Relations <span class="muted small">(reviewed)</span></h2><ul>${relGroup(p.relations_out)}${relGroup(p.relations_in, true)}</ul>` : ''}
    ${p.mentioned_by.length || p.mentions.length ? `<h2>Mentions <span class="muted small">(auto-linked by name)</span></h2>
      ${p.mentioned_by.length ? `<p class="small"><b>Mentioned by:</b>${p.mentioned_by.map(m => `<a href="${wikiHref(m.id)}">${esc(m.title)}</a>`).join(', ')}</p>` : ''}
      ${p.mentions.length ? `<p class="small"><b>Mentions:</b>${p.mentions.map(m => `<a href="${wikiHref(m.id)}">${esc(m.title)}</a>`).join(', ')}</p>` : ''}` : ''}
    ${p.sections.length ? `<h2>Source sections discussing this concept</h2><ul class="small">${p.sections.map(s => `<li>${docLink(s.path, 'L=' + s.start, '· ' + esc(s.title))}
      <span class="muted">L${s.start}-${s.end}${s.count > 1 ? ' · ' + s.count + ' mentions' : ''}</span></li>`).join('')}</ul>` : ''}
    ${p.entities.length ? `<h2>Entities involved</h2><p>${p.entities.map(e => `<a class="chip" href="${entHref(e.id)}">${esc(e.title)} <span class="muted">${esc(ENT_LABEL[e.type] || '')}</span></a>`).join(' ')}</p>` : ''}
    ${p.backlinks.length ? `<h2>Links to this page</h2><p class="small">${p.backlinks.map(b => `<a href="${wikiHref(b.id)}">${esc(b.title)}</a>`).join(', ')}</p>` : ''}
    ${p.red_links.length ? `<p class="small muted">Pages that don’t exist yet: ${p.red_links.map(esc).join(', ')}</p>` : ''}
  </section></div>`);
  bindTree($('#main'));
  if ($('#hubgo')) $('#hubgo').onclick = async () => {
    $('#hubgo').disabled = true; $('#hubgo').textContent = 'Generating…';
    try { const r = await api('POST', 'wiki/' + encodeURIComponent(id) + '/hub');
      toast('Overview generated (r' + ((r.written[0] || {}).rev || '?') + ') and sent to review' + (r.findings.length ? '; note: ' + r.findings.join('; ') : ''));
      location.hash = '#/review/' + encodeURIComponent(id);
    } catch (e) { toast('Failed: ' + e.message); $('#hubgo').disabled = false; }
  };
};

routes.entity = async ([id]) => {
  const e = await get('entities/' + encodeURIComponent(id));
  set(`<div class="panel" style="margin-bottom:10px">${viewTabs('#/wiki')}</div><div class="panel doc">
    <div class="small muted"><a href="#/wiki">Wiki</a> › Entity</div>
    <h1 style="margin:6px 0">${esc(e.title)}</h1>
    <p class="small">${badge('comment', e.type_label || ENT_LABEL[e.type] || 'Unclassified')} ${(e.aliases || []).length ? '<span class="muted">also known as ' + e.aliases.map(esc).join(', ') + '</span>' : ''}</p>
    <p class="small muted">Entities are detected by the document index (PageIndex) and their names verified verbatim in the source. An entity is not a reviewed knowledge card but a navigation entry point to related knowledge.</p>
    ${e.cards.length ? `<h2>Knowledge cards that mention it</h2><div class="cardlist">${e.cards.map(c => `<a class="item" href="${wikiHref(c.id)}"><b>${esc(c.title)}</b> <span class="muted small">${esc(TYPE_LABEL[c.type] || c.type)}${c.count > 1 ? ' · ' + c.count + '×' : ''}</span></a>`).join('')}</div>` : ''}
    <h2>Source locations</h2><ul class="small">${e.sections.map(s => `<li>${docLink(s.path, 'L=' + s.start, '· ' + esc(s.title))} <span class="muted">L${s.start}-${s.end}</span></li>`).join('') ||
      (e.docs || []).map(d => `<li>${docLink(d)}</li>`).join('')}</ul></div>`);
};

// ---------------------------------------------------------------- PageIndex: the unified tree, browsable
routes.tree = async (_, q) => {
  const d = await get('pageindex' + (q.view === 'head' && can('reviewer') ? '?view=head' : ''));
  const st = can('reviewer') ? await get('pageindex/status').catch(() => null) : null;
  const N = d.nodes;
  const tag = n => ({ card: TYPE_LABEL[n.type] || 'Card', doc: 'Document', section: '§', folder: 'Folder', root: '' })[n.kind];
  const href = n => n.kind === 'card' ? wikiHref(n.id) : n.kind === 'doc' ? srcHref(n.path) : n.kind === 'section' ? srcHref(n.path, 'L=' + n.start) : '';
  const li = id => { const n = N[id]; const kids = n.children || [];
    return `<li class="${kids.length ? 'closed' : ''}" data-id="${esc(id)}">${kids.length ? '<span class="tw" data-open>▸</span>' : '<span class="tw"> </span>'}
      ${href(n) ? `<a href="${href(n)}">${esc(n.title)}</a>` : `<b>${esc(n.title)}</b>`} <span class="muted small">${esc(tag(n))}${n.kind === 'section' ? ' L' + n.start + '-' + n.end : ''}${kids.length ? ' · ' + kids.length : ''}</span>
      ${n.summary ? `<div class="small muted gist">${esc(n.summary)}</div>` : ''}<ul></ul></li>`; };
  set(`<div class="panel" style="margin-bottom:10px">${viewTabs('#/tree')}</div><div class="panel">
    <h1 style="margin-top:0">Index tree (PageIndex)</h1>
    <p class="small muted">When answering a question the model walks this tree level by level, like a handbook's table of contents, reasoning about which cards and source sections to read — no vector search, no chunking.
      ${st ? `Node summaries: ${st.compiled}/${st.documents} documents summarized by the LLM${st.pending.length ? ' (the rest use heading + first sentence)' : ''}.` : ''}</p>
    <div class="row"><input id="tq" placeholder="Search source sections (BM25)…" style="width:360px"><button id="tgo">Search</button></div><div id="thits"></div>
    <ul class="pitree">${li('k')}${li('d')}</ul></div>`);
  const root = $('#main');
  root.addEventListener('click', e => {
    const t = e.target.closest('[data-open]'); if (!t) return;
    const item = t.parentElement; const ul = item.querySelector(':scope > ul');
    if (!ul.childElementCount) ul.innerHTML = (N[item.dataset.id].children || []).map(li).join('');
    item.classList.toggle('closed'); t.textContent = item.classList.contains('closed') ? '▸' : '▾';
  });
  root.querySelectorAll('.pitree > li > [data-open]').forEach(x => x.click());
  const search = async () => {
    const r = await get('pageindex/search?q=' + encodeURIComponent($('#tq').value));
    $('#thits').innerHTML = `<div class="cardlist">${r.sections.map(s => `<a class="item" href="${srcHref(s.path, 'L=' + s.start)}"><b>“${esc(docTitle(s.path))}” · ${esc(s.title)}</b>
      <span class="muted small">L${s.start}-${s.end} · ${s.score}</span><br><span class="small muted">${esc(s.summary)}</span></a>`).join('') || '<p class="muted">No results</p>'}</div>`;
  };
  $('#tgo').onclick = search; $('#tq').onkeydown = e => { if (e.key === 'Enter') search(); };
};

// graph: explain how two pieces of knowledge are connected
async function pathFinder(nodes) {
  const opts = nodes.map(n => `<option value="${esc(n.title)}">`).join('');
  return `<details class="small" style="margin:6px 0"><summary><b>Relation path</b>: how are two pieces of knowledge connected?</summary>
    <div class="row"><input id="pa" list="pnodes" placeholder="From (card title)" style="width:240px"> → <input id="pb" list="pnodes" placeholder="To" style="width:240px">
    <button id="pgo">Find</button></div><datalist id="pnodes">${opts}</datalist><div id="pout"></div></details>`;
}
function bindPathFinder(nodes) {
  if (!$('#pgo')) return;
  const byTitle = t => (nodes.find(n => n.title === t) || nodes.find(n => n.id === t) || {}).id;
  $('#pgo').onclick = async () => {
    const a = byTitle($('#pa').value), b = byTitle($('#pb').value);
    if (!a || !b) { $('#pout').innerHTML = '<p class="muted">Pick cards from the dropdown list</p>'; return; }
    const r = await get(`kg/path?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`);
    $('#pout').innerHTML = r.steps ? `<ol>${r.steps.map(s => `<li><a href="${wikiHref(s.from)}">${esc(s.from_title)}</a>
      <b>${s.dir === 'out' ? '—' + esc(REL_LABEL[s.rel] || s.rel) + '→' : '←' + esc(REL_LABEL[s.rel] || s.rel) + '—'}</b>
      <a href="${s.to.startsWith('e:') ? entHref(s.to) : s.to.startsWith('s:') || s.to.startsWith('d:') ? '#' : wikiHref(s.to)}">${esc(s.to_title)}</a>
      <span class="muted">${{ reviewed: 'reviewed', linked: 'name mention', indexed: 'entity', provenance: 'provenance' }[s.layer] || s.layer}${s.basis && s.layer === 'reviewed' ? ' · ' + stLabel(s.basis) : ''}</span></li>`).join('')}</ol>`
      : '<p class="muted">No path between them</p>';
  };
}

routes.login = async () => {
  set(`<div class="panel" style="max-width:380px;margin:40px auto"><h1>Log in</h1><form id="lf"><div class="row"><input id="ln" placeholder="Username" style="width:100%" autocomplete="username"></div>
    <div class="row"><input id="lp" type="password" placeholder="Password" style="width:100%" autocomplete="current-password"></div><div class="row"><button class="primary">Log in</button></div></form></div>`);
  $('#lf').onsubmit = async e => {
    e.preventDefault();
    try { const d = await api('POST', 'login', { name: $('#ln').value.trim(), password: $('#lp').value }); S.token = d.token; localStorage.setItem('lkb_token', d.token); S.me = d.user; location.hash = '#/'; }
    catch (err) { toast(err.message); }
  };
};
routes['404'] = async () => set('<div class="panel"><h1>Page not found</h1></div>');

async function boot() {
  const me = await get('me').catch(() => ({}));
  S.me = me.user || null; S.site = me.site;
  if (!S.me && S.token) { S.token = ''; localStorage.removeItem('lkb_token'); }
  document.title = me.site || 'LithoKB';
  if (!S.me && me.public_read === false && !location.hash.startsWith('#/login')) location.hash = '#/login';
  route();
}
boot();
})();
