import React, { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/common/EmptyState";
import { useOutlineTree } from "@/features/outline/api";
import { useCharacters, useLocations } from "@/features/settings-entity/api";
import { MemoryChapterPanel } from "@/features/memory/MemoryChapterPanel";
import { ConsistencyReviewModal } from "@/features/memory/ConsistencyReviewModal";
import { useRunConsistencyReview } from "@/features/memory/api";
import type { ConsistencyReviewResponse } from "@/features/memory/types";
import { useUiStore } from "@/stores/uiStore";
import {
  useAiSmellScan,
  useChapterWorkspace,
  useContextPreview,
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

  const { data: workspace, isLoading } = useChapterWorkspace(novelUid, effectiveChapterId);
  const saveMut = useSaveChapterContent(novelUid, effectiveChapterId ?? 0);
  const restoreMut = useRestoreChapterVersion(novelUid, effectiveChapterId ?? 0);
  const smellMut = useAiSmellScan(novelUid);

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
  const [reviewOpen, setReviewOpen] = useState(false);
  const [reviewResult, setReviewResult] = useState<ConsistencyReviewResponse | null>(null);
  const [reviewError, setReviewError] = useState<string | null>(null);
  const [confirmOverwriteOpen, setConfirmOverwriteOpen] = useState(false);
  const [critiqueResult, setCritiqueResult] = useState<SelectionCritiqueResult | null>(null);
  const critiqueMut = useCritiqueSelection(novelUid, effectiveChapterId ?? 0);
  const reviewMut = useRunConsistencyReview(novelUid, effectiveChapterId ?? 0);
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
  } = useStreamGenerate(novelUid);

  useEffect(() => {
    if (workspace) {
      setContent(workspace.latest_content);
      setHasScannedSmell(false);
      setSmellHits([]);
      if (!activeSceneId && workspace.scenes.length > 0) {
        setActiveSceneId(workspace.scenes[0].id);
      }
    }
  }, [workspace?.chapter.id, workspace?.latest_version]);

  const triggerAutoSave = (nextText: string) => {
    if (!effectiveChapterId || isComposingRef.current || isStreaming) return;
    saveMut.mutate(
      { content: nextText, source: "manual", create_new_version: false },
      { onSuccess: () => setAutoSavedAt(new Date().toLocaleTimeString([], { hour12: false })) }
    );
  };

  const executeStreamWrite = (mode: "scene" | "chapter", sceneId: number | null) => {
    if (!effectiveChapterId) return;
    if (sceneId) setActiveSceneId(sceneId);
    const isChapterRewrite = mode === "chapter";
    const prefix = !isChapterRewrite && content.trim() ? `${content.trim()}\n\n` : "";
    setContent(prefix);
    startWriteStream(
      {
        chapter_id: effectiveChapterId,
        scene_id: sceneId,
        mode,
        existing_content: isChapterRewrite ? "" : content,
        disabled_context_keys: disabledContextKeys,
        custom_context: customContext,
        instruction: "",
      },
      (delta) => setContent((prev) => prev + delta),
      (fullGenerated) => {
        saveMut.mutate({ content: `${prefix}${fullGenerated}`, source: "ai", create_new_version: true });
      }
    );
  };

  const handleWriteWholeChapter = () => {
    if (content.trim()) {
      setConfirmOverwriteOpen(true);
    } else {
      executeStreamWrite("chapter", null);
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
          onStopStream={stopStream}
          onScanSmell={async () => {
            const res = await smellMut.mutateAsync(content);
            setSmellHits(res.hits);
            setHasScannedSmell(true);
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

        {streamError && (
          <div className="mt-3 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">
            {streamError}
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
            isStreaming={isStreaming}
            onRewriteSelection={handleRewriteSelection}
            onRewriteSmellHit={handleRewriteSmellHit}
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
                onWriteScene={(s: SceneItem) => executeStreamWrite("scene", s.id)}
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
        running={reviewMut.isPending}
        error={reviewError}
      />
      <ConfirmModal
        open={confirmOverwriteOpen}
        onClose={() => setConfirmOverwriteOpen(false)}
        onConfirm={() => executeStreamWrite("chapter", null)}
        title="替换正文确认"
        description="将用全新生成的正文替换本章当前内容（旧内容可在「版本历史」中恢复），是否继续？"
        confirmText="确认替换并生成"
        cancelText="取消"
        confirmVariant="primary"
      />
    </div>
  );
};
