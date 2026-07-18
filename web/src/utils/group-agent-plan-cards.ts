/**
 * Collapse runs of consecutive same-tool `d-agent-plan` task fences in a
 * planning_window markdown string into a single `d-agent-plan-group` fence.
 *
 * This is a rendering-only transform applied AFTER VisParser's incremental
 * merge, on the final markdown string — the uid-based streaming merge
 * (incr/replace/delete) is untouched. Runs are re-derived on every render and
 * the group identity is stable via the first item's uid, so React state
 * (expanded/collapsed) survives as the group grows during streaming.
 *
 * A run is only formed when fences are:
 *   - adjacent (nothing but whitespace between them),
 *   - `item_type === 'task'` with the same `title` (tool name),
 *   - not explicitly parented to another plan item (`parent_uid` null),
 * and the run length reaches `minGroupSize`.
 * `layer_count` is intentionally NOT a condition: tool calls nested inside an
 * agent card's `markdown` carry layer_count > 0, and adjacent siblings at the
 * same level are exactly what should group.
 */

const FENCE_RE = /(```[a-zA-Z0-9-]*\n[\s\S]*?\n```)/g;
const AGENT_PLAN_FENCE_RE = /^```d-agent-plan\n([\s\S]*?)\n```$/;
const DEFAULT_MIN_GROUP_SIZE = 3;

interface PlanJson {
  uid?: string;
  item_type?: string;
  parent_uid?: string | null;
  title?: string;
  [key: string]: unknown;
}

interface PlanFence {
  title: string;
  raw: string;
  json: PlanJson;
}

function parseGroupablePlanFence(segment: string): PlanFence | null {
  const match = segment.match(AGENT_PLAN_FENCE_RE);
  if (!match) return null;
  let json: PlanJson;
  try {
    json = JSON.parse(match[1]);
  } catch {
    return null;
  }
  if (
    json.item_type !== 'task' ||
    json.parent_uid ||
    typeof json.title !== 'string' ||
    !json.title
  ) {
    return null;
  }
  return { title: json.title, raw: segment, json };
}

export function groupConsecutivePlanCards(
  markdown: string,
  minGroupSize: number = DEFAULT_MIN_GROUP_SIZE,
): string {
  if (!markdown.includes('```d-agent-plan')) return markdown;

  const segments = markdown.split(FENCE_RE);
  const out: string[] = [];
  let run: PlanFence[] = [];
  let pendingWhitespace = '';

  const flushRun = () => {
    if (run.length >= minGroupSize) {
      const payload = JSON.stringify({
        uid: `group-${run[0].json.uid ?? run[0].title}`,
        type: 'all',
        item_type: 'task_group',
        title: run[0].title,
        items: run.map((r) => r.json),
      });
      out.push('```d-agent-plan-group\n' + payload + '\n```');
    } else {
      for (const r of run) out.push(r.raw);
    }
    run = [];
  };

  for (const segment of segments) {
    if (!segment) continue;
    if (segment.trim() === '') {
      // Whitespace between fences — buffered; only emitted if the run breaks.
      pendingWhitespace += segment;
      continue;
    }
    const fence = parseGroupablePlanFence(segment);
    if (fence && run.length > 0 && run[0].title === fence.title) {
      // Run continues — whitespace between grouped fences is dropped.
      run.push(fence);
      pendingWhitespace = '';
    } else if (fence) {
      flushRun();
      out.push(pendingWhitespace);
      pendingWhitespace = '';
      run = [fence];
    } else {
      flushRun();
      out.push(pendingWhitespace, segment);
      pendingWhitespace = '';
    }
  }
  flushRun();
  out.push(pendingWhitespace);

  return out.join('');
}
