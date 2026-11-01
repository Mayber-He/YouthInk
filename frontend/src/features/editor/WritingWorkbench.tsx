import React, { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/common/EmptyState";
import { useOutlineTree } from "@/features/outline/api";
import { useCharacters, useLocations } from "@/features/settings-entity/api";
import { MemoryChapterPanel } from "@/features/memory/MemoryChapterPanel";
import { ConsistencyReviewModal } from "@/features/memory/ConsistencyReviewModal";
import { useApplyReviewRevision, useRunConsistencyReview } from "@/features/memory/api";
import type { ConsistencyReviewResponse } from "@/features/memory/types";
import { useUiStore } from "@/stores/uiStore";
import {
  useAiSmellScan,
  useChapterWorkspace,
  useCheckSceneRepetition,
  useContextPreview,
  useGenerateScenes,
  useRestoreChapterVersion,
  useSaveChapterContent,
  useCritiqueSelection,
} from "./api";
import { useStreamGenerate } from "./hooks/useStreamGenerate";
import { SceneBeatsPanel } from "./components/SceneBeatsPanel";
import { ContextPreviewPanel } from "./components/ContextPreviewPanel";
import { VersionHistoryModal } from "./components/VersionHistoryModal";
import { SelectionToolbar } from "./components/SelectionToolbar";
import { WritingHeaderBar } from "./components/WritingHeaderBar";
import { WritingPipelineBar, type WritingPipelineStep } from "./components/WritingPipelineBar";
import { ConfirmModal } from "@/components/ui/ConfirmModal";
import type { AiSmellHit, RewriteActionType, SceneItem, SelectionCritiqueResult } from "./types";

export const WritingWorkbench: React.FC<{ novelUid: string }> = ({ novelUid }) => {
  const {
    selectedChapterId,
    setSelectedChapterId,
    setActiveSection,
    focusMode,
    rightPanelOpen,
  } = useUiStore();

  const { data: outline } = useOutlineTree(novelUid);
  const { data: characters = [] } = useCharacters(novelUid);
  const { data: locations = [] } = useLocations(novelUid);

  const allChapters =
    outline?.volumes.flatMap((v) => v.arcs.flatMap((a) => a.chapters)) ?? [];
  const effectiveChapterId = selectedChapterId ?? allChapters[0]?.id ?? null;
  const currentChapterRef = useRef(effectiveChapterId);
  currentChapterRef.current = effectiveChapterId;

  const { data: workspace, isLoading } = useChapterWorkspace(novelUid, effectiveChapterId);
  const saveMut = useSaveChapterContent(novelUid, effectiveChapterId ?? 0);
  const generateScenesMut = useGenerateScenes(novelUid, effectiveChapterId ?? 0);
  const repetitionMut = useCheckSceneRepetition(novelUid, effectiveChapterId ?? 0);
  const restoreMut = useRestoreChapterVersion(novelUid, effectiveChapterId ?? 0);
  const smellMut = useAiSmellScan(novelUid, effectiveChapterId);

  const [activeSceneId, setActiveSceneId] = useState<number | null>(null);
  const [disabledContextKeys, setDisabledContextKeys] = useState<string[]>([]);
  const [customContext, setCustomContext] = useState("");
  const [rightTab, setRightTab] = useState<"beats" | "context" | "memory">("beats");
  const [historyOpen, setHistoryOpen] = useState(false);
  const [content, setContent] = useState("");
  const [autoSavedAt, setAutoSavedAt] = useState<string | null>(null);
  const [selectionRange, setSelectionRange] = useState({ start: 0, end: 0, text: "" });
  const [smellHits, setSmellHits] = useState<AiSmellHit[]>([]);
  const [hasScannedSmell, setHasScannedSmell] = useState(false);
  const [smellError, setSmellError] = useState<string | null>(null);
  const [reviewOpen, setReviewOpen] = useState(false);
  const [reviewResult, setReviewResult] = useState<ConsistencyReviewResponse | null>(null);
  const [reviewError, setReviewError] = useState<string | null>(null);
  const [confirmOverwriteOpen, setConfirmOverwriteOpen] = useState(false);
  const [supplementOpen, setSupplementOpen] = useState(false);
  const [supplementInstruction, setSupplementInstruction] = useState("");
  const [supplementCandidate, setSupplementCandidate] = useState("");
  const [supplementBaseContent, setSupplementBaseContent] = useState<string | null>(null);
  const [supplementInsertAt, setSupplementInsertAt] = useState<number | null>(null);
  const [supplementReady, setSupplementReady] = useState(false);
  const [supplementSaveError, setSupplementSaveError] = useState<string | null>(null);
  const [critiqueResult, setCritiqueResult] = useState<SelectionCritiqueResult | null>(null);
  const [pipelineStep, setPipelineStep] = useState<WritingPipelineStep>("idle");
  const [streamModelName, setStreamModelName] = useState("");
  const [repetitionNotice, setRepetitionNotice] = useState<{
    tone: "info" | "warn";
    text: string;
    details: string[];
  } | null>(null);
  const contentRef = useRef(content);
  contentRef.current = content;

  useEffect(() => {
    setSmellHits([]);
    setHasScannedSmell(false);
    setSmellError(null);
  }, [content]);
  const [generatedWordsCount, setGeneratedWordsCount] = useState(0);
  const critiqueMut = useCritiqueSelection(novelUid, effectiveChapterId ?? 0);
  const reviewMut = useRunConsistencyReview(novelUid, effectiveChapterId ?? 0);
  const revisionMut = useApplyReviewRevision(novelUid, effectiveChapterId ?? 0);
  const prevChapterIdRef = useRef<number | null>(effectiveChapterId);
  const isComposingRef = useRef(false);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  const { data: contextPreview, isLoading: isCtxLoading } = useContextPreview(
    novelUid,
    effectiveChapterId,
    activeSceneId,
    disabledContextKeys
  );

  const {
    isStreaming,
    streamError,
    metrics,
    stopStream,
    startWriteStream,
    startRewriteStream,
    startSupplementStream,
  } = useStreamGenerate(novelUid);

  useEffect(() => { stopStream(); }, [effectiveChapterId, stopStream]);

  useEffect(() => {
    if (workspace) {
      setContent(workspace.latest_content);
      setHasScannedSmell(false);
      setSmellHits([]);
      if (prevChapterIdRef.current !== workspace.chapter.id) {
        setPipelineStep("idle");
        setReviewResult(null);
        setReviewError(null);
        setSelectionRange({ start: 0, end: 0, text: "" });
        setSupplementOpen(false);
        setSupplementCandidate("");
        setSupplementReady(false);
        prevChapterIdRef.current = workspace.chapter.id;
      }
      if (!activeSceneId && workspace.scenes.length > 0) {
        setActiveSceneId(workspace.scenes[0].id);
      }
    }
  }, [workspace?.chapter.id, workspace?.latest_version]);

  useEffect(() => {
    if (streamError) {
      setPipelineStep("idle");
    }
  }, [streamError]);

  const triggerAutoSave = (nextText: string) => {
    if (!effectiveChapterId || isComposingRef.current || isStreaming) return;
    saveMut.mutate(
      { content: nextText, source: "manual", create_new_version: false },
      { onSuccess: () => setAutoSavedAt(new Date().toLocaleTimeString([], { hour12: false })) }
    );
  };

  const runAutoReview = async () => {
    setPipelineStep("reviewing");
    setReviewError(null);
    try {
      const res = await reviewMut.mutateAsync();
      if (currentChapterRef.current !== effectiveChapterId) return;
      setReviewResult(res);
      setPipelineStep("completed");
    } catch (e) {
      if (currentChapterRef.current !== effectiveChapterId) return;
      setReviewError(e instanceof Error ? e.message : "自动审查失败");
      setPipelineStep("completed");
    }
  };

  // 流式生成单个场景（或整章兜底）；基于 baseContent 续写，resolve 生成的正文，中断/失败 resolve null。
  // 不在此处保存或审查，交由调用方在整段完成后统一处理。
  const runSceneStream = (
    mode: "scene" | "chapter",
    sceneId: number | null,
    baseContent: string
  ): Promise<string | null> =>
    new Promise((resolve) => {
      if (!effectiveChapterId) {
        resolve(null);
        return;
      }
      const prefix = baseContent.trim() ? `${baseContent.trim()}\n\n` : "";
      let generated = "";
      startWriteStream(
        {
          chapter_id: effectiveChapterId,
          scene_id: sceneId,
          mode,
          existing_content: baseContent,
          disabled_context_keys: disabledContextKeys,
          custom_context: customContext,
          instruction: "",
        },
        (delta) => {
          if (currentChapterRef.current !== effectiveChapterId) return;
          setPipelineStep((prev) => (prev === "generating" ? prev : "generating"));
          setGeneratedWordsCount((c) => c + delta.replace(/\s+/g, "").length);
          generated += delta;
          setContent(prefix + generated);
        },
        async (fullGenerated) => {
          if (currentChapterRef.current !== effectiveChapterId) {
            resolve(null);
            return;
          }
          // T5：整个场景流完成后做一次确定性重复检测。超阈值时后端只重写该场景一次；
          // 检测接口本身出错则放行原文（检测器故障不应阻塞写作）。
          if (mode === "scene" && sceneId !== null) {
            try {
              const check = await repetitionMut.mutateAsync({
                sceneId,
                sceneText: fullGenerated,
                chapterSoFar: baseContent,
              });
              if (currentChapterRef.current !== effectiveChapterId) {
                resolve(null);
                return;
              }
              if (check.action === "rewritten") {
                setContent(prefix + check.final_text);
                setRepetitionNotice({
                  tone: "info",
                  text: "检测到与前文重复，已自动重写该场景一次。",
                  details: [],
                });
                resolve(check.final_text);
                return;
              }
              if (check.action === "kept_with_warning" || check.action === "rewrite_failed") {
                setRepetitionNotice({
                  tone: "warn",
                  text:
                    check.action === "rewrite_failed"
                      ? "该场景与前文有重复，自动重写失败，已保留原文，请手动处理。"
                      : "该场景与前文仍有重复（已处理一次），已保留，请留意。",
                  details: check.warnings,
                });
                setContent(prefix + check.final_text);
                resolve(check.final_text);
                return;
              }
            } catch {
              // fail-open：检测不可用时按原文继续
            }
          }
          resolve(fullGenerated);
        },
        (meta) => {
          if (currentChapterRef.current !== effectiveChapterId) return;
          setStreamModelName(meta.model);
          setPipelineStep("connecting");
        },
        () => resolve(null)
      );
    });

  // 逐场景顺序生成整章：每个场景基于已生成正文续写，减少长文本中的前后矛盾与重复。
  const runWholeChapter = async () => {
    if (!effectiveChapterId) return;
    setGeneratedWordsCount(0);
    setReviewResult(null);
    setReviewError(null);
    setRepetitionNotice(null);
    setPipelineStep("assembling");
    const chapterId = effectiveChapterId;
    const originalContent = content;

    let scenes = workspace?.scenes ?? [];
    if (scenes.length === 0) {
      try {
        scenes = await generateScenesMut.mutateAsync({});
      } catch (error) {
        if (currentChapterRef.current !== chapterId) return;
        setReviewError(error instanceof Error ? error.message : "拆解场景节拍失败，请重试。");
        setPipelineStep("completed");
        return;
      }
      if (currentChapterRef.current !== chapterId) return;
    }

    // 无场景可用（拆解返回空）时，回退到整章一次生成，避免卡死。
    const plan: Array<{ mode: "scene" | "chapter"; sceneId: number | null }> =
      scenes.length > 0
        ? scenes.map((s) => ({ mode: "scene" as const, sceneId: s.id }))
        : [{ mode: "chapter", sceneId: null }];

    let chapterText = "";
    for (const step of plan) {
      if (step.sceneId) setActiveSceneId(step.sceneId);
      const generated = await runSceneStream(step.mode, step.sceneId, chapterText);
      // 任一场景中断/失败/切章：停止循环，保留已生成部分不覆盖原稿。
      if (generated === null) {
        if (currentChapterRef.current === chapterId && !chapterText) setContent(originalContent);
        setPipelineStep("idle");
        return;
      }
      chapterText = chapterText.trim() ? `${chapterText.trim()}\n\n${generated}` : generated;
      if (currentChapterRef.current === chapterId) setContent(chapterText);
    }

    if (currentChapterRef.current !== chapterId) return;
    try {
      await saveMut.mutateAsync({ content: chapterText, source: "ai", create_new_version: true });
    } catch (error) {
      if (currentChapterRef.current !== chapterId) return;
      setContent(originalContent);
      setReviewError(error instanceof Error ? error.message : "正文保存失败，尚未审查，请先保存正文。");
      setPipelineStep("completed");
      return;
    }
    if (currentChapterRef.current !== chapterId) return;
    await runAutoReview();
  };

  // 单场景续写：生成后单独保存并审查。
  const executeSceneWrite = async (sceneId: number) => {
    if (!effectiveChapterId) return;
    setActiveSceneId(sceneId);
    setGeneratedWordsCount(0);
    setReviewResult(null);
    setReviewError(null);
    setRepetitionNotice(null);
    setPipelineStep("assembling");
    const chapterId = effectiveChapterId;
    const originalContent = content;
    const base = content;

    const generated = await runSceneStream("scene", sceneId, base);
    if (generated === null) {
      if (currentChapterRef.current === chapterId) setContent(originalContent);
      setPipelineStep("idle");
      return;
    }
    const fullContent = base.trim() ? `${base.trim()}\n\n${generated}` : generated;
    if (currentChapterRef.current !== chapterId) return;
    setContent(fullContent);
    try {
      await saveMut.mutateAsync({ content: fullContent, source: "ai", create_new_version: true });
    } catch (error) {
      if (currentChapterRef.current !== chapterId) return;
      setContent(originalContent);
      setReviewError(error instanceof Error ? error.message : "正文保存失败，尚未审查，请先保存正文。");
      setPipelineStep("completed");
      return;
    }
    if (currentChapterRef.current !== chapterId) return;
    await runAutoReview();
  };

  const handleWriteWholeChapter = () => {
    if (content.trim()) {
      setConfirmOverwriteOpen(true);
    } else {
      void runWholeChapter();
    }
  };

  const handleRewriteSelection = (
    actionType: RewriteActionType,
    targetCharId: number | null,
    instruction: string
  ) => {
    if (!effectiveChapterId || !selectionRange.text.trim()) return;
    const { start, end, text } = selectionRange;
    startRewriteStream(
      {
        chapter_id: effectiveChapterId,
        selected_text: text,
        action_type: actionType,
        target_character_id: targetCharId,
        instruction,
      },
      (rewritten) => {
        const updated = content.slice(0, start) + rewritten + content.slice(end);
        setContent(updated);
        setSelectionRange({ start: 0, end: 0, text: "" });
        saveMut.mutate({ content: updated, source: "ai", create_new_version: true });
      }
    );
  };

  const handleRewriteSmellHit = (hit: AiSmellHit) => {
    if (!effectiveChapterId) return;
    const sStart = Math.max(0, content.lastIndexOf("。", hit.start_index) + 1);
    const nextPeriod = content.indexOf("。", hit.end_index);
    const sEnd = nextPeriod === -1 ? content.length : nextPeriod + 1;
    startRewriteStream(
      {
        chapter_id: effectiveChapterId,
        selected_text: content.slice(sStart, sEnd),
        action_type: "polish",
        instruction: hit.suggestion,
      },
      (rewritten) => {
        const updated = content.slice(0, sStart) + rewritten + content.slice(sEnd);
        setContent(updated);
        setSmellHits((prev) => prev.filter((h) => h.start_index !== hit.start_index));
        saveMut.mutate({ content: updated, source: "ai", create_new_version: true });
      }
    );
  };

  const handleApplySmellRewrite = (hit: AiSmellHit) => {
    if (!effectiveChapterId || !hit.suggested_rewrite.trim()) return;
    const { start_index: start, end_index: end } = hit;
    if (content.slice(start, end) !== hit.matched_text) return;
    const updated = content.slice(0, start) + hit.suggested_rewrite + content.slice(end);
    setContent(updated);
    saveMut.mutate({ content: updated, source: "ai", create_new_version: true });
  };

  // 一键应用全部建议重写：按 start_index 从后往前替换，避免前面的替换移位后续偏移；
  // 替换前校验原文片段仍匹配，跳过已被编辑过的命中。
  const handleApplyAllSmellRewrites = () => {
    if (!effectiveChapterId) return;
    const applicable = smellHits
      .filter((h) => h.suggested_rewrite.trim())
      .sort((a, b) => b.start_index - a.start_index);
    let updated = content;
    let appliedCount = 0;
    const appliedStarts = new Set<number>();
    for (const hit of applicable) {
      const { start_index: start, end_index: end } = hit;
      if (updated.slice(start, end) !== hit.matched_text) continue;
      updated = updated.slice(0, start) + hit.suggested_rewrite + updated.slice(end);
      appliedStarts.add(start);
      appliedCount += 1;
    }
    if (appliedCount === 0) {
      setSmellError("建议片段已与当前正文不匹配（可能已被编辑），请重新扫描。");
      return;
    }
    setContent(updated);
    setSmellHits((prev) => prev.filter((h) => !appliedStarts.has(h.start_index)));
    setSmellError(null);
    saveMut.mutate({ content: updated, source: "ai", create_new_version: true });
  };

  const handleOpenSupplement = () => {
    const insertAt = selectionRange.text
      ? selectionRange.end
      : selectionRange.start;
    setSupplementInsertAt(insertAt);
    setSupplementBaseContent(content);
    setSupplementInstruction("");
    setSupplementCandidate("");
    setSupplementReady(false);
    setSupplementSaveError(null);
    setSupplementOpen(true);
  };

  const handleGenerateSupplement = () => {
    if (!effectiveChapterId || !supplementInstruction.trim()) return;
    const baseContent = content;
    const insertAt = supplementBaseContent === content
      ? Math.min(supplementInsertAt ?? content.length, content.length)
      : Math.min(
          selectionRange.text ? selectionRange.end : selectionRange.start,
          content.length
        );
    setSupplementBaseContent(baseContent);
    setSupplementInsertAt(insertAt);
    setSupplementCandidate("");
    setSupplementReady(false);
    setSupplementSaveError(null);
    startSupplementStream(
      {
        chapter_id: effectiveChapterId,
        content: baseContent,
        insertion_index: insertAt,
        instruction: supplementInstruction.trim(),
        disabled_context_keys: disabledContextKeys,
      },
      (delta) => setSupplementCandidate((current) => current + delta),
      (candidate) => {
        setSupplementCandidate(candidate);
        setSupplementReady(Boolean(candidate.trim()));
      }
    );
  };

  const handleInsertSupplement = async () => {
    if (
      !effectiveChapterId ||
      !supplementCandidate.trim() ||
      supplementBaseContent !== content ||
      supplementInsertAt === null
    ) return;

    const before = content.slice(0, supplementInsertAt);
    const after = content.slice(supplementInsertAt);
    const prefixGap = !before || before.endsWith("\n\n")
      ? ""
      : before.endsWith("\n") ? "\n" : "\n\n";
    const suffixGap = !after || after.startsWith("\n\n")
      ? ""
      : after.startsWith("\n") ? "\n" : "\n\n";
    const passage = supplementCandidate.trim();
    const updated = before + prefixGap + passage + suffixGap + after;
    const caretAt = before.length + prefixGap.length + passage.length;

    setSupplementSaveError(null);
    try {
      await saveMut.mutateAsync({
        content: updated,
        source: "ai",
        create_new_version: true,
      });
      setContent(updated);
      setSupplementOpen(false);
      setSupplementCandidate("");
      setSupplementReady(false);
      requestAnimationFrame(() => {
        const editor = textareaRef.current;
        editor?.focus();
        editor?.setSelectionRange(caretAt, caretAt);
      });
    } catch (error) {
      setSupplementSaveError(error instanceof Error ? error.message : "保存补充内容失败");
    }
  };

  const handleCritiqueSelection = () => {
    if (!effectiveChapterId || !selectionRange.text.trim()) return;
    setCritiqueResult(null);
    critiqueMut.mutate(selectionRange.text.trim(), {
      onSuccess: (res) => setCritiqueResult(res),
    });
  };

  const handleApplyCritiqueSuggestion = (suggestion: string) => {
    if (!effectiveChapterId || !suggestion.trim()) return;
    const { start, end } = selectionRange;
    const updated = content.slice(0, start) + suggestion + content.slice(end);
    setContent(updated);
    setSelectionRange({ start: 0, end: 0, text: "" });
    setCritiqueResult(null);
    saveMut.mutate({ content: updated, source: "ai", create_new_version: true });
  };

  const handleApplyReviewRewrite = async (issueIndex: number): Promise<boolean> => {
    if (!effectiveChapterId || !reviewResult || isStreaming || saveMut.isPending || revisionMut.isPending) return false;
    const result = await revisionMut.mutateAsync({
      reviewId: reviewResult.id, issueIndex, expectedContent: content,
    });
    if (currentChapterRef.current !== effectiveChapterId) return true;
    setContent(result.latest_content);
    setReviewResult({ ...reviewResult, is_stale: true });
    await runAutoReview();
    return true;
  };

  const handleFocusSmellHit = (hit: AiSmellHit) => {
    const el = textareaRef.current;
    if (!el) return;
    el.focus();
    el.setSelectionRange(hit.start_index, hit.end_index);
    setSelectionRange({
      start: hit.start_index,
      end: hit.end_index,
      text: content.slice(hit.start_index, hit.end_index),
    });
  };

  if (allChapters.length === 0) {
    return (
      <div className="p-8">
        <EmptyState
          title="尚未创建任何章节"
          description="请先前往「目录 (卷/弧/章)」模块生成或创建章节，再进入写作工作台。"
          action={<Button size="sm" onClick={() => setActiveSection("outline")}>前往目录规划</Button>}
        />
      </div>
    );
  }

  if (isLoading || !workspace || !effectiveChapterId) {
    return <p className="p-6 text-xs text-slate-400">正在加载写作工作台...</p>;
  }

  const wordCount = content.replace(/\s+/g, "").length;

  return (
    <div className="flex h-full overflow-hidden">
      <div className="flex flex-1 flex-col overflow-y-auto p-6">
        <WritingHeaderBar
          novelUid={novelUid}
          allChapters={allChapters}
          effectiveChapterId={effectiveChapterId}
          wordCount={wordCount}
          autoSavedAt={autoSavedAt}
          latestVersion={workspace.latest_version}
          scenes={workspace.scenes}
          activeSceneId={activeSceneId}
          isStreaming={isStreaming}
          isScanningSmell={smellMut.isPending}
          onSelectChapter={setSelectedChapterId}
          onSelectScene={setActiveSceneId}
          onWriteWholeChapter={handleWriteWholeChapter}
          onStopStream={() => { stopStream(); setPipelineStep("idle"); }}
          onScanSmell={async () => {
            setSmellError(null);
            setHasScannedSmell(false);
            try {
              const res = await smellMut.mutateAsync(content);
              if (contentRef.current !== content) return;
              setSmellHits(res.hits);
              setHasScannedSmell(true);
            } catch (error) {
              setSmellError(error instanceof Error ? error.message : "模型检测失败");
            }
          }}
          onRunConsistencyReview={async () => {
            if (!effectiveChapterId) return;
            setReviewOpen(true);
            setReviewResult(null);
            setReviewError(null);
            try {
              const res = await reviewMut.mutateAsync();
              setReviewResult(res);
            } catch (e) {
              setReviewError(e instanceof Error ? e.message : "审查请求失败");
            }
          }}
          onOpenHistory={() => setHistoryOpen(true)}
          onSaveNewVersion={() => saveMut.mutate({ content, source: "manual", create_new_version: true })}
        />

        <WritingPipelineBar
          currentStep={pipelineStep}
          modelName={streamModelName || metrics?.model}
          generatedWordCount={generatedWordsCount}
          issueCount={reviewResult?.issue_count ?? 0}
          violationCount={reviewResult?.violation_count ?? 0}
          reviewSummary={reviewResult?.summary}
          reviewError={reviewError}
          onOpenReviewDetail={() => setReviewOpen(true)}
          onRetryReview={runAutoReview}
          onDismiss={() => setPipelineStep("idle")}
        />

        {streamError && (
          <div className="mt-3 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">
            {streamError}
          </div>
        )}

        {repetitionNotice && (
          <div
            className={
              repetitionNotice.tone === "warn"
                ? "mt-3 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-800"
                : "mt-3 rounded-lg border border-sky-200 bg-sky-50 px-3 py-2 text-xs text-sky-800"
            }
          >
            <div className="flex items-start justify-between gap-2">
              <span>{repetitionNotice.text}</span>
              <button
                type="button"
                className="shrink-0 cursor-pointer text-[11px] underline"
                onClick={() => setRepetitionNotice(null)}
              >
                知道了
              </button>
            </div>
            {repetitionNotice.details.length > 0 && (
              <ul className="mt-1 list-disc pl-4">
                {repetitionNotice.details.map((d, i) => (
                  <li key={i}>{d}</li>
                ))}
              </ul>
            )}
          </div>
        )}

        {metrics && (
          <div className="mt-2 text-[11px] text-slate-400">
            最近一次生成：{metrics.model} · 上下文 {metrics.contextTokens} tok · 输出 {metrics.outputTokens} tok · 耗时 {metrics.elapsedMs} ms
          </div>
        )}

        <div className="mt-3">
          <SelectionToolbar
            selectedText={selectionRange.text}
            characters={characters}
            aiSmellHits={smellHits}
            hasScannedSmell={hasScannedSmell}
            smellError={smellError}
            isStreaming={isStreaming}
            onOpenSupplement={handleOpenSupplement}
            onRewriteSelection={handleRewriteSelection}
            onRewriteSmellHit={handleRewriteSmellHit}
            onApplySmellRewrite={handleApplySmellRewrite}
            onApplyAllSmellRewrites={handleApplyAllSmellRewrites}
            onFocusSmellHit={handleFocusSmellHit}
            onDismissSmell={() => {
              setHasScannedSmell(false);
              setSmellHits([]);
            }}
            onCritiqueSelection={handleCritiqueSelection}
            isCritiquing={critiqueMut.isPending}
            critiqueResult={critiqueResult}
            onApplyCritiqueSuggestion={handleApplyCritiqueSuggestion}
            onDismissCritique={() => setCritiqueResult(null)}
          />
        </div>

        {supplementOpen && (
          <section className="mt-3 space-y-3 rounded-xl border border-indigo-200 bg-indigo-50/60 p-4 dark:border-indigo-900 dark:bg-indigo-950/30">
            <div>
              <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-100">补充正文内容</h3>
              <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                候选内容会插入到当前光标位置；生成和预览期间不会改动正文。
              </p>
            </div>
            <textarea
              value={supplementInstruction}
              onChange={(event) => setSupplementInstruction(event.target.value)}
              disabled={isStreaming}
              maxLength={2000}
              rows={2}
              placeholder="例如：补充他们最初是怎么加上好友的，要符合前文时间和人物关系"
              className="w-full resize-y rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-800 focus:border-indigo-400 focus:outline-none dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
            />
            {supplementBaseContent !== null && supplementBaseContent !== content && (
              <p className="text-xs text-amber-700 dark:text-amber-300">
                正文在生成后发生了变化。请把光标放到新的插入位置，再重新生成。
              </p>
            )}
            {supplementCandidate && (
              <div className="max-h-64 overflow-y-auto whitespace-pre-wrap rounded-lg border border-slate-200 bg-white p-3 text-sm leading-7 text-slate-800 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100">
                {supplementCandidate}
                {isStreaming && <span className="animate-pulse">▍</span>}
              </div>
            )}
            {supplementSaveError && (
              <p className="text-xs text-rose-600">{supplementSaveError}</p>
            )}
            <div className="flex flex-wrap gap-2">
              <Button
                size="sm"
                disabled={isStreaming || !supplementInstruction.trim()}
                onClick={handleGenerateSupplement}
              >
                {isStreaming ? "生成中..." : supplementCandidate ? "重新生成" : "生成预览"}
              </Button>
              {supplementCandidate && (
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={isStreaming || !supplementReady || supplementBaseContent !== content}
                  onClick={() => void handleInsertSupplement()}
                >
                  插入正文并保存版本
                </Button>
              )}
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  if (isStreaming) stopStream();
                  setSupplementOpen(false);
                  setSupplementCandidate("");
                  setSupplementReady(false);
                }}
              >
                取消
              </Button>
            </div>
          </section>
        )}

        <textarea
          ref={textareaRef}
          value={content}
          onCompositionStart={() => { isComposingRef.current = true; }}
          onCompositionEnd={(e) => {
            isComposingRef.current = false;
            triggerAutoSave(e.currentTarget.value);
          }}
          onChange={(e) => setContent(e.target.value)}
          onBlur={(e) => triggerAutoSave(e.currentTarget.value)}
          onSelect={(e) => {
            const el = e.currentTarget;
            setSelectionRange({
              start: el.selectionStart,
              end: el.selectionEnd,
              text: el.selectionStart !== el.selectionEnd ? el.value.slice(el.selectionStart, el.selectionEnd) : "",
            });
          }}
          placeholder="在此开始撰写青春小说正文，或点击右侧场景「续写此景」由 AI 流式生成..."
          className="novel-prose mt-3 min-h-[520px] w-full flex-1 resize-none rounded-2xl border border-slate-200 bg-white p-6 text-base text-slate-800 shadow-2xs focus:border-indigo-400 focus:outline-none dark:border-slate-800 dark:bg-slate-900 dark:text-slate-100"
        />
      </div>

      {!focusMode && rightPanelOpen && (
        <aside className="flex w-88 shrink-0 flex-col border-l border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
          <div className="flex border-b border-slate-200 p-2 dark:border-slate-800">
            {([["beats", "① 细纲节拍"], ["context", "② 上下文预览"], ["memory", "③ 本章记忆"]] as const).map(([key, label]) => (
              <button
                key={key}
                type="button"
                onClick={() => setRightTab(key)}
                className={`flex-1 rounded-lg py-1.5 text-xs font-medium transition-colors cursor-pointer ${
                  rightTab === key
                    ? "bg-indigo-50 text-indigo-700 dark:bg-indigo-950/70 dark:text-indigo-300"
                    : "text-slate-500 hover:bg-slate-100 dark:text-slate-400"
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          <div className="flex-1 overflow-y-auto p-4">
            {rightTab === "beats" && (
              <SceneBeatsPanel
                novelUid={novelUid}
                chapterId={effectiveChapterId}
                scenes={workspace.scenes}
                characters={characters}
                locations={locations}
                activeSceneId={activeSceneId}
                isStreaming={isStreaming}
                onSelectScene={setActiveSceneId}
                onWriteScene={(s: SceneItem) => void executeSceneWrite(s.id)}
              />
            )}
            {rightTab === "context" && (
              <ContextPreviewPanel
                preview={contextPreview}
                isLoading={isCtxLoading}
                disabledKeys={disabledContextKeys}
                customContext={customContext}
                onToggleKey={(key) =>
                  setDisabledContextKeys((prev) =>
                    prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]
                  )
                }
                onChangeCustomContext={setCustomContext}
              />
            )}
            {rightTab === "memory" && (
              <MemoryChapterPanel
                novelUid={novelUid}
                chapterId={effectiveChapterId}
                chapterStatus={workspace.chapter.status}
                continuityReviewRequired={workspace.chapter.continuity_review_required}
              />
            )}
          </div>
        </aside>
      )}

      <VersionHistoryModal
        open={historyOpen}
        onClose={() => setHistoryOpen(false)}
        versions={workspace.versions}
        onRestore={(ver) => restoreMut.mutate(ver)}
        isRestoring={restoreMut.isPending}
      />
      <ConsistencyReviewModal
        open={reviewOpen}
        onClose={() => setReviewOpen(false)}
        review={reviewResult}
        running={reviewMut.isPending || revisionMut.isPending}
        error={reviewError}
        onApplyRewrite={handleApplyReviewRewrite}
      />
      <ConfirmModal
        open={confirmOverwriteOpen}
        onClose={() => setConfirmOverwriteOpen(false)}
        onConfirm={() => {
          setConfirmOverwriteOpen(false);
          void runWholeChapter();
        }}
        title="替换正文确认"
        description="将用全新生成的正文替换本章当前内容（旧内容可在「版本历史」中恢复），是否继续？"
        confirmText="确认替换并生成"
        cancelText="取消"
        confirmVariant="primary"
      />
    </div>
  );
};
