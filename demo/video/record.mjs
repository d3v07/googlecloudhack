import fs from "node:fs";
import path from "node:path";
import { execSync } from "node:child_process";
import { chromium } from "playwright";

const DIR = "/Users/dev/Documents/GCRAH/demo/video";
const OUT = path.join(DIR, "out");
const AUDIO = path.join(DIR, "audio");
const FF = "/opt/homebrew/bin/ffmpeg";
const FP = "/opt/homebrew/bin/ffprobe";
const BASE = "http://localhost:3100";
const RUN_ID = JSON.parse(fs.readFileSync(path.join(DIR, "prestage.json"), "utf8")).run_id;
const CRED = {
  dev: ["dev.trivedi", "a5rGdW8qTGoGCF23"],
  aakash: ["aakash.singh", "ozIE6iyi4uA5glvP"],
  dbre: ["dbre", "Jd74qM--Gg8PBI_Z"],
};
const W = 1440, H = 900;

// scene order from scenes.json; per-scene duration = its narration length + small tail (no over-pad)
const order = JSON.parse(fs.readFileSync(path.join(DIR, "scenes.json"), "utf8")).scenes.map((s) => s.id);
const adur = (id) => parseFloat(execSync(`${FP} -v error -show_entries format=duration -of csv=p=0 "${path.join(AUDIO, id + ".mp3")}"`).toString().trim());
const scenes = order.map((id) => ({ id, audioDur: adur(id), dur: +(adur(id) + 0.45).toFixed(2) }));

const CURSOR_INIT = () => {
  try { ["user", "dbre", "runreview"].forEach((k) => localStorage.setItem("sift_tour_" + k, "seen")); } catch (e) {}
  const mk = () => {
    if (document.getElementById("__dc")) return;
    const c = document.createElement("div");
    c.id = "__dc";
    c.style.cssText = "position:fixed;left:0;top:0;z-index:2147483647;pointer-events:none;transition:transform .65s cubic-bezier(.4,0,.2,1);transform:translate(720px,440px)";
    c.innerHTML = '<svg width="24" height="24" viewBox="0 0 24 24"><path d="M4 2l6.5 16 2.2-6.3L19 9.3z" fill="#fff" stroke="#0a0b0f" stroke-width="1.6" stroke-linejoin="round"/></svg>';
    document.body.appendChild(c);
    const r = document.createElement("div");
    r.id = "__dr";
    r.style.cssText = "position:fixed;left:0;top:0;width:36px;height:36px;border:3px solid #5cc8e6;border-radius:50%;z-index:2147483646;pointer-events:none;opacity:0;transform:translate(-100px,-100px) scale(.4)";
    document.body.appendChild(r);
  };
  if (document.body) mk(); else document.addEventListener("DOMContentLoaded", mk);
  window.__to = (x, y) => { mk(); document.getElementById("__dc").style.transform = `translate(${x}px,${y}px)`; };
  window.__pulse = (x, y) => {
    mk();
    const r = document.getElementById("__dr");
    r.style.transition = "none"; r.style.opacity = "0"; r.style.transform = `translate(${x - 18}px,${y - 18}px) scale(.4)`;
    requestAnimationFrame(() => { r.style.transition = "transform .45s ease,opacity .45s ease"; r.style.opacity = ".9"; r.style.transform = `translate(${x - 18}px,${y - 18}px) scale(1.5)`; setTimeout(() => { r.style.opacity = "0"; }, 420); });
  };
};

const sleep = (ms) => new Promise((r) => setTimeout(r, Math.max(0, ms)));
const now = () => Date.now();
async function center(page, sel) { const b = await page.locator(sel).first().boundingBox().catch(() => null); return b ? { x: b.x + b.width / 2, y: b.y + b.height / 2 } : null; }
async function moveTo(page, x, y, wait = 720) { await page.evaluate(([x, y]) => window.__to(x, y), [x, y]); await sleep(wait); }
async function moveSel(page, sel) { const p = await center(page, sel); if (p) await moveTo(page, p.x, p.y); return p; }
async function clickSel(page, sel) { const p = await moveSel(page, sel); if (p) { await page.evaluate(([x, y]) => window.__pulse(x, y), [p.x, p.y]); await sleep(260); } await page.locator(sel).first().click({ timeout: 15000 }).catch((e) => console.error("click", sel, e.message)); }
async function pulseSel(page, sel) { const p = await moveSel(page, sel); if (p) { await page.evaluate(([x, y]) => window.__pulse(x, y), [p.x, p.y]); await sleep(380); } }
async function typeInto(page, sel, text) { await moveSel(page, sel); await page.locator(sel).first().click(); await page.locator(sel).first().fill(""); await page.locator(sel).first().pressSequentially(text, { delay: 52 }); }

// smooth, duration-controlled scroll (continuous motion, no jump-cuts)
async function panTo(page, toY, ms = 2400) {
  const fromY = await page.evaluate(() => window.scrollY);
  toY = Math.max(0, toY);
  if (Math.abs(toY - fromY) < 4) { await sleep(ms); return; }
  const steps = Math.max(12, Math.round(ms / 50));
  for (let i = 1; i <= steps; i++) {
    const t = i / steps, e = t < 0.5 ? 2 * t * t : 1 - (-2 * t + 2) ** 2 / 2; // ease-in-out
    await page.evaluate((y) => window.scrollTo(0, y), Math.round(fromY + (toY - fromY) * e));
    await sleep(ms / steps);
  }
}
async function selTop(page, sel) { return await page.evaluate((s) => { const el = document.querySelector(s); return el ? window.scrollY + el.getBoundingClientRect().top : null; }, sel); }
async function panToSel(page, sel, ms = 2400, margin = 80) { const y = await selTop(page, sel); if (y == null) { await sleep(ms); return; } await panTo(page, Math.max(0, y - margin), ms); }

async function login(page, who, hero = 0) {
  const [u, pw] = CRED[who];
  await page.goto(`${BASE}/login`, { waitUntil: "networkidle" });
  await sleep(600 + hero);
  await typeInto(page, 'input[autocomplete="username"]', u);
  await moveSel(page, 'input[type="password"]');
  await page.locator('input[type="password"]').first().fill(pw);
  await sleep(260);
  await clickSel(page, 'button[type="submit"]');
  await page.waitForLoadState("networkidle").catch(() => {});
  await sleep(1100);
}

const ACTIONS = {
  hook: async (page, fill) => { await login(page, "dev", 2600); await fill(); },
  dev_query: async (page, fill) => {
    await clickSel(page, 'button:has-text("Phone orders")');
    await sleep(2600);
    await fill([[560, 0.55], [760, 0.45]]);
  },
  aakash: async (page, fill) => {
    await panTo(page, 0, 500); await clickSel(page, 'button[aria-label="Sign out"]'); await sleep(800);
    await login(page, "aakash");
    await clickSel(page, 'button:has-text("Seattle buyers")');
    await sleep(2400);
    await fill([[560, 1]]);
  },
  dbre_queue: async (page, fill) => {
    await panTo(page, 0, 500); await clickSel(page, 'button[aria-label="Sign out"]'); await sleep(800);
    await login(page, "dbre");
    await page.goto(`${BASE}/dbre`, { waitUntil: "networkidle" }); await sleep(1100);
    await fill([[60, 0.4], [260, 0.6]]);
  },
  diagnose: async (page, fill) => {
    await pulseSel(page, "tr:has-text('Phone') button:has-text('Diagnose'), button:has-text('Diagnose')");
    await sleep(400);
    await page.goto(`${BASE}/run-review?run_id=${RUN_ID}`, { waitUntil: "networkidle" }); await sleep(1300);
    const roles = (await selTop(page, "text=ROLES")) ?? 560;
    const tools = (await selTop(page, "text=TOOL CALLS")) ?? 1050;
    await fill([[roles - 70, 0.45], [tools - 60, 0.55]]);
  },
  gate: async (page, fill) => {
    await panTo(page, 0, 1400);
    await moveSel(page, 'button:has-text("Approve this evidence hash")');
    await fill([[0, 0.5], [120, 0.5]]);
  },
  payoff: async (page, fill) => {
    await panTo(page, 0, 500);
    await clickSel(page, 'button:has-text("Approve this evidence hash")');
    await sleep(7500); // backend builds the gcrah_rec_ index + re-explains -> VERIFIED
    const ba = (await selTop(page, "text=/before\\s*\\/\\s*after/i")) ?? 1700;
    await panTo(page, ba - 70, 2600); // smooth reveal of the collapse
    await fill([[ba - 70, 1]]); // gentle hold/drift on 100,377 -> 15
  },
  memory_close: async (page, fill) => {
    await panToSel(page, 'section[aria-label="Sift Memory"]', 2400, 70);
    await fill([[null, 0.5]]); // dwell on the live Voyage results
    await page.goto(`${BASE}/system-map`, { waitUntil: "networkidle" }); await sleep(1000);
    await panTo(page, 80, 1400);
    await fill([[80, 0.5], [360, 0.5]]);
  },
};

const browser = await chromium.launch({ headless: true });
const ctx = await browser.newContext({ viewport: { width: W, height: H }, recordVideo: { dir: OUT, size: { width: W, height: H } }, deviceScaleFactor: 1 });
await ctx.addInitScript(CURSOR_INIT);
const page = await ctx.newPage();

const offsets = [];
const t0 = now();
for (const s of scenes) {
  const start = (now() - t0) / 1000;
  offsets.push({ id: s.id, start: +start.toFixed(2), dur: s.dur, audioDur: s.audioDur });
  console.log(`scene ${s.id} @ ${start.toFixed(1)}s (len ${s.dur}s)`);
  const sceneStart = now();
  // fill(segments): consume remaining scene time with gentle motion; segments=[[y|null, weight],...]
  const fill = async (segments = [[null, 1]]) => {
    const remain = s.dur * 1000 - (now() - sceneStart);
    if (remain <= 200) return;
    const tw = segments.reduce((a, x) => a + x[1], 0) || 1;
    for (const [y, w] of segments) {
      const ms = (remain * w) / tw;
      if (y == null) await sleep(ms);
      else await panTo(page, y, ms);
    }
  };
  try { await ACTIONS[s.id](page, fill); } catch (e) { console.error(`  action error ${s.id}:`, e.message); }
  const left = s.dur * 1000 - (now() - sceneStart);
  if (left > 0) await sleep(left);
}
const video = await page.video();
await ctx.close();
await browser.close();
const webm = await video.path();
fs.writeFileSync(path.join(DIR, "offsets.json"), JSON.stringify(offsets, null, 2));
console.log("webm:", webm);

const total = offsets[offsets.length - 1].start + offsets[offsets.length - 1].dur;
const inputs = offsets.map((o) => `-i "${path.join(AUDIO, o.id + ".mp3")}"`).join(" ");
const delays = offsets.map((o, i) => `[${i + 1}]adelay=${Math.round(o.start * 1000)}|${Math.round(o.start * 1000)}[a${i}]`).join(";");
const amix = offsets.map((_, i) => `[a${i}]`).join("") + `amix=inputs=${offsets.length}:normalize=0[aout]`;
const finalMp4 = path.join(OUT, "sift-demo.mp4");
execSync(`${FF} -y -i "${webm}" ${inputs} -filter_complex "${delays};${amix}" -map 0:v -map "[aout]" -t ${total.toFixed(2)} -c:v libx264 -pix_fmt yuv420p -preset medium -crf 21 -c:a aac -b:a 192k -movflags +faststart "${finalMp4}"`, { stdio: "inherit" });
console.log("DONE:", finalMp4, `(${total.toFixed(1)}s)`);
