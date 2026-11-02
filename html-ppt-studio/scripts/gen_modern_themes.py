#!/usr/bin/env python3
"""Generate the 'modern' themes (one per style profile in assets/styles/*.json) so palette lives in ONE place.

  python3 scripts/gen_modern_themes.py      # writes assets/themes/<theme>.css, assets/themes.modern.css, updates assets/themes/themes.json

Style JSON fields used: theme, tones{fill,border,solid}, cycle, accent[3], head_color, gradients, shadow, gradient_heading."""
import json, os, glob

HERE = os.path.dirname(os.path.abspath(__file__)); A = os.path.join(HERE, "..", "assets")
FONTS = 'system-ui,-apple-system,"Segoe UI",Roboto,"Helvetica Neue","PingFang SC","Noto Sans SC",sans-serif'
CARD_GROUPS = [".layout-two-col .slide-body", ".layout-three-col .slide-body", ".layout-grid-4 .slide-body", ".layout-feature-icons .slide-body", ".layout-kpi-row .kpis",
               ".layout-faq .qa", ".layout-team .tm", ".layout-pricing .pr", ".layout-roadmap .rm", ".layout-hero .concepts"]
OTHER = [".layout-agenda .agenda", ".layout-process .steps", ".layout-timeline .tl", ".layout-funnel .fn", ".layout-bar-chart .bars"]
hx = lambda c: "#%02x%02x%02x" % tuple(c)


def vars_block(st):
    T = '[data-theme="%s"]' % st["theme"]; flat = not st["gradients"]
    shadow = "0 2px 10px rgba(30,41,59,.07)" if flat else "0 12px 32px rgba(60,90,200,.12),0 2px 6px rgba(60,90,200,.05)"
    a = st["accent"]
    return (f'{T}{{--bg:#ffffff;--bg2:#ffffff;--fg:#374151;--head-color:{st["head_color"]};--muted:#6b7280;--accent:{a[0]};--accent2:{a[1]};--accent3:{a[2]};'
            f'--card:#ffffff;--border:#e5e7eb;--radius:20px;--shadow:{shadow};--head-weight:800;--head-transform:none;--deck-style:{st["name"]};--style:{"clean" if flat else "vivid"};'
            f'--font-head:{FONTS};--font-body:{FONTS};--bg-image:linear-gradient(#ffffff,#ffffff);color-scheme:light}}\n')


def full_css(st):
    T = '[data-theme="%s"]' % st["theme"]; g = st["gradients"]; out = [f"/* ===== {st['name']}: {st['description']} ===== */\n", vars_block(st)]
    tones = st["tones"]; order = st["cycle"][:5]; n = len(order)
    out.append(f'{T} h1,{T} h2,{T} h3,{T} h4{{color:var(--head-color)}}\n')
    if g:
        out.append(f'{T} .card,{T} .chip{{backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px);background:linear-gradient(135deg,#fff,color-mix(in srgb,var(--accent) 5%,#fff));border:1.5px solid var(--border);box-shadow:var(--shadow)}}\n'
                   f'{T} .grad-text{{background-image:linear-gradient(90deg,var(--accent),var(--accent2) 55%,var(--accent3));-webkit-background-clip:text;background-clip:text;color:transparent}}\n'
                   f'{T} .kicker{{background:linear-gradient(90deg,var(--accent),var(--accent2));-webkit-background-clip:text;background-clip:text;color:transparent}}\n'
                   f'{T} .icon,{T} .layout-team .avatar{{background:linear-gradient(135deg,var(--accent),var(--accent2) 60%,var(--accent3));color:#fff;box-shadow:0 8px 20px color-mix(in srgb,var(--accent) 28%,transparent)}}\n'
                   f'{T} hr.rule,{T} .hud-progress{{background:linear-gradient(90deg,var(--accent),var(--accent2),var(--accent3))}}\n'
                   f'{T} .layout-cover .deco{{background:radial-gradient(circle at 30% 30%,color-mix(in srgb,var(--accent) 30%,#fff),color-mix(in srgb,var(--accent2) 22%,#fff) 60%,transparent 72%);filter:blur(6px);opacity:.9}}\n'
                   f'{T} .layout-table th{{background:linear-gradient(90deg,var(--accent),var(--accent2));color:#fff}}\n'
                   f'{T} .layout-roadmap .q header{{background:linear-gradient(90deg,var(--accent),var(--accent2));color:#fff}}\n'
                   f'{T} .layout-pricing .plan.hot{{border:2px solid var(--accent2);background:#fff}}\n')
    else:
        out.append(f'{T} .card,{T} .chip{{background:#fff;border:1.5px solid var(--border);box-shadow:var(--shadow);backdrop-filter:none}}\n'
                   f'{T} .grad-text{{background:none;-webkit-text-fill-color:currentColor;color:var(--accent)}}\n{T} .kicker{{background:none;-webkit-text-fill-color:currentColor;color:var(--accent)}}\n'
                   f'{T} .icon,{T} .layout-team .avatar{{background:var(--accent);color:#fff;box-shadow:none}}\n{T} hr.rule,{T} .hud-progress{{background:var(--accent)}}\n'
                   f'{T} .layout-cover .deco{{background:#eef2ff;filter:none;opacity:1}}\n{T} .layout-table th{{background:#eef2ff;color:var(--head-color)}}\n'
                   f'{T} .layout-roadmap .q header{{background:#eef2ff;color:var(--head-color)}}\n{T} .layout-pricing .plan.hot{{border:2px solid var(--accent);background:#fff}}\n'
                   # flat overrides of the diagram canvas
                   f'{T} .dg .dn{{background:var(--tf);border:1.5px solid var(--tb);box-shadow:0 2px 8px rgba(30,60,120,.06);color:var(--head-color)}}\n'
                   f'{T} .dg .dn.diamond{{background:none;border:0;box-shadow:none}}{T} .dg .dn.diamond svg.bg{{filter:drop-shadow(0 2px 5px rgba(30,60,120,.07))}}\n'
                   f'{T} .dg .grp{{border-width:1.5px;background:color-mix(in srgb,var(--tf) 38%,#fff)}}{T} .dg .gh{{box-shadow:none}}\n'
                   f'{T} .dg .pn{{background:color-mix(in srgb,var(--tf) 80%,#fff);border:1.5px solid var(--tbs);box-shadow:0 2px 8px rgba(30,41,59,.05)}}{T} .dg .pn.dashed{{background:#fff}}\n'
                   f'{T} .dg .note,{T} .dg .chip2{{box-shadow:none}}\n')
    for ln in ("s", ):
        pass
    out.append(f'{T}{{--c1s:{hx(tones[order[0]]["solid"])};--c2s:{hx(tones[order[1]]["solid"])};--c3s:{hx(tones[order[2]]["solid"])};--c4s:{hx(tones[order[3]]["solid"])};--c5s:{hx(tones[order[4]]["solid"])}}}\n')
    for k, tn in enumerate(order, 1):
        t = tones[tn]; out.append(",".join(f'{T} {gp} > :nth-child({n}n+{k})' for gp in CARD_GROUPS + OTHER) + f'{{--tf:{hx(t["fill"])};--tb:{hx(t["border"])};--ts:{hx(t["solid"])}}}\n')
    cardbg = "linear-gradient(135deg,var(--tf),color-mix(in srgb,var(--tf) 45%,#fff))" if g else "var(--tf)"
    sh = "0 8px 22px color-mix(in srgb,var(--ts) 14%,transparent)" if g else "0 2px 8px rgba(30,41,59,.06)"
    out.append(",".join(f'{T} {gp} > .card' for gp in CARD_GROUPS) + f'{{background:{cardbg};border:1.5px solid var(--tb);box-shadow:{sh}}}\n')
    out.append(",".join(f'{T} {gp} > .card h3' for gp in CARD_GROUPS) + "{color:var(--ts)}\n")
    icbg = "linear-gradient(135deg,var(--ts),color-mix(in srgb,var(--ts) 70%,#fff))" if g else "var(--ts)"
    out.append(",".join(f'{T} {gp} > .card .icon' for gp in CARD_GROUPS) + f"{{background:{icbg};color:#fff}}\n")
    out.append(f'{T} .layout-kpi-row .kpis > .card .v{{color:var(--ts)}}\n{T} .layout-hero .concepts > .card h3{{color:var(--head-color)}}\n'
               f'{T} .layout-agenda .agenda > li{{background:{cardbg};border:1.5px solid var(--tb)}}\n{T} .layout-agenda .agenda > li::before{{color:var(--ts)}}\n'
               f'{T} .layout-process .steps > .step{{background:{cardbg};border:1.5px solid var(--tb)}}\n{T} .layout-process .steps > .step .n,{T} .layout-process .steps > .step h3{{color:var(--ts)}}\n'
               f'{T} .layout-timeline .tl > .ev::before{{border-color:var(--ts)}}\n{T} .layout-timeline .tl > .ev .yr{{color:var(--ts)}}\n'
               f'{T} .layout-funnel .fn > .lv{{background:{cardbg};border:1.5px solid var(--tb);color:var(--head-color)}}\n'
               f'{T} .layout-bar-chart .bars > .b .fill{{background:{"linear-gradient(90deg,var(--ts),color-mix(in srgb,var(--ts) 60%,#fff))" if g else "var(--ts)"}}}\n')
    for k, tn in enumerate(order, 1): out.append(f'{T} ul.bullets > li:nth-child({n}n+{k})::before{{background:{hx(tones[tn]["solid"])}}}\n')
    B, P, Gr, O, R = [tones[x] for x in order]
    box = lambda t, extra="": f'background:{hx(t["fill"])};border:1.5px solid {hx(t["border"])};{extra}'
    out.append(f'{T} .layout-comparison .vs > .card:first-child{{{box(B)}}}{T} .layout-comparison .vs > .card:first-child h3{{color:{hx(B["solid"])}}}\n'
               f'{T} .layout-comparison .vs > .card:last-child{{{box(P)}}}{T} .layout-comparison .vs > .card:last-child h3{{color:{hx(P["solid"])}}}\n'
               f'{T} .layout-pros-cons .pros{{{box(Gr, "border-top:8px solid " + hx(Gr["solid"]))}}}{T} .layout-pros-cons .cons{{{box(R, "border-top:8px solid " + hx(R["solid"]))}}}\n'
               f'{T} .layout-pros-cons .pros h3{{color:{hx(Gr["solid"])}}}{T} .layout-pros-cons .cons h3{{color:{hx(R["solid"])}}}\n')
    for cls, tn in (("s", order[2]), ("w", order[3]), ("o", order[0]), ("t", order[4])):
        t = tones[tn]; out.append(f'{T} .layout-swot .sw .card.{cls}{{{box(t, "border-left:12px solid " + hx(t["solid"]))}}}{T} .layout-swot .sw .card.{cls} h3{{color:{hx(t["solid"])}}}\n')
    for k, tn in enumerate(order[:4]):
        t = tones[tn]; out.append(f'{T} .layout-layers .ly > :nth-child(8n+{2 * k + 1}){{--tf:{hx(t["fill"])};--tb:{hx(t["border"])};--ts:{hx(t["solid"])}}}\n')
    out.append(f'{T} .layout-layers .ly .lab{{background:var(--tf);color:var(--ts);border:1.5px solid var(--tb)}}\n{T} .layout-layers .ly .it.card{{background:color-mix(in srgb,var(--tf) 55%,#fff);border:1.5px solid var(--tb)}}\n'
               f'{T} .dag .node{{background:{cardbg if not g else "linear-gradient(135deg,rgba(255,255,255,.92),color-mix(in srgb,var(--tf) 70%,#fff))"};border-color:var(--tb)}}{T} .dag .node .ni{{background:{icbg}}}\n'
               f'{T} .layout-code .win{{background:#f6f8fc;border:1.5px solid var(--border);box-shadow:var(--shadow)}}{T} .layout-code .win header{{background:#eaeff7;color:#7886a0}}{T} .layout-code pre{{color:#2f3a4c}}\n'
               f'{T} .layout-code pre .k{{color:{hx(P["solid"])}}}{T} .layout-code pre .s{{color:{hx(Gr["solid"])}}}{T} .layout-code pre .c{{color:#8a97ab}}{T} .layout-code pre .f{{color:{hx(B["solid"])}}}{T} .layout-code pre .n{{color:{hx(O["solid"])}}}\n')
    return "".join(out)


def main():
    styles = [json.load(open(p, encoding="utf-8")) for p in sorted(glob.glob(os.path.join(A, "styles", "*.json")))]
    css = "/* GENERATED by scripts/gen_modern_themes.py from assets/styles/*.json — do not edit by hand. */\n" + "\n".join(full_css(s) for s in styles)
    open(os.path.join(A, "themes.modern.css"), "w", encoding="utf-8").write(css)
    tj = os.path.join(A, "themes", "themes.json"); th = json.load(open(tj, encoding="utf-8")); th = [x for x in th if not x["name"].startswith("modern-tech")]
    for i, s in enumerate(sorted(styles, key=lambda x: x["name"] != "vivid")):
        open(os.path.join(A, "themes", s["theme"] + ".css"), "w", encoding="utf-8").write(f"/* {s['theme']} ({s['name']}) — {s['description']} */\n" + vars_block(s))
        th.insert(i, {"name": s["theme"], "label": "Modern Tech" + ("" if s["name"] == "vivid" else " (flat)"), "mode": "light"})
    json.dump(th, open(tj, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print("wrote themes.modern.css for", [s["theme"] for s in styles])


if __name__ == "__main__": main()
