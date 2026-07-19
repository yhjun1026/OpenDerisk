/**
 * splitVisFences — 把 VIS markdown(planning_window 等)切分为有序段:
 * vis 围栏段(组件)与纯文本段。
 *
 * 这是"组件级局部渲染"的基础:每段有稳定 key(围栏段优先取 JSON body 里的
 * uid),React 按 key 做 mount/unmount/move 级别的 reconcile,配合 memo
 * 实现只有内容变化的组件才重渲染,替代整串 markdown 的全量 GPTVis 渲染。
 *
 * 围栏边界规则:闭合 ``` 必须位于行首。VIS 围栏 body 是单行 JSON
 * (内部换行被转义为 \n),JSON 字符串内联出现的 ``` 不会位于行首,
 * 因此不会误判。
 */

export interface VisSegment {
  kind: 'fence' | 'text';
  /** 稳定 key:fence 段为 uid(无 uid 时为 lang+序号),text 段为序号 */
  key: string;
  lang?: string;
  body: string;
}

const FENCE_START_RE = /^```([a-zA-Z0-9-]*)\s*$/;

/** 从围栏 body(单行 JSON)中提取 uid,失败返回 null */
function extractUid(body: string): string | null {
  // body 是单行 JSON,uid 通常在开头附近,用正则比 JSON.parse 便宜且容错(流式截断)
  const match = body.match(/"uid"\s*:\s*"([^"]+)"/);
  return match ? match[1] : null;
}

export function splitVisFences(markdown: string): VisSegment[] {
  const segments: VisSegment[] = [];
  if (!markdown) return segments;

  const lines = markdown.split('\n');
  let textBuf: string[] = [];
  let fenceLang: string | null = null;
  let fenceBuf: string[] = [];
  let fenceSeq = 0;
  let textSeq = 0;

  const flushText = () => {
    const body = textBuf.join('\n');
    textBuf = [];
    if (body.trim()) {
      segments.push({ kind: 'text', key: `t${textSeq++}`, body });
    }
  };
  const flushFence = () => {
    const body = fenceBuf.join('\n');
    fenceBuf = [];
    const uid = extractUid(body);
    segments.push({
      kind: 'fence',
      key: uid ?? `f${fenceSeq}-${fenceLang}`,
      lang: fenceLang ?? undefined,
      body,
    });
    fenceSeq++;
    fenceLang = null;
  };

  for (const line of lines) {
    if (fenceLang === null) {
      const start = line.match(FENCE_START_RE);
      if (start) {
        flushText();
        fenceLang = start[1];
        fenceBuf = [];
        continue;
      }
      textBuf.push(line);
    } else {
      // 闭合围栏:行首的 ```(允许尾随空白)
      if (/^```\s*$/.test(line)) {
        flushFence();
        continue;
      }
      fenceBuf.push(line);
    }
  }
  // 未闭合的流式围栏:按围栏段渲染(组件内部对截断 JSON 有容错/占位)
  if (fenceLang !== null) {
    flushFence();
  } else {
    flushText();
  }

  return segments;
}
