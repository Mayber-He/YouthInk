import React, { useState } from "react";
import { Check, CheckCircle2, Sparkles, X } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import {
  useFinalizeChapter,
  usePendingQueue,
  useSummaries,
  useUpdatePendingItem,
} from "./api";
import type { FinalizeChapterResponse } from "./types";

interface MemoryChapterPanelProps {
  novelUid: string;
  chapterId: number;
  chapterStatus: string;
  continuityReviewRequired: boolean;
}

const CATEGORY_LABEL: Record<string, string> = {
  fact: "事实",
  char_state: "人物状态",
  cognitive: "认知秘密",
  relationship: "人物关系",
  foreshadowing: "伏笔",
};

export const MemoryChapterPanel: React.FC<MemoryChapterPanelProps> = ({
  novelUid,
  chapterId,
  chapterStatus,
  continuityReviewRequired,
}) => {
  const finalizeMut = useFinalizeChapter(novelUid, chapterId);
  const { data: summaries = [] } = useSummaries(novelUid, "chapter");
  const { data: pendingItems = [] } = usePendingQueue(
    novelUid,
    undefined,
    chapterId,
    "pending"
  );
  const updateItemMut = useUpdatePendingItem(novelUid);

  const [lastResult, setLastResult] = useState<FinalizeChapterResponse | null>(
    null
  );

  const chapterSummary = summaries.find((s) => s.ref_id === chapterId);

  const handleFinalize = async () => {
    const res = await finalizeMut.mutateAsync();
    setLastResult(res);
  };

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-indigo-200 bg-indigo-50/60 p-3 dark:border-indigo-900 dark:bg-indigo-950/30">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-xs font-semibold text-indigo-900 dark:text-indigo-200">
              定稿才入库 · 记忆闭环
            </div>
            <p className="mt-0.5 text-[11px] text-indigo-700/80 dark:text-indigo-300/80">
              点击定稿表示确认当前正文，并自动通过本章一致性复核，同时更新快照、索引、摘要与设定抽取。
            </p>
          </div>
          <Badge tone={chapterStatus === "final" ? "emerald" : "amber"}>
            {chapterStatus === "final" ? "已定稿" : "草稿/写作中"}
          </Badge>
        </div>

        <Button
          size="sm"
          className="mt-3 w-full"
          onClick={handleFinalize}
          disabled={finalizeMut.isPending}
        >
          <Sparkles className="h-3.5 w-3.5" />
          {finalizeMut.isPending
            ? "正在定稿入库..."
            : chapterStatus === "final"
              ? "重新定稿并更新记忆库"
              : "一键定稿并入库"}
        </Button>

        {lastResult && (
          <div className="mt-2.5 rounded-lg bg-white/90 p-2 text-[11px] text-slate-600 dark:bg-slate-900 dark:text-slate-300">
            <div className="flex items-center gap-1 font-medium text-emerald-700 dark:text-emerald-400">
              <CheckCircle2 className="h-3.5 w-3.5" />
              定稿入库成功！本章一致性复核自动通过，已创建快照备份
            </div>
            <div className="mt-1">
              切分索引：{lastResult.chunks_indexed} 个片段 · 信任模式自动确认：
              {lastResult.auto_confirmed_count} 项 · 待人工确认：
              {lastResult.pending_count} 项
            </div>
          </div>
        )}
      </div>

      {continuityReviewRequired && (
        <div className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-xs text-amber-900 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-200">
          本章或前文正文有修改，相关上下文暂不参与生成。请先定稿较早章节，再按顺序重新定稿本章和后续受影响章节；定稿表示确认当前正文并自动通过本章复核。
        </div>
      )}

      {/* 本章摘要 */}
      <div className="rounded-xl border border-slate-200 p-3 dark:border-slate-800">
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold text-slate-800 dark:text-slate-200">
            本章剧情摘要
          </span>
          {chapterSummary?.is_stale && (
            <Badge tone="amber">正文已改·建议重新定稿</Badge>
          )}
        </div>
        {chapterSummary ? (
          <p className="mt-2 text-xs leading-relaxed text-slate-600 dark:text-slate-300">
            {chapterSummary.content}
          </p>
        ) : (
          <p className="mt-2 text-xs text-slate-400">
            本章尚未生成定稿摘要。点击上方「一键定稿并入库」自动生成。
          </p>
        )}
      </div>

      {/* 本章待确认抽取项 */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold text-slate-800 dark:text-slate-200">
            本章待确认设定变更 ({pendingItems.length})
          </span>
        </div>

        {pendingItems.length === 0 ? (
          <p className="rounded-lg border border-dashed border-slate-200 p-3 text-center text-xs text-slate-400 dark:border-slate-800">
            本章暂无待确认项（常规事实与伏笔线索已由信任模式自动入库）
          </p>
        ) : (
          pendingItems.map((item) => (
            <div
              key={`${item.item_type}-${item.id}`}
              className="rounded-lg border border-slate-200 bg-slate-50/70 p-2.5 text-xs dark:border-slate-800 dark:bg-slate-800/40"
            >
              <div className="flex items-center justify-between gap-2">
                <Badge tone="indigo">
                  {CATEGORY_LABEL[item.item_type] ?? item.item_type}
                </Badge>
                {Boolean(item.raw_payload.is_stale) && (
                  <Badge tone="amber">来源正文已修改</Badge>
                )}
                <div className="flex items-center gap-1">
                  <button
                    type="button"
                    onClick={() =>
                      updateItemMut.mutate({
                        item_type: item.item_type,
                        id: item.id,
                        action: "confirm",
                      })
                    }
                    className="rounded bg-emerald-600 px-2 py-0.5 text-[11px] text-white hover:bg-emerald-500 cursor-pointer"
                  >
                    <Check className="inline h-3 w-3" /> 确认
                  </button>
                  <button
                    type="button"
                    onClick={() =>
                      updateItemMut.mutate({
                        item_type: item.item_type,
                        id: item.id,
                        action: "discard",
                      })
                    }
                    className="rounded bg-slate-200 px-2 py-0.5 text-[11px] text-slate-700 hover:bg-rose-100 hover:text-rose-700 cursor-pointer dark:bg-slate-700 dark:text-slate-300"
                  >
                    <X className="inline h-3 w-3" /> 丢弃
                  </button>
                </div>
              </div>
              <p className="mt-1.5 font-medium text-slate-800 dark:text-slate-200">
                {item.summary_text}
              </p>
              {item.source_quote && (
                <p className="mt-1 border-l-2 border-slate-300 pl-2 text-[11px] italic text-slate-500">
                  “{item.source_quote}”
                </p>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
};
