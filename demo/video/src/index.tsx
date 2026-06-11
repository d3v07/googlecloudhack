import React from "react";
import { Audio } from "@remotion/media";
import {
  AbsoluteFill,
  Composition,
  Easing,
  Img,
  Sequence,
  Video,
  interpolate,
  registerRoot,
  staticFile,
  useCurrentFrame,
} from "remotion";

const FPS = 30;
const WIDTH = 1920;
const HEIGHT = 1080;
const DURATION = 5400;

type Scene = {
  id: string;
  from: number;
  duration: number;
  title: string;
  speaker: "DBRE Operator" | "Dev Trivedi" | "Aakash Singh";
  audio: string;
  screen?: string;
  mediaDuration?: number;
  focus?: "left" | "center" | "right" | "top" | "middle" | "bottom";
  bullets: string[];
  accent: "cyan" | "yellow" | "green";
};

const scenes: Scene[] = [
  {
    id: "hook",
    from: 0,
    duration: 360,
    title: "Sift: evidence-driven DBRE",
    speaker: "DBRE Operator",
    audio: "audio/01-hook.mp3",
    screen: "screens/system-map.png",
    focus: "top",
    accent: "cyan",
    bullets: ["Real workload", "Hash-bound human approval", "Verification proves the fix"],
  },
  {
    id: "dev",
    from: 360,
    duration: 570,
    title: "Dev runs a live workload",
    speaker: "Dev Trivedi",
    audio: "audio/02-dev.mp3",
    screen: "recordings/01-dev-workload.mp4",
    mediaDuration: 7.56,
    focus: "center",
    accent: "cyan",
    bullets: ["Guided query builder", "Read-only execution", "Explain evidence captured"],
  },
  {
    id: "aakash",
    from: 930,
    duration: 570,
    title: "Aakash creates another signal",
    speaker: "Aakash Singh",
    audio: "audio/03-aakash.mp3",
    screen: "recordings/02-aakash-workload.mp4",
    mediaDuration: 7.32,
    focus: "right",
    accent: "cyan",
    bullets: ["Second user", "Same live collection", "Attribution preserved"],
  },
  {
    id: "queue",
    from: 1500,
    duration: 750,
    title: "DBRE queue ranks evidence",
    speaker: "DBRE Operator",
    audio: "audio/04-queue.mp3",
    screen: "recordings/03-dbre-diagnose.mp4",
    mediaDuration: 29,
    focus: "center",
    accent: "yellow",
    bullets: ["Blocking SORT", "Over-scan ratio", "Caused by Dev / Aakash"],
  },
  {
    id: "agents",
    from: 2250,
    duration: 840,
    title: "3 roles / 4 read-only tools",
    speaker: "DBRE Operator",
    audio: "audio/05-agents.mp3",
    screen: "recordings/04-run-review-system.mp4",
    mediaDuration: 14.44,
    focus: "top",
    accent: "green",
    bullets: ["Diagnose Agent", "Candidate Agent", "Rationale Agent", "No agent mutation authority"],
  },
  {
    id: "memory",
    from: 3090,
    duration: 810,
    title: "Sift Memory stays out-of-band",
    speaker: "DBRE Operator",
    audio: "audio/06-safety-memory.mp3",
    screen: "recordings/04-run-review-system.mp4",
    mediaDuration: 14.44,
    focus: "middle",
    accent: "cyan",
    bullets: ["Voyage retrieval context", "DBRE-only", "Never changes the EvidencePack"],
  },
  {
    id: "approval",
    from: 3900,
    duration: 810,
    title: "Human approves the exact hash",
    speaker: "DBRE Operator",
    audio: "audio/07-approval.mp3",
    screen: "recordings/04-run-review-system.mp4",
    mediaDuration: 14.44,
    focus: "top",
    accent: "yellow",
    bullets: ["Approve this evidence hash", "Mutation blocked before approval", "Backend keeps credentials"],
  },
  {
    id: "verify",
    from: 4710,
    duration: 390,
    title: "Backend applies, then re-explains",
    speaker: "DBRE Operator",
    audio: "audio/08-verify.mp3",
    screen: "recordings/04-run-review-system.mp4",
    mediaDuration: 14.44,
    focus: "bottom",
    accent: "green",
    bullets: ["SORT removed", "Selected index evidenced", "Metrics improve"],
  },
  {
    id: "close-dev",
    from: 5100,
    duration: 90,
    title: "My query got faster.",
    speaker: "Dev Trivedi",
    audio: "audio/09-dev-close.mp3",
    accent: "cyan",
    bullets: ["Real user impact"],
  },
  {
    id: "close-aakash",
    from: 5190,
    duration: 90,
    title: "And the DBRE can prove why.",
    speaker: "Aakash Singh",
    audio: "audio/10-aakash-close.mp3",
    accent: "cyan",
    bullets: ["Auditable evidence"],
  },
  {
    id: "close",
    from: 5280,
    duration: 120,
    title: "Sift",
    speaker: "DBRE Operator",
    audio: "audio/11-close.mp3",
    screen: "screens/system-map.png",
    focus: "top",
    accent: "green",
    bullets: ["Agents recommend", "Deterministic code decides", "Humans approve", "Verification proves"],
  },
];

const accent = {
  cyan: "#5ec9e8",
  yellow: "#f4b63d",
  green: "#31d489",
};

function fitImage(focus?: Scene["focus"]) {
  const y =
    focus === "bottom"
      ? "-52%"
      : focus === "middle"
        ? "-34%"
        : focus === "top"
          ? "0%"
          : "-8%";
  const x = focus === "right" ? "-7%" : focus === "left" ? "7%" : "0%";
  return { x, y };
}

function BackgroundGrid() {
  return (
    <AbsoluteFill
      style={{
        background:
          "linear-gradient(90deg, rgba(92,201,232,.055) 1px, transparent 1px), linear-gradient(rgba(92,201,232,.055) 1px, transparent 1px), radial-gradient(circle at 70% 15%, rgba(92,201,232,.12), transparent 34%), #070a0f",
        backgroundSize: "72px 72px, 72px 72px, 100% 100%",
      }}
    />
  );
}

function LogoMark() {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 18 }}>
      <Img src={staticFile("logo.svg")} style={{ width: 58 }} />
      <div style={{ fontSize: 58, fontWeight: 800, letterSpacing: 0 }}>Sift</div>
    </div>
  );
}

function ScreenMedia({ scene }: { scene: Scene }) {
  const frame = useCurrentFrame() - scene.from;
  if (!scene.screen) return null;
  const p = interpolate(frame, [0, scene.duration], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });
  const pos = fitImage(scene.focus);
  const isVideo = scene.screen.endsWith(".mp4");
  const scale = scene.id === "hook" || scene.id === "close" ? 0.72 : isVideo ? 1 : 0.86 + p * 0.035;
  const videoRate = scene.mediaDuration
    ? Math.min(1, scene.mediaDuration / (scene.duration / FPS))
    : 1;
  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        opacity: scene.id === "hook" || scene.id === "close" ? 0.22 : 0.94,
        filter: scene.id === "hook" || scene.id === "close" ? "blur(2px)" : "none",
        transform: `translate(${pos.x}, ${pos.y}) scale(${scale})`,
        transformOrigin: "top center",
      }}
    >
      {isVideo ? (
        <Video
          src={staticFile(scene.screen)}
          muted
          playbackRate={videoRate}
          style={{
            width: "100%",
            height: "100%",
            objectFit: "cover",
            borderRadius: 0,
          }}
        />
      ) : (
        <Img
          src={staticFile(scene.screen)}
          style={{
            width: "100%",
            height: "auto",
            borderRadius: 24,
            border: "1px solid rgba(140,160,190,.24)",
            boxShadow: "0 50px 120px rgba(0,0,0,.45)",
          }}
        />
      )}
    </div>
  );
}

function SceneOverlay({ scene }: { scene: Scene }) {
  const frame = useCurrentFrame() - scene.from;
  const enter = interpolate(frame, [0, 28], [0.94, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });
  const color = accent[scene.accent];
  const hero = scene.id === "hook" || scene.id === "close";
  return (
    <div
      style={{
        position: "absolute",
        left: hero ? 130 : 104,
        top: hero ? 150 : 90,
        width: hero ? 920 : 670,
        opacity: enter,
        transform: `translateY(${(1 - enter) * 28}px)`,
      }}
    >
      {hero ? <LogoMark /> : null}
      <div
        style={{
          marginTop: hero ? 42 : 0,
          color,
          fontSize: 24,
          textTransform: "uppercase",
          letterSpacing: 2.4,
          fontWeight: 700,
        }}
      >
        {scene.speaker}
      </div>
      <h1
        style={{
          margin: "16px 0 24px",
          color: "white",
          fontSize: hero ? 72 : 52,
          lineHeight: 1.04,
          letterSpacing: 0,
        }}
      >
        {scene.title}
      </h1>
      <div
        style={{
          display: "grid",
          gap: 12,
          padding: 24,
          borderRadius: 22,
          background: "rgba(13,18,27,.88)",
          border: `1px solid ${color}55`,
          boxShadow: "0 24px 80px rgba(0,0,0,.36)",
        }}
      >
        {scene.bullets.map((bullet) => (
          <div
            key={bullet}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 14,
              color: "#d9e7f2",
              fontSize: 28,
              lineHeight: 1.18,
            }}
          >
            <span
              style={{
                display: "block",
                width: 12,
                height: 12,
                borderRadius: 999,
                background: color,
                boxShadow: `0 0 20px ${color}`,
                flex: "0 0 auto",
              }}
            />
            <span>{bullet}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function TimelineBar() {
  const frame = useCurrentFrame();
  const progress = frame / DURATION;
  return (
    <div
      style={{
        position: "absolute",
        left: 82,
        right: 82,
        bottom: 58,
        height: 8,
        borderRadius: 999,
        background: "rgba(120,140,170,.2)",
        overflow: "hidden",
      }}
    >
      <div
        style={{
          width: `${progress * 100}%`,
          height: "100%",
          background: "linear-gradient(90deg, #5ec9e8, #f4b63d, #31d489)",
        }}
      />
    </div>
  );
}

function SceneAudio({ scene }: { scene: Scene }) {
  return (
    <Sequence from={scene.from} durationInFrames={scene.duration}>
      <Audio src={staticFile(scene.audio)} volume={0.96} />
    </Sequence>
  );
}

function SceneLayer({ scene }: { scene: Scene }) {
  return (
    <Sequence from={scene.from} durationInFrames={scene.duration}>
      <AbsoluteFill style={{ overflow: "hidden" }}>
        <ScreenMedia scene={scene} />
        <div
          style={{
            position: "absolute",
            inset: 0,
            background:
              scene.id === "hook" || scene.id === "close"
                ? "linear-gradient(90deg, rgba(7,10,15,.98), rgba(7,10,15,.58), rgba(7,10,15,.72))"
                : "linear-gradient(90deg, rgba(7,10,15,.86), rgba(7,10,15,.18), rgba(7,10,15,.46))",
          }}
        />
        <SceneOverlay scene={scene} />
      </AbsoluteFill>
    </Sequence>
  );
}

function DemoVideo() {
  return (
    <AbsoluteFill style={{ fontFamily: "Arial, Helvetica, sans-serif", color: "white" }}>
      <BackgroundGrid />
      {scenes.map((scene) => (
        <React.Fragment key={scene.id}>
          <SceneLayer scene={scene} />
          <SceneAudio scene={scene} />
        </React.Fragment>
      ))}
      <TimelineBar />
      <div
        style={{
          position: "absolute",
          right: 82,
          bottom: 82,
          color: "#8fa7bd",
          fontSize: 22,
        }}
      >
        gcrah-dashboard-2vbnam7yma-uc.a.run.app
      </div>
    </AbsoluteFill>
  );
}

function RemotionRoot() {
  return (
    <Composition
      id="SiftDemo"
      component={DemoVideo}
      durationInFrames={DURATION}
      fps={FPS}
      width={WIDTH}
      height={HEIGHT}
    />
  );
}

registerRoot(RemotionRoot);
