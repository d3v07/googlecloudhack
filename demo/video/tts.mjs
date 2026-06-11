import fs from "node:fs";
import path from "node:path";
import { execSync } from "node:child_process";

const ROOT = "/Users/dev/Documents/GCRAH";
const DIR = path.join(ROOT, "demo/video");
const AUDIO = path.join(DIR, "audio");
fs.mkdirSync(AUDIO, { recursive: true });

const env = {};
for (const line of fs.readFileSync(path.join(ROOT, ".env"), "utf8").split("\n")) {
  const m = line.match(/^([A-Z0-9_]+)=(.*)$/);
  if (m) env[m[1]] = m[2].replace(/^["']|["']$/g, "");
}
const KEY = env.ELEVENLABS_API_KEY;
const MODEL = env.ELEVENLABS_MODEL_ID || "eleven_multilingual_v2";
const RAW = { dev: env.DEMO_VOICE_DEV, aakash: env.DEMO_VOICE_AAKASH, dbre: env.DEMO_VOICE_DBRE };
if (!KEY || !RAW.dev || !RAW.aakash || !RAW.dbre) {
  console.error("missing ELEVENLABS_API_KEY or DEMO_VOICE_* in .env");
  process.exit(1);
}

// .env holds display names ("Liam - Energetic..."); resolve them to voice_ids.
const vres = await fetch("https://api.elevenlabs.io/v1/voices", { headers: { "xi-api-key": KEY } });
if (!vres.ok) {
  console.error("voices list failed:", vres.status, (await vres.text()).slice(0, 200));
  process.exit(1);
}
const lib = (await vres.json()).voices.map((v) => ({ id: v.voice_id, name: v.name }));
const resolve = (val) => {
  if (/^[A-Za-z0-9]{18,}$/.test(val)) return val; // already an id
  const base = val.split(/\s*[-–—]\s*/)[0].trim().toLowerCase();
  const hit =
    lib.find((v) => v.name.toLowerCase() === base) ||
    lib.find((v) => v.name.toLowerCase().startsWith(base)) ||
    lib.find((v) => base.startsWith(v.name.toLowerCase()));
  if (!hit) {
    console.error(`no voice matches "${val}". Available: ${lib.map((v) => v.name).join(", ")}`);
    process.exit(1);
  }
  return hit.id;
};
const VOICES = { dev: resolve(RAW.dev), aakash: resolve(RAW.aakash), dbre: resolve(RAW.dbre) };
console.log("resolved voices:", Object.fromEntries(Object.entries(RAW).map(([k, v]) => [k, v.split(/\s*-\s*/)[0]])));

const FF = "/opt/homebrew/bin/ffmpeg";
const FP = "/opt/homebrew/bin/ffprobe";
const dur = (f) =>
  parseFloat(execSync(`${FP} -v error -show_entries format=duration -of csv=p=0 "${f}"`).toString().trim());

const scenes = JSON.parse(fs.readFileSync(path.join(DIR, "scenes.json"), "utf8")).scenes;
const timed = [];

for (const s of scenes) {
  const res = await fetch(`https://api.elevenlabs.io/v1/text-to-speech/${VOICES[s.voice]}`, {
    method: "POST",
    headers: { "xi-api-key": KEY, "Content-Type": "application/json", Accept: "audio/mpeg" },
    body: JSON.stringify({
      text: s.text,
      model_id: MODEL,
      voice_settings: { stability: 0.5, similarity_boost: 0.8, style: 0.15, use_speaker_boost: true },
    }),
  });
  if (!res.ok) {
    console.error(`TTS FAIL ${s.id}: ${res.status} ${(await res.text()).slice(0, 300)}`);
    process.exit(1);
  }
  const raw = path.join(AUDIO, `${s.id}.mp3`);
  fs.writeFileSync(raw, Buffer.from(await res.arrayBuffer()));
  const a = dur(raw);
  const V = Math.max(a + 0.8, s.minDur);
  const wav = path.join(AUDIO, `${s.id}.wav`);
  execSync(`${FF} -y -i "${raw}" -af apad -t ${V.toFixed(2)} -ar 44100 -ac 2 "${wav}" 2>/dev/null`);
  timed.push({ id: s.id, voice: s.voice, dur: +V.toFixed(2), audioDur: +a.toFixed(2) });
  console.log(`  ${s.id.padEnd(13)} voice=${s.voice.padEnd(6)} tts=${a.toFixed(1)}s -> scene=${V.toFixed(1)}s`);
}

const list = path.join(AUDIO, "concat.txt");
fs.writeFileSync(list, timed.map((t) => `file '${path.join(AUDIO, t.id + ".wav")}'`).join("\n"));
execSync(`${FF} -y -f concat -safe 0 -i "${list}" -c copy "${path.join(DIR, "narration.wav")}" 2>/dev/null`);
fs.writeFileSync(
  path.join(DIR, "scenes.timed.json"),
  JSON.stringify({ scenes: timed, total: +timed.reduce((x, t) => x + t.dur, 0).toFixed(1) }, null, 2),
);
console.log("TOTAL:", timed.reduce((x, t) => x + t.dur, 0).toFixed(1), "s");
