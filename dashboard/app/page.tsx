import { AgentRunView } from "@/components/AgentRunView";
import { loadPack } from "@/lib/api";

// Server component: loads the initial pack (live read API → fallback to the
// bundled example), then hands off to the interactive client view, which can
// trigger a live agent run (#37) via the same-origin /api/run proxy.
export default async function AgentRunPage({
  searchParams,
}: {
  searchParams: Promise<{ run_id?: string }>;
}) {
  const { run_id } = await searchParams;
  const { pack, source, notice } = await loadPack(run_id);

  return <AgentRunView initialPack={pack} initialSource={source} initialNotice={notice} />;
}
