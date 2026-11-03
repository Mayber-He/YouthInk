import React, { useState } from "react";
import {
  AlertTriangle,
  Check,
  CheckCircle2,
  EyeOff,
  RotateCcw,
  Sparkles,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Modal } from "@/components/ui/Modal";
import {
  fetchConsistencyReview,
  fetchConsistencyReviews,
  useChapterMemoryItems,
  useConsistencyReviews,
  useFinalizeChapter,
  usePendingQueue,
  useSetMemoryItemDisabled,
  useSummaries,
  useUpdatePendingItem,
} from "./api";
import type {
  ChapterMemoryItem,
  ConsistencyIssue,
  DisableableMemoryCategory,
  FinalizeChapterResponse,
} from "./types";

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

const CATEGORY_ORDER: DisableableMemoryCategory[] = [
  "fact",
  "char_state",
  "cognitive",
  "relationship",
  "foreshadowing",
];

const CHECK_TYPE_LABEL: Record<string, string> = {
  constraint: "约束",
  fact: "事实",
  character: "人物",
  common_sense: "常理逻辑",
  continuity: "跨章连贯",
  prose: "表达与删冗",
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
  const { data: reviews = [] } = useConsistencyReviews(novelUid, chapterId);
  const { data: memoryItems = [] } = useChapterMemoryItems(novelUid, chapterId);
  const updateItemMut = useUpdatePendingItem(novelUid);
  const disableMut = useSetMemoryItemDisabled(novelUid);

  const [lastResult, setLastResult] = useState<FinalizeChapterResponse | null>(
    null
  );
  const [finalizeError, setFinalizeError] = useState<string | null>(null);
  const [finalizeWarning, setFinalizeWarning] = useState<{
    issues: ConsistencyIssue[];
    stale: boolean;
  } | null>(null);

  const chapterSummary = summaries.find((s) => s.ref_id === chapterId);

  const groupedMemory = CATEGORY_ORDER.map((type) => ({
    type,
    items: memoryItems.filter(
      (item) => item.item_type === type && item.status !== "discarded"
    ),
  })).filter((group) => group.items.length > 0);

  const conflictCount = memoryItems.filter(
    (item) => item.conflict && item.is_effective
  ).length;

  const runFinalize = async () => {
    setFinalizeError(null);
    try {
      const res = await finalizeMut.mutateAsync();
      setLastResult(res);
    } catch (error) {
      setFinalizeError(error instanceof Error ? error.message : "定稿失败，请重试。");
    }
  };

  const handleFinalize = async () => {
    try {
      // 先用列表接口确认最新一次审查；列表未加载完时直接补拉一次。
      const list = reviews.length
        ? reviews
        : await fetchConsistencyReviews(novelUid, chapterId);
      const latest = list[0];
      if (latest && latest.violation_count > 0) {
        const detail = await fetchConsistencyReview(novelUid, latest.id);
        const issues = detail.issues.filter((issue) => issue.verdict === "violation");
        if (issues.length > 0) {
          setFinalizeWarning({ issues, stale: detail.is_stale });
          return;
        }
      }
    } catch {
      // 预检失败不阻塞定稿；定稿本身仍会由后端完整执行。
    }
    await runFinalize();
  };

  const confirmFinalize = async () => {
    setFinalizeWarning(null);
    await runFinalize();
  };

  const renderMemoryItem = (item: ChapterMemoryItem) => {
    const sourceChapter = item.chapter_display_index
      ? `第 ${item.chapter_display_index} 章《${item.chapter_title}》`
      : item.chapter_title || "来源章节未标注";
    const storyTime = item.story_time || "故事时间未标注";
    const statusBadge = item.is_disabled ? (
      <Badge tone="default">已停用</Badge>
    ) : item.status === "pending" ? (
      <Badge tone="amber">待确认</Badge>
    ) : (
      <Badge tone="emerald">生效中</Badge>
    );

    return (
      <div
        key={`${item.item_type}-${item.id}`}
        className={`rounded-lg border p-2.5 text-xs ${
          item.conflict
            ? "border-rose-300 bg-rose-50/60 dark:border-rose-900 dark:bg-rose-950/30"
            : "border-slate-200 bg-slate-50/70 dark:border-slate-800 dark:bg-slate-800/40"
        }`}
      >
        <div className="flex flex-wrap items-center gap-1.5">
          {statusBadge}
          {item.conflict && (
            <Badge tone="rose">
              <AlertTriangle className="h-3 w-3" /> 可能冲突
            </Badge>
          )}
          {item.is_disabled && (
            <span className="text-[11px] text-slate-400">不注入上下文</span>
          )}
          <div className="ml-auto">
            {item.status === "pending" ? (
              <span className="text-[11px] text-slate-400">
                确认后才生效，可在下方队列处理
              </span>
            ) : (
              <Button
                variant="outline"
                size="sm"
                className="h-6 gap-1 px-2 text-[11px] cursor-pointer"
                disabled={disableMut.isPending}
                onClick={() =>
                  disableMut.mutate({
                    item_type: item.item_type,
                    id: item.id,
                    is_disabled: !item.is_disabled,
                  })
                }
              >
                {item.is_disabled ? (
                  <>
                    <RotateCcw className="h-3 w-3" />
                    恢复注入
                  </>
                ) : (
                  <>
                    <EyeOff className="h-3 w-3" />
                    停用
                  </>
                )}
              </Button>
            )}
          </div>
        </div>
        <p
          className={`mt-1.5 font-medium ${
            item.is_disabled
              ? "text-slate-400 line-through"
              : "text-slate-800 dark:text-slate-200"
          }`}
        >
          {item.content}
        </p>
        <p className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">
          来源：{sourceChapter} · {storyTime}
        </p>
        {item.conflict && item.conflict_reason && (
          <p className="mt-1 text-[11px] text-rose-600 dark:text-rose-300">
            {item.conflict_reason}；请确认是否停用其中一条。
          </p>
        )}
      </div>
    );
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

        {finalizeError && (
          <div className="mt-2.5 rounded-lg bg-rose-50 p-2 text-[11px] text-rose-700 dark:bg-rose-950/40 dark:text-rose-300">
            定稿失败：{finalizeError}
          </div>
        )}

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
            {lastResult.extraction_status === "failed" && (
              <div className="mt-1.5 rounded bg-rose-50 px-2 py-1 font-medium text-rose-700 dark:bg-rose-950/40 dark:text-rose-300">
                ⚠️ 本章记忆抽取失败：仅生成了占位事实，请在下方待确认列表中人工补录。
              </div>
            )}
            {lastResult.extraction_status === "partial" && (
              <div className="mt-1.5 rounded bg-amber-50 px-2 py-1 font-medium text-amber-700 dark:bg-amber-950/40 dark:text-amber-300">
                ⚠️ 本章记忆抽取部分失败：部分条目因格式不符或引文不在正文中已被丢弃，请核对下方结果。
              </div>
            )}
          </div>
        )}
      </div>

      {continuityReviewRequired && (
        <div className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-xs text-amber-900 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-200">
          本章或前文正文有修改，相关上下文暂不参与生成。请先定稿较早章节，再按顺序重新定稿本章和后续受影响章节；定稿表示确认当前正文并自动通过本章复核。
        </div>
      )}

      {/* 本章新增记忆：按类型分组，可逐条停用/恢复 */}
      <div className="rounded-xl border border-slate-200 p-3 dark:border-slate-800">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="text-xs font-semibold text-slate-800 dark:text-slate-200">
            本章新增记忆 ({memoryItems.length})
          </span>
          {conflictCount > 0 && (
            <Badge tone="rose">
              <AlertTriangle className="h-3 w-3" />
              {conflictCount} 条可能冲突
            </Badge>
          )}
        </div>
        <p className="mt-0.5 text-[11px] text-slate-500 dark:text-slate-400">
          停用后该条不再注入写作上下文，但记录仍保留，可随时恢复。关系只注入同一对人物的最新一条，其余仍在此列出。
        </p>

        {groupedMemory.length === 0 ? (
          <p className="mt-2 rounded-lg border border-dashed border-slate-200 p-3 text-center text-xs text-slate-400 dark:border-slate-800">
            本章暂无新增记忆。定稿后自动抽取的事实、状态、认知、关系与伏笔会显示在这里。
          </p>
        ) : (
          <div className="mt-2 space-y-3">
            {groupedMemory.map((group) => (
              <div key={group.type}>
                <div className="mb-1.5 flex items-center gap-1.5">
                  <Badge tone="indigo">{CATEGORY_LABEL[group.type]}</Badge>
                  <span className="text-[11px] text-slate-400">
                    {group.items.length} 条
                  </span>
                </div>
                <div className="space-y-1.5">
                  {group.items.map(renderMemoryItem)}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

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

      <Modal
        open={finalizeWarning !== null}
        onClose={() => setFinalizeWarning(null)}
        title="定稿前确认：最新一致性审查有违反项"
      >
        <div className="space-y-3">
          <p className="text-sm text-slate-700 dark:text-slate-200">
            本章最新一次一致性审查发现 {finalizeWarning?.issues.length ?? 0}{" "}
            条违反项。定稿不会自动修改正文，请确认是否仍然继续。
          </p>
          {finalizeWarning?.stale && (
            <p className="rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:bg-amber-950/30 dark:text-amber-200">
              这次审查之后正文或前文发生过修改，审查结果可能已过期，请结合当前正文判断。
            </p>
          )}
          <div className="max-h-[50vh] space-y-2 overflow-y-auto">
            {finalizeWarning?.issues.map((issue, index) => (
              <div
                key={`${issue.ref_id ?? "issue"}-${index}`}
                className="rounded-lg border border-rose-200 bg-rose-50/60 p-3 text-xs dark:border-rose-900 dark:bg-rose-950/30"
              >
                <div className="flex flex-wrap items-center gap-1.5">
                  <Badge tone="rose">违反</Badge>
                  <Badge tone="default">
                    {CHECK_TYPE_LABEL[issue.check_type] ?? "其他"}
                  </Badge>
                  {issue.ref_label && (
                    <span className="text-slate-500 dark:text-slate-400">
                      {issue.ref_label}
                    </span>
                  )}
                </div>
                <p className="mt-1.5 font-medium text-slate-800 dark:text-slate-100">
                  {issue.description}
                </p>
                {issue.evidence_quote && (
                  <p className="mt-1 border-l-2 border-rose-300 pl-2 text-[11px] italic text-slate-600 dark:border-rose-800 dark:text-slate-400">
                    “{issue.evidence_quote}”
                  </p>
                )}
              </div>
            ))}
          </div>
          <div className="flex justify-end gap-2 pt-1">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setFinalizeWarning(null)}
              disabled={finalizeMut.isPending}
            >
              取消，先修改正文
            </Button>
            <Button
              size="sm"
              onClick={confirmFinalize}
              disabled={finalizeMut.isPending}
            >
              {finalizeMut.isPending ? "正在定稿..." : "仍然定稿"}
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
};
