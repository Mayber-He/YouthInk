import React, { useState } from "react";
import {
  Check,
  CheckCheck,
  CheckSquare,
  ExternalLink,
  EyeOff,
  RefreshCw,
  RotateCcw,
  Search,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/common/EmptyState";
import { useUiStore } from "@/stores/uiStore";
import type { CharacterMemoryType, ScheduleStatus } from "@/types/api";
import {
  useBatchPendingAction,
  usePendingQueue,
  useRagSearch,
  useRebuildMemoryIndex,
  useSetMemoryItemDisabled,
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
  cognitive: { label: "人物记忆", tone: "rose" },
  relationship: { label: "人物关系", tone: "indigo" },
  foreshadowing: { label: "埋设/回收伏笔", tone: "emerald" },
  fact: { label: "剧情事实", tone: "default" },
  constraint_check: { label: "约束检查", tone: "rose" },
};

const MEMORY_TYPE_LABEL: Record<string, string> = {
  daily: "日常认知",
  schedule: "临时安排",
  secret: "秘密认知",
};

const SCHEDULE_STATUS_LABEL: Record<string, string> = {
  pending: "待办",
  completed: "已完成",
  cancelled: "已取消",
  expired: "已过期",
};

export const PendingQueueSection: React.FC<PendingQueueSectionProps> = ({
  novelUid,
}) => {
  const { setSelectedChapterId, setActiveSection } = useUiStore();
  const [typeFilter, setTypeFilter] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<string>("pending");
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [editText, setEditText] = useState("");
  const [editMemoryType, setEditMemoryType] =
    useState<CharacterMemoryType>("secret");
  const [editTimeScope, setEditTimeScope] = useState("");
  const [editScheduleStatus, setEditScheduleStatus] =
    useState<ScheduleStatus>("pending");
  const [editLearnedBy, setEditLearnedBy] = useState("");
  const [ragQuery, setRagQuery] = useState("");

  const { data: items = [], isLoading } = usePendingQueue(
    novelUid,
    typeFilter || undefined,
    null,
    statusFilter
  );
  const updateMut = useUpdatePendingItem(novelUid);
  const disableMut = useSetMemoryItemDisabled(novelUid);
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

  const startEdit = (item: PendingQueueItem, key: string) => {
    setEditingKey(key);
    if (item.item_type === "cognitive") {
      setEditText(String(item.raw_payload.secret || item.summary_text || ""));
      setEditMemoryType(
        (String(
          item.raw_payload.memory_type || "secret"
        ) as CharacterMemoryType) || "secret"
      );
      setEditTimeScope(String(item.raw_payload.time_scope || ""));
      setEditScheduleStatus(
        (String(
          item.raw_payload.schedule_status || "pending"
        ) as ScheduleStatus) || "pending"
      );
      setEditLearnedBy(String(item.raw_payload.learned_by || ""));
    } else {
      setEditText(item.summary_text);
    }
  };

  const submitEdit = (item: PendingQueueItem) => {
    updateMut.mutate(
      {
        item_type: item.item_type,
        id: item.id,
        action: "edit",
        updated_text: editText.trim(),
        ...(item.item_type === "cognitive"
          ? {
              memory_type: editMemoryType,
              time_scope: editTimeScope.trim(),
              schedule_status:
                editMemoryType === "schedule" ? editScheduleStatus : "pending",
              learned_by: editLearnedBy.trim(),
            }
          : {}),
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
            确认后才生效：未确认的状态变更与人物记忆（日常认知、临时安排、秘密认知）不会注入后续章节上下文，杜绝连环幻觉污染。
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
            ["cognitive", "人物记忆"],
            ["relationship", "人物关系"],
            ["foreshadowing", "伏笔"],
            ["fact", "事实"],
            ["constraint_check", "约束检查"],
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
          description="定稿章节后抽取的高风险人物状态、关系与人物记忆会在此处排队等待确认。"
        />
      ) : (
        <div className="space-y-2.5">
          {items.map((item) => {
            const key = `${item.item_type}-${item.id}`;
            const meta = TYPE_META[item.item_type] ?? TYPE_META.fact;
            const isEditing = editingKey === key;
            const memType =
              item.item_type === "cognitive"
                ? String(item.raw_payload.memory_type || "secret")
                : "";
            const schedStatus =
              item.item_type === "cognitive"
                ? String(item.raw_payload.schedule_status || "pending")
                : "";
            const timeScope =
              item.item_type === "cognitive"
                ? String(item.raw_payload.time_scope || "")
                : "";
            const knowerNames =
              item.item_type === "cognitive" &&
              Array.isArray(item.raw_payload.knower_names)
                ? (item.raw_payload.knower_names as string[])
                : [];
            const learnedBy =
              item.item_type === "cognitive"
                ? String(item.raw_payload.learned_by || "")
                : "";

            return (
              <div
                key={key}
                className="rounded-xl border border-slate-200 bg-white p-4 shadow-2xs dark:border-slate-800 dark:bg-slate-900"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge tone={meta.tone}>{meta.label}</Badge>
                    {item.item_type === "cognitive" && memType && (
                      <Badge
                        tone={
                          memType === "daily"
                            ? "indigo"
                            : memType === "schedule"
                              ? "amber"
                              : "rose"
                        }
                      >
                        {MEMORY_TYPE_LABEL[memType] || "秘密认知"}
                      </Badge>
                    )}
                    {item.item_type === "cognitive" && memType === "schedule" && (
                      <Badge tone={schedStatus === "pending" ? "amber" : "emerald"}>
                        安排状态：{SCHEDULE_STATUS_LABEL[schedStatus] || schedStatus}
                      </Badge>
                    )}
                    {item.is_disabled && <Badge tone="default">已停用·不注入</Badge>}
                    {item.chapter_id ? (
                      <button
                        type="button"
                        onClick={() => handleJumpChapter(item.chapter_id)}
                        className="flex items-center gap-1 text-xs font-medium text-indigo-600 hover:underline cursor-pointer dark:text-indigo-400"
                      >
                        第 {item.chapter_display_index ?? item.chapter_id} 章《{item.chapter_title}》
                        <ExternalLink className="h-3 w-3" />
                      </button>
                    ) : (
                      item.item_type === "cognitive" && (
                        <span className="text-xs text-slate-500">故事开始前已知</span>
                      )
                    )}
                  </div>

                  <div className="flex items-center gap-1.5">
                    {!isEditing && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => startEdit(item, key)}
                      >
                        编辑
                      </Button>
                    )}
                    {item.status === "confirmed" &&
                      item.item_type !== "constraint_check" && (
                        <Button
                          variant="outline"
                          size="sm"
                          disabled={disableMut.isPending}
                          onClick={() =>
                            disableMut.mutate({
                              item_type: item.item_type as Exclude<
                                MemoryItemCategory,
                                "constraint_check"
                              >,
                              id: item.id,
                              is_disabled: !item.is_disabled,
                            })
                          }
                        >
                          {item.is_disabled ? (
                            <>
                              <RotateCcw className="h-3.5 w-3.5" />
                              恢复注入
                            </>
                          ) : (
                            <>
                              <EyeOff className="h-3.5 w-3.5" />
                              停用注入
                            </>
                          )}
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
                  <div className="mt-2 space-y-2">
                    <div className="flex items-center gap-2">
                      <input
                        type="text"
                        value={editText}
                        onChange={(e) => setEditText(e.target.value)}
                        className="flex-1 rounded-lg border border-indigo-300 px-3 py-1.5 text-xs dark:border-indigo-700 dark:bg-slate-800"
                      />
                      <Button size="sm" onClick={() => submitEdit(item)}>保存并确认</Button>
                      <Button variant="ghost" size="sm" onClick={() => setEditingKey(null)}>取消</Button>
                    </div>
                    {item.item_type === "cognitive" && (
                      <div className="grid grid-cols-1 gap-2 sm:grid-cols-4">
                        <select
                          value={editMemoryType}
                          onChange={(e) =>
                            setEditMemoryType(
                              e.target.value as CharacterMemoryType
                            )
                          }
                          className="rounded-lg border border-slate-300 bg-white px-2.5 py-1 text-xs dark:border-slate-700 dark:bg-slate-800"
                        >
                          <option value="daily">日常认知</option>
                          <option value="schedule">临时安排</option>
                          <option value="secret">秘密认知</option>
                        </select>
                        <input
                          type="text"
                          value={editTimeScope}
                          onChange={(e) => setEditTimeScope(e.target.value)}
                          placeholder="适用时间说明（如：今天早八）"
                          className="rounded-lg border border-slate-300 bg-white px-2.5 py-1 text-xs dark:border-slate-700 dark:bg-slate-800"
                        />
                        {editMemoryType === "schedule" && (
                          <select
                            value={editScheduleStatus}
                            onChange={(e) =>
                              setEditScheduleStatus(
                                e.target.value as ScheduleStatus
                              )
                            }
                            className="rounded-lg border border-slate-300 bg-white px-2.5 py-1 text-xs dark:border-slate-700 dark:bg-slate-800"
                          >
                            <option value="pending">待办</option>
                            <option value="completed">已完成</option>
                            <option value="cancelled">已取消</option>
                            <option value="expired">已过期</option>
                          </select>
                        )}
                        <input
                          type="text"
                          value={editLearnedBy}
                          onChange={(e) => setEditLearnedBy(e.target.value)}
                          placeholder="获知方式"
                          className="rounded-lg border border-slate-300 bg-white px-2.5 py-1 text-xs dark:border-slate-700 dark:bg-slate-800"
                        />
                      </div>
                    )}
                  </div>
                ) : (
                  <>
                    <p className="mt-2 text-sm font-medium text-slate-800 dark:text-slate-100">
                      {item.summary_text}
                    </p>
                    {item.item_type === "cognitive" &&
                      (knowerNames.length > 0 || timeScope || learnedBy) && (
                        <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500 dark:text-slate-400">
                          {knowerNames.length > 0 && (
                            <span>知情人物：{knowerNames.join("、")}</span>
                          )}
                          {timeScope && <span>适用时间：{timeScope}</span>}
                          {learnedBy && <span>获知方式：{learnedBy}</span>}
                        </div>
                      )}
                  </>
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
            {ragMut.data.embedding_error && (
              <div role="alert" className="rounded-lg bg-rose-50 p-2 text-xs text-rose-800 dark:bg-rose-950/40 dark:text-rose-200">
                向量模型不可用：{ragMut.data.embedding_error}（以下仅为全文检索 FTS 结果）
              </div>
            )}
            {!ragMut.data.embedding_error && ragMut.data.embedding_model_mismatch && (
              <div className="rounded-lg bg-amber-50 p-2 text-xs text-amber-800">
                向量索引需要重建：检测到旧版 256 维哈希向量，与当前 {ragMut.data.embedding_dimension || 1024} 维模型不兼容；
                不兼容章节暂不参与向量检索。请点击右上角「一键重建全书索引」。
              </div>
            )}
            {ragMut.data.vector_index_pending_rebuild && (
              <div role="alert" className="rounded-lg bg-amber-50 p-2 text-xs text-amber-800">
                向量索引待重建：{ragMut.data.vector_index_error || "上次索引失败"}；
                以下结果可能缺少部分章节的向量召回，全文检索 FTS 不受影响。
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
