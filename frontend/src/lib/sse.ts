/** SSE stream reader bound to AbortController (Dev Doc Section 3.1.3 & 5.2). */

export interface SseMetaEvent {
  generation_id: number;
  model: string;
  context_tokens: number;
  /** 生成前衔接检查状态：ok 已生效 | skipped 无前文可衔接（正常） | failed 未生效 */
  boundary_status?: "ok" | "skipped" | "failed";
  /** boundary_status 为 failed 时给用户看的说明（“衔接检查未生效…”） */
  boundary_note?: string;
}

export interface SseDoneEvent {
  input_tokens: number;
  output_tokens: number;
  elapsed_ms: number;
}

export interface SseErrorEvent {
  code: string;
  message: string;
}

export interface StreamHandlers {
  onMeta?: (meta: SseMetaEvent) => void;
  onDelta: (deltaContent: string) => void;
  onDone?: (done: SseDoneEvent) => void;
  onError?: (err: SseErrorEvent) => void;
}

export async function consumeSseStream(
  url: string,
  body: unknown,
  signal: AbortSignal,
  handlers: StreamHandlers
): Promise<void> {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });

  if (!response.ok || !response.body) {
    const text = await response.text();
    handlers.onError?.({
      code: "STREAM_OPEN_ERROR",
      message: text || `无法建立流式连接 (${response.status})`,
    });
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  const dispatchBlock = (block: string) => {
    const lines = block.split("\n");
    let eventName = "message";
    let dataStr = "";

    for (const line of lines) {
      if (line.startsWith("event:")) {
        eventName = line.slice(6).trim();
      } else if (line.startsWith("data:")) {
        dataStr += line.slice(5).trim();
      }
    }

    if (!dataStr) return;
    try {
      const parsed: unknown = JSON.parse(dataStr);
      if (eventName === "meta") {
        handlers.onMeta?.(parsed as SseMetaEvent);
      } else if (eventName === "delta") {
        const content = (parsed as { content?: string }).content ?? "";
        if (content) handlers.onDelta(content);
      } else if (eventName === "done") {
        handlers.onDone?.(parsed as SseDoneEvent);
      } else if (eventName === "error") {
        handlers.onError?.(parsed as SseErrorEvent);
      }
    } catch {
      // Ignore malformed frame
    }
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() ?? "";
    for (const block of blocks) dispatchBlock(block);
  }

  // 流关闭后 buffer 里可能残留最后一帧（done/error 恰好是收尾帧时常见）。
  // 不 flush 的话 done 帧会被丢弃，前端永远收不到完成信号，误报“未完整结束”。
  buffer += decoder.decode();
  if (buffer.trim()) dispatchBlock(buffer);
}
