import fs from "node:fs";
import path from "node:path";
import { execSync } from "node:child_process";
import { chromium } from "playwright";

const DIR = "/Users/dev/Documents/GCRAH/demo/video";
const OUT = path.join(DIR, "out");
const AUDIO = path.join(DIR, "audio");
const FF = "/opt/homebrew/bin/ffmpeg";
const BASE = "http://localhost:3100";
const RUN_ID = JSON.parse(fs.readFileSync(path.join(DIR, "prestage.json"), "utf8")).run_id;
const CRED = {
  dev: ["dev.trivedi", "a5rGdW8qTGoGCF23"],
  aakash: ["aakash.singh", "ozIE6iyi4uA5glvP"],
  dbre: ["dbre", "Jd74qM--Gg8PBI_Z"],
};
const scenes = JSON.parse(fs.readFileSync(path.join(DIR, "scenes.timed.json"), "utf8")).scenes;
const W = 1440, H = 900;

const CURSOR_INIT = () => {
  try {
    localStorage.setItem("sift_tour_user", "seen");
    localStorage.setItem("sift_tour_dbre", "seen");
    localStorage.setItem("sift_tour_runreview", "seen");
  } catch (e) {}
  const mk = () => {
    if (document.getElementById("__dc")) return;
    const c = document.createElement("div");
    c.id = "__dc";
    c.style.cssText =
      "position:fixed;left:0;top:0;z-index:2147483647;pointer-events:none;transition:transform .7s cubic-bezier(.4,0,.2,1);transform:translate(720px,450px)";
    c.innerHTML =
      '<svg width="24" height="24" viewBox="0 0 24 24"><path d="M4 2l6.5 16 2.2-6.3L19 9.3z" fill="#fff" stroke="#0a0b0f" stroke-width="1.6" stroke-linejoin="round"/></svg>';
    document.body.appendChild(c);
    const r = document.createElement("div");
    r.id = "__dr";
    r.style.cssText =
      "position:fixed;left:0;top:0;width:36px;height:36px;border:3px solid #5cc8e6;border-radius:50%;z-index:2147483646;pointer-events:none;opacity:0;transform:translate(-100px,-100px) scale(.4)";
    document.body.appendChild(r);
  };
  if (document.body) mk();
  else document.addEventListener("DOMContentLoaded", mk);
  window.__to = (x, y) => { mk(); document.getElementById("__dc").style.transform = `translate(${x}px,${y}px)`; };
  window.__pulse = (x, y) => {
    mk();
    const r = document.getElementById("__dr");
    r.style.transition = "none"; r.style.opacity = "0";
    r.style.transform = `translate(${x - 18}px,${y - 18}px) scale(.4)`;
    requestAnimationFrame(() => {
      r.style.transition = "transform .45s ease,opacity .45s ease";
      r.style.opacity = ".9"; r.style.transform = `translate(${x - 18}px,${y - 18}px) scale(1.5)`;
      setTimeout(() => { r.style.opacity = "0"; }, 420);
    });
  };
};

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function center(page, sel) { const b = await page.locator(sel).first().boundingBox(); return b ? { x: b.x + b.width / 2, y: b.y + b.height / 2 } : null; }
async function moveTo(page, x, y, wait = 800) { await page.evaluate(([x, y]) => window.__to(x, y), [x, y]); await sleep(wait); }
async function moveSel(page, sel) { const p = await center(page, sel); if (p) await moveTo(page, p.x, p.y); return p; }
async function clickSel(page, sel) {
  const p = await moveSel(page, sel);
  if (p) { await page.evaluate(([x, y]) => window.__pulse(x, y), [p.x, p.y]); await sleep(280); }
  await page.locator(sel).first().click({ timeout: 15000 }).catch((e) => console.error("click", sel, e.message));
}
async function pulseSel(page, sel) {
  const p = await moveSel(page, sel);
  if (p) { await page.evaluate(([x, y]) => window.__pulse(x, y), [p.x, p.y]); await sleep(400); }
}
async function typeInto(page, sel, text) {
  await moveSel(page, sel);
  await page.locator(sel).first().click();
  await page.locator(sel).first().fill("");
  await page.locator(sel).first().pressSequentially(text, { delay: 55 });
}
async function scrollTo(page, y, wait = 1100) { await page.evaluate((y) => window.scrollTo({ top: y, behavior: "smooth" }), y); await sleep(wait); }

async function login(page, who, lingerLogin = 0) {
  const [u, pw] = CRED[who];
  await page.goto(`${BASE}/login`, { waitUntil: "networkidle" });
  await sleep(700 + lingerLogin);
  await typeInto(page, 'input[autocomplete="username"]', u);
  await moveSel(page, 'input[type="password"]');
  await page.locator('input[type="password"]').first().fill(pw);
  await sleep(300);
  await clickSel(page, 'button[type="submit"]');
  await page.waitForLoadState("networkidle").catch(() => {});
  await sleep(1300);
}
async function runPreset(page, text) {
  await clickSel(page, `button:has-text("${text}")`);
  await sleep(2600);
  await scrollTo(page, 540);
}
async function signOut(page) { await scrollTo(page, 0, 600); await clickSel(page, 'button[aria-label="Sign out"]'); await sleep(900); }

const ACTIONS = {
  hook: async (page) => { await login(page, "dev", 3500); },
  dev_query: async (page) => { await runPreset(page, "Phone orders"); },
  aakash: async (page) => { await signOut(page); await login(page, "aakash"); await runPreset(page, "Seattle buyers"); },
  dbre_queue: async (page) => { await signOut(page); await login(page, "dbre"); await page.goto(`${BASE}/dbre`, { waitUntil: "networkidle" }); await sleep(1200); await scrollTo(page, 90, 900); await scrollTo(page, 200, 900); },
  diagnose: async (page) => {
    await pulseSel(page, "tr:has-text('Phone') button:has-text('Diagnose'), button:has-text('Diagnose')");
    await sleep(500);
    await page.goto(`${BASE}/run-review?run_id=${RUN_ID}`, { waitUntil: "networkidle" });
    await sleep(1500);
    await scrollTo(page, 640);
    await scrollTo(page, 1040);
  },
  gate: async (page) => { await scrollTo(page, 120, 1000); await moveSel(page, 'button:has-text("Approve this evidence hash")'); await sleep(900); },
  payoff: async (page) => {
    await clickSel(page, 'button:has-text("Approve this evidence hash")');
    await sleep(9000); // backend builds index + re-explains
    await scrollTo(page, 120, 900);
    await scrollTo(page, 1640, 1200); // before/after explain-plan diff
    await sleep(1500);
  },
  memory_close: async (page) => {
    await scrollTo(page, 1180, 1200); // Sift Memory panel (voyage)
    await sleep(3500);
    await page.goto(`${BASE}/system-map`, { waitUntil: "networkidle" });
    await sleep(1200);
    await scrollTo(page, 200);
  },
};

const browser = await chromium.launch({ headless: true });
const ctx = await browser.newContext({ viewport: { width: W, height: H }, recordVideo: { dir: OUT, size: { width: W, height: H } }, deviceScaleFactor: 1 });
await ctx.addInitScript(CURSOR_INIT);
const page = await ctx.newPage();

const offsets = [];
const t0 = Date.now();
for (const s of scenes) {
  const start = (Date.now() - t0) / 1000;
  offsets.push({ id: s.id, start: +start.toFixed(2), dur: s.dur, audioDur: s.audioDur });
  console.log(`scene ${s.id} @ ${start.toFixed(1)}s (hold ${s.dur}s)`);
  const sceneStart = Date.now();
  try { await ACTIONS[s.id](page); } catch (e) { console.error(`  action error ${s.id}:`, e.message); }
  const remain = s.dur - (Date.now() - sceneStart) / 1000;
  if (remain > 0) await sleep(remain * 1000);
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
const cmd = `${FF} -y -i "${webm}" ${inputs} -filter_complex "${delays};${amix}" -map 0:v -map "[aout]" -t ${total.toFixed(2)} -c:v libx264 -pix_fmt yuv420p -preset medium -crf 21 -c:a aac -b:a 192k -movflags +faststart "${finalMp4}"`;
console.log("muxing -> sift-demo.mp4 ...");
execSync(cmd, { stdio: "inherit" });
console.log("DONE:", finalMp4);
