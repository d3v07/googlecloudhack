import { createHmac } from "node:crypto";
import { mkdirSync, readFileSync, renameSync, rmSync } from "node:fs";
import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";
import ffmpegPath from "ffmpeg-static";
import playwright from "playwright";

const { chromium } = playwright;
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, "../../..");

const DASHBOARD_URL = process.env.DEMO_DASHBOARD_URL || "http://127.0.0.1:3100";
const SESSION_SECRET = process.env.SESSION_SECRET || readEnvValue("SESSION_SECRET");
const outDir = "public/recordings";

function readEnvValue(name) {
  try {
    const env = readFileSync(path.join(repoRoot, ".env"), "utf8");
    for (const line of env.split(/\r?\n/)) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith("#") || !trimmed.startsWith(`${name}=`)) continue;
      return trimmed.slice(name.length + 1).replace(/^['"]|['"]$/g, "");
    }
  } catch {
    return "";
  }
  return "";
}

if (!SESSION_SECRET) {
  throw new Error("SESSION_SECRET is required to create local demo sessions.");
}

mkdirSync(outDir, { recursive: true });

function b64url(input) {
  return Buffer.from(input)
    .toString("base64")
    .replaceAll("+", "-")
    .replaceAll("/", "_")
    .replace(/=+$/g, "");
}

function sessionToken({ username, displayName, role }) {
  const now = Math.floor(Date.now() / 1000);
  const header = b64url(JSON.stringify({ alg: "HS256", typ: "JWT" }));
  const payload = b64url(
    JSON.stringify({
      sub: username,
      name: displayName,
      role,
      iat: now,
      exp: now + 6 * 3600,
    }),
  );
  const body = `${header}.${payload}`;
  const signature = createHmac("sha256", SESSION_SECRET).update(body).digest("base64url");
  return `${body}.${signature}`;
}

async function closeTour(page) {
  const close = page.getByRole("button", { name: /close tour/i });
  try {
    await close.click({ timeout: 2500 });
  } catch {
    // Tour was already dismissed.
  }
}

async function addSession(context, identity) {
  await context.addCookies([
    {
      name: "gcrah_session",
      value: sessionToken(identity),
      domain: "127.0.0.1",
      path: "/",
      httpOnly: true,
      sameSite: "Lax",
    },
  ]);
}

async function wait(ms) {
  await new Promise((resolve) => setTimeout(resolve, ms));
}

async function installCursor(page) {
  await page.evaluate(() => {
    if (document.getElementById("sift-demo-cursor")) return;
    const style = document.createElement("style");
    style.textContent = `
      #sift-demo-cursor {
        position: fixed;
        z-index: 2147483647;
        left: 28px;
        top: 28px;
        width: 28px;
        height: 28px;
        pointer-events: none;
        transform: translate(-4px, -4px);
        transition: left 260ms cubic-bezier(.16,1,.3,1), top 260ms cubic-bezier(.16,1,.3,1), transform 120ms ease;
        filter: drop-shadow(0 8px 18px rgba(0,0,0,.65));
      }
      #sift-demo-cursor svg {
        width: 100%;
        height: 100%;
      }
      .sift-demo-ripple {
        position: fixed;
        z-index: 2147483646;
        width: 14px;
        height: 14px;
        border: 3px solid rgba(94,201,232,.95);
        border-radius: 999px;
        pointer-events: none;
        transform: translate(-50%, -50%);
        animation: sift-demo-ripple 620ms ease-out forwards;
        box-shadow: 0 0 24px rgba(94,201,232,.85);
      }
      @keyframes sift-demo-ripple {
        from { opacity: 1; width: 14px; height: 14px; }
        to { opacity: 0; width: 76px; height: 76px; }
      }
    `;
    const cursor = document.createElement("div");
    cursor.id = "sift-demo-cursor";
    cursor.innerHTML = `
      <svg viewBox="0 0 32 32" fill="none" aria-hidden="true">
        <path d="M5 3L25 18.5L15.4 20.2L10.8 29L5 3Z" fill="#f8fbff" stroke="#06111a" stroke-width="2" stroke-linejoin="round"/>
        <path d="M15.4 20.2L20.7 28.6" stroke="#06111a" stroke-width="2" stroke-linecap="round"/>
      </svg>
    `;
    document.documentElement.append(style, cursor);
  });
}

async function moveCursor(page, x, y) {
  await installCursor(page);
  await page.evaluate(
    ({ x: nextX, y: nextY }) => {
      const cursor = document.getElementById("sift-demo-cursor");
      if (!cursor) return;
      cursor.style.left = `${nextX}px`;
      cursor.style.top = `${nextY}px`;
      cursor.style.transform = "translate(-4px, -4px)";
    },
    { x, y },
  );
  await page.mouse.move(x, y, { steps: 24 });
  await wait(320);
}

async function clickAt(page, x, y) {
  await moveCursor(page, x, y);
  await page.evaluate(
    ({ x: clickX, y: clickY }) => {
      const cursor = document.getElementById("sift-demo-cursor");
      if (cursor) {
        cursor.style.transform = "translate(-4px, -4px) scale(.82)";
        setTimeout(() => {
          cursor.style.transform = "translate(-4px, -4px)";
        }, 150);
      }
      const ripple = document.createElement("div");
      ripple.className = "sift-demo-ripple";
      ripple.style.left = `${clickX}px`;
      ripple.style.top = `${clickY}px`;
      document.documentElement.append(ripple);
      setTimeout(() => ripple.remove(), 680);
    },
    { x, y },
  );
  await page.mouse.click(x, y);
  await wait(520);
}

async function clickLocator(page, locator, offset = { x: 0.5, y: 0.5 }) {
  await locator.waitFor({ state: "visible", timeout: 25000 });
  await locator.scrollIntoViewIfNeeded();
  const box = await locator.boundingBox();
  if (!box) throw new Error("Cannot click locator without a visible bounding box.");
  await clickAt(page, box.x + box.width * offset.x, box.y + box.height * offset.y);
}

async function scrollWithCursor(page, y) {
  await moveCursor(page, 1490, 760);
  await page.mouse.wheel(0, y);
  await wait(900);
}

function convertWebmToMp4(webmPath, mp4Path) {
  rmSync(mp4Path, { force: true });
  const result = spawnSync(
    ffmpegPath,
    [
      "-y",
      "-i",
      webmPath,
      "-c:v",
      "libx264",
      "-preset",
      "veryfast",
      "-crf",
      "18",
      "-pix_fmt",
      "yuv420p",
      "-an",
      "-movflags",
      "+faststart",
      mp4Path,
    ],
    { stdio: "inherit" },
  );
  if (result.status !== 0) throw new Error(`ffmpeg conversion failed for ${webmPath}`);
}

async function recordClip(browser, name, identity, run) {
  const tempDir = `${outDir}/tmp-${name}`;
  rmSync(tempDir, { recursive: true, force: true });
  mkdirSync(tempDir, { recursive: true });
  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    deviceScaleFactor: 1,
    recordVideo: { dir: tempDir, size: { width: 1920, height: 1080 } },
  });
  await addSession(context, identity);
  const page = await context.newPage();
  await page.addInitScript(() => {
    localStorage.setItem("sift_tour_user", "seen");
    localStorage.setItem("sift_tour_dbre", "seen");
    localStorage.setItem("sift_tour_review", "seen");
  });
  const video = page.video();
  try {
    await run(page);
  } finally {
    await context.close();
  }
  const source = await video.path();
  const dest = `${outDir}/${name}.webm`;
  const mp4Dest = `${outDir}/${name}.mp4`;
  rmSync(dest, { force: true });
  renameSync(source, dest);
  rmSync(tempDir, { recursive: true, force: true });
  convertWebmToMp4(dest, mp4Dest);
  console.log(`captured ${dest}`);
}

async function main() {
  const browser = await chromium.launch({ headless: true });
  const dev = { username: "dev.trivedi", displayName: "Dev Trivedi", role: "user" };
  const aakash = { username: "aakash.singh", displayName: "Aakash Singh", role: "user" };
  const dbre = { username: "dbre", displayName: "DBRE Operator", role: "dbre" };

  await recordClip(browser, "01-dev-workload", dev, async (page) => {
    await page.goto(`${DASHBOARD_URL}/console`, { waitUntil: "networkidle" });
    await installCursor(page);
    await closeTour(page);
    await wait(800);
    await clickLocator(page, page.getByRole("button", { name: /Denver buyers 30/i }));
    await page.getByText(/Captured to the DBRE slow-query queue/i).waitFor({ timeout: 25000 });
    await wait(2800);
  });

  await recordClip(browser, "02-aakash-workload", aakash, async (page) => {
    await page.goto(`${DASHBOARD_URL}/console`, { waitUntil: "networkidle" });
    await installCursor(page);
    await closeTour(page);
    await wait(800);
    await clickLocator(page, page.getByRole("button", { name: /Online orders 18/i }));
    await page.getByText(/Captured to the DBRE slow-query queue/i).waitFor({ timeout: 25000 });
    await wait(2600);
  });

  let runId = "";
  await recordClip(browser, "03-dbre-diagnose", dbre, async (page) => {
    await page.goto(`${DASHBOARD_URL}/dbre`, { waitUntil: "networkidle" });
    await installCursor(page);
    await closeTour(page);
    const diagnoseButton = page.locator("button").filter({ hasText: "Diagnose" }).first();
    await diagnoseButton.waitFor({ timeout: 20000 });
    await wait(1000);
    await clickLocator(page, diagnoseButton);
    await page.waitForURL(/\/runs\//, { timeout: 90000 });
    runId = new URL(page.url()).pathname.split("/").filter(Boolean).pop() ?? "";
    await installCursor(page);
    await page.getByText(/Approve this evidence hash/i).waitFor({ timeout: 30000 });
    await wait(3500);
  });

  await recordClip(browser, "04-run-review-system", dbre, async (page) => {
    await page.goto(`${DASHBOARD_URL}/runs/${encodeURIComponent(runId)}`, { waitUntil: "networkidle" });
    await installCursor(page);
    await closeTour(page);
    await page.getByText(/Approve this evidence hash/i).waitFor({ timeout: 20000 });
    await moveCursor(page, 1280, 385);
    await wait(2500);
    await scrollWithCursor(page, 1500);
    await wait(2200);
    await scrollWithCursor(page, 1900);
    await wait(2200);
    await page.goto(`${DASHBOARD_URL}/system-map`, { waitUntil: "networkidle" });
    await installCursor(page);
    await moveCursor(page, 1140, 580);
    await wait(3500);
  });

  await browser.close();
}

await main();
