import { getSession, getSessionToken } from "@/lib/auth";
import { WorkloadConsole } from "@/components/WorkloadConsole";

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

export default async function ConsolePage() {
  const session = await getSession();
  const presets = await loadPresets();
  return <WorkloadConsole displayName={session?.displayName ?? "you"} presets={presets} />;
}
