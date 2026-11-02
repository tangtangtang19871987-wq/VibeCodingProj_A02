#!/usr/bin/env python3
"""Pre-render the icon library (diagram_geom.ICONS) to white 192px transparent PNGs in ../assets/icons/.
PPTX uses them on coloured badges; HTML uses inline SVG. Dev-time only (PNGs are committed): needs node + Playwright.
   python3 render_icons.py
"""
import json, os, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import diagram_geom as G

OUT = os.path.normpath(os.path.join(HERE, "..", "assets", "icons")); os.makedirs(OUT, exist_ok=True)
JS = r"""
const {chromium}=require('playwright'); const [,, data, out]=process.argv; const icons=JSON.parse(require('fs').readFileSync(data,'utf8'));
(async()=>{const b=await chromium.launch(); const pg=await b.newPage({viewport:{width:192,height:192}});
for(const [n,d] of Object.entries(icons)){
 await pg.setContent(`<html><body style="margin:0;background:transparent"><svg xmlns="http://www.w3.org/2000/svg" width="192" height="192" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="${d}"/></svg></body></html>`);
 await pg.screenshot({path:out+'/'+n+'.png',omitBackground:true,clip:{x:0,y:0,width:192,height:192}});}
await b.close();})();
"""
with tempfile.TemporaryDirectory() as d:
    open(os.path.join(d, "icons.json"), "w").write(json.dumps(G.ICONS)); open(os.path.join(d, "r.js"), "w").write(JS)
    root = subprocess.check_output(["npm", "root", "-g"], text=True).strip()
    subprocess.check_call(["node", os.path.join(d, "r.js"), os.path.join(d, "icons.json"), OUT], env=dict(os.environ, NODE_PATH=root))
print("rendered", len(G.ICONS), "icons ->", OUT)
