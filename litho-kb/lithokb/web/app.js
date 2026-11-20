/* LithoKB single-page UI. No framework, no build step. */
(function () {
'use strict';
const $ = s => document.querySelector(s);
const esc = MD.esc;
const S = { me: null, token: localStorage.getItem('lkb_token') || '', site: '', srcCache: {} };
const RANK = { anonymous: 0, reader: 1, reviewer: 2, admin: 3 };
const can = r => RANK[S.me ? S.me.role : 'anonymous'] >= RANK[r];
const TYPE_ZH = { topic:'主题', summary:'文档摘要', synthesis:'问答综合', concept:'概念', method:'方法', model:'模型', algorithm:'算法', parameter:'参数', metric:'指标',
  process:'工艺', tool:'工具', material:'材料', equipment:'设备', issue:'问题', result:'结论', person_or_org:'人物/机构' };
const ST_ZH = { draft:'草稿', in_review:'待审阅', changes_requested:'需修改', approved:'已通过', rejected:'已拒绝', published:'已发布',
  withdrawn:'已下架', superseded:'已被替换', active:'在架', exact:'原文精确匹配', moved:'原文位置偏移', fuzzy:'近似匹配', missing:'原文未找到',
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
  return data;
}
const get = p => api('GET', p);
function toast(msg, ms = 3500) { const d = document.createElement('div'); d.textContent = msg; $('#toast').appendChild(d); setTimeout(() => d.remove(), ms); }
const fmtTime = t => t ? String(t).replace('T', ' ').slice(0, 16) : '';
const set = html => { $('#main').innerHTML = html; };

// ---------------------------------------------------------------- shell
function renderShell(route) {
  const links = [['#/', '首页'], ['#/k', '知识'], ['#/graph', '图谱'], ['#/src', '原始文档']];
  if (S.me) links.push(['#/ask', '问答']);
  const rev = [['#/review', '审阅'], ['#/traces', 'LLM观测'], ['#/schema', '规范'], ['#/lint', '健康']];
  const adm = [['#/publish', '发布'], ['#/compile', '编译'], ['#/users', '用户'], ['#/log', '日志']];
  const a = (l, cls = '') => `<a href="${l[0]}" class="${cls} ${('#/' + route[0]) === l[0] || (route[0] === '' && l[0] === '#/') ? 'on' : ''}">${l[1]}</a>`;
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

function renderCardBody(card, known) {
  return MD.render(card.body || '', {
    wiki: (id, label) => {
      const k = MD.slug(id).replace(/[^a-z0-9-]/g, '');
      const miss = known && !known.has(k);
      return `<a href="${cardHref(k)}" class="${miss ? 'muted' : ''}" title="${miss ? '尚未发布/不存在' : ''}">${esc(label)}</a>`;
    },
    ev: id => `<a class="ev" data-ev="${esc(id)}" href="javascript:void 0">${esc(id)}</a>`,
    link: h => h, img: s => s,
  });
}

function evidenceList(card, withLines) {
  if (!card.evidence || !card.evidence.length) return '<p class="muted">无证据引用。</p>';
  return '<ol class="evlist">' + card.evidence.map(e => {
    const ln = e.found_lines || e.lines;
    return `<li id="ev-${esc(e.id)}"><b>${esc(e.id)}</b> ${badge(e.check || 'missing')}
      <a href="${srcHref(e.path, 'L=' + encodeURIComponent(ln))}">${esc(e.path)} · L${esc(ln)}</a>
      ${e.found_lines && e.found_lines !== e.lines ? `<span class="small muted">（模型声称 L${esc(e.lines)}）</span>` : ''}
      <div class="quote">${esc(e.quote)}</div>${withLines ? `<div class="srclines" data-path="${esc(e.path)}" data-lines="${esc(ln)}"></div>` : ''}</li>`;
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
  const all = await get('cards');
  const visible = can('reviewer') ? all.filter(c => c.published_rev || q.all) : all;
  if (!id) {
    const byType = {};
    visible.filter(c => c.type !== 'summary').forEach(c => (byType[c.type] = byType[c.type] || []).push(c));
    const sums = visible.filter(c => c.type === 'summary');
    set(`<div class="cols"><aside class="panel side">${topicTree(visible)}</aside><section class="panel"><h1>知识卡片</h1>
      <p class="muted small">${visible.length} 张${can('reviewer') ? '已发布卡片（审阅中的卡片见 <a href="#/review">审阅</a>）' : ''}</p>
      ${Object.entries(byType).map(([t, cs]) => `<h3>${esc(TYPE_ZH[t] || t)} <span class="muted small">${cs.length}</span></h3><div class="cardlist">` +
        cs.map(c => `<a class="item" href="${cardHref(c.id)}"><b>${esc(c.title)}</b><br><span class="muted small">${esc(c.summary || '')}</span></a>`).join('') + '</div>').join('')}
      <h2>文档摘要层 <span class="muted small">${sums.length} 篇 · 每篇原始文档一张摘要卡片，指向它贡献的知识</span></h2><div class="cardlist">${sums.map(c =>
        `<a class="item" href="${cardHref(c.id)}"><b>${esc(c.title)}</b> <span class="mono small muted">${(c.sources || []).map(x => esc(x.path)).join(', ')}</span><br><span class="muted small">${esc(c.summary || '')}</span></a>`).join('') || '<p class="muted">无</p>'}</div></section></div>`);
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
  if ((head.stale_sources || []).length) banners += `<div class="banner warn">原始文档已更新，此卡片可能过时：${head.stale_sources.map(esc).join('，')}</div>`;
  set(`<div class="cols"><aside class="panel side">${topicTree(visible, id)}</aside>
    <article class="panel doc"><div class="row">${badge('t', TYPE_ZH[card.type] || card.type)}${can('reviewer') ? badge(head.status) : ''}
      <span class="small muted">r${card.rev} · 证据核验 ${Math.round((card.grounding || {}).score * 100 || 0)}% · ${card.origin && card.origin.kind === 'llm' ? 'LLM 编译 ' + esc(card.origin.model || '') : '人工编辑 ' + esc((card.origin || {}).user || '')}${card.published_by ? ' · 由 ' + esc(card.published_by) + ' 发布于 ' + fmtTime(card.published_at) : ''}</span></div>
    ${banners}<h1>${esc(card.title)}</h1>${(card.aliases || []).length ? `<p class="muted small">别名：${card.aliases.map(esc).join('，')}</p>` : ''}
    <p><i>${esc(card.summary || '')}</i></p>${renderCardBody(card, known)}
    ${relationsBlock(card, d.backlinks)}${(card.relations || []).length ? '<p>' + basisSummary(card.relations) + '</p>' : ''}
    <h3>证据（原文引用，系统自动核验）</h3>${evidenceList(card, false)}
    <p class="small muted">来源：${(card.sources || []).map(s => `<a href="${srcHref(s.path)}">${esc(s.path)}</a> v${s.version}`).join('，')}
    ${can('reviewer') && card.origin && card.origin.run ? ` · <a href="#/traces/${esc(card.origin.run)}">查看编译过程</a>` : ''}</p></article></div>`);
  bindTree($('#main')); bindEvidence($('#main'));
};

routes.src = async (parts, q) => {
  const path = parts.join('/');
  const tree = await get('sources');
  const treeHtml = n => '<ul>' + n.children.filter(c => !(c.type === 'file' && c.path === n.index && n.path)).map(c => c.type === 'dir'
    ? `<li class="dir ${path.startsWith(c.path + '/') ? '' : 'closed'}"><span data-toggle>${esc(c.title || c.name)}</span>${c.index ? `<a href="${srcHref(c.index)}" class="${c.index === path ? 'on' : ''}" style="font-size:12px;color:var(--muted)">· 目录页</a>` : ''}${treeHtml(c)}</li>`
    : `<li><a href="${c.name.match(/\.(md|markdown|mdx)$/i) ? srcHref(c.path) : '/raw/' + c.path}" class="${c.path === path ? 'on' : ''}" title="${esc(c.path)}">${esc(c.title || c.name)}</a></li>`).join('') + '</ul>';
  const up = can('reviewer') ? `<details style="margin-top:12px"><summary>上传 Markdown 文件/文件夹</summary>
      <div class="row"><input type="file" id="upfiles" multiple accept=".md,.markdown,.mdx,.png,.jpg,.jpeg,.gif,.svg,.webp,.pdf,.csv,.txt,.json,.yaml,.yml"></div>
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
    if (/\.(md|markdown|mdx|txt|csv|json|ya?ml|svg)$/i.test(f.name)) { r.onload = () => res({ path: rel, text: r.result }); r.readAsText(f); }
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
    <h3>原始文档（${d.sources.length}）</h3><div class="cardlist">${d.sources.map(s =>
    `<a class="item" href="${srcHref(s.path, 'L=' + s.line)}"><span class="mono">${esc(s.path)}:${s.line}</span><br><span class="muted small">…${esc(s.snippet)}…</span></a>`).join('') || '<p class="muted">无</p>'}</div></div>`);
};

// ---------------------------------------------------------------- graph
routes.graph = async (_, q) => {
  const g0 = await get('graph' + (q.all ? '?all=1' : ''));
  const keep = new Set(g0.nodes.filter(n => q.sum || n.type !== 'summary').map(n => n.id));
  const g = { nodes: g0.nodes.filter(n => keep.has(n.id)), edges: g0.edges.filter(e => keep.has(e.s) && keep.has(e.t)) };
  const types = [...new Set(g.nodes.map(n => n.type))];
  set(`<div class="row"><b>知识图谱</b><span class="muted small">${g.nodes.length} 节点 · ${g.edges.length} 关系 · 滚轮缩放，拖动平移，点击打开</span>
      ${can('reviewer') ? `<label class="small"><input type="checkbox" id="gall" ${q.all ? 'checked' : ''}> 包含未发布</label>` : ''}
      <input id="gfilter" placeholder="高亮…" style="width:160px"></div>
    <div class="legend row">${types.map(t => `<span><i style="background:${TYPE_COLORS[t] || '#888'}"></i>${esc(TYPE_ZH[t] || t)}</span>`).join('')}
      <span class="small muted">边：实线 原文明确 · 虚线 推断 · 橙色点线 存疑 · 红色 矛盾</span>
      <label class="small"><input type="checkbox" id="gsum"> 显示文档摘要节点</label></div>
    <canvas id="graph"></canvas>`);
  const gnav = () => { const p = []; if ($('#gall') && $('#gall').checked) p.push('all=1'); if ($('#gsum').checked) p.push('sum=1'); location.hash = '#/graph' + (p.length ? '?' + p.join('&') : ''); };
  if ($('#gall')) $('#gall').onchange = gnav; $('#gsum').checked = !!q.sum; $('#gsum').onchange = gnav;
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
routes.review = async ([id], q) => {
  if (id) return reviewWorkspace(id, q);
  const cards = await get('cards');
  const tab = q.s || 'in_review';
  const tabs = ['in_review', 'changes_requested', 'approved', 'rejected', 'draft', 'published'];
  const amb = c => (c.relations || []).filter(r => r.basis === 'ambiguous').length;
  const rows = cards.filter(c => c.status === tab).sort((a, b) => amb(b) - amb(a) || ((a.grounding || {}).score || 0) - ((b.grounding || {}).score || 0));
  set(`<div class="panel"><h1>审阅队列</h1><div class="tabs">${tabs.map(t => `<a href="#/review?s=${t}" class="${t === tab ? 'on' : ''}">${zh(t)} (${cards.filter(c => c.status === t).length})</a>`).join('')}</div>
    <table class="grid"><tr><th>卡片</th><th>类型</th><th>修订</th><th>来源</th><th>证据核验</th><th>关系</th><th>编译来源</th><th>更新</th></tr>
    ${rows.map(c => `<tr><td><a href="#/review/${encodeURIComponent(c.id)}"><b>${esc(c.title)}</b></a><br><span class="mono muted">${esc(c.id)}</span>
        ${c.lifecycle !== 'active' ? badge(c.lifecycle) : ''}${(c.stale_sources || []).length ? badge('stale', '原文已变') : ''}${c.published_rev ? badge('published', '在线 r' + c.published_rev) : ''}</td>
      <td>${esc(TYPE_ZH[c.type] || c.type)}</td><td>r${c.rev}</td><td class="small">${(c.sources || []).map(s => esc(s.path)).join('<br>')}</td>
      <td>${gbadge(c.grounding)}</td><td>${basisSummary(c.relations)}</td><td class="small">${c.origin.kind === 'llm' ? `<a href="#/traces/${esc(c.origin.run)}">LLM ${esc(c.origin.model)}</a>` : c.origin.kind === 'query' ? `<a href="#/ask/${esc(c.origin.run)}">问答回写 ${esc(c.origin.user)}</a>` : '人工 ' + esc(c.origin.user)}</td><td class="small">${fmtTime(c.updated)}</td></tr>`).join('') || '<tr><td colspan="8" class="muted">空</td></tr>'}</table></div>`);
};
function gbadge(g) {
  g = g || {}; const s = Math.round((g.score || 0) * 100);
  return `${badge(s >= 90 ? 'exact' : s >= 60 ? 'fuzzy' : 'missing', s + '%')}<span class="small muted">${g.exact || 0}/${g.total || 0} 精确${g.missing ? '，' + g.missing + ' 未找到' : ''}</span>`;
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
      <div class="diff">${df.diff.split('\n').map(l => `<div class="${l.startsWith('+') ? 'a' : l.startsWith('-') ? 'd' : l.startsWith('@') ? 'h' : ''}">${esc(l) || ' '}</div>`).join('')}</div>`;
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
    tabBody = `<p class="small muted">修订 r${r.rev} · ${fmtTime(r.created)} · ${r.origin.kind === 'llm' ? 'LLM ' + esc(r.origin.model) : '人工 ' + esc(r.origin.user)} · ${esc(r.change_note || '')}</p><div class="doc"><h1>${esc(r.title)}</h1>${renderCardBody(r, known)}</div>${evidenceList(r)}`;
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
      <span class="small muted">r${h.rev}${h.published_rev ? ' · 已发布 r' + h.published_rev : ''} · ${h.origin.kind === 'llm' ? 'LLM 编译 ' + esc(h.origin.model) : '人工编辑 ' + esc(h.origin.user)} · <a href="${cardHref(id)}?view=head">读者视图</a></span></div>
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
      <h3>关系的认识论状态</h3><p>${basisSummary(h.relations)}</p>
      <h3>证据核验 ${gbadge(h.grounding)}</h3>
      <p class="small muted">模型给出的每条引用都被逐字核对原文行；高亮行为原文。</p>
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
  files.sort((a, b) => (a.startsWith('ans-') - b.startsWith('ans-')) || order.indexOf(a.replace(/^(nav|ans)-/, '')) - order.indexOf(b.replace(/^(nav|ans)-/, '')));
  const tabs = [['overview', '概览'], ...files.map(f => [f, (STEP[f.slice(0, 4)] || '') + (NAMES[f.replace(/^(nav|ans)-/, '')] || f)])];
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
      <div>用量</div><div class="small mono">${esc(JSON.stringify(u))}</div><div>耗时 / 费用</div><div>${r.latency_s}s ${r.cost_usd !== undefined ? '· $' + r.cost_usd : ''} · stop=${esc(r.stop_reason || '')}</div>
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
    ambiguous_relation: '存在“存疑”关系待人工判断', missing_summary: '文档缺少摘要卡片（需重新编译）' };
  set(`<div class="panel"><h1>知识库健康检查</h1><p class="muted">${issues.length} 项</p><table class="grid"><tr><th>卡片</th><th>问题</th><th>详情</th></tr>${issues.map(i =>
    `<tr><td><a href="#/review/${encodeURIComponent(i.card)}">${esc(i.card)}</a></td><td>${esc(KIND[i.kind] || i.kind)}</td><td class="small">${esc(i.detail)}</td></tr>`).join('')}</table></div>`);
};

// ---------------------------------------------------------------- admin
routes.publish = async () => {
  const cards = await get('cards');
  const appr = cards.filter(c => c.status === 'approved');
  const pub = cards.filter(c => c.published_rev);
  set(`<div class="panel"><h1>发布台</h1><h3>审阅通过、等待发布（${appr.length}）</h3>
    <table class="grid"><tr><th>卡片</th><th>修订</th><th>核验</th><th>当前在线</th><th></th></tr>${appr.map(c => `<tr><td><a href="#/review/${encodeURIComponent(c.id)}">${esc(c.title)}</a></td><td>r${c.rev}</td><td>${gbadge(c.grounding)}</td>
      <td>${c.published_rev ? 'r' + c.published_rev : '—'}</td><td><button class="primary" data-pub="${esc(c.id)}">发布</button> <button class="warn" data-ret="${esc(c.id)}">打回</button></td></tr>`).join('') || '<tr><td colspan=5 class="muted">无</td></tr>'}</table>
    <h3>已发布内容管理（${pub.length}）</h3><table class="grid"><tr><th>卡片</th><th>在线修订</th><th>状态</th><th>发布</th><th></th></tr>${pub.map(c => `<tr><td><a href="${cardHref(c.id)}">${esc(c.title)}</a></td><td>r${c.published_rev}${c.rev !== c.published_rev ? ` <span class="small muted">（新修订 r${c.rev} ${zh(c.status)}）</span>` : ''}</td>
      <td>${badge(c.lifecycle)}${c.replaced_by ? ' → ' + esc(c.replaced_by) : ''}${(c.stale_sources || []).length ? badge('stale', '原文已变') : ''}</td><td class="small">${esc(c.published_by || '')} ${fmtTime(c.published_at)}</td>
      <td>${c.lifecycle === 'active' ? `<button class="bad" data-wd="${esc(c.id)}">下架</button> <button data-sup="${esc(c.id)}">替换为…</button>` : `<button class="ok" data-rs="${esc(c.id)}">恢复</button>`}</td></tr>`).join('')}</table></div>`);
  const act = async (id, action, extra = {}) => { try { await api('POST', `cards/${encodeURIComponent(id)}/action`, { action, ...extra }); toast(zh(action) + ' ✓'); route(); } catch (e) { toast(e.message); } };
  document.querySelectorAll('[data-pub]').forEach(b => b.onclick = () => act(b.dataset.pub, 'publish'));
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
    <div class="row"><label>后端</label><select id="cbackend">${['mock', 'anthropic', 'command'].map(b => `<option ${b === plan.backend ? 'selected' : ''}>${b}</option>`).join('')}</select>
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
      <div class="row"><button class="primary" id="qgo">提问</button>${can('reviewer') ? '<label class="small"><input type="checkbox" id="qall"> 包含未发布（审阅中）卡片</label>' : ''}<span id="qwait" class="small muted"></span></div>
      ${res}</section><aside class="panel">${histHtml}</aside></div>`);
  bindEvidence($('#main')); fillSourceLines($('#main'));
  $('#qgo').onclick = async () => {
    const question = $('#qq').value.trim(); if (!question) return;
    $('#qgo').disabled = true; $('#qwait').textContent = '模型正在阅读与作答…';
    try { const r = await api('POST', 'ask', { question, include_unpublished: !!($('#qall') && $('#qall').checked) }); location.hash = '#/ask/' + r.id; }
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
