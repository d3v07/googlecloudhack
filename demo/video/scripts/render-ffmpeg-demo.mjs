import { spawnSync } from "node:child_process";
import fs from "node:fs";
import fsp from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import ffmpegPath from "ffmpeg-static";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(__dirname, "..");
const publicDir = path.join(root, "public");
const outDir = path.join(root, "out");
const segmentDir = path.join(outDir, "segments");
const textDir = path.join(outDir, "text");
const font = "/System/Library/Fonts/Supplemental/Arial.ttf";
const boldFont = "/System/Library/Fonts/Supplemental/Arial Bold.ttf";
const width = 1920;
const height = 1080;
const fps = 30;

const scenes = [
  {
    id: "hook",
    duration: 12,
    speaker: "DBRE Operator",
    title: "Sift: evidence-driven DBRE",
    media: "screens/system-map.png",
    audio: "audio/01-hook.mp3",
    accent: "5ec9e8",
    bullets: ["Real workload", "Hash-bound human approval", "Verification proves the fix"],
  },
  {
    id: "dev",
    duration: 19,
    speaker: "Dev Trivedi",
    title: "Dev runs a live workload",
    media: "recordings/01-dev-workload.mp4",
    mediaDuration: 7.92,
    audio: "audio/02-dev.mp3",
    accent: "5ec9e8",
    bullets: ["Clicks a workload preset", "Runs against live MongoDB", "Explain evidence is captured"],
  },
  {
    id: "aakash",
    duration: 19,
    speaker: "Aakash Singh",
    title: "Aakash creates another signal",
    media: "recordings/02-aakash-workload.mp4",
    mediaDuration: 7.6,
    audio: "audio/03-aakash.mp3",
    accent: "5ec9e8",
    bullets: ["Second user", "Read-only capped query", "Attribution preserved"],
  },
  {
    id: "queue",
    duration: 25,
    speaker: "DBRE Operator",
    title: "DBRE queue ranks evidence",
    media: "recordings/03-dbre-diagnose.mp4",
    mediaDuration: 10.68,
    audio: "audio/04-queue.mp3",
    accent: "f4b63d",
    bullets: ["Blocking SORT", "Over-scan ratio", "Caused by Dev / Aakash"],
  },
  {
    id: "agents",
    duration: 28,
    speaker: "DBRE Operator",
    title: "3 roles / 4 read-only tools",
    media: "recordings/04-run-review-system.mp4",
    mediaDuration: 18.04,
    audio: "audio/05-agents.mp3",
    accent: "31d489",
    bullets: ["Diagnose Agent", "Candidate Agent", "Rationale Agent", "Agents never mutate"],
  },
  {
    id: "memory",
    duration: 27,
    speaker: "DBRE Operator",
    title: "Sift Memory stays out-of-band",
    media: "recordings/04-run-review-system.mp4",
    mediaDuration: 18.04,
    audio: "audio/06-safety-memory.mp3",
    accent: "5ec9e8",
    bullets: ["Voyage retrieval context", "DBRE-only", "Never changes the EvidencePack"],
  },
  {
    id: "approval",
    duration: 27,
    speaker: "DBRE Operator",
    title: "Human approves the exact hash",
    media: "recordings/04-run-review-system.mp4",
    mediaDuration: 18.04,
    audio: "audio/07-approval.mp3",
    accent: "f4b63d",
    bullets: ["Approve this evidence hash", "Mutation blocked before approval", "Backend keeps credentials"],
  },
  {
    id: "verify",
    duration: 13,
    speaker: "DBRE Operator",
    title: "Backend applies, then re-explains",
    media: "recordings/04-run-review-system.mp4",
    mediaDuration: 18.04,
    audio: "audio/08-verify.mp3",
    accent: "31d489",
    bullets: ["SORT removed", "Selected index evidenced", "Metrics improve"],
  },
  {
    id: "close-dev",
    duration: 3,
    speaker: "Dev Trivedi",
    title: "My query got faster.",
    media: "screens/workload-console.png",
    audio: "audio/09-dev-close.mp3",
    accent: "5ec9e8",
    bullets: ["Real user impact"],
  },
  {
    id: "close-aakash",
    duration: 3,
    speaker: "Aakash Singh",
    title: "And the DBRE can prove why.",
    media: "screens/dbre-queue.png",
    audio: "audio/10-aakash-close.mp3",
    accent: "5ec9e8",
    bullets: ["Auditable evidence"],
  },
  {
    id: "close",
    duration: 4,
    speaker: "DBRE Operator",
    title: "Sift",
    media: "screens/system-map.png",
    audio: "audio/11-close.mp3",
    accent: "31d489",
    bullets: ["Agents recommend", "Deterministic code decides", "Humans approve", "Verification proves"],
  },
];

const run = (args, label) => {
  const result = spawnSync(ffmpegPath, args, { stdio: "inherit" });
  if (result.status !== 0) {
    throw new Error(`${label} failed with exit ${result.status}`);
  }
};

const textPath = async (sceneId, name, text) => {
  const file = path.join(textDir, `${sceneId}-${name}.txt`);
  await fsp.writeFile(file, text, "utf8");
  return file;
};

const drawText = ({ input, output, textFile, x, y, size, color = "ffffff", fontFile = font }) =>
  `[${input}]drawtext=fontfile=${fontFile}:textfile=${textFile}:x=${x}:y=${y}:fontsize=${size}:fontcolor=0x${color}:line_spacing=8:shadowcolor=0x000000@0.85:shadowx=2:shadowy=2[${output}]`;

const renderScene = async (scene, index) => {
  const mediaPath = path.join(publicDir, scene.media);
  const audioPath = path.join(publicDir, scene.audio);
  const output = path.join(segmentDir, `${String(index + 1).padStart(2, "0")}-${scene.id}.mp4`);
  const isVideo = scene.media.endsWith(".mp4");
  const titleFile = await textPath(scene.id, "title", scene.title);
  const speakerFile = await textPath(scene.id, "speaker", scene.speaker.toUpperCase());
  const bulletFiles = await Promise.all(scene.bullets.map((b, i) => textPath(scene.id, `bullet-${i}`, `- ${b}`)));
  const urlFile = await textPath(scene.id, "url", "gcrah-dashboard-2vbnam7yma-uc.a.run.app");

  const baseFilter = isVideo
    ? `[0:v]setpts=${scene.duration / scene.mediaDuration}*PTS,trim=duration=${scene.duration},fps=${fps},scale=${width}:${height}:force_original_aspect_ratio=increase,crop=${width}:${height},setsar=1[base]`
    : `[0:v]trim=duration=${scene.duration},fps=${fps},scale=${width}:${height}:force_original_aspect_ratio=increase,crop=${width}:${height},setsar=1[base]`;

  const panelX = isVideo ? 64 : 82;
  const panelY = isVideo ? 798 : 82;
  const panelW = isVideo ? 1160 : 740;
  const panelH = isVideo ? 242 : scene.title === "Sift" ? 560 : 420;
  const speakerX = panelX + 34;
  const speakerY = isVideo ? panelY + 28 : 116;
  const titleX = panelX + 34;
  const titleY = isVideo ? panelY + 66 : 162;
  const titleSize = isVideo ? 42 : scene.title === "Sift" ? 92 : 54;
  const bulletX = panelX + 40;
  const bulletStartY = isVideo ? panelY + 136 : scene.title === "Sift" ? 326 : 284;
  const bulletSpacing = isVideo ? 29 : scene.title === "Sift" ? 52 : 48;
  const bulletSize = isVideo ? 24 : 30;
  const filters = [
    baseFilter,
    `[base]drawbox=x=0:y=0:w=${width}:h=${height}:color=0x070a0f@${isVideo ? "0.12" : "0.38"}:t=fill[shade]`,
    `[shade]drawbox=x=${panelX}:y=${panelY}:w=${panelW}:h=${panelH}:color=0x0d121b@${isVideo ? "0.82" : "0.88"}:t=fill[panel]`,
    `[panel]drawbox=x=${panelX}:y=${panelY}:w=${panelW}:h=${panelH}:color=0x${scene.accent}@0.76:t=3[panelBorder]`,
    drawText({ input: "panelBorder", output: "speaker", textFile: speakerFile, x: speakerX, y: speakerY, size: isVideo ? 24 : 28, color: scene.accent, fontFile: boldFont }),
    drawText({ input: "speaker", output: "title", textFile: titleFile, x: titleX, y: titleY, size: titleSize, color: "ffffff", fontFile: boldFont }),
    ...bulletFiles.map((file, i) =>
      drawText({
        input: i === 0 ? "title" : `bullet${i - 1}`,
        output: `bullet${i}`,
        textFile: file,
        x: bulletX,
        y: bulletStartY + i * bulletSpacing,
        size: bulletSize,
        color: "d9e7f2",
      }),
    ),
    drawText({
      input: `bullet${bulletFiles.length - 1}`,
      output: "vout",
      textFile: urlFile,
      x: 1340,
      y: 1012,
      size: 23,
      color: "8fa7bd",
    }),
    `[1:a]apad,atrim=0:${scene.duration},asetpts=N/SR/TB[aout]`,
  ];

  const args = [
    "-y",
    ...(isVideo ? ["-stream_loop", "-1", "-i", mediaPath] : ["-loop", "1", "-framerate", String(fps), "-t", String(scene.duration), "-i", mediaPath]),
    "-i",
    audioPath,
    "-filter_complex",
    filters.join(";"),
    "-map",
    "[vout]",
    "-map",
    "[aout]",
    "-t",
    String(scene.duration),
    "-r",
    String(fps),
    "-c:v",
    "libx264",
    "-preset",
    "veryfast",
    "-crf",
    "20",
    "-pix_fmt",
    "yuv420p",
    "-c:a",
    "aac",
    "-ar",
    "44100",
    "-ac",
    "2",
    "-movflags",
    "+faststart",
    output,
  ];

  console.log(`Rendering scene ${index + 1}/${scenes.length}: ${scene.id}`);
  run(args, `render ${scene.id}`);
  return output;
};

await fsp.mkdir(segmentDir, { recursive: true });
await fsp.mkdir(textDir, { recursive: true });

const segmentFiles = [];
for (const [index, scene] of scenes.entries()) {
  segmentFiles.push(await renderScene(scene, index));
}

const concatFile = path.join(outDir, "concat.txt");
await fsp.writeFile(concatFile, segmentFiles.map((file) => `file '${file.replaceAll("'", "'\\''")}'`).join("\n"), "utf8");

const finalPath = path.join(outDir, "sift-demo-3min.mp4");
console.log("Concatenating final video");
run(["-y", "-f", "concat", "-safe", "0", "-i", concatFile, "-c", "copy", "-movflags", "+faststart", finalPath], "concat");

const thumbPath = path.join(outDir, "sift-demo-thumbnail.png");
console.log("Writing thumbnail");
run(["-y", "-ss", "178", "-i", finalPath, "-frames:v", "1", thumbPath], "thumbnail");

console.log(`Wrote ${finalPath}`);
