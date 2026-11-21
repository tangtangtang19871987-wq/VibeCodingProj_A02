/* LithoKB single-page UI. No framework, no build step. */
(function () {
'use strict';
const $ = s => document.querySelector(s);
const esc = MD.esc;
const S = { me: null, token: localStorage.getItem('lkb_token') || '', site: '', srcCache: {}, titles: {} };
const RANK = { anonymous: 0, reader: 1, reviewer: 2, admin: 3 };
const can = r => RANK[S.me ? S.me.role : 'anonymous'] >= RANK[r];
const TYPE_ZH = { topic:'主题', summary:'文档摘要', synthesis:'问答综合', concept:'概念', method:'方法', model:'模型', algorithm:'算法', parameter:'参数', metric:'指标',
  process:'工艺', tool:'工具', material:'材料', equipment:'设备', issue:'问题', result:'结论', person_or_org:'人物/机构' };
const ST_ZH = { draft:'草稿', in_review:'待审阅', changes_requested:'需修改', approved:'已通过', rejected:'已拒绝', published:'已发布',
  withdrawn:'已下架', superseded:'已被替换', active:'在架', exact:'原文精确匹配', moved:'原文位置偏移', elided:'省略式匹配', card:'引自卡片', fuzzy:'近似匹配', missing:'原文未找到',
  no_source:'来源缺失', approve:'通过', request_changes:'要求修改', reject:'拒绝', comment:'评论', submit:'提交审阅', publish:'发布',
  return:'打回', reopen:'重新审阅', extracted:'原文明确', inferred:'推断', ambiguous:'存疑', withdraw:'下架', restore:'恢复上架', supersede:'替换为', done:'完成', failed:'失败', running:'进行中', queued:'排队' };
const zh = k => ST_ZH[k] || k;
const badge = (k, txt) => `<span class="badge b-${esc(k)}">${esc(txt || zh(k))}</span>`;
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
  const links = [['#/', '首页'], ['#/wiki', '知识'], ['#/src', '原始文档']];
  if (S.me) links.push(['#/ask', '问答']);
  const rev = [['#/review', '审阅'], ['#/issues', '问题'], ['#/traces', 'LLM观测'], ['#/schema', '规范'], ['#/lint', '健康']];
  const adm = [['#/publish', '发布'], ['#/compile', '编译'], ['#/users', '用户'], ['#/log', '日志']];
  const viewRoutes = ['k', 'wiki', 'tree', 'entity', 'graph', 'mindmap', 'timeline', 'facts'];
  const a = (l, cls = '') => `<a href="${l[0]}" class="${cls} ${('#/' + route[0]) === l[0] || (route[0] === '' && l[0] === '#/') || (l[0] === '#/wiki' && viewRoutes.includes(route[0])) ? 'on' : ''}">${l[1]}</a>`;
  let nav = links.map(l => a(l)).join('');
  if (can('reviewer')) nav += '<span class="sep"></span>' + rev.map(l => a(l, 'role-reviewer')).join('');
  if (can('admin')) nav += adm.map(l => a(l, 'role-admin')).join('');
  $('#nav').innerHTML = nav;
  $('#who').innerHTML = S.me
    ? `<span>${esc(S.me.display || S.me.name)} · ${esc({ reader: '读者', reviewer: '审阅者', admin: '管理员' }[S.me.role])}</span><button id="logout">退出</button>`
    : `<a href="#/login">登录</a>`;
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
    set(`<div class="panel"><h1>出错了</h1><p class="muted">${esc(e.message)}</p></div>`);
  }
}
window.addEventListener('hashchange', route);
$('#qform').onsubmit = e => { e.preventDefault(); location.hash = '#/search?q=' + encodeURIComponent($('#q').value); };

// ---------------------------------------------------------------- shared renderers
function cardHref(id) { return '#/k/' + encodeURIComponent(id); }
function srcHref(path, q) { return '#/src/' + path.split('/').map(encodeURIComponent).join('/') + (q ? '?' + q : ''); }

const docTitle = p => S.titles[p] || p.split('/').pop().replace(/\.(md|markdown|mdx)$/i, '');
const docLink = (p, q, label) => `<a href="${srcHref(p, q)}" title="${esc(p)}">《${esc(docTitle(p))}》${label ? ' ' + label : ''}</a>`;
function renderCardBody(card, known) {
  // legacy bodies say "补充（来自 path.md）": show the document title, linked to the original
  const body = (card.body || '').replace(/补充（来自 ([^）\[\]]+?\.(?:md|markdown|mdx))）/g, (_, p) => `补充（来自 [《${docTitle(p)}》](src:${p})）`);
  return MD.render(body, {
    wiki: (id, label) => {
      const k = MD.slug(id).replace(/[^a-z0-9-]/g, '');
      const miss = known && !known.has(k);
      const shown = (label === id && S.cardTitles && S.cardTitles[k]) ? S.cardTitles[k] : label;  // [[id]] → the page title
      return `<a href="${cardHref(k)}" class="${miss ? 'muted' : ''}" title="${miss ? '尚未发布/不存在' : esc(k)}">${esc(shown)}</a>`;
    },
    ev: id => `<a class="ev" data-ev="${esc(id)}" href="javascript:void 0">${esc(id)}</a>`,
    link: h => h.startsWith('src:') ? srcHref(h.slice(4)) : h, img: s => s,
  });
}

function evidenceList(card, withLines) {
  if (!card.evidence || !card.evidence.length) return '<p class="muted">无证据引用。</p>';
  return '<ol class="evlist">' + card.evidence.map(e => {
    const ln = e.found_lines || e.lines;
    if (e.card) return `<li id="ev-${esc(e.id)}"><b>${esc(e.id)}</b> ${badge(e.check === 'card' ? 'exact' : 'missing', zh(e.check))}
      <a href="${cardHref(e.card)}">卡片 ${esc(e.card)}</a><div class="quote">${esc(e.quote)}</div></li>`;
    return `<li id="ev-${esc(e.id)}"><b>${esc(e.id)}</b> ${badge(e.check || 'missing')}${e.not_read ? ' <span class="badge b-warn">未在阅读计划中</span>' : ''}
      ${docLink(e.path, 'L=' + encodeURIComponent(ln), '· 第 ' + esc(ln) + ' 行')}
      ${e.found_lines && e.found_lines !== e.lines ? `<span class="small muted">（模型声称 L${esc(e.lines)}）</span>` : ''}
      <div class="quote">${esc(e.quote)}</div>${withLines ? `<details ${['exact', 'moved'].includes(e.check) ? '' : 'open'}><summary class="small muted">原文上下文${['exact', 'moved'].includes(e.check) ? '' : '（需人工确认）'}</summary><div class="srclines" data-path="${esc(e.path)}" data-lines="${esc(ln)}"></div></details>` : ''}</li>`;
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
    } catch (e) { el.innerHTML = `<span class="muted small">无法读取原文：${esc(e.message)}</span>`; }
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
  return ` <span class="badge b-${cls}" title="认识论状态：${zh(b)}${r.evidence ? '，证据 ' + esc(r.evidence) : ''}">${zh(b)}${conf}${r.evidence ? ' · ' + esc(r.evidence) : ''}</span>`;
}
function basisSummary(rels) {
  const c = { extracted: 0, inferred: 0, ambiguous: 0 };
  (rels || []).forEach(r => c[r.basis || 'inferred']++);
  return `<span class="small muted">原文明确 ${c.extracted} · 推断 ${c.inferred} </span>${c.ambiguous ? badge('request_changes', '存疑 ' + c.ambiguous) : ''}`;
}
function relationsBlock(card, backlinks) {
  const rels = card.relations || [];
  let h = '';
  if (rels.length) {
    const g = {};
    rels.forEach(r => (g[r.rel] = g[r.rel] || []).push(r));
    h += '<h3>关系</h3><ul>' + Object.entries(g).map(([rel, rs]) =>
      `<li><span class="badge">${esc(rel)}</span> ${rs.map(r => `<a href="${cardHref(r.target)}">${esc(r.target)}</a>${basisBadge(r)}${r.note ? ` <span class="muted small">${esc(r.note)}</span>` : ''}`).join('，')}</li>`).join('') + '</ul>';
  }
  if (backlinks && backlinks.length) h += '<h3>被引用</h3><p>' + backlinks.map(b => `<a href="${cardHref(b.id)}">${esc(b.title)}</a>`).join(' · ') + '</p>';
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
      return sub ? `<li class="dir"><span data-toggle>${esc(c.title)}</span>${link.replace('">', '" style="font-size:12px;color:var(--muted)">· 概览 ')}${sub}</li>` : `<li>${link}</li>`;
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
      <div class="stat"><b>${st.published}</b><span>已发布知识卡片</span></div>
      <div class="stat"><b>${st.sources}</b><span>原始文档</span></div>
      ${can('reviewer') ? `<div class="stat"><b>${st.cards}</b><span>全部卡片（含未发布）</span></div>
      <div class="stat"><b>${(st.by_status.in_review || 0)}</b><span>待审阅</span></div>
      <div class="stat"><b>${(st.by_status.approved || 0)}</b><span>待发布</span></div>` : ''}
    </div>
    <div class="cols"><aside class="panel side"><h3 style="margin-top:0">知识体系</h3>${topicTree(cards.filter(c => can('reviewer') ? c.published_rev : true))}</aside>
    <section class="panel"><h2 style="margin-top:0">最近发布</h2><div class="cardlist">${st.recent.map(c =>
      `<a class="item" href="${cardHref(c.id)}"><b>${esc(c.title)}</b> <span class="muted small">${fmtTime(c.at)}</span><br><span class="muted small">${esc(c.summary)}</span></a>`).join('') || '<p class="muted">尚无已发布的知识。</p>'}</div>
    <p class="small muted" style="margin-top:16px">两层结构：<a href="#/src">原始文档</a>（第一层，原样保存、可追溯上传者与版本）→ LLM 编译的<a href="#/k">知识卡片</a>（第二层，经人工审阅后发布，每条结论附原文证据并自动核验）。</p></section></div>`);
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
    set(`<div class="panel" style="margin-bottom:16px">${viewTabs('#/k')}${bar}</div><div class="cols"><aside class="panel side">${topicTree(visible)}</aside><section class="panel"><h1>知识卡片</h1>
      <p class="muted small">${visible.length} 张${can('reviewer') ? '已发布卡片（审阅中的卡片见 <a href="#/review">审阅</a>）' : ''}${condQS() ?
        ` · 按适用条件筛选：明确符合 <b>${visible.filter(c => c.applies === 'yes').length}</b> 张，通用（原文未说明条件）${visible.filter(c => c.applies === 'general').length} 张；已排除不适用的卡片` : ''}</p>
      ${Object.entries(byType).map(([t, cs]) => `<h3>${esc(TYPE_ZH[t] || t)} <span class="muted small">${cs.length}</span></h3><div class="cardlist">` +
        cs.map(c => `<a class="item" href="${cardHref(c.id)}"><b>${esc(c.title)}</b> ${appliesBadge(c.applies)} ${condChips(c.conditions)}<br><span class="muted small">${esc(c.summary || '')}</span></a>`).join('') + '</div>').join('')}
      <h2>文档摘要层 <span class="muted small">${sums.length} 篇 · 每篇原始文档一张摘要卡片，指向它贡献的知识</span></h2><div class="cardlist">${sums.map(c =>
        `<a class="item" href="${cardHref(c.id)}"><b>${esc(c.title)}</b> <span class="mono small muted">${(c.sources || []).map(x => esc(x.path)).join(', ')}</span><br><span class="muted small">${esc(c.summary || '')}</span></a>`).join('') || '<p class="muted">无</p>'}</div></section></div>`);
    bindCond();
    return bindTree($('#main'));
  }
  const d = await get('cards/' + encodeURIComponent(id));
  if (d.lifecycle === 'superseded') {
    return set(`<div class="panel"><h1>${esc(d.title)}</h1><div class="banner warn">该知识已被替换为 <a href="${cardHref(d.replaced_by)}">${esc(d.replaced_by)}</a>。</div></div>`);
  }
  const showHead = can('reviewer') && (q.view === 'head' || !d.published);
  const card = showHead ? d.head : d.published;
  const known = new Set(all.map(c => c.id));
  const head = d.head;
  let banners = '';
  if (can('reviewer')) {
    if (head.lifecycle !== 'active') banners += `<div class="banner bad">此卡片状态：${zh(head.lifecycle)}${head.replaced_by ? ' → ' + esc(head.replaced_by) : ''}（读者不可见）</div>`;
    if (d.published && head.rev !== head.published_rev)
      banners += `<div class="banner info">有新修订 r${head.rev}（${zh(head.status)}）尚未发布。正在查看：${showHead ? '最新修订 r' + head.rev : '已发布 r' + head.published_rev}。
        <a href="${cardHref(id)}?view=${showHead ? 'published' : 'head'}">切换</a> · <a href="#/review/${encodeURIComponent(id)}">去审阅</a></div>`;
    if (!d.published) banners += `<div class="banner warn">尚未发布（${zh(head.status)}），读者不可见。 <a href="#/review/${encodeURIComponent(id)}">去审阅</a></div>`;
  }
  if ((d.issues || []).some(i => i.kind === 'contradiction')) banners += `<div class="banner bad">此卡片涉及尚未解决的矛盾，详见文末“已知分歧与待解问题”。</div>`;
  if ((head.stale_sources || []).length) banners += `<div class="banner warn">原始文档已更新，此卡片可能过时：${head.stale_sources.map(esc).join('，')}</div>`;
  set(`<div class="cols"><aside class="panel side">${topicTree(visible, id)}</aside>
    <article class="panel doc"><div class="row">${badge('t', TYPE_ZH[card.type] || card.type)}${can('reviewer') ? badge(head.status) : ''}
      <span class="small muted">r${card.rev} · 证据核验 ${Math.round((card.grounding || {}).score * 100 || 0)}% · ${originLabel(card.origin, false)}${card.published_by ? ' · 由 ' + esc(card.published_by) + ' 发布于 ' + fmtTime(card.published_at) : ''}</span></div>
    ${banners}<h1>${esc(card.title)}</h1>${(card.aliases || []).length ? `<p class="muted small">别名：${card.aliases.map(esc).join('，')}</p>` : ''}
    <p><i>${esc(card.summary || '')}</i></p>${renderCardBody(card, known)}
    ${relationsBlock(card, d.backlinks)}${(card.relations || []).length ? '<p>' + basisSummary(card.relations) + '</p>' : ''}
    ${facetsBlock(card)}
    <h3>证据（原文引用，系统自动核验）</h3>${evidenceList(card, false)}
    <p class="small muted">来源：${(card.sources || []).map(s => `${docLink(s.path)} <span title="版本">v${s.version}</span>`).join('，')}
    ${can('reviewer') && card.origin && card.origin.run ? ` · <a href="#/traces/${esc(card.origin.run)}">查看编译过程</a>` : ''}</p>
    ${issuesBlock(d.issues, id)}</article></div>`);
  bindTree($('#main')); bindEvidence($('#main')); bindReport();
};

routes.src = async (parts, q) => {
  const path = parts.join('/');
  const tree = await get('sources');
  const treeHtml = n => '<ul>' + n.children.filter(c => !(c.type === 'file' && c.path === n.index && n.path)).map(c => c.type === 'dir'
    ? `<li class="dir ${path.startsWith(c.path + '/') ? '' : 'closed'}"><span data-toggle>${esc(c.title || c.name)}</span>${c.index ? `<a href="${srcHref(c.index)}" class="${c.index === path ? 'on' : ''}" style="font-size:12px;color:var(--muted)">· 目录页</a>` : ''}${treeHtml(c)}</li>`
    : `<li><a href="${c.name.match(/\.(md|markdown|mdx)$/i) ? srcHref(c.path) : '/raw/' + c.path}" class="${c.path === path ? 'on' : ''}" title="${esc(c.path)}">${esc(c.title || c.name)}</a></li>`).join('') + '</ul>';
  const up = can('reviewer') ? `<details style="margin-top:12px"><summary>上传 Markdown / HTML 文件或文件夹</summary>
      <div class="row"><input type="file" id="upfiles" multiple accept=".md,.markdown,.mdx,.html,.htm,.png,.jpg,.jpeg,.gif,.svg,.webp,.pdf,.csv,.txt,.json,.yaml,.yml"></div>
      <div class="row"><input type="file" id="updir" webkitdirectory multiple></div>
      <div class="row"><input id="upprefix" placeholder="目标文件夹（可选）" style="width:100%"></div>
      <div class="row"><input id="upnote" placeholder="上传说明（可选）" style="width:100%"></div>
      <div class="row"><button class="primary" id="upgo">上传</button></div><div id="upres" class="small"></div></details>` : '';
  let mainHtml = `<h1>原始文档</h1><p class="muted">第一层：原样保存的 Markdown 文档，保持作者的目录结构、索引顺序与相互链接。</p>`;
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
    mainHtml = `<div class="row small muted"><span class="mono">${esc(path)}</span> · v${q.v || meta.version}${q.v && +q.v !== meta.version ? ' <span class="badge b-warn">历史版本</span>' : ''}
        · 上传：${esc(meta.by)} ${fmtTime(meta.at)} · 首次：${esc(meta.first_by)} ${fmtTime(meta.first_at)}
        · <a href="${srcHref(path, raw ? (q.v ? 'v=' + q.v : '') : 'raw=1' + (q.v ? '&v=' + q.v : ''))}">${raw ? '渲染视图' : '原文（带行号）'}</a>
        · <a href="/raw/${esc(path)}${q.v ? '?v=' + q.v : ''}" target="_blank">下载</a></div>
      ${meta.derived_from ? `<div class="banner warn">此文档由 HTML 原件自动转换（${esc(meta.converter)}）。原件始终保留：<a href="/raw/${esc(meta.derived_from)}" target="_blank">查看原始 HTML</a> · <a href="/raw/${esc(meta.derived_from)}" download>下载</a></div>` : ''}
      ${sumCard ? `<div class="banner info">文档摘要卡片：<a href="${cardHref(sumCard.id)}${sumCard.public ? '' : '?view=head'}">${esc(sumCard.title)}</a> ${can('reviewer') ? badge(sumCard.status) : ''}</div>` : ''}
      ${d.tree && d.tree.nodes.length ? `<details class="tree" ${raw ? 'open' : ''} style="margin:8px 0"><summary class="small">文档目录树（${d.tree.lines} 行 · 按标题结构建立，用于问答导航与长文档分章编译）</summary>${outlineHtml(d.tree.nodes)}</details>` : ''}
      ${body}
      <details style="margin-top:16px"><summary class="small">版本历史（${meta.history.length}）</summary><table class="grid"><tr><th>版本</th><th>上传者</th><th>时间</th><th>sha256</th><th>说明</th></tr>
        ${meta.history.slice().reverse().map(h => `<tr><td><a href="${srcHref(path, 'v=' + h.version)}">v${h.version}</a></td><td>${esc(h.by)}</td><td>${fmtTime(h.at)}</td><td class="mono">${esc(h.sha256.slice(0, 12))}</td><td>${esc(h.note || '')}</td></tr>`).join('')}</table></details>
      ${d.derived_cards.length ? `<h3>由此文档编译的知识</h3><p>${d.derived_cards.map(c => `<a href="${cardHref(c.id)}">${esc(c.title)}</a> ${can('reviewer') ? badge(c.status) : ''}${c.stale ? badge('stale', '需更新') : ''}`).join(' · ')}</p>` : ''}
      ${can('admin') ? `<p><button class="bad small" id="retire">停用此文档</button></p>` : ''}`;
  }
  set(`<div class="cols"><aside class="panel side"><div class="tree">${treeHtml(tree)}</div>${up}</aside><section class="panel">${mainHtml}</section></div>`);
  bindTree($('#main'));
  if (q.L) { const el = document.getElementById('L' + q.L.split('-')[0]); if (el) el.scrollIntoView({ block: 'center' }); }
  if (q.h) { const el = document.getElementById(q.h) || document.getElementById(MD.slug(q.h)); if (el) el.scrollIntoView(); }
  const rb = $('#retire'); if (rb) rb.onclick = async () => { if (!confirm('停用后文档存档到历史，引用它的卡片会被标记为过时。继续？')) return; await api('DELETE', 'sources/file?path=' + encodeURIComponent(path)); toast('已停用'); location.hash = '#/src'; };
  const go = $('#upgo'); if (go) go.onclick = () => upload();
};

async function upload() {
  const files = [...$('#upfiles').files, ...$('#updir').files];
  if (!files.length) return toast('请选择文件或文件夹');
  const items = await Promise.all(files.map(f => new Promise(res => {
    const r = new FileReader();
    const rel = f.webkitRelativePath || f.name;
    if (/\.(md|markdown|mdx|txt|csv|json|ya?ml|svg|html?)$/i.test(f.name)) { r.onload = () => res({ path: rel, text: r.result }); r.readAsText(f); }
    else { r.onload = () => res({ path: rel, b64: String(r.result).split(',')[1] || '' }); r.readAsDataURL(f); }
  })));
  const d = await api('POST', 'sources/upload', { files: items, prefix: $('#upprefix').value.trim(), note: $('#upnote').value.trim() });
  $('#upres').innerHTML = d.results.map(r => `${badge(r.status === 'skipped' ? 'warn' : 'published', r.status)} ${esc(r.path)} ${r.reason ? esc(r.reason) : ''}`).join('<br>');
  toast(`上传完成：${d.results.filter(r => r.status === 'added' || r.status === 'updated').length} 个文件有变化`);
  setTimeout(route, 800);
}

routes.search = async (_, q) => {
  $('#q').value = q.q || '';
  const d = await get('search?q=' + encodeURIComponent(q.q || ''));
  set(`<div class="panel"><h1>搜索：${esc(q.q || '')}</h1><h3>知识卡片（${d.cards.length}）</h3><div class="cardlist">${d.cards.map(c =>
    `<a class="item" href="${cardHref(c.id)}"><b>${esc(c.title)}</b> ${can('reviewer') ? badge(c.status) : ''}<br><span class="muted small">${esc(c.summary)}</span></a>`).join('') || '<p class="muted">无</p>'}</div>
    <h3>原始文档章节（${d.sources.length}）</h3><div class="cardlist">${d.sources.map(s =>
    `<a class="item" href="${srcHref(s.path, 'L=' + s.line)}"><b>《${esc(docTitle(s.path))}》· ${esc(s.title || '')}</b> <span class="muted small">L${s.line}-${s.end || ''}</span><br><span class="muted small">${esc(s.snippet)}</span></a>`).join('') || '<p class="muted">无</p>'}</div></div>`);
};

// ---------------------------------------------------------------- graph
routes.graph = async (_, q) => {
  const g0 = await get(withCond('graph' + (q.all ? '?all=1' : '')));
  const bar = await condBar();
  const keep = new Set(g0.nodes.filter(n => q.sum || n.type !== 'summary').map(n => n.id));
  const g = { nodes: g0.nodes.filter(n => keep.has(n.id)), edges: g0.edges.filter(e => keep.has(e.s) && keep.has(e.t)) };
  const types = [...new Set(g.nodes.map(n => n.type))];
  set(`<div class="panel" style="margin-bottom:10px">${viewTabs('#/graph')}${bar}</div><div class="row"><b>知识图谱</b><span class="muted small">${g.nodes.length} 节点 · ${g.edges.length} 关系 · 滚轮缩放，拖动平移，点击打开</span>
      ${can('reviewer') ? `<label class="small"><input type="checkbox" id="gall" ${q.all ? 'checked' : ''}> 包含未发布</label>` : ''}
      <input id="gfilter" placeholder="高亮…" style="width:160px"></div>
    <div class="legend row">${types.map(t => `<span><i style="background:${TYPE_COLORS[t] || '#888'}"></i>${esc(TYPE_ZH[t] || t)}</span>`).join('')}
      <span class="small muted">边：实线 原文明确 · 虚线 推断 · 橙色点线 存疑 · 红色 矛盾</span>
      <label class="small"><input type="checkbox" id="gsum"> 显示文档摘要节点</label></div>
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
    if (hover) { ctx.fillStyle = ink; ctx.font = '13px sans-serif'; ctx.fillText(`${hover.title}  [${TYPE_ZH[hover.type] || hover.type} · ${zh(hover.status)}]`, 10, H - 12); }
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
const RISK_ZH = { low: '低风险', medium: '中风险', high: '高风险' };
const riskBadge = r => r ? `<span class="badge b-${r.level === 'low' ? 'exact' : r.level === 'medium' ? 'request_changes' : 'missing'}" title="${esc((r.reasons || []).join('\n') || '证据全部精确命中原文；无存疑/矛盾关系；单一来源；粒度合规')}">${RISK_ZH[r.level]}</span>` : '';
const sizeBadge = g => g ? `<span class="small muted" title="阅读单位：汉字或英文单词">${g.units} 字/词 · ${g.minutes} 分钟</span>${(g.issues || []).map(i => ' ' + badge(i === 'long' ? 'comment' : 'warn', { thin: '过薄', long: '偏长', too_long: '过长', fragmented: '补充段多', broad: '证据过多' }[i] || i)).join('')}` : '';
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
  set(`<div class="panel"><h1>审阅队列</h1><div class="tabs">${tabs.map(t => `<a href="#/review?s=${t}" class="${t === tab ? 'on' : ''}">${zh(t)} (${cards.filter(c => c.status === t).length})</a>`).join('')}</div>
    <div class="row small">按风险：${['', 'high', 'medium', 'low'].map(r => `<a href="#/review?s=${tab}${r ? '&r=' + r : ''}" class="badge ${r === risk ? 'b-in_review' : ''}">${r ? RISK_ZH[r] + ' ' + counts[r] : '全部 ' + (counts.high + counts.medium + counts.low)}</a>`).join(' ')}
      <span class="muted">· 高/中风险须逐张审阅；只有低风险卡片可以批量通过（服务器强制），批量必须填写评语并留下审计记录。</span></div>
    ${batchable && counts.low ? `<details class="panel" style="margin:8px 0;padding:10px 14px" ${risk === 'low' ? 'open' : ''}><summary><b>批量通过低风险卡片</b> <span class="small muted">（已选 <span id="bsel">0</span> 张）</span></summary>
      <p class="small muted">低风险判定：证据全部逐字命中原文（精确/位置偏移）；无存疑或矛盾关系；单一来源；非人工修改、非更新已发布内容；置信度 ≥ 0.7；粒度合规。批量通过后，每张卡片各自留下审阅记录（带批次号），审计日志记录批次与判定标准。</p>
      <div class="row"><button id="bsall">选中本页全部低风险</button><button id="bsnone">清空</button></div>
      <textarea id="bcomment" placeholder="评语（必填，至少 10 个字）：说明批量通过的依据与你的核对方式，例如“抽查其中 5 张对照原文，均与原文一致；其余依据证据全部精确匹配”"></textarea>
      <div class="row"><button class="primary" id="bgo">批量通过所选</button><span id="bres" class="small"></span></div></details>` : ''}
    <table class="grid"><tr>${batchable ? '<th></th>' : ''}<th>卡片</th><th>风险</th><th>类型</th><th>篇幅</th><th>来源</th><th>证据核验</th><th>关系</th><th>编译来源</th></tr>
    ${rows.map(c => `<tr>${batchable ? `<td>${c.risk && c.risk.level === 'low' ? `<input type="checkbox" class="bsel" value="${esc(c.id)}">` : ''}</td>` : ''}
      <td><a href="#/review/${encodeURIComponent(c.id)}"><b>${esc(c.title)}</b></a><br><span class="mono muted">${esc(c.id)}</span>
        ${c.lifecycle !== 'active' ? badge(c.lifecycle) : ''}${(c.stale_sources || []).length ? badge('stale', '原文已变') : ''}${c.published_rev ? badge('published', '在线 r' + c.published_rev) : ''}</td>
      <td>${riskBadge(c.risk)}${c.risk && c.risk.reasons.length ? `<div class="small muted" style="max-width:260px">${c.risk.reasons.slice(0, 2).map(esc).join('；')}${c.risk.reasons.length > 2 ? '…' : ''}</div>` : ''}</td>
      <td>${esc(TYPE_ZH[c.type] || c.type)} <span class="small muted">r${c.rev}</span></td><td>${sizeBadge(c.risk && c.risk.granularity)}</td>
      <td class="small">${(c.sources || []).map(s => docLink(s.path)).join('<br>')}</td>
      <td>${gbadge(c.grounding, c)}</td><td>${basisSummary(c.relations)}</td><td class="small">${originLabel(c.origin)}</td></tr>`).join('') || '<tr><td colspan="9" class="muted">空</td></tr>'}</table></div>`);
  const boxes = () => [...document.querySelectorAll('.bsel')];
  const upd = () => { const el = $('#bsel'); if (el) el.textContent = boxes().filter(b => b.checked).length; };
  boxes().forEach(b => b.onchange = upd);
  if ($('#bsall')) $('#bsall').onclick = () => { boxes().forEach(b => b.checked = true); upd(); };
  if ($('#bsnone')) $('#bsnone').onclick = () => { boxes().forEach(b => b.checked = false); upd(); };
  if ($('#bgo')) $('#bgo').onclick = async () => {
    const ids = boxes().filter(b => b.checked).map(b => b.value), comment = $('#bcomment').value.trim();
    if (!ids.length) return toast('未选择卡片');
    if (comment.length < 10) return toast('批量操作必须填写评语（至少 10 个字）');
    if (!confirm(`确认批量通过 ${ids.length} 张低风险卡片？每张卡片都会记录你的评语与批次号。`)) return;
    try {
      const r = await api('POST', 'cards/_batch', { ids, action: 'approve', comment });
      toast(`${r.batch}：通过 ${r.done.length} 张${r.skipped.length ? '，跳过 ' + r.skipped.length + ' 张' : ''}`, 6000);
      if (r.skipped.length) alert('以下卡片未通过批量检查，需逐张审阅：\n' + r.skipped.map(x => x.id + '：' + x.reason).join('\n'));
      route();
    } catch (e) { toast(e.message); }
  };
};
const FIELD_ZH = { title: '标题', type: '类型', parent: '上级主题', summary: '摘要', aliases: '别名', confidence: '置信度' };
function semanticDiff(sd) {
  if (!sd) return '';
  const val = v => Array.isArray(v) ? v.map(esc).join('，') || '（空）' : (v === null || v === undefined || v === '' ? '（空）' : esc(String(v)));
  const rel = r => `<span class="badge">${esc(r.rel)}</span> ${esc(r.target)}${basisBadge(r)}`;
  const ev = e => `<b>${esc(e.id)}</b> ${docLink(e.path, 'L=' + encodeURIComponent(e.lines), '· 第 ' + esc(e.lines) + ' 行')} <span class="small">${esc((e.quote || '').slice(0, 120))}</span>`;
  const sec = (title, items, cls) => items.length ? `<h4 style="margin:12px 0 4px">${title}（${items.length}）</h4><ul class="small">${items.map(x => `<li class="${cls || ''}">${x}</li>`).join('')}</ul>` : '';
  const nothing = !sd.fields.length && !sd.relations_added.length && !sd.relations_removed.length && !sd.relations_changed.length &&
    !sd.evidence_added.length && !sd.evidence_removed.length && !sd.body;
  return `<div class="banner info small">r${sd.a || '（空）'} → r${sd.b} · ${originLabel(sd.origin, false)}${sd.change_note ? ' · ' + esc(sd.change_note) : ''}</div>
    ${nothing ? '<p class="muted">两个修订内容相同。</p>' : ''}
    ${sec('字段变化', sd.fields.map(f => `<b>${esc(FIELD_ZH[f.field] || f.field)}</b>：<span class="diff"><span class="d">${val(f.before)}</span> → <span class="a">${val(f.after)}</span></span>`))}
    ${sec('新增关系', sd.relations_added.map(rel), 'a')}${sec('移除关系', sd.relations_removed.map(rel), 'd')}
    ${sec('关系状态变化', sd.relations_changed.map(c => `${rel(c.before)} → ${basisBadge(c.after)}`))}
    ${sec('新增证据', sd.evidence_added.map(ev), 'a')}
    ${(sd.evidence_moved || []).length ? (() => { const by = {}; sd.evidence_moved.forEach(e => e.moved_to.forEach(t => (by[t] = by[t] || []).push(e)));
      return `<h4 style="margin:12px 0 4px">移至其他卡片的证据（${sd.evidence_moved.length}，未丢失）</h4><ul class="small">${Object.entries(by).map(([t, es]) =>
        `<li>→ <a href="#/review/${encodeURIComponent(t)}">${esc(t)}</a>：${es.length} 条（${es.map(e => esc(e.id)).join('、')}）</li>`).join('')}</ul>`; })() : ''}
    ${sec('移除证据（不再出现在任何卡片中）', sd.evidence_removed.map(ev), 'd')}
    ${sd.evidence_renumbered ? `<p class="small muted">${sd.evidence_renumbered} 条证据仅编号变化</p>` : ''}
    ${sd.body ? `<h4 style="margin:12px 0 4px">正文改动</h4><div class="diff">${sd.body.split('\n').slice(2).map(l => `<div class="${l.startsWith('+') ? 'a' : l.startsWith('-') ? 'd' : l.startsWith('@') ? 'h' : ''}">${esc(l) || ' '}</div>`).join('')}</div>` : '<p class="small muted">正文无改动。</p>'}`;
}
function originLabel(o, link = true) {
  o = o || {};
  if (o.kind === 'llm') return link && o.run ? `<a href="#/traces/${esc(o.run)}">LLM ${esc(o.model || '')}</a>` : 'LLM 编译 ' + esc(o.model || '');
  if (o.kind === 'query') return link && o.run ? `<a href="#/ask/${esc(o.run)}">问答回写 ${esc(o.user || '')}</a>` : '问答回写 ' + esc(o.user || '');
  if (o.kind === 'schema') return '编译规范主题骨架' + (o.schema ? ' v' + esc(o.schema) : '');
  if (o.kind === 'human') return '人工编辑 ' + esc(o.user || '');
  return esc(o.kind || '—');
}
function gbadge(g, card) {
  g = g || {};
  if (!g.total) return card && card.type === 'topic' ? '<span class="small muted">主题卡，无需证据</span>' : badge('missing', '无证据');
  const s = Math.round((g.score || 0) * 100);
  return `${badge(s >= 90 ? 'exact' : s >= 60 ? 'fuzzy' : 'missing', s + '%')}<span class="small muted">${(g.exact || 0) + (g.moved || 0) + (g.elided || 0) + (g.card || 0)}/${g.total || 0} 可核验${g.missing ? '，' + g.missing + ' 未找到' : ''}</span>`;
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
    tabBody = `<div class="row small">对比：<select id="dbase">${[0, ...d.revisions.filter(r => r !== h.rev)].map(r => `<option value="${r}" ${r === diffBase ? 'selected' : ''}>${r ? 'r' + r + (r === h.published_rev ? '（已发布）' : '') : '（空）'}</option>`).join('')}</select> → r${h.rev}</div>
      ${semanticDiff(df.semantic)}
      <details style="margin-top:12px"><summary class="small muted">原始文本差异（frontmatter + 正文）</summary><div class="diff">${df.diff.split('\n').map(l => `<div class="${l.startsWith('+') ? 'a' : l.startsWith('-') ? 'd' : l.startsWith('@') ? 'h' : ''}">${esc(l) || ' '}</div>`).join('')}</div></details>`;
  }
  if (tab === 'edit') tabBody = `<p class="small muted">人工修改将生成新修订（来源记为你本人），重新进入审阅流程。</p>
      <div class="row"><label style="width:60px">标题</label><input id="e_title" value="${esc(h.title)}" style="flex:1"></div>
      <div class="row"><label style="width:60px">类型</label><select id="e_type">${Object.keys(TYPE_ZH).map(t => `<option ${t === h.type ? 'selected' : ''} value="${t}">${TYPE_ZH[t]}</option>`).join('')}</select>
        <label>上级主题</label><input id="e_parent" value="${esc(h.parent || '')}" list="cardids"><datalist id="cardids">${all.map(c => `<option value="${esc(c.id)}">${esc(c.title)}</option>`).join('')}</datalist></div>
      <div class="row"><label style="width:60px">别名</label><input id="e_aliases" value="${esc((h.aliases || []).join(', '))}" style="flex:1"></div>
      <div class="row"><label style="width:60px">摘要</label><input id="e_summary" value="${esc(h.summary || '')}" style="flex:1"></div>
      <label class="small">正文（Markdown，[[卡片id]] 链接，[E1] 证据标记）</label><textarea id="e_body" class="code">${esc(h.body)}</textarea>
      <label class="small">关系（JSON）</label><textarea id="e_rel" class="code" style="min-height:90px">${esc(JSON.stringify(h.relations || [], null, 1))}</textarea>
      <label class="small">证据（JSON：id, path, lines, quote —— 保存后自动重新核验）</label><textarea id="e_ev" class="code" style="min-height:140px">${esc(JSON.stringify((h.evidence || []).map(e => ({ id: e.id, path: e.path, lines: e.lines, quote: e.quote })), null, 1))}</textarea>
      <div class="row"><input id="e_note" placeholder="修改说明" style="flex:1"><button class="primary" id="e_save">保存为新修订</button></div>`;
  if (tab === 'history') tabBody = `<table class="grid"><tr><th>时间</th><th>谁</th><th>动作</th><th>修订</th><th>说明</th></tr>${(d.review_log || []).slice().reverse().map(r =>
      `<tr><td class="small">${fmtTime(r.ts)}</td><td>${esc(r.user)} <span class="muted small">${esc(r.role)}</span></td><td>${badge(r.verdict)}${r.target ? ' → ' + esc(r.target) : ''}</td><td>r${r.rev}</td><td>${esc(r.comment || '')}${r.anchor ? ` <span class="muted small">@${esc(r.anchor)}</span>` : ''}</td></tr>`).join('') || '<tr><td colspan=5 class="muted">尚无审阅记录</td></tr>'}</table>
    <h3>修订</h3><p>${d.revisions.map(r => `<a href="#/review/${encodeURIComponent(id)}?tab=rev&r=${r}">r${r}</a>${r === h.published_rev ? '（已发布）' : ''}`).join(' · ')}</p>
    <h3>事件</h3><table class="grid">${(d.events || []).slice().reverse().map(e => `<tr><td class="small">${fmtTime(e.ts)}</td><td>${esc(e.actor)}</td><td class="mono">${esc(e.action)}</td><td class="small mono">${esc(JSON.stringify(e.detail || {}))}</td></tr>`).join('')}</table>`;
  if (tab === 'rev') {
    const r = await get(`cards/${encodeURIComponent(id)}/rev/${+q.r}`);
    tabBody = `<p class="small muted">修订 r${r.rev} · ${fmtTime(r.created)} · ${originLabel(r.origin, false)} · ${esc(r.change_note || '')}</p><div class="doc"><h1>${esc(r.title)}</h1>${renderCardBody(r, known)}</div>${evidenceList(r)}`;
  }
  const v = d.reviews.votes;
  const isAdmin = can('admin');
  const adminBtns = isAdmin ? `<div class="row"><b class="small">管理员决定：</b>
      ${h.status === 'approved' ? '<button class="primary" data-act="publish">发布</button>' : ''}
      ${['approved', 'in_review', 'rejected'].includes(h.status) ? '<button class="warn" data-act="return">打回修改</button>' : ''}
      ${h.status !== 'rejected' && h.status !== 'published' ? '<button class="bad" data-act="reject">否决</button>' : ''}
      ${['rejected', 'changes_requested'].includes(h.status) ? '<button data-act="reopen">重新审阅</button>' : ''}
      ${h.published_rev && h.lifecycle === 'active' ? '<button class="bad" data-act="withdraw">下架</button><button data-act="supersede">替换为…</button>' : ''}
      ${h.lifecycle !== 'active' ? '<button class="ok" data-act="restore">恢复上架</button>' : ''}</div>` : '';
  set(`<div class="row"><a href="#/review?s=${h.status}">← 审阅队列</a> <span class="mono muted">${esc(id)}</span> ${badge(h.status)} ${badge(h.lifecycle)}
      <span class="small muted">r${h.rev}${h.published_rev ? ' · 已发布 r' + h.published_rev : ''} · ${originLabel(h.origin, false)} · <a href="${cardHref(id)}?view=head">读者视图</a></span></div>
    ${h.change_note ? `<div class="banner info">修订说明：${esc(h.change_note)}</div>` : ''}
    ${(h.stale_sources || []).length ? `<div class="banner warn">原文在编译后已变更：${h.stale_sources.map(esc).join('，')} —— 建议重新编译</div>` : ''}
    <div class="cols3"><section class="panel"><div class="tabs">${[['card', '卡片'], ['diff', '差异'], ['edit', '编辑'], ['history', '审阅记录']].map(([t, n]) =>
      `<a href="#/review/${encodeURIComponent(id)}?tab=${t}" class="${t === tab ? 'on' : ''}">${n}</a>`).join('')}</div>${tabBody}</section>
    <aside class="panel side" style="max-height:none;position:static">
      <h3 style="margin-top:0">审阅决定</h3>
      <p class="small">当前修订 r${h.rev} 投票：${badge('approve', '通过 ' + v.approve)}${badge('request_changes', '要求修改 ' + v.request_changes)}${badge('reject', '拒绝 ' + v.reject)}</p>
      <textarea id="rv_comment" placeholder="评语（必填：要求修改/拒绝/打回时）"></textarea>
      <div class="row"><input id="rv_anchor" placeholder="针对位置，如 E2 或 段落（可选）" style="flex:1"></div>
      <div class="row"><button class="ok" data-act="approve">通过</button><button class="warn" data-act="request_changes">要求修改</button><button class="bad" data-act="reject">拒绝</button><button data-act="comment">仅评论</button>
        ${['draft', 'changes_requested'].includes(h.status) ? '<button data-act="submit">提交审阅</button>' : ''}</div>
      ${adminBtns}
      ${d.risk ? `<h3>审阅风险 ${riskBadge(d.risk)}</h3>${d.risk.reasons.length ? `<ul class="small">${d.risk.reasons.map(r => `<li>${esc(r)}</li>`).join('')}</ul>` : '<p class="small muted">证据全部精确命中原文，无存疑关系，单一来源，粒度合规。</p>'}
        <p class="small">篇幅：${sizeBadge(d.risk.granularity)}${d.risk.granularity.needs_consolidation ? ` <button id="consolidate" class="warn">整合重写 / 拆分</button>` : ''}
        ${can('admin') && (d.risk.granularity.issues || []).includes('thin') ? ` <button id="mergeinto">并入其他卡片…</button>` : ''}</p>` : ''}
      <h3>关系的认识论状态</h3><p>${basisSummary(h.relations)}</p>
      <h3>证据核验 ${gbadge(h.grounding, h)}</h3>
      <p class="small muted">模型给出的每条引用都被逐字核对原文行。精确匹配的原文上下文默认折叠，需人工确认的默认展开。</p>
      ${evidenceList(h, true)}
      ${findings.length ? `<h3>编译器校验发现</h3><ul class="small">${findings.map(f => `<li>${badge(f.level === 'error' ? 'error' : 'warn', f.level)} ${esc(f.msg)}</li>`).join('')}</ul>` : ''}
      ${h.origin.kind === 'query' ? `<div class="banner info">此卡片来自问答回写：<a href="#/ask/${esc(h.origin.run)}">查看原问答与阅读计划</a></div>` : ''}
      ${trace && trace.run.kind !== 'query' ? `<h3>LLM 编译过程</h3><div class="kv"><div>运行</div><div><a href="#/traces/${esc(trace.run.id)}">${esc(trace.run.id)}</a></div><div>模型</div><div>${esc(trace.run.model)}</div>
        <div>耗时</div><div>${trace.run.latency_s}s</div><div>置信度</div><div>${h.confidence ?? '—'}</div>
        <div>编译规范</div><div>${trace.run.schema ? `<a href="#/schema?v=${trace.run.schema.version}">v${trace.run.schema.version}</a>` : '—'}</div>
        ${(trace.run.sections || []).length ? `<div>分章编译</div><div class="small">${trace.run.sections.map(x => esc(x.path + ' §' + x.part + ' L' + x.lines)).join('<br>')}</div>` : ''}</div>
        ${trace.run.notes ? `<p class="small"><b>编译器备注：</b>${esc(trace.run.notes)}</p>` : ''}
        <details><summary class="small">模型思考摘要</summary><pre class="box">${esc(trace['thinking.md'] || '')}</pre></details>` : ''}
    </aside></div>`);
  bindEvidence($('#main'));
  fillSourceLines($('#main'));
  const db = $('#dbase'); if (db) db.onchange = () => { location.hash = `#/review/${encodeURIComponent(id)}?tab=diff&base=${db.value}`; };
  document.querySelectorAll('[data-act]').forEach(b => b.onclick = async () => {
    const act = b.dataset.act;
    const comment = $('#rv_comment').value.trim();
    if (['request_changes', 'reject', 'return'].includes(act) && !comment) return toast('请填写评语');
    let target = '';
    if (act === 'supersede') { target = prompt('替换为哪张卡片（id）？') || ''; if (!target) return; }
    if (['publish', 'withdraw', 'reject'].includes(act) && !confirm(`确认：${zh(act)}？`)) return;
    try { await api('POST', `cards/${encodeURIComponent(id)}/action`, { action: act, comment, target, anchor: $('#rv_anchor').value.trim() }); toast(zh(act) + ' ✓'); route(); }
    catch (e) { toast(e.message); }
  });
  const cb = $('#consolidate'); if (cb) cb.onclick = async () => {
    if (!confirm('调用 LLM 整合重写（必要时拆分为子概念卡）？只使用卡片已有的、已核验的证据；结果作为新修订进入审阅。')) return;
    cb.disabled = true; cb.textContent = '整合中…';
    try { const r = await api('POST', `cards/${encodeURIComponent(id)}/consolidate`, {});
      if (r.status !== 'done') throw new Error(r.error || '失败');
      toast(`整合完成：${r.before.units} → ${r.after.units} 字/词；写出 ${r.written.length} 张卡片修订`, 6000);
      location.hash = `#/review/${encodeURIComponent(id)}?tab=diff`; route();
    } catch (e) { toast('整合失败：' + e.message); cb.disabled = false; cb.textContent = '整合重写 / 拆分'; }
  };
  const mb = $('#mergeinto'); if (mb) mb.onclick = async () => {
    const into = prompt('把本卡并入哪张卡片（id）？本卡将被标记为“已被替换”。'); if (!into) return;
    try { const r = await api('POST', `cards/${encodeURIComponent(id)}/merge`, { into }); toast('已并入 ' + into + '（r' + r.rev + '，待审阅）'); location.hash = '#/review/' + encodeURIComponent(into) + '?tab=diff'; }
    catch (e) { toast(e.message); }
  };
  const sv = $('#e_save'); if (sv) sv.onclick = async () => {
    try {
      const body = { title: $('#e_title').value, type: $('#e_type').value, parent: $('#e_parent').value.trim(), summary: $('#e_summary').value,
        aliases: $('#e_aliases').value.split(',').map(s => s.trim()).filter(Boolean), body: $('#e_body').value,
        relations: JSON.parse($('#e_rel').value || '[]'), evidence: JSON.parse($('#e_ev').value || '[]'), change_note: $('#e_note').value || '人工编辑' };
      const r = await api('PUT', 'cards/' + encodeURIComponent(id), body); toast('已保存为 r' + r.rev); location.hash = `#/review/${encodeURIComponent(id)}?tab=diff`;
    } catch (e) { toast('保存失败：' + e.message); }
  };
}

// ---------------------------------------------------------------- LLM observability
routes.traces = async ([rid], q) => {
  if (rid) return traceView(rid, q);
  const [runs, st] = await Promise.all([get('traces'), get('traces/stats')]);
  const g = st.grounding;
  set(`<h1>LLM 观测</h1><p class="muted">每一次知识编译调用的完整记录：提示词、模型原始输出、思考摘要、用量、耗时、校验与证据核验结果。</p>
    <div class="stats"><div class="stat"><b>${st.runs}</b><span>调用次数（失败 ${st.failed || 0}）</span></div>
      <div class="stat"><b>${(st.input_tokens / 1000).toFixed(1)}k / ${(st.output_tokens / 1000).toFixed(1)}k</b><span>输入 / 输出 tokens</span></div>
      <div class="stat"><b>$${st.cost_usd}</b><span>估算费用</span></div><div class="stat"><b>${st.runs ? (st.latency_s / st.runs).toFixed(1) : 0}s</b><span>平均耗时</span></div>
      <div class="stat"><b>${st.cards_written}</b><span>写出的卡片修订</span></div>
      <div class="stat"><b>${g.total ? Math.round((g.exact + g.moved) / g.total * 100) : 0}%</b><span>引用原文可核验（${g.exact + g.moved}/${g.total}）</span></div></div>
    <div class="cols3"><section class="panel"><table class="grid"><tr><th>运行</th><th>类型</th><th>状态</th><th>来源 / 问题</th><th>模型</th><th>耗时</th><th>卡片</th><th>核验</th><th>发现</th></tr>
      ${runs.map(r => `<tr><td><a href="#/traces/${esc(r.id)}" class="mono">${esc(r.id)}</a><br><span class="small muted">${esc(r.by)}</span></td><td>${r.kind === 'query' ? badge('comment', '问答') : badge('t', '编译')}${(r.sections || []).length ? badge('t', '分章 ' + r.sections[0].part) : ''}</td><td>${badge(r.status)}</td>
        <td class="small">${r.kind === 'query' ? esc((r.question || '').slice(0, 60)) : r.sources.map(esc).join('<br>')}</td>
        <td class="small">${esc(r.model || '')}</td><td>${r.latency_s ?? ''}s</td><td>${(r.written || []).length}</td><td>${r.grounding ? gbadge(r.grounding) : ''}</td><td>${(r.findings || []).length}</td></tr>`).join('')}</table></section>
    <aside class="panel"><h3 style="margin-top:0">常见校验发现</h3><table class="grid">${Object.entries(st.findings).sort((a, b) => b[1] - a[1]).map(([k, n]) => `<tr><td class="small">${esc(k)}</td><td>${n}</td></tr>`).join('') || '<tr><td class="muted">无</td></tr>'}</table>
      <h3>关系认识论状态（累计）</h3><p>${Object.entries(st.bases).map(([b, n]) => badge(b === 'extracted' ? 'exact' : b === 'ambiguous' ? 'request_changes' : 'comment', zh(b) + ' ' + n)).join(' ')}</p>
      <h3>按编译规范版本</h3><table class="grid">${Object.entries(st.by_schema).map(([v, x]) => `<tr><td><a href="#/schema?v=${v.slice(1)}">${esc(v)}</a></td><td>${x.runs} 次</td><td>可核验 ${x.total ? Math.round(x.exact / x.total * 100) : 0}%</td></tr>`).join('') || '<tr><td class="muted">无</td></tr>'}</table>
      <h3>按模型</h3><table class="grid">${Object.entries(st.by_model).map(([m, x]) => `<tr><td class="small">${esc(m)}</td><td>${x.runs} 次</td><td>${(x.latency_s / x.runs).toFixed(1)}s</td></tr>`).join('')}</table></aside></div>`);
};

async function traceView(rid, q) {
  const t = await get('traces/' + encodeURIComponent(rid));
  const r = t.run;
  const tab = q.tab || 'overview';
  const NAMES = { 'thinking.md': '思考摘要', 'prompt.md': '用户提示', 'system.md': '系统提示', 'response.md': '原始输出', 'parsed.json': '解析结果', 'error.txt': '错误' };
  const STEP = { 'nav-': '导航·', 'ans-': '回答·' };
  const order = ['thinking.md', 'prompt.md', 'system.md', 'response.md', 'parsed.json', 'error.txt'];
  const files = Object.keys(t).filter(k => k !== 'run');
  const rank = f => (f.startsWith('ans-') ? 1 : 0) + (/^retry/.test(f) ? 2 : 0);
  files.sort((a, b) => rank(a) - rank(b) || order.indexOf(a.replace(/^(nav|ans|retry\d+)-/, '')) - order.indexOf(b.replace(/^(nav|ans|retry\d+)-/, '')));
  const pre = f => (f.match(/^(nav|ans|retry\d+)-/) || [''])[0];
  const label = f => { const p = pre(f); return (STEP[p] || (p ? '重试' + p.slice(5, -1) + '·' : '')) + (NAMES[f.slice(p.length)] || f); };
  const tabs = [['overview', '概览'], ...files.map(f => [f, label(f)])];
  const u = r.usage || {};
  let body = '';
  if (tab === 'overview' && r.kind === 'query') body = `<div class="kv"><div>问题</div><div><b>${esc(r.question)}</b></div><div>状态</div><div>${badge(r.status)} ${esc(r.error || '')}</div>
      <div>提问人</div><div>${esc(r.by)} · 范围 ${r.scope === 'all' ? '含未发布' : '仅已发布'}</div><div>后端 / 模型</div><div>${esc(r.backend)} / ${esc(r.model)}</div>
      <div>耗时 / 费用</div><div>${r.latency_s}s ${r.cost_usd !== undefined ? '· $' + r.cost_usd : ''}</div><div>引用核验</div><div>${r.grounding ? gbadge(r.grounding) : ''}</div></div>
      <p><a href="#/ask/${esc(r.id)}">在问答页查看答案与阅读计划 →</a></p>
      <h3>每次 LLM 调用</h3><table class="grid">${(r.calls || []).map(c => `<tr><td>${esc(c.step)}</td><td class="small">${esc(c.model)}</td><td>${c.latency_s}s</td><td class="small mono">${esc(JSON.stringify(c.usage))}</td><td class="small">${(c.prompt_chars / 1000).toFixed(1)}k 字符</td></tr>`).join('')}</table>
      <h3>时间线</h3><ul class="timeline">${(r.timeline || []).map(s => `<li><span class="mono">${fmtTime(s.ts).slice(11)}</span> ${esc(s.step)} <span class="muted">${esc(JSON.stringify(Object.fromEntries(Object.entries(s).filter(([k]) => !['ts', 'step'].includes(k)))))}</span></li>`).join('')}</ul>`;
  else if (tab === 'overview') body = `<div class="kv"><div>状态</div><div>${badge(r.status)} ${esc(r.error || '')}</div><div>发起人</div><div>${esc(r.by)}</div>
      <div>后端 / 模型</div><div>${esc(r.backend)} / ${esc(r.model)} ${r.effort ? '· effort ' + esc(r.effort) : ''}</div><div>提示词版本</div><div class="mono">${esc(r.prompt_version)}</div>
      <div>编译规范</div><div>${r.schema ? `<a href="#/schema?v=${r.schema.version}">SCHEMA.md v${r.schema.version}</a> <span class="mono small muted">${esc(r.schema.sha)}</span>` : '—'}</div>
      ${(r.sections || []).length ? `<div>分章编译</div><div class="small">${r.sections.map(x => `${esc(x.path)} §${esc(x.part)} L${esc(x.lines)}：${x.titles.map(esc).join('，')}`).join('<br>')}</div>` : ''}
      <div>关系状态</div><div>${r.bases ? Object.entries(r.bases).map(([b, n]) => zh(b) + ' ' + n).join(' · ') : '—'}</div>
      <div>来源文档</div><div>${r.sources.map(s => `<a href="${srcHref(s)}">${esc(s)}</a> <span class="mono small muted">${esc((r.source_shas[s] || '').slice(0, 10))}</span>`).join('<br>')}</div>
      <div>上下文</div><div class="small">${r.context ? `索引 ${r.context.index_cards} 张卡片 · 关联卡片全文 ${r.context.related_cards.length} 张 · 提示 ${(r.context.prompt_chars / 1000).toFixed(1)}k 字符` : ''}</div>
      <div>用量</div><div class="small mono">${esc(JSON.stringify(u))}</div><div>耗时 / 费用</div><div>${r.latency_s}s ${r.cost_usd !== undefined ? '· $' + r.cost_usd : ''} · stop=${esc(r.stop_reason || '')}${r.attempts > 1 ? ' · ' + badge('warn', '重试 ' + (r.attempts - 1) + ' 次') : ''}</div>
      ${(r.attempt_errors || []).length ? `<div>无效输出</div><div class="small">${r.attempt_errors.map(esc).join('<br>')}</div>` : ''}
      <div>证据核验</div><div>${r.grounding ? gbadge(r.grounding) : ''}</div></div>
    ${r.notes ? `<h3>编译器备注（给审阅者）</h3><div class="banner info">${esc(r.notes)}</div>` : ''}
    <h3>写出的卡片修订</h3><table class="grid">${(r.written || []).map(w => `<tr><td><a href="#/review/${encodeURIComponent(w.id)}">${esc(w.id)}</a></td><td>${w.action === 'create' ? '新建' : '更新'}</td><td>r${w.rev}</td><td>${gbadge(w.grounding)}</td></tr>`).join('') || '<tr><td class="muted">无</td></tr>'}</table>
    <h3>校验发现（${(r.findings || []).length}）</h3><table class="grid">${(r.findings || []).map(f => `<tr><td>${badge(f.level === 'error' ? 'error' : f.level === 'info' ? 'comment' : 'warn', f.level)}</td><td class="mono small">${esc(f.card)}</td><td class="small">${esc(f.msg)}</td></tr>`).join('') || '<tr><td class="muted">无</td></tr>'}</table>
    <h3>时间线</h3><ul class="timeline">${(r.timeline || []).map(s => `<li><span class="mono">${fmtTime(s.ts).slice(11)}</span> ${esc(s.step)} <span class="muted">${esc(JSON.stringify(Object.fromEntries(Object.entries(s).filter(([k]) => !['ts', 'step'].includes(k)))))}</span></li>`).join('')}</ul>`;
  else {
    const key = tab;
    body = `<p class="small muted">${(t[key] || '').length} 字符 · 以下为发送给 / 来自模型的原文，未经修改。</p><pre class="box">${esc(t[key] || '(无)')}</pre>`;
  }
  set(`<div class="row"><a href="#/traces">← LLM 观测</a><span class="mono">${esc(rid)}</span></div><div class="panel"><div class="tabs">${tabs.map(([k, n]) => `<a href="#/traces/${esc(rid)}?tab=${encodeURIComponent(k)}" class="${k === tab ? 'on' : ''}">${n}</a>`).join('')}</div>${body}</div>`);
}

routes.lint = async () => {
  const issues = await get('lint');
  const KIND = { dangling_relation: '关系指向不存在的卡片', dangling_wikilink: '正文链接指向不存在的卡片', dangling_parent: '上级主题不存在', stale_source: '原文已更新（需重新编译）',
    ungrounded_evidence: '引用未在原文中找到', no_evidence: '没有证据', dangling_replacement: '替换目标不存在',
    ambiguous_relation: '存在“存疑”关系待人工判断', missing_summary: '文档缺少摘要卡片（需重新编译）', duplicate_source: '原始文档内容高度重复',
    granularity_thin: '粒度过薄（单一事实，宜并入相关卡片）', granularity_too_long: '篇幅过长（需整合或拆分）',
    granularity_fragmented: '补充段过多（需整合重写）', granularity_broad: '证据过多（可能包含多个概念）' };
  set(`<div class="panel"><h1>知识库健康检查</h1><p class="muted">${issues.length} 项</p><table class="grid"><tr><th>卡片</th><th>问题</th><th>详情</th></tr>${issues.map(i =>
    `<tr><td><a href="#/review/${encodeURIComponent(i.card)}">${esc(i.card)}</a></td><td>${esc(KIND[i.kind] || i.kind)}</td><td class="small">${esc(i.detail)}</td></tr>`).join('')}</table></div>`);
};

// ---------------------------------------------------------------- admin
routes.publish = async () => {
  const cards = await get('cards');
  const appr = cards.filter(c => c.status === 'approved');
  const pub = cards.filter(c => c.published_rev);
  set(`<div class="panel"><h1>发布台</h1><h3>审阅通过、等待发布（${appr.length}）</h3>
    ${appr.length > 1 ? `<details style="margin:6px 0"><summary class="small"><b>批量发布</b>（已选 <span id="psel">0</span> 张；必须填写评语，留下审计记录）</summary>
      <div class="row"><button id="psall">全选</button></div><textarea id="pcomment" placeholder="发布评语（必填，至少 10 个字），例如“本批为第14讲相关卡片，均已经两位审阅者通过”"></textarea>
      <div class="row"><button class="primary" id="pgo">批量发布所选</button></div></details>` : ''}
    <table class="grid"><tr><th></th><th>卡片</th><th>修订</th><th>核验</th><th>当前在线</th><th></th></tr>${appr.map(c => `<tr><td><input type="checkbox" class="psel" value="${esc(c.id)}"></td><td><a href="#/review/${encodeURIComponent(c.id)}">${esc(c.title)}</a></td><td>r${c.rev}</td><td>${gbadge(c.grounding, c)}</td>
      <td>${c.published_rev ? 'r' + c.published_rev : '—'}</td><td><button class="primary" data-pub="${esc(c.id)}">发布</button> <button class="warn" data-ret="${esc(c.id)}">打回</button></td></tr>`).join('') || '<tr><td colspan=6 class="muted">无</td></tr>'}</table>
    <h3>已发布内容管理（${pub.length}）</h3><table class="grid"><tr><th>卡片</th><th>在线修订</th><th>状态</th><th>发布</th><th></th></tr>${pub.map(c => `<tr><td><a href="${cardHref(c.id)}">${esc(c.title)}</a></td><td>r${c.published_rev}${c.rev !== c.published_rev ? ` <span class="small muted">（新修订 r${c.rev} ${zh(c.status)}）</span>` : ''}</td>
      <td>${badge(c.lifecycle)}${c.replaced_by ? ' → ' + esc(c.replaced_by) : ''}${(c.stale_sources || []).length ? badge('stale', '原文已变') : ''}</td><td class="small">${esc(c.published_by || '')} ${fmtTime(c.published_at)}</td>
      <td>${c.lifecycle === 'active' ? `<button class="bad" data-wd="${esc(c.id)}">下架</button> <button data-sup="${esc(c.id)}">替换为…</button>` : `<button class="ok" data-rs="${esc(c.id)}">恢复</button>`}</td></tr>`).join('')}</table></div>`);
  const act = async (id, action, extra = {}) => { try { await api('POST', `cards/${encodeURIComponent(id)}/action`, { action, ...extra }); toast(zh(action) + ' ✓'); route(); } catch (e) { toast(e.message); } };
  document.querySelectorAll('[data-pub]').forEach(b => b.onclick = () => act(b.dataset.pub, 'publish'));
  const pboxes = () => [...document.querySelectorAll('.psel')];
  const pupd = () => { const el = $('#psel'); if (el) el.textContent = pboxes().filter(b => b.checked).length; };
  pboxes().forEach(b => b.onchange = pupd);
  if ($('#psall')) $('#psall').onclick = () => { pboxes().forEach(b => b.checked = true); pupd(); };
  if ($('#pgo')) $('#pgo').onclick = async () => {
    const ids = pboxes().filter(b => b.checked).map(b => b.value), comment = $('#pcomment').value.trim();
    if (!ids.length) return toast('未选择卡片');
    if (comment.length < 10) return toast('批量发布必须填写评语（至少 10 个字）');
    if (!confirm(`确认批量发布 ${ids.length} 张卡片？发布后读者可见。`)) return;
    try { const r = await api('POST', 'cards/_batch', { ids, action: 'publish', comment }); toast(`${r.batch}：发布 ${r.done.length} 张`); route(); }
    catch (e) { toast(e.message); }
  };
  document.querySelectorAll('[data-ret]').forEach(b => b.onclick = () => { const c = prompt('打回理由：'); if (c) act(b.dataset.ret, 'return', { comment: c }); });
  document.querySelectorAll('[data-wd]').forEach(b => b.onclick = () => { const c = prompt('下架理由：'); if (c !== null) act(b.dataset.wd, 'withdraw', { comment: c }); });
  document.querySelectorAll('[data-rs]').forEach(b => b.onclick = () => act(b.dataset.rs, 'restore'));
  document.querySelectorAll('[data-sup]').forEach(b => b.onclick = () => { const t = prompt('替换为哪张卡片（id）？'); if (t) act(b.dataset.sup, 'supersede', { target: t, comment: prompt('说明：') || '' }); });
};

routes.compile = async () => {
  const [plan, jobs, tree] = await Promise.all([get('compile/plan'), get('compile/jobs'), get('compile/plan?all=1')]);
  const changed = new Set(plan.paths);
  set(`<div class="cols3"><section class="panel"><h1>知识编译</h1>
    <p class="muted small">整篇文档送入 LLM（不切片、不向量化）：同时附上全库卡片索引和已由这些文档编译出的卡片全文，使模型更新而不是重复创建。产出全部进入审阅队列。</p>
    <div class="row"><button id="selchg">选择有变化的（${plan.paths.length}）</button><button id="selall">全选</button><button id="selnone">清空</button></div>
    <div style="max-height:360px;overflow:auto;border:1px solid var(--line);border-radius:6px;padding:6px 10px">${tree.paths.map(p =>
      `<label class="row" style="margin:2px 0"><input type="checkbox" class="cp" value="${esc(p)}" ${changed.has(p) ? 'checked' : ''}><span class="mono">${esc(p)}</span>${changed.has(p) ? badge('warn', '新/有变化') : ''}</label>`).join('')}</div>
    <div class="row"><label>后端</label><select id="cbackend">${['mock', 'openrouter', 'anthropic', 'command'].map(b => `<option ${b === plan.backend ? 'selected' : ''}>${b}</option>`).join('')}</select>
      <span class="small muted">默认模型 ${esc(plan.model)}（config.json）</span><label>每次调用文档数</label><input id="cfpc" type="number" min="1" value="1" style="width:60px"></div>
    <textarea id="cinst" placeholder="给编译器的附加指令（可选），例如：重点抽取模型参数与典型取值"></textarea>
    <div class="row"><button class="primary" id="cgo">开始编译</button></div></section>
    <aside class="panel"><h3 style="margin-top:0">任务</h3>${jobs.map(j => `<div style="border-bottom:1px solid var(--line);padding:6px 0"><span class="mono">${esc(j.id)}</span> ${badge(j.status)} ${j.done}/${j.total}<br>
      <span class="small muted">${esc(j.by)} · ${fmtTime(j.at)} · ${esc(j.backend)}</span><br>${j.runs.map(r => `<a class="mono small" href="#/traces/${esc(r)}">${esc(r)}</a>`).join('<br>')}</div>`).join('') || '<p class="muted">本次服务启动后无任务</p>'}</aside></div>`);
  const boxes = () => [...document.querySelectorAll('.cp')];
  $('#selchg').onclick = () => boxes().forEach(b => b.checked = changed.has(b.value));
  $('#selall').onclick = () => boxes().forEach(b => b.checked = true);
  $('#selnone').onclick = () => boxes().forEach(b => b.checked = false);
  $('#cgo').onclick = async () => {
    const paths = boxes().filter(b => b.checked).map(b => b.value);
    if (!paths.length) return toast('未选择文档');
    try {
      const j = await api('POST', 'compile', { paths, backend: $('#cbackend').value, instructions: $('#cinst').value, files_per_call: +$('#cfpc').value || 1 });
      toast('已启动 ' + j.id); poll(j.id);
    } catch (e) { toast(e.message); }
  };
  const running = jobs.find(j => j.status === 'running' || j.status === 'queued'); if (running) poll(running.id);
}
function poll(jid) {
  const t = setInterval(async () => {
    if (!location.hash.startsWith('#/compile')) return clearInterval(t);
    const jobs = await get('compile/jobs').catch(() => []);
    const j = jobs.find(x => x.id === jid);
    if (!j || j.status === 'done') { clearInterval(t); toast('编译完成'); route(); }
  }, 1500);
}

routes.users = async () => {
  const users = await get('users');
  const roles = ['reader', 'reviewer', 'admin'], RZ = { reader: '读者', reviewer: '审阅者', admin: '管理员' };
  set(`<div class="panel"><h1>用户与权限</h1><table class="grid"><tr><th>用户</th><th>显示名</th><th>角色</th><th>状态</th><th>创建</th><th></th></tr>
    ${users.map(u => `<tr><td class="mono">${esc(u.name)}</td><td>${esc(u.display)}</td><td><select data-role="${esc(u.name)}">${roles.map(r => `<option value="${r}" ${r === u.role ? 'selected' : ''}>${RZ[r]}</option>`).join('')}</select></td>
      <td>${u.active ? badge('active', '启用') : badge('withdrawn', '停用')}</td><td class="small">${fmtTime(u.created)}</td>
      <td><button data-toggle-user="${esc(u.name)}" data-active="${u.active}">${u.active ? '停用' : '启用'}</button> <button data-pw="${esc(u.name)}">重置密码</button></td></tr>`).join('')}</table>
    <h3>新增用户</h3><div class="row"><input id="nu" placeholder="用户名"><input id="nd" placeholder="显示名"><input id="np" type="password" placeholder="初始密码">
      <select id="nr">${roles.map(r => `<option value="${r}">${RZ[r]}</option>`).join('')}</select><button class="primary" id="nadd">添加</button></div></div>`);
  const upd = async (n, b) => { try { await api('PUT', 'users/' + encodeURIComponent(n), b); toast('已更新'); route(); } catch (e) { toast(e.message); route(); } };
  document.querySelectorAll('[data-role]').forEach(s => s.onchange = () => upd(s.dataset.role, { role: s.value }));
  document.querySelectorAll('[data-toggle-user]').forEach(b => b.onclick = () => upd(b.dataset.toggleUser, { active: b.dataset.active !== 'true' }));
  document.querySelectorAll('[data-pw]').forEach(b => b.onclick = () => { const p = prompt('新密码：'); if (p) upd(b.dataset.pw, { password: p }); });
  $('#nadd').onclick = async () => { try { await api('POST', 'users', { name: $('#nu').value.trim(), display: $('#nd').value.trim(), password: $('#np').value, role: $('#nr').value }); toast('已添加'); route(); } catch (e) { toast(e.message); } };
};

routes.log = async (_, q) => {
  const evs = await get('events?limit=500' + (q.target ? '&target=' + encodeURIComponent(q.target) : ''));
  set(`<div class="panel"><h1>审计日志</h1><p class="muted small">所有上传、编译、审阅、发布与用户管理动作（log/events.jsonl，只追加）。</p>
    <div class="row"><input id="lf" placeholder="过滤…" style="width:260px"></div>
    <table class="grid" id="lt"><tr><th>时间</th><th>谁</th><th>动作</th><th>对象</th><th>详情</th></tr>${evs.map(e => `<tr><td class="small">${fmtTime(e.ts)}</td><td>${esc(e.actor)}</td><td class="mono">${esc(e.action)}</td>
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
  const histHtml = `<h3 style="margin-top:0">${can('reviewer') ? '最近的问答' : '我的问答'}</h3>${hist.map(h =>
    `<div style="border-bottom:1px solid var(--line);padding:5px 0"><a href="#/ask/${esc(h.id)}" class="${h.id === rid ? 'on' : ''}">${esc((h.question || '').slice(0, 60))}</a><br>
     <span class="small muted">${esc(h.by)} · ${fmtTime(h.started)} ${h.status !== 'done' ? badge(h.status) : ''}${h.filed_as ? ' · 已回写 ' + esc(h.filed_as) : ''}</span></div>`).join('') || '<p class="muted small">暂无</p>'}`;
  let res = '';
  if (run) {
    const n = run.navigation || {}, a = run.answer || {};
    const evRender = (a.evidence || []).map(e => ({ ...e }));
    res = `<div class="row small muted">问题 · ${esc(run.by)} · ${fmtTime(run.started)} · 范围：${run.scope === 'all' ? '含未发布' : '仅已发布'} ·
        ${run.latency_s}s · ${can('reviewer') ? `<a href="#/traces/${esc(run.id)}">完整 LLM 记录</a>` : ''}</div><h2 style="margin-top:4px">${esc(run.question)}</h2>
      ${run.status !== 'done' ? `<div class="banner bad">失败：${esc(run.error || '')}</div>` : `
      <details open><summary><b>① 阅读计划</b> <span class="small muted">模型先看知识树与文档目录树，决定读什么（不使用向量检索）</span></summary>
        <div class="banner info">${esc(n.reasoning || '')}</div>
        <div class="small"><b>读取卡片（${(n.cards || []).length}）：</b>${(n.cards || []).map(c => `<a href="${cardHref(c)}">${esc(c)}</a>`).join(' · ') || '—'}</div>
        <div class="small"><b>读取原文章节（${(n.sections || []).length}）：</b><ul>${(n.sections || []).map(s => `<li><a href="${srcHref(s.path, 'L=' + s.lines)}">${esc(s.path)} › ${esc(s.title)}</a> <span class="muted">L${esc(s.lines)}</span> ${s.why ? '<span class="muted">— ' + esc(s.why) + '</span>' : ''}</li>`).join('') || '<li class="muted">无</li>'}</ul></div>
      </details>
      <h3>② 回答 ${gbadge(run.grounding)} ${a.confidence != null ? `<span class="small muted">置信度 ${a.confidence}</span>` : ''}</h3>
      <div class="doc">${renderCardBody({ body: a.answer_md }, known)}</div>
      ${a.gaps ? `<div class="banner warn">资料缺口：${esc(a.gaps)}</div>` : ''}
      <h3>③ 引用核验</h3>${evidenceList({ evidence: evRender }, true)}
      ${can('reviewer') ? (run.filed_as ? `<div class="banner info">已回写为知识卡片 <a href="#/review/${esc(run.filed_as)}">${esc(run.filed_as)}</a>（进入审阅流程）</div>` :
        `<h3>④ 回写为知识</h3><p class="small muted">好的问答会成为一张「问答综合」卡片进入审阅；发布后成为知识库的一部分——知识因使用而增长。</p>
        <div class="row"><input id="fb_title" placeholder="卡片标题（默认用问题）" style="flex:1"><input id="fb_parent" placeholder="上级主题 id（可选）" list="cardids2"><datalist id="cardids2">${all.filter(c => c.type === 'topic').map(c => `<option value="${esc(c.id)}">${esc(c.title)}</option>`).join('')}</datalist>
        <button class="primary" id="fb_go">提交为知识卡片</button></div>`) : ''}`}`;
  }
  set(`<div class="cols3"><section class="panel"><h1>问答</h1>
      <p class="muted small">基于知识库作答：先按知识树与文档目录推理出阅读计划，再精读选中的卡片与原文章节，回答中的每条原文引用都会被自动核验。</p>
      <textarea id="qq" placeholder="例如：Hopkins 模型在 EUV 条件下有什么局限？ILT 与 OPC 的主要区别是什么？" style="min-height:70px"></textarea>
      ${await condBar()}
      <div class="row"><button class="primary" id="qgo">提问</button>${can('reviewer') ? '<label class="small"><input type="checkbox" id="qall"> 包含未发布（审阅中）卡片</label>' : ''}<span id="qwait" class="small muted"></span></div>
      ${res}</section><aside class="panel">${histHtml}</aside></div>`);
  bindEvidence($('#main')); fillSourceLines($('#main')); bindCond();
  $('#qgo').onclick = async () => {
    const question = $('#qq').value.trim(); if (!question) return;
    document.querySelectorAll('[data-cond]').forEach(i => { S.cond[i.dataset.cond] = i.value.trim(); });
    try { localStorage.setItem('lkb_cond', JSON.stringify(S.cond)); } catch (e) {}
    $('#qgo').disabled = true; $('#qwait').textContent = '模型正在阅读与作答…';
    try { const r = await api('POST', 'ask', { question, include_unpublished: !!($('#qall') && $('#qall').checked), cond: condQS() }); location.hash = '#/ask/' + r.id; }
    catch (e) { toast(e.message); $('#qgo').disabled = false; $('#qwait').textContent = ''; }
  };
  const fb = $('#fb_go'); if (fb) fb.onclick = async () => {
    try { const h = await api('POST', `queries/${encodeURIComponent(run.id)}/file`, { title: $('#fb_title').value.trim(), parent: $('#fb_parent').value.trim() });
      toast('已提交为 ' + h.id); location.hash = '#/review/' + encodeURIComponent(h.id); } catch (e) { toast(e.message); }
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
  set(`<div class="cols3"><section class="panel"><h1>编译规范 SCHEMA.md <span class="small muted">v${v}${v !== sc.version ? '（历史版本）' : '（当前）'}</span></h1>
      <p class="small muted">知识编译器每次编译都会完整阅读此规范：领域本体、主题骨架、卡片类型用法、命名写作规范、关系含义、不编译什么。
      修改它即可改变知识的编译方式，无需改代码；每次编译记录都会注明所用版本，便于比较不同版本的编译效果。固定的「证据 / 认识论标签 / 输出格式」协议在代码中，不可在此修改。</p>
      <div class="tabs"><a href="#/schema?v=${v}" class="${!q.diff ? 'on' : ''}">${editable ? '编辑' : '查看'}</a><a href="#/schema?v=${v}&diff=1" class="${q.diff ? 'on' : ''}">与上一版差异</a></div>
      ${q.diff ? `<div class="diff">${df.split('\n').map(l => `<div class="${l.startsWith('+') ? 'a' : l.startsWith('-') ? 'd' : l.startsWith('@') ? 'h' : ''}">${esc(l) || ' '}</div>`).join('')}</div>` :
        editable ? `<textarea id="sc_text" class="code" style="min-height:60vh">${esc(text)}</textarea>
          <div class="row"><input id="sc_note" placeholder="修改说明（必填）" style="flex:1"><button class="primary" id="sc_save">保存为新版本</button></div>`
        : `<div class="doc">${MD.render(text)}</div>`}</section>
    <aside class="panel"><h3 style="margin-top:0">版本历史</h3><table class="grid">${sc.history.slice().reverse().map(h =>
      `<tr><td><a href="#/schema?v=${h.version}">v${h.version}</a></td><td class="small">${esc(h.by)}<br>${fmtTime(h.at)}</td><td class="small">${esc(h.note || '')}</td></tr>`).join('')}</table>
      <p class="small muted">在「LLM 观测」中可按规范版本对比引用可核验率。</p></aside></div>`);
  const sv = $('#sc_save'); if (sv) sv.onclick = async () => {
    const note = $('#sc_note').value.trim(); if (!note) return toast('请填写修改说明');
    try { const e = await api('PUT', 'schema', { text: $('#sc_text').value, note }); toast('已保存为 v' + e.version); location.hash = '#/schema?v=' + e.version; route(); }
    catch (e) { toast(e.message); }
  };
};

// ---------------------------------------------------------------- applicability filter (shared by all views)
const DIM_ZH = { node: '工艺节点', wavelength: '波长', na: 'NA', layer: '图层', mask: '掩模', application: '应用' };
S.cond = (() => { try { return JSON.parse(localStorage.getItem('lkb_cond') || '{}'); } catch (e) { return {}; } })();
const condQS = () => Object.entries(S.cond).filter(([, v]) => v).map(([k, v]) => `${k}:${v}`).join(',');
const withCond = path => { const c = condQS(); return c ? path + (path.includes('?') ? '&' : '?') + 'cond=' + encodeURIComponent(c) : path; };
async function condBar() {
  if (!S.dims) S.dims = await get('dims').catch(() => ({}));
  const dims = Object.keys(S.dims);
  if (!dims.length) return '';
  return `<div class="row small condbar"><b>适用条件</b>${dims.map(d => `<label>${esc((S.dims[d] || [DIM_ZH[d] || d])[0])}
      <input data-cond="${esc(d)}" value="${esc(S.cond[d] || '')}" placeholder="如：${esc(((S.dims[d] || [])[1] || '').split('、')[0].replace(/^如\s*/, ''))}" style="width:120px"></label>`).join('')}
    <button id="condgo">筛选</button>${condQS() ? '<button id="condclr">清除</button>' : ''}
    <span class="muted">未标注条件的知识视为通用，始终显示（标“通用”）。</span></div>`;
}
function bindCond() {
  const go = () => { document.querySelectorAll('[data-cond]').forEach(i => { S.cond[i.dataset.cond] = i.value.trim(); });
    try { localStorage.setItem('lkb_cond', JSON.stringify(S.cond)); } catch (e) {} route(); };
  if ($('#condgo')) $('#condgo').onclick = go;
  document.querySelectorAll('[data-cond]').forEach(i => i.onkeydown = e => { if (e.key === 'Enter') go(); });
  if ($('#condclr')) $('#condclr').onclick = () => { S.cond = {}; try { localStorage.removeItem('lkb_cond'); } catch (e) {} route(); };
}
const condChips = (conds, evLink) => (conds || []).map(c => `<span class="badge b-comment" title="依据 ${esc(c.evidence || '')}">${esc((S.dims && S.dims[c.dim] ? S.dims[c.dim][0] : DIM_ZH[c.dim]) || c.dim)}：${esc(c.value)}${evLink && c.evidence ? ' · ' + esc(c.evidence) : ''}</span>`).join(' ');
const appliesBadge = a => a === 'general' ? '<span class="badge" title="原文未说明适用条件">通用</span>' : a === 'yes' ? '<span class="badge b-exact">符合条件</span>' : '';

// view switcher shared by the knowledge views
const VIEWS = [['#/wiki', 'Wiki'], ['#/k', '卡片'], ['#/tree', '索引树'], ['#/graph', '图谱'], ['#/mindmap', '思维导图'], ['#/timeline', '时间线'], ['#/facts', '对比表'], ['#/src', '文档目录']];
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
  if (!center) { set(`<div class="panel">${viewTabs('#/mindmap')}${bar}<p class="muted">暂无可显示的知识。</p></div>`); return bindCond(); }
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
  const wrap = (t, n) => { const s = String(t).replace(/\s*[（(][^)）]*[)）]\s*$/, ''); const out = []; for (let i = 0; i < s.length && out.length < 3; i += n) out.push(s.slice(i, i + n)); return out; };
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
    <div class="row small"><b>中心：</b><a href="${cardHref(center.id)}">${esc(center.title)}</a>${parent ? ` · 上一级 <a href="#/mindmap/${encodeURIComponent(parent.id)}">${esc(parent.title)}</a>` : ''}
      <span class="muted">· 实线：下级概念（带 +N 的可继续展开）· 橙色虚线：相关概念</span>
      <select id="mmtopic" style="margin-left:auto"><option value="">切换主题…</option>${cards.filter(c => kids(c.id).length).map(c => `<option value="${esc(c.id)}" ${c.id === center.id ? 'selected' : ''}>${esc(c.title)}（${kids(c.id).length}）</option>`).join('')}</select></div>
    <svg viewBox="0 0 ${W} ${H}" style="width:100%;height:auto;max-height:76vh">${svg}</svg>
    ${ring1.length || relIds.length ? '' : '<p class="muted">该节点没有下级或相关概念。</p>'}</div>`);
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
      <div class="small muted">${badge('t', TYPE_ZH[r.card_type] || r.card_type)}<a href="${cardHref(r.card)}">${esc(r.card_title)}</a> · ${r.path ? docLink(r.path, 'L=' + encodeURIComponent(r.lines), '· 第 ' + esc(r.lines) + ' 行') : ''} ${r.check ? badge(r.check) : ''}</div></div></div>`;
  set(`<div class="panel">${viewTabs('#/timeline')}${bar}
    <p class="small muted">时间线由卡片中带日期的事件生成（每个事件都引用了已核验的原文证据）。${can('reviewer') ? ` <a href="#/timeline${q.all ? '' : '?all=1'}">${q.all ? '只看已发布' : '包含未发布'}</a>` : ''}</p>
    ${dated.length ? `<h3>按年份</h3><div class="timeline-v">${Object.keys(groups).sort((a, b) => a - b).map(y => `<div class="tl-year"><span>${y}</span></div>${groups[y].map(item).join('')}`).join('')}</div>` : (eras.length ? '' : '<p class="muted">暂无带日期的事件。</p>')}
    ${eras.length ? `<h3>按工艺节点演进 <span class="small muted">（节点由大到小 ≈ 由早到晚）</span></h3><div class="timeline-v">${eras.map(r => `<div class="tl-year"><span>${nodeOf(r.when)}nm</span></div>${item(r)}`).join('')}</div>` : ''}
    ${undated.length ? `<h3>其他时期</h3>${undated.map(item).join('')}` : ''}</div>`);
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
  const condTxt = r => Object.entries(r.conditions || {}).map(([k, v]) => `${(S.dims[k] || [DIM_ZH[k] || k])[0]}：${v}`).concat((r.card_conditions || []).map(c => `${(S.dims[c.dim] || [DIM_ZH[c.dim] || c.dim])[0]}：${c.value}`));
  set(`<div class="panel">${viewTabs('#/facts')}${bar}
    <div class="row small"><input id="ff" placeholder="筛选参数 / 指标 / 卡片…" value="${esc(q.f || '')}" style="width:260px">
      <span class="muted">${rows.length} 条事实 · ${Object.keys(groups).length} 个参数/指标 · 同名参数并排比较；每个取值都链接到原文。</span>
      ${can('reviewer') ? `<a href="#/facts${q.all ? '' : '?all=1'}">${q.all ? '只看已发布' : '包含未发布'}</a>` : ''}</div>
    <table class="grid"><tr><th>参数 / 指标</th><th>取值</th><th>适用条件</th><th>所属卡片</th><th>出处</th></tr>
    ${Object.entries(groups).map(([name, rs]) => rs.map((r, i) => `<tr>${i === 0 ? `<td rowspan="${rs.length}"><b>${esc(name)}</b>${rs.length > 1 ? `<br><span class="small muted">${rs.length} 处</span>` : ''}</td>` : ''}
      <td><b>${esc(r.value)}</b> ${esc(r.unit || '')}</td><td class="small">${condTxt(r).map(esc).join('<br>') || '<span class="muted">通用</span>'}</td>
      <td class="small"><a href="${cardHref(r.card)}">${esc(r.card_title)}</a></td>
      <td class="small">${r.path ? docLink(r.path, 'L=' + encodeURIComponent(r.lines), '· 第 ' + esc(r.lines) + ' 行') : ''} ${r.check ? badge(r.check) : ''}<div class="muted" title="${esc(r.quote)}">${esc((r.quote || '').slice(0, 60))}…</div></td></tr>`).join('')).join('') || '<tr><td colspan="5" class="muted">暂无结构化事实。</td></tr>'}</table></div>`);
  bindCond();
  $('#ff').onkeydown = e => { if (e.key === 'Enter') location.hash = '#/facts?f=' + encodeURIComponent(e.target.value) + (q.all ? '&all=1' : ''); };
};

// ---------------------------------------------------------------- issue register
const ISSUE_ZH = { contradiction: '矛盾', open_question: '开放问题', gap: '知识缺口', report: '读者报告' };
const ISSUE_CLS = { contradiction: 'reject', open_question: 'request_changes', gap: 'comment', report: 'warn' };
routes.issues = async ([iid], q) => {
  if (iid) return issueView(iid);
  const d = await get('issues' + (q.status !== 'all' ? '?status=' + (q.status || 'open') : '') + (q.kind ? (q.status === 'all' ? '?' : '&') + 'kind=' + q.kind : ''));
  const st = d.stats || {};
  set(`<div class="panel"><h1>${can('reviewer') ? '问题登记簿' : '我的报告'}</h1>
    <p class="small muted">矛盾、开放问题、知识缺口与读者报告。知识库不粉饰矛盾：未解决的矛盾与开放问题会显示在相关卡片上，所有读者可见；缺口告诉管理员下一步该补哪些资料。</p>
    ${can('reviewer') ? `<div class="row small">${['', 'contradiction', 'open_question', 'gap', 'report'].map(k => `<a class="badge ${(q.kind || '') === k ? 'b-in_review' : ''}" href="#/issues?kind=${k}&status=${q.status || 'open'}">${k ? ISSUE_ZH[k] + ' ' + ((st.by_kind || {})[k] || 0) : '全部未解决 ' + (st.open || 0)}</a>`).join(' ')}
      · 状态：${['open', 'resolved', 'wontfix', 'all'].map(s => `<a href="#/issues?status=${s}${q.kind ? '&kind=' + q.kind : ''}" class="badge ${(q.status || 'open') === s ? 'b-in_review' : ''}">${{ open: '未解决', resolved: '已解决', wontfix: '不处理', all: '全部' }[s]}</a>`).join(' ')}</div>` : ''}
    <table class="grid"><tr><th>类型</th><th>问题</th><th>相关卡片</th><th>来源</th><th>状态</th><th>更新</th></tr>
    ${d.items.map(i => `<tr><td>${badge(ISSUE_CLS[i.kind], ISSUE_ZH[i.kind])}${i.seen > 1 ? `<br><span class="small muted">出现 ${i.seen} 次</span>` : ''}</td>
      <td><a href="#/issues/${esc(i.id)}"><b>${esc(i.title)}</b></a><div class="small muted">${esc((i.detail || '').slice(0, 120))}</div></td>
      <td class="small">${i.cards.map(c => `<a href="#/review/${encodeURIComponent(c)}">${esc(c)}</a>`).join('<br>')}</td>
      <td class="small">${esc((i.origin || {}).kind || '')}${(i.origin || {}).run ? `<br><a href="#/${i.origin.kind === 'query' ? 'ask' : 'traces'}/${esc(i.origin.run)}">记录</a>` : ''}</td>
      <td>${badge(i.status === 'open' ? 'in_review' : i.status === 'resolved' ? 'published' : 'rejected', { open: '未解决', resolved: '已解决', wontfix: '不处理' }[i.status])}</td><td class="small">${fmtTime(i.updated)}</td></tr>`).join('') || '<tr><td colspan="6" class="muted">无</td></tr>'}</table></div>`);
};
async function issueView(iid) {
  const i = await get('issues/' + encodeURIComponent(iid));
  set(`<div class="row"><a href="#/issues">← 问题登记簿</a></div><div class="panel"><div class="row">${badge(ISSUE_CLS[i.kind], ISSUE_ZH[i.kind])}
      ${badge(i.status === 'open' ? 'in_review' : 'published', { open: '未解决', resolved: '已解决', wontfix: '不处理' }[i.status])}<span class="small muted">由 ${esc(i.by)} 于 ${fmtTime(i.created)} 提出 · 出现 ${i.seen || 1} 次</span></div>
    <h1>${esc(i.title)}</h1><p>${esc(i.detail || '')}</p>
    ${i.cards.length ? `<p class="small">相关卡片：${i.cards.map(c => `<a href="${cardHref(c)}">${esc(c)}</a>`).join('，')}</p>` : ''}
    ${(i.evidence || []).length ? `<h3>原文依据</h3>${evidenceList({ evidence: i.evidence }, false)}` : ''}
    ${i.resolution ? `<div class="banner info">处理结论：${esc(i.resolution)}</div>` : ''}
    <h3>处理记录</h3><table class="grid">${i.history.map(h => `<tr><td class="small">${fmtTime(h.ts)}</td><td>${esc(h.user)}</td><td>${esc({ open: '提出', seen_again: '再次出现', comment: '评论', resolve: '解决', wontfix: '不处理', reopen: '重新打开' }[h.action] || h.action)}</td><td class="small">${esc(h.comment || '')}</td></tr>`).join('')}</table>
    ${S.me ? `<textarea id="ic" placeholder="评论 / 处理说明（解决或不处理时必填）"></textarea><div class="row"><button data-ia="comment">评论</button>
      ${can('reviewer') ? (i.status === 'open' ? '<button class="ok" data-ia="resolve">标记已解决</button><button data-ia="wontfix">不处理</button>' : '<button data-ia="reopen">重新打开</button>') : ''}</div>` : ''}</div>`);
  document.querySelectorAll('[data-ia]').forEach(b => b.onclick = async () => {
    try { await api('POST', `issues/${encodeURIComponent(iid)}/action`, { action: b.dataset.ia, comment: $('#ic').value.trim() }); toast('已记录'); route(); }
    catch (e) { toast(e.message); }
  });
}
function facetsBlock(card) {
  const ev = Object.fromEntries((card.evidence || []).map(e => [e.id, e]));
  const reviewer = can('reviewer');
  const keep = items => (items || []).filter(x => x.supported !== false || reviewer);  // readers only see supported facets
  card = { ...card, conditions: keep(card.conditions), facts: keep(card.facts), events: keep(card.events) };
  const ref = (id, x) => (ev[id] ? `<a class="ev" data-ev="${esc(id)}" href="javascript:void 0">${esc(id)}</a>` : '') +
    (x && x.supported === false ? ' <span class="badge b-missing" title="所引原文没有明确说明该值">原文不支持</span>' : '');
  let h = '';
  if ((card.conditions || []).length) h += `<h3>适用条件</h3><p>${(card.conditions).map(c => `${condChips([c])} ${ref(c.evidence, c)}`).join(' &nbsp; ')}</p>`;
  else h += `<p class="small muted">适用条件：原文未说明（视为通用）。</p>`;
  if ((card.facts || []).length) h += `<h3>关键参数与指标</h3><table class="grid"><tr><th>名称</th><th>取值</th><th>条件</th><th>依据</th></tr>${card.facts.map(f => `<tr><td>${esc(f.name)}</td><td><b>${esc(f.value)}</b> ${esc(f.unit || '')}</td><td class="small">${Object.entries(f.conditions || {}).map(([k, v]) => esc(((S.dims || {})[k] || [DIM_ZH[k] || k])[0] + '：' + v)).join('，') || '—'}</td><td>${ref(f.evidence, f)}</td></tr>`).join('')}</table>`;
  if ((card.events || []).length) h += `<h3>时间节点</h3><ul>${card.events.map(e => `<li><b>${esc(e.when)}</b> ${esc(e.what)} ${ref(e.evidence, e)}</li>`).join('')}</ul>`;
  return h;
}
function issuesBlock(issues, cid) {
  const list = (issues || []);
  return `${list.length ? `<div class="banner warn"><b>已知分歧与待解问题（${list.length}）</b><ul class="small" style="margin:4px 0">${list.map(i => `<li>${badge(ISSUE_CLS[i.kind], ISSUE_ZH[i.kind])} ${can('reviewer') || i.kind === 'contradiction' || i.kind === 'open_question' ? `<a href="#/issues/${esc(i.id)}">${esc(i.title)}</a>` : esc(i.title)}</li>`).join('')}</ul></div>` : ''}
    ${S.me ? `<details style="margin-top:12px"><summary class="small">发现错误或表述不清？报告问题</summary><input id="rp_t" placeholder="问题标题（如：E3 引用的数值与原文不一致）" style="width:100%;margin:6px 0">
      <textarea id="rp_d" placeholder="详细说明（可选）"></textarea><div class="row"><button id="rp_go" data-card="${esc(cid)}">提交报告</button></div></details>` : ''}`;
}
function bindReport() {
  const b = $('#rp_go'); if (!b) return;
  b.onclick = async () => { const title = $('#rp_t').value.trim(); if (title.length < 4) return toast('请填写问题标题');
    try { await api('POST', 'issues', { kind: 'report', card: b.dataset.card, title, detail: $('#rp_d').value.trim() }); toast('已提交，审阅者会处理'); route(); } catch (e) { toast(e.message); } };
}

// ---------------------------------------------------------------- wiki: every page a navigation hub
const wikiHref = id => '#/wiki/' + encodeURIComponent(id);
const entHref = id => '#/entity/' + encodeURIComponent(String(id).replace(/^e:/, ''));
const REL_ZH = { is_a:'是一种', part_of:'属于', uses:'使用', depends_on:'依赖', implements:'实现', improves:'改进', alternative_to:'可替代',
  contrasts_with:'对比', causes:'导致', mitigates:'缓解', measured_by:'由…度量', parameter_of:'是…的参数', input_to:'输入到', output_of:'产出自',
  example_of:'是…的例子', contradicts:'矛盾', covers:'涵盖', related_to:'相关' };
const ENT_ZH = { tool:'软件/工具', equipment:'设备', organization:'机构', material:'材料', standard:'格式/标准', person:'人物', product:'产品' };
function wikiSide(cards, cur) {
  return `<aside class="panel side"><h3 style="margin-top:0"><a href="#/wiki">Wiki 首页</a></h3>${topicTree(cards, cur).replace(/#\/k\//g, '#/wiki/')}</aside>`;
}
routes.wiki = async ([id], q) => {
  const view = q.view === 'head' && can('reviewer') ? '?view=head' : '';
  const cards = await get('cards');
  S.cardTitles = Object.fromEntries(cards.map(c => [c.id, c.title]));
  const side = wikiSide(cards.filter(c => can('reviewer') ? c.published_rev : true), id);
  if (!id) {
    const h = await get('wiki' + view);
    set(`<div class="panel" style="margin-bottom:10px">${viewTabs('#/wiki')}</div><div class="cols">${side}<section class="panel">
      <h1 style="margin-top:0">知识库 Wiki</h1>
      <p class="muted small">${h.pages} 个页面 · 图谱 ${Object.values(h.graph.nodes).reduce((a, b) => a + b, 0)} 个节点 / ${Object.values(h.graph.edges).reduce((a, b) => a + b, 0)} 条边
        （已审阅关系 ${h.graph.edges.reviewed || 0} · 概念提及 ${h.graph.edges.linked || 0} · 实体 ${h.graph.edges.indexed || 0}）</p>
      <h3>主题</h3><div class="grid2">${h.topics.map(t => `<a class="item tile" href="${wikiHref(t.id)}"><b>${esc(t.title)}</b>
        <span class="muted small">${t.children} 个下级页面 ${t.has_overview ? '' : '· <i>尚无综述</i>'}</span><br><span class="small">${esc(t.summary || '')}</span></a>`).join('')}</div>
      <h3>核心概念 <span class="muted small">（按图谱中心度）</span></h3><p>${h.central.map(c => `<a class="chip" href="${wikiHref(c.id)}">${esc(c.title)}</a>`).join(' ')}</p>
      ${h.entities.length ? `<h3>实体 <span class="muted small">（工具、设备、机构…，由索引自动识别并逐字核验）</span></h3><p>${h.entities.map(e =>
        `<a class="chip" href="${entHref(e.id)}">${esc(e.title)} <span class="muted">${esc(ENT_ZH[e.type] || '')}</span></a>`).join(' ')}</p>` : ''}
      <h3>最近更新</h3><div class="cardlist">${h.recent.map(c => `<a class="item" href="${wikiHref(c.id)}"><b>${esc(c.title)}</b> <span class="muted small">${esc(TYPE_ZH[c.type] || c.type)} · ${fmtTime(c.at)}</span></a>`).join('')}</div>
      ${can('reviewer') && h.hub_gaps.length ? `<h3>Wiki 结构缺口</h3><ul class="small">${h.hub_gaps.map(g => g.kind === 'topic_without_overview'
        ? `<li>主题 <a href="${wikiHref(g.id)}">${esc(g.title)}</a> 有 ${g.children} 个下级页面，但没有综述</li>`
        : `<li>图谱中紧密相连的一组卡片分属不同主题（${g.parents.map(esc).join('、')}）：${g.titles.map(esc).join('、')} — 可能需要一个共同主题</li>`).join('')}</ul>` : ''}
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
    return Object.entries(g).map(([rel, xs]) => `<li><b>${dirIn ? '被' : ''}${esc(REL_ZH[rel] || rel)}</b>：${xs.map(r =>
      `<a href="${wikiHref(r.id)}">${esc(r.title)}</a>${r.basis && r.basis !== 'extracted' ? ' <span class="muted small">(' + zh(r.basis) + ')</span>' : ''}`).join('、')}</li>`).join('');
  };
  set(`<div class="panel" style="margin-bottom:10px">${viewTabs('#/wiki')}</div><div class="cols">${side}<section class="panel doc">
    <div class="small muted crumbs"><a href="#/wiki">Wiki</a>${p.breadcrumbs.map(b => ` › <a href="${wikiHref(b.id)}">${esc(b.title)}</a>`).join('')}</div>
    <h1 style="margin:6px 0">${esc(p.title)}</h1>
    <p class="small">${badge('comment', TYPE_ZH[p.type] || p.type)} ${p.aliases.length ? '<span class="muted">又称 ' + p.aliases.map(esc).join('、') + '</span>' : ''}
      ${condChips(p.conditions)} · <a href="${cardHref(p.id)}">证据与审阅记录 →</a></p>
    <p><i>${esc(p.summary)}</i></p>
    ${body}
    ${p.type === 'topic' && can('reviewer') ? `<p><button id="hubgo">${(p.body || '').trim().length > 40 ? '重新生成' : '生成'}主题综述（LLM，进入审阅）</button></p>` : ''}
    ${p.children.length ? `<h2>下级页面</h2><div class="cardlist">${p.children.map(c => `<a class="item" href="${wikiHref(c.id)}"><b>${esc(c.title)}</b>
      <span class="muted small">${esc(TYPE_ZH[c.type] || c.type)}</span> ${c.conditions.map(x => `<span class="badge b-comment">${esc(x)}</span>`).join(' ')}<br><span class="small muted">${esc(c.summary)}</span></a>`).join('')}</div>` : ''}
    ${p.relations_out.length || p.relations_in.length ? `<h2>关系 <span class="muted small">（经审阅）</span></h2><ul>${relGroup(p.relations_out)}${relGroup(p.relations_in, true)}</ul>` : ''}
    ${p.mentioned_by.length || p.mentions.length ? `<h2>相互提及 <span class="muted small">（按名称自动链接）</span></h2>
      ${p.mentioned_by.length ? `<p class="small"><b>提到本页的：</b>${p.mentioned_by.map(m => `<a href="${wikiHref(m.id)}">${esc(m.title)}</a>`).join('、')}</p>` : ''}
      ${p.mentions.length ? `<p class="small"><b>本页提到的：</b>${p.mentions.map(m => `<a href="${wikiHref(m.id)}">${esc(m.title)}</a>`).join('、')}</p>` : ''}` : ''}
    ${p.sections.length ? `<h2>原文中讨论此概念的章节</h2><ul class="small">${p.sections.map(s => `<li>${docLink(s.path, 'L=' + s.start, '· ' + esc(s.title))}
      <span class="muted">L${s.start}-${s.end}${s.count > 1 ? ' · 提及 ' + s.count + ' 次' : ''}</span></li>`).join('')}</ul>` : ''}
    ${p.entities.length ? `<h2>涉及的实体</h2><p>${p.entities.map(e => `<a class="chip" href="${entHref(e.id)}">${esc(e.title)} <span class="muted">${esc(ENT_ZH[e.type] || '')}</span></a>`).join(' ')}</p>` : ''}
    ${p.backlinks.length ? `<h2>链接到本页</h2><p class="small">${p.backlinks.map(b => `<a href="${wikiHref(b.id)}">${esc(b.title)}</a>`).join('、')}</p>` : ''}
    ${p.red_links.length ? `<p class="small muted">尚不存在的页面：${p.red_links.map(esc).join('、')}</p>` : ''}
  </section></div>`);
  bindTree($('#main'));
  if ($('#hubgo')) $('#hubgo').onclick = async () => {
    $('#hubgo').disabled = true; $('#hubgo').textContent = '生成中…';
    try { const r = await api('POST', 'wiki/' + encodeURIComponent(id) + '/hub');
      toast('已生成综述（r' + ((r.written[0] || {}).rev || '?') + '），已进入审阅' + (r.findings.length ? '；注意：' + r.findings.join('；') : ''));
      location.hash = '#/review/' + encodeURIComponent(id);
    } catch (e) { toast('失败：' + e.message); $('#hubgo').disabled = false; }
  };
};

routes.entity = async ([id]) => {
  const e = await get('entities/' + encodeURIComponent(id));
  set(`<div class="panel" style="margin-bottom:10px">${viewTabs('#/wiki')}</div><div class="panel doc">
    <div class="small muted"><a href="#/wiki">Wiki</a> › 实体</div>
    <h1 style="margin:6px 0">${esc(e.title)}</h1>
    <p class="small">${badge('comment', e.type_label || ENT_ZH[e.type] || '未分类')} ${(e.aliases || []).length ? '<span class="muted">又称 ' + e.aliases.map(esc).join('、') + '</span>' : ''}</p>
    <p class="small muted">实体由文档索引（PageIndex）识别，名称已在原文中逐字核验；它不是经审阅的知识卡片，而是帮助你找到相关知识的导航入口。</p>
    ${e.cards.length ? `<h2>提到它的知识卡片</h2><div class="cardlist">${e.cards.map(c => `<a class="item" href="${wikiHref(c.id)}"><b>${esc(c.title)}</b> <span class="muted small">${esc(TYPE_ZH[c.type] || c.type)}${c.count > 1 ? ' · ' + c.count + ' 次' : ''}</span></a>`).join('')}</div>` : ''}
    <h2>原文出处</h2><ul class="small">${e.sections.map(s => `<li>${docLink(s.path, 'L=' + s.start, '· ' + esc(s.title))} <span class="muted">L${s.start}-${s.end}</span></li>`).join('') ||
      (e.docs || []).map(d => `<li>${docLink(d)}</li>`).join('')}</ul></div>`);
};

// ---------------------------------------------------------------- PageIndex: the unified tree, browsable
routes.tree = async (_, q) => {
  const d = await get('pageindex' + (q.view === 'head' && can('reviewer') ? '?view=head' : ''));
  const st = can('reviewer') ? await get('pageindex/status').catch(() => null) : null;
  const N = d.nodes;
  const tag = n => ({ card: TYPE_ZH[n.type] || '卡片', doc: '文档', section: '§', folder: '文件夹', root: '' })[n.kind];
  const href = n => n.kind === 'card' ? wikiHref(n.id) : n.kind === 'doc' ? srcHref(n.path) : n.kind === 'section' ? srcHref(n.path, 'L=' + n.start) : '';
  const li = id => { const n = N[id]; const kids = n.children || [];
    return `<li class="${kids.length ? 'closed' : ''}" data-id="${esc(id)}">${kids.length ? '<span class="tw" data-open>▸</span>' : '<span class="tw"> </span>'}
      ${href(n) ? `<a href="${href(n)}">${esc(n.title)}</a>` : `<b>${esc(n.title)}</b>`} <span class="muted small">${esc(tag(n))}${n.kind === 'section' ? ' L' + n.start + '-' + n.end : ''}${kids.length ? ' · ' + kids.length : ''}</span>
      ${n.summary ? `<div class="small muted gist">${esc(n.summary)}</div>` : ''}<ul></ul></li>`; };
  set(`<div class="panel" style="margin-bottom:10px">${viewTabs('#/tree')}</div><div class="panel">
    <h1 style="margin-top:0">索引树（PageIndex）</h1>
    <p class="small muted">问答时，模型像查手册目录一样在这棵树上逐层展开、推理选择要读的卡片与原文章节——不做向量检索，也不切块。
      ${st ? `节点摘要：${st.compiled}/${st.documents} 篇文档已由 LLM 编写摘要${st.pending.length ? '（其余使用标题 + 首句）' : ''}。` : ''}</p>
    <div class="row"><input id="tq" placeholder="在原文章节中检索（BM25，无需空格）…" style="width:360px"><button id="tgo">检索</button></div><div id="thits"></div>
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
    $('#thits').innerHTML = `<div class="cardlist">${r.sections.map(s => `<a class="item" href="${srcHref(s.path, 'L=' + s.start)}"><b>《${esc(docTitle(s.path))}》· ${esc(s.title)}</b>
      <span class="muted small">L${s.start}-${s.end} · ${s.score}</span><br><span class="small muted">${esc(s.summary)}</span></a>`).join('') || '<p class="muted">无结果</p>'}</div>`;
  };
  $('#tgo').onclick = search; $('#tq').onkeydown = e => { if (e.key === 'Enter') search(); };
};

// graph: explain how two pieces of knowledge are connected
async function pathFinder(nodes) {
  const opts = nodes.map(n => `<option value="${esc(n.title)}">`).join('');
  return `<details class="small" style="margin:6px 0"><summary><b>关系路径</b>：两条知识之间是怎么联系起来的？</summary>
    <div class="row"><input id="pa" list="pnodes" placeholder="起点（卡片标题）" style="width:240px"> → <input id="pb" list="pnodes" placeholder="终点" style="width:240px">
    <button id="pgo">查找</button></div><datalist id="pnodes">${opts}</datalist><div id="pout"></div></details>`;
}
function bindPathFinder(nodes) {
  if (!$('#pgo')) return;
  const byTitle = t => (nodes.find(n => n.title === t) || nodes.find(n => n.id === t) || {}).id;
  $('#pgo').onclick = async () => {
    const a = byTitle($('#pa').value), b = byTitle($('#pb').value);
    if (!a || !b) { $('#pout').innerHTML = '<p class="muted">请从下拉列表中选择卡片</p>'; return; }
    const r = await get(`kg/path?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`);
    $('#pout').innerHTML = r.steps ? `<ol>${r.steps.map(s => `<li><a href="${wikiHref(s.from)}">${esc(s.from_title)}</a>
      <b>${s.dir === 'out' ? '—' + esc(REL_ZH[s.rel] || s.rel) + '→' : '←' + esc(REL_ZH[s.rel] || s.rel) + '—'}</b>
      <a href="${s.to.startsWith('e:') ? entHref(s.to) : s.to.startsWith('s:') || s.to.startsWith('d:') ? '#' : wikiHref(s.to)}">${esc(s.to_title)}</a>
      <span class="muted">${{ reviewed: '经审阅', linked: '名称提及', indexed: '实体', provenance: '出处' }[s.layer] || s.layer}${s.basis && s.layer === 'reviewed' ? ' · ' + zh(s.basis) : ''}</span></li>`).join('')}</ol>`
      : '<p class="muted">两者之间没有路径</p>';
  };
}

routes.login = async () => {
  set(`<div class="panel" style="max-width:380px;margin:40px auto"><h1>登录</h1><form id="lf"><div class="row"><input id="ln" placeholder="用户名" style="width:100%" autocomplete="username"></div>
    <div class="row"><input id="lp" type="password" placeholder="密码" style="width:100%" autocomplete="current-password"></div><div class="row"><button class="primary">登录</button></div></form></div>`);
  $('#lf').onsubmit = async e => {
    e.preventDefault();
    try { const d = await api('POST', 'login', { name: $('#ln').value.trim(), password: $('#lp').value }); S.token = d.token; localStorage.setItem('lkb_token', d.token); S.me = d.user; location.hash = '#/'; }
    catch (err) { toast(err.message); }
  };
};
routes['404'] = async () => set('<div class="panel"><h1>页面不存在</h1></div>');

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
