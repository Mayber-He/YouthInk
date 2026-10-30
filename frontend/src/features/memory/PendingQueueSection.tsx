import React, { useState } from "react";
import {
  Check,
  CheckCheck,
  CheckSquare,
  ExternalLink,
  RefreshCw,
  Search,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/common/EmptyState";
import { useUiStore } from "@/stores/uiStore";
import {
  useBatchPendingAction,
  usePendingQueue,
  useRagSearch,
  useRebuildMemoryIndex,
  useUpdatePendingItem,
} from "./api";
import type { MemoryItemCategory, PendingQueueItem } from "./types";

interface PendingQueueSectionProps {
  novelUid: string;
}

const TYPE_META: Record<
  MemoryItemCategory,
  { label: string; tone: "indigo" | "amber" | "rose" | "emerald" | "default" }
> = {
  char_state: { label: "人物状态", tone: "amber" },
  cognitive: { label: "秘密认知", tone: "rose" },
  relationship: { label: "人物关系", tone: "indigo" },
  foreshadowing: { label: "埋设/回收伏笔", tone: "emerald" },
  fact: { label: "剧情事实", tone: "default" },
};

export const PendingQueueSection: React.FC<PendingQueueSectionProps> = ({
  novelUid,
}) => {
  const { setSelectedChapterId, setActiveSection } = useUiStore();
  const [typeFilter, setTypeFilter] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<string>("pending");
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [editText, setEditText] = useState("");
  const [ragQuery, setRagQuery] = useState("");

  const { data: items = [], isLoading } = usePendingQueue(
    novelUid,
    typeFilter || undefined,
    null,
    statusFilter
  );
  const updateMut = useUpdatePendingItem(novelUid);
  const batchMut = useBatchPendingAction(novelUid);
  const ragMut = useRagSearch(novelUid);
  const rebuildMut = useRebuildMemoryIndex(novelUid);

  const handleBatch = (action: "confirm" | "discard") => {
    if (items.length === 0) return;
    batchMut.mutate({
      action,
      items: items.map((i) => ({ item_type: i.item_type, id: i.id })),
    });
  };

  const handleJumpChapter = (chapterId: number | null) => {
    if (!chapterId) return;
    setSelectedChapterId(chapterId);
    setActiveSection("writing");
  };

  const submitEdit = (item: PendingQueueItem) => {
    updateMut.mutate(
      {
        item_type: item.item_type,
        id: item.id,
        action: "edit",
        updated_text: editText.trim(),
      },
      { onSuccess: () => setEditingKey(null) }
    );
  };

  return (
    <div className="mx-auto max-w-5xl space-y-6 p-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="flex items-center gap-2 text-lg font-bold text-slate-900 dark:text-slate-100">
            <CheckSquare className="h-5 w-5 text-indigo-600" />
            待确认记忆队列 & 混合检索中心
          </h2>
          <p className="mt-0.5 text-xs text-slate-500">
            确认后才生效：未确认的状态变更与秘密认知不会注入后续章节上下文，杜绝连环幻觉污染。
          </p>
        </div>

        {statusFilter === "pending" && items.length > 0 && (
          <div className="flex items-center gap-2">
            <Button size="sm" onClick={() => handleBatch("confirm")} disabled={batchMut.isPending}>
              <CheckCheck className="h-3.5 w-3.5" />
              一键全部确认 ({items.length})
            </Button>
            <Button variant="outline" size="sm" onClick={() => handleBatch("discard")} disabled={batchMut.isPending}>
              <X className="h-3.5 w-3.5" />
              全部丢弃
            </Button>
          </div>
        )}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-slate-900">
        <div className="flex flex-wrap items-center gap-1.5">
          {[
            ["", "全部类型"],
            ["char_state", "人物状态"],
            ["cognitive", "秘密认知"],
            ["relationship", "人物关系"],
            ["foreshadowing", "伏笔"],
            ["fact", "事实"],
          ].map(([k, label]) => (
            <button
              key={k}
              type="button"
              onClick={() => setTypeFilter(k)}
              className={`rounded-lg px-2.5 py-1 text-xs font-medium cursor-pointer ${
                typeFilter === k
                  ? "bg-indigo-600 text-white"
                  : "bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-300"
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-1.5">
          {[
            ["pending", "待确认"],
            ["confirmed", "已确认"],
            ["discarded", "已丢弃"],
          ].map(([st, label]) => (
            <button
              key={st}
              type="button"
              onClick={() => setStatusFilter(st)}
              className={`rounded-lg px-2.5 py-1 text-xs font-medium cursor-pointer ${
                statusFilter === st
                  ? "bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900"
                  : "text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {isLoading ? (
        <p className="text-xs text-slate-400">正在加载记忆队列...</p>
      ) : items.length === 0 ? (
        <EmptyState
          title={statusFilter === "pending" ? "当前没有待确认的设定变更" : "该筛选条件下暂无记录"}
          description="定稿章节后抽取的高风险人物状态、关系与秘密认知会在此处排队等待确认。"
        />
      ) : (
        <div className="space-y-2.5">
          {items.map((item) => {
            const key = `${item.item_type}-${item.id}`;
            const meta = TYPE_META[item.item_type] ?? TYPE_META.fact;
            const isEditing = editingKey === key;

            return (
              <div
                key={key}
                className="rounded-xl border border-slate-200 bg-white p-4 shadow-2xs dark:border-slate-800 dark:bg-slate-900"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <Badge tone={meta.tone}>{meta.label}</Badge>
                    {item.chapter_id && (
                      <button
                        type="button"
                        onClick={() => handleJumpChapter(item.chapter_id)}
                        className="flex items-center gap-1 text-xs font-medium text-indigo-600 hover:underline cursor-pointer dark:text-indigo-400"
                      >
                        第 {item.chapter_display_index ?? item.chapter_id} 章《{item.chapter_title}》
                        <ExternalLink className="h-3 w-3" />
                      </button>
                    )}
                  </div>

                  <div className="flex items-center gap-1.5">
                    {!isEditing && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => {
                          setEditingKey(key);
                          setEditText(item.summary_text);
                        }}
                      >
                        编辑
                      </Button>
                    )}
                    {item.status !== "confirmed" && (
                      <Button
                        size="sm"
                        onClick={() =>
                          updateMut.mutate({ item_type: item.item_type, id: item.id, action: "confirm" })
                        }
                      >
                        <Check className="h-3.5 w-3.5" />
                        确认生效
                      </Button>
                    )}
                    {item.status !== "discarded" && (
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() =>
                          updateMut.mutate({ item_type: item.item_type, id: item.id, action: "discard" })
                        }
                      >
                        <X className="h-3.5 w-3.5" />
                        丢弃
                      </Button>
                    )}
                  </div>
                </div>

                {isEditing ? (
                  <div className="mt-2 flex items-center gap-2">
                    <input
                      type="text"
                      value={editText}
                      onChange={(e) => setEditText(e.target.value)}
                      className="flex-1 rounded-lg border border-indigo-300 px-3 py-1.5 text-xs dark:border-indigo-700 dark:bg-slate-800"
                    />
                    <Button size="sm" onClick={() => submitEdit(item)}>保存并确认</Button>
                    <Button variant="ghost" size="sm" onClick={() => setEditingKey(null)}>取消</Button>
                  </div>
                ) : (
                  <p className="mt-2 text-sm font-medium text-slate-800 dark:text-slate-100">{item.summary_text}</p>
                )}

                {item.source_quote && (
                  <button
                    type="button"
                    onClick={() => handleJumpChapter(item.chapter_id)}
                    className="mt-2 block w-full rounded-lg bg-slate-50 px-3 py-1.5 text-left text-xs italic text-slate-500 hover:bg-indigo-50/50 cursor-pointer dark:bg-slate-800/60"
                  >
                    原文出处（点击跳转定位）：“{item.source_quote}”
                  </button>
                )}
              </div>
            );
          })}
        </div>
      )}

      <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-2xs dark:border-slate-800 dark:bg-slate-900">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h3 className="text-xs font-semibold text-slate-800 dark:text-slate-200">
              三层混合检索（Metadata 过滤 + 向量语义 + jieba FTS5 + RRF 融合）
            </h3>
            <p className="text-[11px] text-slate-500">
              检索已定稿章节的历史场景片段，或切换 Embedding 模型后一键重建全书索引。
            </p>
          </div>
          <Button variant="outline" size="sm" onClick={() => rebuildMut.mutate()} disabled={rebuildMut.isPending}>
            <RefreshCw className="h-3.5 w-3.5" />
            一键重建全书索引
          </Button>
        </div>

        {rebuildMut.data && (
          <p className="mt-2 text-xs text-emerald-600">
            索引重建完成：已重算 {rebuildMut.data.chapters_reindexed} 章，共 {rebuildMut.data.chunks_indexed} 个向量片段。
          </p>
        )}

        <div className="mt-3 flex gap-2">
          <input
            type="text"
            value={ragQuery}
            onChange={(e) => setRagQuery(e.target.value)}
            placeholder="输入剧情关键词、道具名或伏笔描述测试 RRF 混合召回..."
            className="flex-1 rounded-lg border border-slate-200 px-3 py-1.5 text-xs dark:border-slate-700 dark:bg-slate-800"
          />
          <Button size="sm" onClick={() => ragQuery.trim() && ragMut.mutate({ q: ragQuery })} disabled={ragMut.isPending}>
            <Search className="h-3.5 w-3.5" />
            混合检索
          </Button>
        </div>

        {ragMut.data && (
          <div className="mt-3 space-y-2">
            {ragMut.data.embedding_model_mismatch && (
              <div className="rounded-lg bg-amber-50 p-2 text-xs text-amber-800">
                检测到当前 Embedding 模型与历史向量不一致，请点击右上角「一键重建全书索引」。
              </div>
            )}
            {ragMut.data.hits.map((hit) => (
              <div
                key={hit.chunk_id}
                className="rounded-lg border border-slate-100 bg-slate-50 p-2.5 text-xs dark:border-slate-800 dark:bg-slate-800/50"
              >
                <div className="flex items-center justify-between text-[11px] text-slate-500">
                  <span>章节 #{hit.chapter_id} · 召回源：{hit.source.toUpperCase()}</span>
                  <span>RRF 得分：{hit.rrf_score}</span>
                </div>
                <p className="mt-1 text-slate-700 dark:text-slate-300">{hit.text}</p>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
