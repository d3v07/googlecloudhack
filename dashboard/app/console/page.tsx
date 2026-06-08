import { getSession, getSessionToken } from "@/lib/auth";
import { WorkloadConsole } from "@/components/WorkloadConsole";
import { Tour, type TourStep } from "@/components/Tour";

interface Preset {
  key: string;
  label: string;
  intent: string;
}

async function loadPresets(): Promise<Preset[]> {
  const base = (process.env.API_URL ?? process.env.NEXT_PUBLIC_API_URL)?.trim();
  const token = await getSessionToken();
  if (!base || !token) return [];
  try {
    const res = await fetch(`${base.replace(/\/+$/, "")}/workload/presets`, {
      headers: { authorization: `Bearer ${token}`, accept: "application/json" },
      cache: "no-store",
    });
    if (!res.ok) return [];
    return (await res.json()) as Preset[];
  } catch {
    return [];
  }
}

const USER_TOUR: TourStep[] = [
  {
    title: "Welcome to Sift",
    body: "This is your workload console. Run real, read-only queries against the live collection — Sift captures each one's explain evidence for the DBRE to triage.",
  },
  {
    title: "Quick workloads",
    body: "Click a preset to run a realistic query. An amber dot is a slow 'trap' shape; a green dot is healthy. Run a few to build up a workload.",
  },
  {
    title: "Or build your own",
    body: "Pick a store or method, an age range, a sort field and a limit, then Run query. Every query stays read-only and capped — you can't hurt the cluster.",
  },
  {
    title: "Read the verdict",
    body: "Each run shows the real plan: a blocking SORT, docs examined vs returned, and the stages — captured and attributed to you for the DBRE to fix.",
  },
];

export default async function ConsolePage() {
  const session = await getSession();
  const presets = await loadPresets();
  return (
    <>
      <WorkloadConsole displayName={session?.displayName ?? "you"} presets={presets} />
      <Tour id="user" title="Workload console" steps={USER_TOUR} />
    </>
  );
}
