import { createHmac } from "node:crypto";
import { mkdirSync, renameSync, rmSync } from "node:fs";
import playwright from "playwright";

const { chromium } = playwright;

const DASHBOARD_URL = process.env.DEMO_DASHBOARD_URL || "http://127.0.0.1:3100";
const SESSION_SECRET = process.env.SESSION_SECRET;
const outDir = "public/recordings";

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
  rmSync(dest, { force: true });
  renameSync(source, dest);
  rmSync(tempDir, { recursive: true, force: true });
  console.log(`captured ${dest}`);
}

async function main() {
  const browser = await chromium.launch({ headless: true });
  const dev = { username: "dev.trivedi", displayName: "Dev Trivedi", role: "user" };
  const aakash = { username: "aakash.singh", displayName: "Aakash Singh", role: "user" };
  const dbre = { username: "dbre", displayName: "DBRE Operator", role: "dbre" };

  await recordClip(browser, "01-dev-workload", dev, async (page) => {
    await page.goto(`${DASHBOARD_URL}/console`, { waitUntil: "networkidle" });
    await closeTour(page);
    await wait(800);
    await page.getByRole("button", { name: /Denver buyers 30/i }).click();
    await page.getByText(/Captured to the DBRE slow-query queue/i).waitFor({ timeout: 25000 });
    await wait(2800);
  });

  await recordClip(browser, "02-aakash-workload", aakash, async (page) => {
    await page.goto(`${DASHBOARD_URL}/console`, { waitUntil: "networkidle" });
    await closeTour(page);
    await wait(800);
    await page.getByRole("button", { name: /Online orders 18/i }).click();
    await page.getByText(/Captured to the DBRE slow-query queue/i).waitFor({ timeout: 25000 });
    await wait(2600);
  });

  let runId = "";
  await recordClip(browser, "03-dbre-diagnose", dbre, async (page) => {
    await page.goto(`${DASHBOARD_URL}/dbre`, { waitUntil: "networkidle" });
    await closeTour(page);
    const diagnoseButton = page.locator("button").filter({ hasText: "Diagnose" }).first();
    await diagnoseButton.waitFor({ timeout: 20000 });
    await wait(1000);
    await diagnoseButton.click();
    await page.waitForURL(/\/runs\//, { timeout: 90000 });
    runId = new URL(page.url()).pathname.split("/").filter(Boolean).pop() ?? "";
    await page.getByText("3 read-only agent roles", { exact: true }).waitFor({ timeout: 25000 });
    await wait(3500);
  });

  await recordClip(browser, "04-run-review-system", dbre, async (page) => {
    await page.goto(`${DASHBOARD_URL}/runs/${encodeURIComponent(runId)}`, { waitUntil: "networkidle" });
    await closeTour(page);
    await page.getByText(/Approve this evidence hash/i).waitFor({ timeout: 20000 });
    await wait(2500);
    await page.mouse.wheel(0, 1500);
    await wait(2200);
    await page.mouse.wheel(0, 1900);
    await wait(2200);
    await page.goto(`${DASHBOARD_URL}/system-map`, { waitUntil: "networkidle" });
    await wait(3500);
  });

  await browser.close();
}

await main();
