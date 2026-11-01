/** Hook for SSE streaming generation & selection rewrite with AbortController (Dev Doc 3.1.3). */

import { useCallback, useEffect, useRef, useState } from "react";
import { consumeSseStream } from "@/lib/sse";
import type { RewriteActionType } from "../types";

interface StreamMetrics {
  model: string;
  contextTokens: number;
  outputTokens: number;
  elapsedMs: number;
}

/** 被截断时给用户看的说明（length=撞长度上限；content_filter=被安全策略过滤）。 */
function truncationMessage(reason: string, what: string, kept: string): string {
  return reason === "content_filter"
    ? `${what}内容被模型安全策略截断，结果不完整，${kept}。请调整要求后重试。`
    : `${what}因达到长度上限被截断，结果不完整，${kept}。请缩短范围或在模型设置里调高最大输出长度后重试。`;
}

export function useStreamGenerate(novelUid: string) {
  const abortRef = useRef<AbortController | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamError, setStreamError] = useState<string | null>(null);
  const [metrics, setMetrics] = useState<StreamMetrics | null>(null);

  const stopStream = useCallback(() => {
    if (abortRef.current) {
      abortRef.current.abort();
    }
    setIsStreaming(false);
  }, []);

  useEffect(() => {
    return () => {
      if (abortRef.current) {
        abortRef.current.abort();
      }
    };
  }, []);

  const startWriteStream = useCallback(
    async (
      params: {
        chapter_id: number;
        scene_id: number | null;
        mode: "scene" | "chapter";
        existing_content: string;
        disabled_context_keys: string[];
        custom_context: string;
        instruction: string;
      },
      onChunk: (delta: string) => void,
      onComplete?: (fullGenerated: string) => void,
      onMeta?: (meta: {
        model: string;
        context_tokens: number;
        boundary_status?: "ok" | "skipped" | "failed";
        boundary_note?: string;
      }) => void,
      onInterrupted?: () => void
    ) => {
      stopStream();
      const controller = new AbortController();
      abortRef.current = controller;
      setIsStreaming(true);
      setStreamError(null);
      let accumulated = "";
      let completed = false;
      let hadError = false;
      // T7：服务端告知输出被截断（length / content_filter）。这种“流正常结束但内容不完整”
      // 不能走成功路径，否则半截正文会被保存、审查，并作为上文喂给下一个场景。
      let truncatedReason: string | null = null;

      try {
        await consumeSseStream(
          `/api/stream/novels/${novelUid}/write`,
          params,
          controller.signal,
          {
            onMeta: (meta) => {
              setMetrics({
                model: meta.model,
                contextTokens: meta.context_tokens,
                outputTokens: 0,
                elapsedMs: 0,
              });
              onMeta?.(meta);
            },
            onDelta: (delta) => {
              if (controller.signal.aborted) return;
              accumulated += delta;
              onChunk(delta);
            },
            onDone: (done) => {
              completed = true;
              if (done.truncated) truncatedReason = done.finish_reason ?? "length";
              setMetrics((prev) => ({
                model: prev?.model ?? "",
                contextTokens: done.input_tokens,
                outputTokens: done.output_tokens,
                elapsedMs: done.elapsed_ms,
              }));
            },
            onError: (err) => {
              hadError = true;
              setStreamError(err.message);
            },
          }
        );
      } catch (err) {
        hadError = true;
        if ((err as Error)?.name !== "AbortError") {
          setStreamError(err instanceof Error ? err.message : "流式生成中断");
        }
      } finally {
        if (abortRef.current === controller) {
          if (accumulated && completed && !hadError && !controller.signal.aborted && !truncatedReason) {
            await onComplete?.(accumulated);
          } else {
            onInterrupted?.();
            if (!hadError && !controller.signal.aborted) {
              setStreamError(
                truncatedReason
                  ? truncationMessage(truncatedReason, "生成", "已保留原稿")
                  : "生成未完整结束，已保留原稿，请重试。"
              );
            }
          }
          if (abortRef.current === controller) {
            setIsStreaming(false);
            abortRef.current = null;
          }
        }
      }
    },
    [novelUid, stopStream]
  );

  const startRewriteStream = useCallback(
    async (
      params: {
        chapter_id: number;
        selected_text: string;
        action_type: RewriteActionType;
        target_character_id?: number | null;
        instruction?: string;
      },
      onResult: (rewrittenText: string) => void
    ) => {
      stopStream();
      const controller = new AbortController();
      abortRef.current = controller;
      setIsStreaming(true);
      setStreamError(null);
      let accumulated = "";
      let truncatedReason: string | null = null;

      try {
        await consumeSseStream(
          `/api/stream/novels/${novelUid}/rewrite`,
          params,
          controller.signal,
          {
            onDelta: (delta) => {
              accumulated += delta;
            },
            onDone: (done) => {
              if (done.truncated) truncatedReason = done.finish_reason ?? "length";
            },
            onError: (err) => {
              setStreamError(err.message);
            },
          }
        );
        // 改写结果会替换选区并自动保存新版本：被截断的半截文本绝不能走这条路径。
        if (truncatedReason) {
          setStreamError(truncationMessage(truncatedReason, "改写", "原文未被替换"));
        } else if (accumulated.trim()) {
          onResult(accumulated.trim());
        }
      } catch (err) {
        if ((err as Error)?.name !== "AbortError") {
          setStreamError(err instanceof Error ? err.message : "改写中断");
        }
      } finally {
        setIsStreaming(false);
        abortRef.current = null;
      }
    },
    [novelUid, stopStream]
  );

  const startSupplementStream = useCallback(
    async (
      params: {
        chapter_id: number;
        content: string;
        insertion_index: number;
        instruction: string;
        disabled_context_keys: string[];
      },
      onChunk: (delta: string) => void,
      onComplete: (candidate: string) => void
    ) => {
      stopStream();
      const controller = new AbortController();
      abortRef.current = controller;
      setIsStreaming(true);
      setStreamError(null);
      let accumulated = "";
      let hadError = false;
      let truncatedReason: string | null = null;

      try {
        await consumeSseStream(
          `/api/stream/novels/${novelUid}/supplement`,
          params,
          controller.signal,
          {
            onMeta: (meta) => {
              setMetrics({
                model: meta.model,
                contextTokens: meta.context_tokens,
                outputTokens: 0,
                elapsedMs: 0,
              });
            },
            onDelta: (delta) => {
              accumulated += delta;
              onChunk(delta);
            },
            onDone: (done) => {
              if (done.truncated) truncatedReason = done.finish_reason ?? "length";
              setMetrics((prev) => ({
                model: prev?.model ?? "",
                contextTokens: done.input_tokens,
                outputTokens: done.output_tokens,
                elapsedMs: done.elapsed_ms,
              }));
            },
            onError: (err) => {
              hadError = true;
              setStreamError(err.message);
            },
          }
        );
      } catch (err) {
        if ((err as Error)?.name !== "AbortError") {
          hadError = true;
          setStreamError(err instanceof Error ? err.message : "补充内容生成中断");
        }
      } finally {
        setIsStreaming(false);
        abortRef.current = null;
        if (truncatedReason && !hadError && !controller.signal.aborted) {
          // 补充内容是需要用户确认的候选；被截断的候选不当作“生成完成”呈现。
          setStreamError(truncationMessage(truncatedReason, "补充", "候选未被采用"));
        } else if (!hadError && !controller.signal.aborted && accumulated.trim()) {
          onComplete(accumulated.trim());
        }
      }
    },
    [novelUid, stopStream]
  );

  return {
    isStreaming,
    streamError,
    metrics,
    stopStream,
    startWriteStream,
    startRewriteStream,
    startSupplementStream,
  };
}
