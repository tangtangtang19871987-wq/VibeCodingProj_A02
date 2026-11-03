# Troubleshooting — traps found while building (symptom → cause → fix)

## HTML draft
| symptom | cause | fix (already in code — keep it) |
|---|---|---|
| Overview mode shows empty slides | `[data-anim]` elements start at opacity 0 and only animate on `.is-active` | `body.overview .slide [data-anim]{opacity:1;animation:none}` |
| SVG arrowheads missing on some slides | duplicate `<marker id>` across slides; the first definition lives in a hidden slide, and markers inherit its `visibility:hidden` | unique marker ids per diagram (`m<N><hex>`) |
| Arrowheads missing after a refactor | marker id contained `#` (`m1#2a3a7a`) while the reference used the hex without `#` | build ids from `hex[1:]` everywhere |
| A node suddenly loses its colour and text shrinks | inline style string glued two CSS variables without `;` (`--ts:#1470e8--k:1.45`) | `_pos()` joins vars with `;` — when adding a CSS variable, check the generated HTML |
| Canvas overflows the slide | logical canvas scale too large with title + subtitle | `US = 1.6` (1.76 for cover diagrams) |
| `.grad-text` invisible on some themes | gradient text needs `background-clip:text` and a gradient background | defined per style in generated `themes.modern.css` |

## PPTX (python-pptx)
| symptom | cause | fix |
|---|---|---|
| Text inside shapes tiny | fitting measured a 0×0 box when text was put into an existing shape | measure `shape.width/height` when `shape=` is passed |
| KPI numbers wrap in serif themes | width heuristic too optimistic for bold / Georgia | widen factor 1.2 (bold) × 1.15 (Georgia); one font size for all tiles |
| Table cells tiny | fitted all columns as one paragraph stack | fit each cell separately, take the minimum |
| Lint says overflow but render is fine | lint ignored the text frame's real margins | lint uses actual margins (keep) |
| Node sub-label 9 pt (lint ERROR) | auto-shrink went below 10 pt | min 10 pt; widen nodes instead of shrinking |
| Radial "glow" circles render as hard-edged discs in LibreOffice | path-gradient alpha is unreliable in LO | no glows; pure white page |
| Edges not glued to nodes | python-pptx connectors can't do bent routes reliably | freeform polylines with `tailEnd` arrows (documented limitation) |
| Icons were pictures (not editable) | PNG icons on badges | `svgpath.py` flattens the SVG path → native freeform group (`draw_icon`) |
| 3+ stop gradients / alpha | not exposed by python-pptx | write `a:gradFill` / `a:alpha` XML (`gfill`, `glow_fill`) |
| Table style banding / grid looks off | default table style | set "No Style, No Grid" GUID and fill cells explicitly |
| Gradient fills disappear in the flat style | `gfill` intentionally returns a solid fill when `flat` | expected; vivid keeps gradients |
| Multi-colour cycling vanished in vivid | `tn()` was gated on the `flat` flag instead of "modern style" | gate on `t["glass"]` (any modern style); flat only controls gradients/shadows |

## Colour & style
| symptom | cause | fix |
|---|---|---|
| "Blue" looks purple | indigo #4F46E5 is ~243° hue, next to violet ~262° | blue must be 205–230°; selftest enforces ≥25° gap to purple |
| Page looks empty / grey | panel fills mixed too much white; borders too pale | tints at full tone fill (or 80 %); clear tone outlines |
| `deck_colors` maps a pale blue to `dark` | neutral `dark` fill is a near-white blue-grey | neutrals only match as lines/labels (fixed) |
| Golden distance numbers disagree with the eye | signature is a coarse hue histogram | goldens are tripwires; always look with `deck_compare` |
| Comparing renders unfairly | golden image showed slides 1+3 but test compared 4 slides | each golden lists the exact slides it corresponds to |

## Outline / diagram schema
| symptom | cause | fix |
|---|---|---|
| Edge goes to the wrong point | `to` used both for target id and side fraction | target-side fraction is `ti`, source-side `fo` |
| Overlaps after every new diagram | coordinates invented from scratch | copy an example skeleton; `deck_check` reports overlaps |

## opencode & environment
| symptom | cause | fix |
|---|---|---|
| "skills not loaded" | false alarm: `opencode debug skill` output was truncated by a pipe | write the output to a file, then parse |
| Which dirs does opencode read? | v1.19.5 accepts singular and plural: `.opencode/agent(s)`, `command(s)`, `tool(s)`, `skill(s)` | verify with `opencode debug config`, `opencode debug skill > f`, `opencode debug agent <name> > f` |
| Custom tools need dependencies | opencode auto-installs `@opencode-ai/plugin` into `.opencode/node_modules` | ignored in git; version pinned in `.opencode/package.json` |
| `opencode run` → "Proxy refused to open a tunnel: 403" | the cloud environment's network policy blocks `openrouter.ai` | user allows the domain in the environment's Network access, or runs locally; never fake results |
| Key variable name | opencode's OpenRouter provider reads `OPENROUTER_API_KEY` (the cloud env had `OPEN_ROUTER_API_KEY`) | map it in the command env; never print or commit keys |
| Adding a git submodule of a third-party repo was refused | auto-mode classifier treats it as untrusted code integration | `setup.sh` fetches ppt-master on the user's machine instead |
| A commit went in with a failing selftest | `selftest | tail` hid the exit code | check "0 failed" before `git commit` |
| Archive for local use | — | `git archive --format=zip --prefix=<repo>/ HEAD`; symlinks survive on macOS/Linux, not on plain Windows unzip |

## Seeing (vision) chain
| symptom | cause | fix |
|---|---|---|
| `deck_preview` fails: "needs LibreOffice (soffice)" / "pdftoppm" | renderer not installed on this machine | install LibreOffice + poppler (`setup.sh` prints the commands); until then say you cannot look, don't pretend |
| You `read` a PNG but get no visual content | the selected model has no image input | tell the user to switch to a vision model (e.g. Claude Sonnet/Opus via OpenRouter) |
| Render differs slightly from PowerPoint | LibreOffice ≠ PowerPoint (fonts, shadows, gradients) | judge layout/colour from the render; mention fidelity limits; if the user sends a PowerPoint screenshot, that wins |
| User wants you to check the HTML draft | no HTML screenshot tool | open `draft.html` in a browser yourself is not possible — ask the user for a screenshot, or judge from the PPTX render (same outline, same palette) |
