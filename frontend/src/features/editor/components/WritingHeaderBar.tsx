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
  onSelectChapter: (chapterId: number) => void;
  onSelectScene: (sceneId: number) => void;
  onWriteWholeChapter: () => void;
  onStopStream: () => void;
  onScanSmell: () => void;
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
  onSelectChapter,
  onSelectScene,
  onWriteWholeChapter,
  onStopStream,
  onScanSmell,
  onOpenHistory,
  onSaveNewVersion,
}) => {
  const [showTopBeats, setShowTopBeats] = useState(true);

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

          <Button variant="outline" size="sm" onClick={onScanSmell}>
            <SearchCheck className="h-3.5 w-3.5" />
            AI 味检测
          </Button>

          <Button variant="outline" size="sm" onClick={onOpenHistory}>
            <History className="h-3.5 w-3.5" />
            版本 (v{latestVersion})
          </Button>

          <Button variant="outline" size="sm" onClick={onSaveNewVersion}>
            <Save className="h-3.5 w-3.5" />
            存为新版本
          </Button>

          <a
            href={`/api/v1/novels/${novelUid}/export?format=md`}
            download
            className="inline-flex items-center gap-1 rounded-lg border border-slate-300 px-2.5 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-200"
          >
            <Download className="h-3.5 w-3.5" />
            导出 MD
          </a>
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
