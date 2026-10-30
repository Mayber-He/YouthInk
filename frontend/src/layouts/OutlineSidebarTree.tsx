import React from "react";
import { CheckCircle2, Circle, FileText } from "lucide-react";
import type { ChapterStatus, OutlineTree } from "@/types/api";

interface OutlineSidebarTreeProps {
  outline: OutlineTree | undefined;
  selectedChapterId: number | null;
  onSelectChapter: (chapterId: number) => void;
}

const renderChapterIcon = (status: ChapterStatus) => {
  if (status === "final") {
    return <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-emerald-500" />;
  }
  if (status === "draft" || status === "outline") {
    return <FileText className="h-3.5 w-3.5 shrink-0 text-amber-500" />;
  }
  return <Circle className="h-3.5 w-3.5 shrink-0 text-slate-300" />;
};

export const OutlineSidebarTree: React.FC<OutlineSidebarTreeProps> = ({
  outline,
  selectedChapterId,
  onSelectChapter,
}) => {
  return (
    <div className="border-t border-slate-100 p-3 dark:border-slate-800">
      <div className="mb-2 flex items-center justify-between px-2 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
        <span>章节目录树</span>
        <span>{outline?.total_chapters ?? 0} 章</span>
      </div>
      {outline && outline.volumes.length > 0 ? (
        <div className="space-y-2 text-xs">
          {outline.volumes.map((v) => (
            <div key={v.id} className="space-y-1">
              <div className="truncate px-2 font-semibold text-slate-700 dark:text-slate-300">
                {v.title}
              </div>
              {v.arcs.flatMap((a) =>
                a.chapters.map((ch) => (
                  <button
                    key={ch.id}
                    type="button"
                    onClick={() => onSelectChapter(ch.id)}
                    className={`flex w-full items-center gap-1.5 rounded-md px-2.5 py-1 text-left text-[11px] transition-colors cursor-pointer ${
                      selectedChapterId === ch.id
                        ? "bg-indigo-50 font-medium text-indigo-700 dark:bg-indigo-950/60 dark:text-indigo-300"
                        : "text-slate-600 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800"
                    }`}
                  >
                    {renderChapterIcon(ch.status)}
                    <span className="truncate">
                      第{ch.display_index}章 {ch.title}
                    </span>
                  </button>
                ))
              )}
            </div>
          ))}
        </div>
      ) : (
        <p className="px-2 text-[11px] text-slate-400">
          暂无章节，可在「目录」模块生成。
        </p>
      )}
    </div>
  );
};
