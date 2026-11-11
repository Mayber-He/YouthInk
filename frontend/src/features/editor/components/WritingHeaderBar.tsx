import React, { useState } from "react";
import {
  Check,
  ChevronDown,
  ChevronUp,
  Download,
  History,
  Play,
  Save,
  SearchCheck,
  ShieldCheck,
  Sparkles,
  Square,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import type { ChapterItem } from "@/types/api";
import type { SceneItem } from "../types";

interface WritingHeaderBarProps {
  novelUid: string;
  allChapters: ChapterItem[];
  effectiveChapterId: number;
  wordCount: number;
  autoSavedAt: string | null;
  latestVersion: number;
  scenes: SceneItem[];
  activeSceneId: number | null;
  isStreaming: boolean;
  isScanningSmell?: boolean;
  isReviewingStyle?: boolean;
  onSelectChapter: (chapterId: number) => void;
  onSelectScene: (sceneId: number) => void;
  onWriteWholeChapter: () => void;
  onStopStream: () => void;
  onScanSmell: () => void;
  onRunStyleReview?: () => void;
  onRunConsistencyReview: () => void;
  onOpenHistory: () => void;
  onSaveNewVersion: () => void;
}

export const WritingHeaderBar: React.FC<WritingHeaderBarProps> = ({
  novelUid,
  allChapters,
  effectiveChapterId,
  wordCount,
  autoSavedAt,
  latestVersion,
  scenes,
  activeSceneId,
  isStreaming,
  isScanningSmell = false,
  isReviewingStyle = false,
  onSelectChapter,
  onSelectScene,
  onWriteWholeChapter,
  onStopStream,
  onScanSmell,
  onRunStyleReview,
  onRunConsistencyReview,
  onOpenHistory,
  onSaveNewVersion,
}) => {
  const [showTopBeats, setShowTopBeats] = useState(true);
  const [exportMenuOpen, setExportMenuOpen] = useState(false);

  const currentChapter = allChapters.find((ch) => ch.id === effectiveChapterId);
  const currentChapterName = currentChapter
    ? `第${currentChapter.display_index}章 ${currentChapter.title.replace(/[\\/*?:"<>|]/g, "_").trim()}`
    : "章节";
  const chapterFileName = `${currentChapterName}.md`;

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 pb-3 dark:border-slate-800">
        <div className="flex items-center gap-2.5">
          <select
            value={effectiveChapterId}
            onChange={(e) => onSelectChapter(Number(e.target.value))}
            className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm font-bold text-slate-900 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
          >
            {allChapters.map((ch) => (
              <option key={ch.id} value={ch.id}>
                第 {ch.display_index} 章：{ch.title}
              </option>
            ))}
          </select>
          <Badge tone="indigo">{wordCount.toLocaleString()} 字</Badge>
          {autoSavedAt && (
            <span className="inline-flex items-center gap-1 text-[11px] text-emerald-600">
              <Check className="h-3 w-3" />
              已保存 {autoSavedAt}
            </span>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          {isStreaming ? (
            <Button variant="danger" size="sm" onClick={onStopStream}>
              <Square className="h-3.5 w-3.5" />
              停止生成
            </Button>
          ) : (
            <Button size="sm" onClick={onWriteWholeChapter}>
              <Play className="h-3.5 w-3.5" />
              流式写本章
            </Button>
          )}

          {onRunStyleReview && (
            <Button
              variant="secondary"
              size="sm"
              disabled={isReviewingStyle}
              onClick={onRunStyleReview}
            >
              <Sparkles className="h-3.5 w-3.5 text-indigo-600" />
              {isReviewingStyle ? "诊脉中..." : "文风诊脉"}
            </Button>
          )}

          <Button
            variant="outline"
            size="sm"
            disabled={isScanningSmell}
            onClick={onScanSmell}
          >
            <SearchCheck className="h-3.5 w-3.5" />
            {isScanningSmell ? "检测中..." : "AI 味检测"}
          </Button>

          <Button variant="outline" size="sm" onClick={onRunConsistencyReview}>
            <ShieldCheck className="h-3.5 w-3.5" />
            一致性审查
          </Button>

          <Button variant="outline" size="sm" onClick={onOpenHistory}>
            <History className="h-3.5 w-3.5" />
            版本 (v{latestVersion})
          </Button>

          <Button variant="outline" size="sm" onClick={onSaveNewVersion}>
            <Save className="h-3.5 w-3.5" />
            存为新版本
          </Button>

          <div className="relative inline-flex items-center">
            <a
              href={`/api/v1/novels/${novelUid}/export?format=md&chapter_id=${effectiveChapterId}`}
              download={chapterFileName}
              title={`导出本章：${chapterFileName}`}
              className="inline-flex items-center gap-1 rounded-l-lg border border-slate-300 px-2.5 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-200"
            >
              <Download className="h-3.5 w-3.5" />
              导出本章 MD
            </a>
            <button
              type="button"
              onClick={() => setExportMenuOpen(!exportMenuOpen)}
              className="inline-flex items-center rounded-r-lg border-y border-r border-slate-300 px-1 py-1.5 text-xs text-slate-500 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300"
              title="更多导出选项"
            >
              <ChevronDown className="h-3 w-3" />
            </button>
            {exportMenuOpen && (
              <div
                className="absolute right-0 top-full z-20 mt-1 w-36 rounded-lg border border-slate-200 bg-white py-1 shadow-lg dark:border-slate-700 dark:bg-slate-800"
                onMouseLeave={() => setExportMenuOpen(false)}
              >
                <a
                  href={`/api/v1/novels/${novelUid}/export?format=md&chapter_id=${effectiveChapterId}`}
                  download={chapterFileName}
                  onClick={() => setExportMenuOpen(false)}
                  className="flex items-center gap-2 px-3 py-1.5 text-xs text-slate-700 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-700"
                >
                  导出本章 (MD)
                </a>
                <a
                  href={`/api/v1/novels/${novelUid}/export?format=md`}
                  download
                  onClick={() => setExportMenuOpen(false)}
                  className="flex items-center gap-2 px-3 py-1.5 text-xs text-slate-700 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-700"
                >
                  导出全书 (MD)
                </a>
              </div>
            )}
          </div>
        </div>
      </div>

      {scenes.length > 0 && (
        <div className="mt-3 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-xs dark:border-slate-800 dark:bg-slate-900">
          <div className="flex items-center justify-between">
            <span className="font-semibold text-slate-700 dark:text-slate-300">
              本章场景节拍总览 ({scenes.length} 幕)
            </span>
            <button
              type="button"
              onClick={() => setShowTopBeats(!showTopBeats)}
              className="inline-flex items-center gap-1 text-slate-400 hover:text-slate-600 cursor-pointer"
            >
              {showTopBeats ? (
                <>
                  收起 <ChevronUp className="h-3.5 w-3.5" />
                </>
              ) : (
                <>
                  展开 <ChevronDown className="h-3.5 w-3.5" />
                </>
              )}
            </button>
          </div>
          {showTopBeats && (
            <div className="mt-2 flex flex-wrap gap-2">
              {scenes.map((s, i) => (
                <div
                  key={s.id}
                  onClick={() => onSelectScene(s.id)}
                  className={`flex items-center gap-2 rounded-lg border px-2.5 py-1.5 cursor-pointer ${
                    activeSceneId === s.id
                      ? "border-indigo-400 bg-indigo-50/60 dark:border-indigo-700 dark:bg-indigo-950/40"
                      : "border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-950"
                  }`}
                >
                  <Badge tone="indigo">幕 {i + 1}</Badge>
                  <span className="max-w-xs truncate text-slate-700 dark:text-slate-300">
                    {s.beat}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
