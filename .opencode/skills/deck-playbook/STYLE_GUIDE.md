# Style guide — the look this user likes

## 1. Where the truth lives (in priority order)
1. **Images the user approved** — `evals/golden/` (`manifest.json` lists them with the user's own words):
   - `vivid-reference.png` — "我要的是你之前做出来的这种": hero slide + LangGraph flow; true blue, gradient blue→purple headline, glass cubes, vivid outlines, coloured soft shadows.
   - `liked-diagram-render.png` — "这种就是我喜欢的": Context-builder, LangGraph flow and two-lane memory slides; pale fills + clear coloured outlines, five hues.
2. **The user's original references** — `references/`:
   - `ref-0-langgraph-hero.png` (opening slide: headline left, glass cubes centre, flow right, three concept cards bottom-left, legend)
   - `ref-1-context-builder.png` (five coloured source cards → builder → model → code panel; three panels underneath)
   - `ref-2-langgraph-flow.png` (START pill → agent → diamond → branches with coloured chips → END; numbered notes; code / node legend / key-points column)
   - `ref-3-memory-lanes.png` (two lanes with solid header pills, nodes inside, merging into a wide runtime node)
   - `ref-4-palette-spec-screenshot.png` (a palette table the user brought from Gemini: indigo/violet/emerald/amber/rose fills + deep borders). This became the `flat` style; when rendered, its indigo read as purple and the user later asked for the vivid look back — treat it as an alternative, not the default.
   - The green music-note circle at the top-left of refs 1–3 is a phone overlay, not part of the design.
3. **The style profile** — `html-ppt-studio/assets/styles/vivid.json` (default, theme `modern-tech`) and `flat.json` (theme `modern-tech-flat`). Print with `deck_catalog palette`.

## 2. The look in words (vivid, default)
- **Page:** pure white. No glows, no tinted page background, no dark backgrounds. (User explicitly: "我希望背景色是纯白".)
- **Typography:** titles deep navy, body dark grey; small coloured kicker above the title; the opener headline may be a blue→purple gradient.
- **Cards / nodes:** pale tint fill of the tone (very light, slightly gradient in vivid), a **clear 1.5–2 px outline in the tone colour**, rounded corners, a soft shadow tinted with the tone. Never grey-on-white cards with grey borders — that reads as "no colour".
- **Icons:** in a filled circle of the tone colour (gradient in vivid), white vector glyph; the same icon keeps the same colour across a deck.
- **Colour count:** rich. Five hues are normal on a dense diagram (the references use five). Parallel items cycle blue → purple → green → orange → pink. A page that is all blue is a defect.
- **Hues:** blue = a real blue (≈ #2270F2, hue ~220°), purple = violet (≈ #7444F6), green ≈ #0F9A68, orange/amber ≈ #F08A1C ("黄色" in the user's words means this amber), pink ≈ #E83E80. Exact values: `deck_catalog palette`.
- **Edges:** rounded orthogonal elbows; solid = sequential, dashed = conditional / loop; colour follows the source node (or navy for a whole flow); branch labels are small coloured chips (green "需要调用工具", orange "无需调用工具", YES/NO).
- **Diagram furniture:** START/END grey pills; decision = diamond; lanes = large rounded container with a solid pill header in the lane colour; numbered notes = small light cards with a coloured number badge; right-hand column of panels (code, node legend with icons, key points).
- **3D motif:** a cluster of three cubes (green small top-left, big violet, small blue) with glass gradient faces and dots — on the opener only.
- **Composition:** left = concept & headline, centre = visual, right = technical logic.

## 3. What the user rejected (don't do these)
| rejected | user's words | why it happened |
|---|---|---|
| Dark tech themes (midnight etc.) | "完全错误的配色" | first demos used a dark default |
| Washed-out, low-saturation, flat everything | "颜色还不太对", "你这里头什么也没有" | constraints were over-applied to the whole palette |
| Pages with only blue / blue+grey | "我图片中出现了好几种颜色…黄色、紫色、蓝色、绿色" | multi-colour cycling existed only in diagrams |
| Indigo used as "blue" | (implicit) "你后面做的又退回去了" | indigo #4F46E5 next to violet looks like two purples |
| Losing gradient headline / glass cubes / coloured shadows | "我要的是你之前做出来的这种" | flat style replaced the vivid one |
| Tinted / glowing page background | "我希望背景色是纯白" | early glass theme had radial glows |

## 4. Semantic colour table (diagrams and cards)
| tone | use for | typical icons |
|---|---|---|
| blue | input, data, messages, general flow, branching/conditions in LangGraph style, output | doc, chat, search, globe, split, history |
| purple | model / LLM / agent / runtime / instructions | robot, layers, bolt (answers from the model) |
| green | tools, storage, success, persistence | wrench, terminal, database, server, cube |
| orange (amber) | decision, condition, state/progress, final answer, warning, retry | filter, sliders, refresh |
| pink | memory, long-term knowledge, error | memory |
| gray | START / END / neutral panels | — |
| dark | navy lines for a monochrome flow | — |
If the user's reference assigns differently, **follow the reference** and keep it consistent across the deck.
