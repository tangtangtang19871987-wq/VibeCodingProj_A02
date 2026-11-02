// Custom opencode tools for the tech-report PPTX agent.
// Each tool is a typed, validated wrapper around ONE subcommand of
//   .opencode/skills/tech-report-pptx/scripts/deck.py
// so the model never has to hand-assemble shell commands. Tool names are <file>_<export>: deck_catalog, deck_new, ...
import { tool } from "@opencode-ai/plugin"
import path from "path"

async function deck(worktree: string, args: string[]): Promise<string> {
  const script = path.join(worktree, ".opencode/skills/tech-report-pptx/scripts/deck.py")
  const proc = Bun.spawn(["python3", script, ...args], { cwd: worktree, stdout: "pipe", stderr: "pipe" })
  const [out, err] = await Promise.all([new Response(proc.stdout).text(), new Response(proc.stderr).text()])
  const code = await proc.exited
  const text = (out + err).trim()
  return code === 0 ? text : `[exit ${code}]\n${text}`
}

export const catalog = tool({
  description:
    "List what the deck builder supports: slide types and their fields, the exact colour palette, icons, themes, or the full diagram manual. Call this before writing or changing an outline.",
  args: { topic: tool.schema.enum(["types", "palette", "icons", "themes", "diagram", "all"]).optional() },
  async execute(a, ctx) { return deck(ctx.worktree, ["catalog", a.topic ?? "all"]) },
})

export const create = tool({
  description: "Create output/<slug>/outline.json (cover + closing skeleton). Then fill it with the write/edit tools.",
  args: {
    slug: tool.schema.string().describe("folder name under output/, ascii, no spaces"),
    title: tool.schema.string().optional(),
    theme: tool.schema.string().optional().describe("default modern-tech — do not change unless the user asks"),
    lang: tool.schema.string().optional(),
  },
  async execute(a, ctx) {
    const args = ["new", a.slug]
    if (a.title) args.push("--title", a.title)
    if (a.theme) args.push("--theme", a.theme)
    if (a.lang) args.push("--lang", a.lang)
    return deck(ctx.worktree, args)
  },
})

export const check = tool({
  description:
    "Validate an outline BEFORE building: slide types/fields, diagram geometry (overlaps, out-of-canvas, unknown ids/icons/tones, edges crossing nodes) and colour rules. Fix every ERROR.",
  args: { outline: tool.schema.string().describe("path to outline.json") },
  async execute(a, ctx) { return deck(ctx.worktree, ["check", a.outline]) },
})

export const edit = tool({
  description:
    "Structured outline edits so you never rewrite the whole JSON for a small change. ops: show [N] | set-meta KEY VALUE | set-theme NAME | replace N JSON | insert N JSON | append JSON | delete N | move FROM TO | patch N JSON (deep merge; null deletes a key). JSON may be given as '@file.json'.",
  args: {
    outline: tool.schema.string(),
    op: tool.schema.enum(["show", "set-meta", "set-theme", "replace", "insert", "append", "delete", "move", "patch"]),
    args: tool.schema.array(tool.schema.string()).optional().describe("operands, e.g. ['3', '{\"title\":\"New title\"}']"),
  },
  async execute(a, ctx) { return deck(ctx.worktree, ["edit", a.outline, a.op, ...(a.args ?? [])]) },
})

export const build = tool({
  description:
    "Build the deliverables from an outline: runs check, writes draft.html (presentable preview) and deck.pptx (NATIVE, editable PowerPoint), then verify + lint. Returns a JSON summary. Exit code != 0 means fix and rebuild.",
  args: {
    outline: tool.schema.string(),
    theme: tool.schema.string().optional(),
    out: tool.schema.string().optional().describe("output directory (default: next to the outline)"),
    no_html: tool.schema.boolean().optional(),
  },
  async execute(a, ctx) {
    const args = ["build", a.outline]
    if (a.theme) args.push("--theme", a.theme)
    if (a.out) args.push("--out", a.out)
    if (a.no_html) args.push("--no-html")
    return deck(ctx.worktree, args)
  },
})

export const preview = tool({
  description:
    "Render slides to PNG (LibreOffice) plus a contact sheet so you can LOOK at them with the read tool. Always do this after a build and after every layout fix.",
  args: {
    file: tool.schema.string().describe("deck.pptx or outline.json"),
    pages: tool.schema.string().optional().describe("comma list, e.g. '2,5'"),
    dpi: tool.schema.number().optional(),
  },
  async execute(a, ctx) {
    const args = ["preview", a.file]
    if (a.pages) args.push("--pages", a.pages)
    if (a.dpi) args.push("--dpi", String(a.dpi))
    return deck(ctx.worktree, args)
  },
})

export const verify = tool({
  description:
    "Acceptance check of a .pptx: ZERO pictures (everything must be native/editable), pure-white backgrounds, palette audit, fonts, inventory of native text/charts/tables/shapes.",
  args: { deck: tool.schema.string(), allow_pictures: tool.schema.boolean().optional() },
  async execute(a, ctx) { return deck(ctx.worktree, ["verify", a.deck, ...(a.allow_pictures ? ["--allow-pictures"] : [])]) },
})

export const lint = tool({
  description: "Layout lint of a .pptx: text overflow, off-slide shapes, tiny fonts, missing notes/titles, font families.",
  args: { deck: tool.schema.string(), render: tool.schema.boolean().optional() },
  async execute(a, ctx) { return deck(ctx.worktree, ["lint", a.deck, ...(a.render ? ["--render"] : [])]) },
})

export const colors = tool({
  description:
    "MEASURE the colours of a reference image (optionally a crop 'x0,y0,x1,y1') and map them to the palette. Use this whenever the user says the colours are wrong or supplies a reference screenshot — never guess hex values.",
  args: { image: tool.schema.string(), crop: tool.schema.string().optional(), top: tool.schema.number().optional() },
  async execute(a, ctx) {
    const args = ["colors", a.image]
    if (a.crop) args.push("--crop", a.crop)
    if (a.top) args.push("--top", String(a.top))
    return deck(ctx.worktree, args)
  },
})
