# `diagram` slide — authoring manual

For architecture / flow / concept-map slides in the user's reference style: **semantic pastel-tint nodes with vector icons, coloured rounded arrows, lanes, numbered notes, code / list / legend panels, soft flat 3D cubes**. Same JSON renders to HTML (`outline_to_html.py`) and to *native editable* PPTX (`outline_to_pptx.py`). Working examples: `examples/diagrams.example.json` (4 slides reproducing the reference images: cover+flow, context-builder, LangGraph flow, two-lane memory).

```json
{"type":"diagram","kicker":"…","title":"…","subtitle":"…","edge_color":"source|dark","cover":false,
  "elements":[ … ], "edges":[ … ], "notes":"…"}
```
`cover:true` hides the title bar (use with a `heading` element for an opening slide).

## Canvas
Everything is placed in **1000 × 490 units** (x→right, y→down, origin top-left of the drawing area). Minimum useful sizes: node height ≥ 36, text ≥ 12 units (renders ≈ 10pt). Leave ≥ 8-unit gaps. **Run `check_outline.py` — it reports overlaps, out-of-canvas elements, unknown ids/icons/tones, edges crossing nodes.**

## Elements (`kind`)
| kind | fields |
|---|---|
| `node` | `id,x,y,w,h,label,sub?,tone,icon?,shape?(round\|pill\|diamond),layout?(row\|stack),valign?(top),dashed?` — `row`: icon left + text; `stack`: icon on top, centred (diamond defaults to stack); `pill` for START/END (no icon) |
| `group` | `x,y,w,h,tone,label` — lane container with header pill; children simply sit inside (no overlap error) |
| `note` | `x,y,w,h,n?,text,tone?` — numbered annotation card (n = badge number) |
| `chip` | `x,y,text,tone` — small label pill (width automatic) |
| `panel` | `x,y,w,h,tone,title?,icon?,id?,in?,dashed?,stack?,body` — body is ONE of `{"code":"…"}` · `{"bullets":[…]}` · `{"items":[{icon,tone,title,sub?}]}` (icon list) · `{"rows":[{chip,tone,text:[…]}]}` (framework chips + bullets) · `{"legend":[{style,tone,text}]}` · `{"text":"…"}`. `in:"<node id>"` = sits inside that node (skip overlap check). `stack:true` = concept card (big icon on top, title, text) |
| `text` | `x,y,w,h,text,size?,bold?,tone?` |
| `heading` | `x,y,w,h?,kicker?,title (\\n for lines),tagline?` — gradient headline for opening slides |
| `cubes` | `x,y,w,h` — cluster of three soft flat 3D cubes + dots (≈ 190×250 looks right) |

## Edges
`{"from":id,"to":id,"style":"solid|dashed","tone":…,"fs":"l|r|t|b","ts":"l|r|t|b","fo":0..1,"ti":0..1,"mid":0..1,"via":[[x,y],…],"bulge":30,"label":"…","label_tone":…,"label_at":[x,y]}`
- Auto-routing picks sides from relative position; give `fs`/`ts` for control. Orthogonal elbows with rounded corners.
- **Fan-in** (several sources → one target): same `ts`, different `ti` (0.1…0.9) and different `mid` so lines don't overlap. **Merge** (lanes → one node): same `ti` and same `mid`.
- **Loop back** (dashed): `fs:"l", ts:"l", bulge:30` (goes around the left side) or explicit `via` waypoints (`via` points must be orthogonal).
- Colour: `tone` per edge, else the source node's tone (`edge_color:"source"`); `edge_color:"dark"` = navy for all (LangGraph style). Convention: **solid = sequential, dashed = conditional / loop**; label branches with chips (`需要调用工具` green, `无需调用工具` orange / `YES` `NO`).

## Colour rules — style profile `vivid` (default). Source of truth: `html-ppt-studio/assets/styles/*.json` (run `deck_catalog palette` for the values)
Page: **pure white**. Titles deep navy, body dark grey. Nodes/cards: pale (gradient) tint + vivid outline in the tone colour; icons, labels, edges and lane pills use the vivid tone colour; coloured soft shadows; headline gradient blue→purple; cubes are glass gradients. Never: dark backgrounds, neon, large saturated blocks. Same component type ⇒ same colour on every slide.

| tone | meaning |
|---|---|
| `blue` (true blue) | input / data / general flow / branching |
| `purple` | model / agent / runtime / instructions |
| `green` | tools / storage / success |
| `orange` (amber) | decision / condition / state / answer / warning |
| `pink` | memory / long-term knowledge / error |
| `gray` | start / end / neutral |
| `dark` | navy edges |

(`teal`, `yellow` are retired — `check_outline.py` errors on them and names the replacement.)
Colour richness: pages are NOT one-colour. Parallel cards / steps / series cycle blue → purple → green → orange → pink (automatic outside `diagram`); in `diagram` slides assign tones by meaning, typically 4–5 per slide.
`soft:true` = pale outline for info cards (identical to the vivid outline in `vivid`); `key:true` on a **small** node = heavier border + coloured label.
Icon ⇒ colour is fixed across the deck (e.g. `robot` always purple, `wrench` green, `memory` pink); the checker warns when an icon changes colour.

## Icons
`bolt`, `bulb`, `chat`, `check`, `cloud`, `code`, `cube`, `database`, `doc`, `filter`, `flag`, `gear`, `globe`, `history`, `layers`, `link`, `lock`, `memory`, `play`, `refresh`, `robot`, `search`, `server`, `share`, `shield`, `split`, `terminal`, `user`, `wrench`

## Layout recipes (copy coordinates from the examples)
- **Sources → processor → model → output** (context-builder): left column of 5 nodes (x 0, w 280, h 54, step 64), big `stack` node at x≈345, model node x≈610, code panel x≈805; bottom row of 3 panels y≈330, h≈158.
- **Decision flow** (langgraph): flow on the left (x 0–640): START pill → node → diamond → two branches → merge; numbered `note`s to the right of nodes; right column x≈675: code panel, `items` panel, key-points panel.
- **Lanes** (memory): two `group`s side by side (x 0 / 515, w 485), two nodes each, arrows down, both merging into one wide `node` at y≈392.
- **Opening slide**: `cover:true`; `heading` left, three `stack` concept panels bottom-left, `cubes` centre, mini flow right (START → nodes → diamond → END, dashed loop, legend panel).
- Keep ≤ ~14 elements per slide; if you need more, split the slide. Text per node: label ≤ 14 chars (CJK) / sub ≤ 24 chars.
