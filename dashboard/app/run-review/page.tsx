import { AgentRunView } from "@/components/AgentRunView";
import { loadPack } from "@/lib/api";

// Run Review (Layer 1): the deep single-run view — approval gate, before/after
// explain diff, trace, finding/recommendation. Loads the initial pack (live read
// API → fallback to the bundled example), then hands off to the interactive
// client view, which can trigger a live agent run (#37) via /api/run.
export default async function RunReviewPage({
  searchParams,
}: {
  searchParams: Promise<{ run_id?: string }>;
}) {
  const { run_id } = await searchParams;
  const { pack, source, notice } = await loadPack(run_id);

  return <AgentRunView initialPack={pack} initialSource={source} initialNotice={notice} />;
}
