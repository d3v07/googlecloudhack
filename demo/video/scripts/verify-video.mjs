import { execFileSync } from "node:child_process";
import { existsSync, statSync } from "node:fs";

const files = [
  "public/audio/01-hook.mp3",
  "public/audio/02-dev.mp3",
  "public/audio/03-aakash.mp3",
  "public/audio/04-queue.mp3",
  "public/audio/05-agents.mp3",
  "public/audio/06-safety-memory.mp3",
  "public/audio/07-approval.mp3",
  "public/audio/08-verify.mp3",
  "public/audio/09-dev-close.mp3",
  "public/audio/10-aakash-close.mp3",
  "public/audio/11-close.mp3",
  "out/sift-demo-3min.mp4",
  "out/sift-demo-thumbnail.png",
];

for (const file of files) {
  if (!existsSync(file)) throw new Error(`${file} is missing`);
  const size = statSync(file).size;
  if (size <= 0) throw new Error(`${file} is empty`);
  console.log(`${file}: ${size} bytes`);
}

for (const file of files.filter((entry) => entry.endsWith(".mp3"))) {
  const afinfo = execFileSync("afinfo", [file], { encoding: "utf8" });
  const match = afinfo.match(/estimated duration: ([0-9.]+) sec/);
  if (!match || Number(match[1]) <= 0) {
    throw new Error(`${file} has no measurable audio duration`);
  }
}

const mdls = execFileSync("mdls", ["-raw", "-name", "kMDItemDurationSeconds", "out/sift-demo-3min.mp4"], {
  encoding: "utf8",
});
const duration = Number(mdls.trim());
if (!Number.isFinite(duration)) throw new Error("Could not parse video duration from mdls.");
console.log(`duration=${duration.toFixed(6)}s`);
if (Math.abs(duration - 180) > 1 / 30) {
  throw new Error(`Expected 180s within one frame, got ${duration}s`);
}
