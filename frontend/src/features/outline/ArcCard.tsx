import React from "react";
import {
  ArrowDown,
  ArrowUp,
  FileEdit,
  Loader2,
  Plus,
  Sparkles,
  Trash2,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { LockToggle } from "@/components/common/LockToggle";
import type { ArcTreeNode, ChapterItem, ChapterStatus } from "@/types/api";

const STATUS_BADGE: Record<
  ChapterStatus,
  { label: string; tone: "default" | "indigo" | "amber" | "emerald" }
> = {
  pending: { label: "未开始", tone: "default" },
  outline: { label: "已出细纲", tone: "indigo" },
  draft: { label: "草稿中", tone: "amber" },
  final: { label: "已定稿", tone: "emerald" },
};

interface ArcCardProps {
  arc: ArcTreeNode;
  isGenerating: boolean;
  onGenerateChapters: (arcId: number) => void;
  onCreateChapter: (arcId: number) => void;
  onDeleteArc: (arcId: number) => void;
  onUpdateChapter: (
    chapterId: number,
    input: Partial<{ title: string; synopsis: string; locked: boolean }>
  ) => void;
  onMoveChapter: (
    chapters: ChapterItem[],
    index: number,
    direction: "up" | "down"
  ) => void;
  onOpenWriting: (chapterId: number) => void;
  onDeleteChapter: (chapterId: number) => void;
}

export const ArcCard: React.FC<ArcCardProps> = ({
  arc,
  isGenerating,
  onGenerateChapters,
  onCreateChapter,
  onDeleteArc,
  onUpdateChapter,
  onMoveChapter,
  onOpenWriting,
  onDeleteChapter,
}) => {
  return (
    <div className="rounded-xl border border-slate-200/80 bg-slate-50/50 p-4 dark:border-slate-800 dark:bg-slate-950/40">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold text-indigo-700 dark:text-indigo-300">
              {arc.title}
            </span>
            <Badge>{arc.chapters.length} 章</Badge>
          </div>
          {(arc.goal || arc.core_conflict) && (
            <p className="mt-0.5 text-xs text-slate-500">
              目标：{arc.goal || "—"} · 冲突：{arc.core_conflict || "—"}
            </p>
          )}
        </div>

        <div className="flex items-center gap-1.5">
          <Button
            size="sm"
            disabled={isGenerating}
            onClick={() => onGenerateChapters(arc.id)}
          >
            {isGenerating ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Sparkles className="h-3.5 w-3.5" />
            )}
            AI 滚动生成本弧章节
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => onCreateChapter(arc.id)}
          >
            <Plus className="h-3.5 w-3.5" />
            新建章
          </Button>
          <button
            type="button"
            onClick={() => onDeleteArc(arc.id)}
            className="rounded-md p-1 text-slate-400 hover:bg-rose-50 hover:text-rose-600 cursor-pointer"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      <div className="mt-3 space-y-2">
        {arc.chapters.map((ch, idx) => (
          <div
            key={ch.id}
            className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-slate-200 bg-white px-3.5 py-2.5 text-xs dark:border-slate-800 dark:bg-slate-900"
          >
            <div className="flex flex-1 items-center gap-2.5">
              <span className="shrink-0 font-mono font-semibold text-indigo-600 dark:text-indigo-400">
                第 {ch.display_index} 章
              </span>
              <input
                type="text"
                defaultValue={ch.title}
                onBlur={(e) => {
                  const val = e.target.value.trim();
                  if (val && val !== ch.title) {
                    onUpdateChapter(ch.id, { title: val });
                  }
                }}
                className="w-44 rounded border border-transparent px-1.5 py-0.5 font-semibold text-slate-900 focus:border-indigo-400 focus:bg-slate-50 focus:outline-none dark:text-slate-100 dark:focus:bg-slate-950"
              />
              <input
                type="text"
                placeholder="章节梗概..."
                defaultValue={ch.synopsis}
                onBlur={(e) => {
                  const val = e.target.value.trim();
                  if (val !== ch.synopsis) {
                    onUpdateChapter(ch.id, { synopsis: val });
                  }
                }}
                className="flex-1 rounded border border-transparent px-1.5 py-0.5 text-slate-500 focus:border-indigo-400 focus:bg-slate-50 focus:outline-none dark:text-slate-400 dark:focus:bg-slate-950"
              />
            </div>

            <div className="flex items-center gap-1.5">
              <Badge tone={STATUS_BADGE[ch.status].tone}>
                {STATUS_BADGE[ch.status].label}
              </Badge>
              {ch.continuity_review_required && (
                <Badge tone="amber">连续性待复核</Badge>
              )}
              <LockToggle
                locked={ch.locked}
                onToggle={(next) => onUpdateChapter(ch.id, { locked: next })}
              />
              <button
                type="button"
                disabled={idx === 0}
                onClick={() => onMoveChapter(arc.chapters, idx, "up")}
                title="上移（浮点排序）"
                className="rounded p-1 text-slate-400 hover:bg-slate-100 disabled:opacity-30 cursor-pointer"
              >
                <ArrowUp className="h-3.5 w-3.5" />
              </button>
              <button
                type="button"
                disabled={idx === arc.chapters.length - 1}
                onClick={() => onMoveChapter(arc.chapters, idx, "down")}
                title="下移（浮点排序）"
                className="rounded p-1 text-slate-400 hover:bg-slate-100 disabled:opacity-30 cursor-pointer"
              >
                <ArrowDown className="h-3.5 w-3.5" />
              </button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => onOpenWriting(ch.id)}
              >
                <FileEdit className="h-3.5 w-3.5" />
                写作
              </Button>
              <button
                type="button"
                onClick={() => onDeleteChapter(ch.id)}
                className="rounded p-1 text-slate-400 hover:bg-rose-50 hover:text-rose-600 cursor-pointer"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
