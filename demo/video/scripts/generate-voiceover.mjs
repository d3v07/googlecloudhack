import { mkdir, writeFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import path from "node:path";

const apiKey = process.env.ELEVENLABS_API_KEY?.trim();
const modelId = process.env.ELEVENLABS_MODEL_ID?.trim() || "eleven_multilingual_v2";

const voiceRefs = {
  dbre: process.env.DEMO_VOICE_DBRE?.trim(),
  dev: process.env.DEMO_VOICE_DEV?.trim(),
  aakash: process.env.DEMO_VOICE_AAKASH?.trim(),
};

const scenes = [
  {
    id: "01-hook",
    role: "dbre",
    text:
      "Sift watches MongoDB workload, finds slow queries, recommends a safe index, waits for approval, and proves the fix.",
  },
  {
    id: "02-dev",
    role: "dev",
    text:
      "I am Dev Trivedi. I run a normal application query: buyers in Denver, age thirty to fifty, newest orders first. Sift runs it against the live collection, captures the explain plan, and attributes the workload to me.",
  },
  {
    id: "03-aakash",
    role: "aakash",
    text:
      "I am Aakash Singh. I run another real query from the same app surface. I do not need to understand indexes. The query is read-only, capped, measured, and added to the DBRE queue with my name attached.",
  },
  {
    id: "04-queue",
    role: "dbre",
    text:
      "Now I sign in as the DBRE. This queue is not fake telemetry. These are captured user workloads, ranked by evidence: blocking sort, collection scan, keys examined, and over-scan ratio. The product shows who caused the query and why it is worth reviewing.",
  },
  {
    id: "05-agents",
    role: "dbre",
    text:
      "When I diagnose a query, three read-only Agent Engine roles run: Diagnose, Candidate, and Rationale. They use four read-only tools: explain the slow query, compare candidate indexes, diagnose the candidate, and rationalize the recommendation. The agents explain. They do not mutate.",
  },
  {
    id: "06-safety-memory",
    role: "dbre",
    text:
      "Sift Memory adds retrieval context from runbook-style guidance, but it is only DBRE context. It never changes the EvidencePack, the approval hash, the winner, apply, or verification. The deterministic controller remains the authority for safety.",
  },
  {
    id: "07-approval",
    role: "dbre",
    text:
      "The recommendation is hash-bound. Before anything can change in MongoDB, I review the exact evidence hash and approve that specific pack. If the evidence changes, the approval no longer matches. The browser never gets database credentials.",
  },
  {
    id: "08-verify",
    role: "dbre",
    text:
      "After approval, only the backend applies the index and re-explains. Verified means sort is gone, the selected index is used, and metrics improve.",
  },
  {
    id: "09-dev-close",
    role: "dev",
    text: "My query got faster.",
  },
  {
    id: "10-aakash-close",
    role: "aakash",
    text: "And the DBRE can prove why.",
  },
  {
    id: "11-close",
    role: "dbre",
    text:
      "That is Sift: recommend, approve, verify.",
  },
];

function fail(message) {
  console.error(message);
  process.exit(1);
}

if (!apiKey) fail("ELEVENLABS_API_KEY is missing.");
for (const [role, ref] of Object.entries(voiceRefs)) {
  if (!ref) fail(`DEMO_VOICE_${role.toUpperCase()} is missing.`);
}

async function apiJson(pathname) {
  const response = await fetch(`https://api.elevenlabs.io/v1${pathname}`, {
    headers: { "xi-api-key": apiKey },
  });
  if (!response.ok) {
    fail(`ElevenLabs API failed at ${pathname}: ${response.status}`);
  }
  return response.json();
}

async function resolveVoices() {
  const data = await apiJson("/voices");
  const voices = data.voices ?? [];
  const byId = new Map(voices.map((voice) => [voice.voice_id, voice]));
  const byName = new Map(voices.map((voice) => [String(voice.name ?? "").toLowerCase(), voice]));
  const resolved = {};
  for (const [role, ref] of Object.entries(voiceRefs)) {
    const voice = byId.get(ref) ?? byName.get(ref.toLowerCase());
    if (!voice?.voice_id) fail(`Voice not found for ${role}.`);
    resolved[role] = voice.voice_id;
    console.log(`${role}: ${voice.name}`);
  }
  if (new Set(Object.values(resolved)).size !== 3) fail("Expected three distinct voices.");
  return resolved;
}

async function generate(scene, voiceId, outFile) {
  if (existsSync(outFile)) {
    console.log(`skip existing ${path.basename(outFile)}`);
    return;
  }
  const response = await fetch(`https://api.elevenlabs.io/v1/text-to-speech/${voiceId}`, {
    method: "POST",
    headers: {
      "xi-api-key": apiKey,
      "Content-Type": "application/json",
      Accept: "audio/mpeg",
    },
    body: JSON.stringify({
      text: scene.text,
      model_id: modelId,
      voice_settings: {
        stability: 0.52,
        similarity_boost: 0.78,
        style: scene.role === "dbre" ? 0.18 : 0.28,
        use_speaker_boost: true,
      },
    }),
  });
  if (!response.ok) {
    const detail = await response.text();
    fail(`TTS failed for ${scene.id}: ${response.status} ${detail.slice(0, 180)}`);
  }
  const audio = Buffer.from(await response.arrayBuffer());
  await writeFile(outFile, audio);
  console.log(`wrote ${path.basename(outFile)} (${audio.length} bytes)`);
}

const outDir = path.resolve("public/audio");
await mkdir(outDir, { recursive: true });
const voices = await resolveVoices();
for (const scene of scenes) {
  await generate(scene, voices[scene.role], path.join(outDir, `${scene.id}.mp3`));
}
