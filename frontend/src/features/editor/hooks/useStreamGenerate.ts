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
      onMeta?: (meta: { model: string; context_tokens: number }) => void,
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
          if (accumulated && completed && !hadError && !controller.signal.aborted) {
            await onComplete?.(accumulated);
          } else {
            onInterrupted?.();
            if (!hadError && !controller.signal.aborted) setStreamError("生成未完整结束，已保留原稿，请重试。");
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

      try {
        await consumeSseStream(
          `/api/stream/novels/${novelUid}/rewrite`,
          params,
          controller.signal,
          {
            onDelta: (delta) => {
              accumulated += delta;
            },
            onError: (err) => {
              setStreamError(err.message);
            },
          }
        );
        if (accumulated.trim()) {
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
        if (!hadError && !controller.signal.aborted && accumulated.trim()) {
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
