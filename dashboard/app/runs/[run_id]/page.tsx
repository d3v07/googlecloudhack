import { AgentRunView } from "@/components/AgentRunView";
import { loadPack } from "@/lib/api";

export const dynamic = "force-dynamic";

// Run view (Layer 1) by path: /runs/<run_id>. The canonical deep single-run view.
// Awaits the route param, loads the initial pack (live read API → fallback to the
// bundled example), then hands off to the interactive client view. /run-review
// stays as a legacy query-param alias.
export default async function RunPage({
  params,
}: {
  params: Promise<{ run_id: string }>;
}) {
  const { run_id } = await params;
  const { pack, source, notice } = await loadPack(run_id);

  return <AgentRunView initialPack={pack} initialSource={source} initialNotice={notice} />;
}
