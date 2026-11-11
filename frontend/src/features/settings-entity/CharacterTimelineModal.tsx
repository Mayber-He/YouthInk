import React, { useState } from "react";
import {
  Clock,
  Edit3,
  Eye,
  EyeOff,
  HeartHandshake,
  Plus,
  RotateCcw,
  UserCheck,
} from "lucide-react";
import { Modal } from "@/components/ui/Modal";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import type {
  CharacterItem,
  CharacterMemoryItem,
  CharacterMemoryType,
  ChapterItem,
  ScheduleStatus,
} from "@/types/api";
import {
  useCreateCharacterMemory,
  useUpdateCharacterMemory,
} from "@/features/memory/api";
import { useCharacters, useCharacterTimeline } from "./api";

interface CharacterTimelineModalProps {
  novelUid: string;
  character: CharacterItem | null;
  chapters: ChapterItem[];
  onClose: () => void;
}

const STATE_FIELD_LABELS: Record<string, string> = {
  location: "当前位置/环境",
  body: "身体状态",
  emotion: "情绪与心理",
  goal: "当前目标",
  identity: "身份变化",
  item: "持有重要物品",
  appearance: "外貌变化",
};

const MEMORY_TYPE_META: Record<
  CharacterMemoryType,
  { label: string; tone: "indigo" | "amber" | "rose" | "emerald" | "default" }
> = {
  daily: { label: "日常认知", tone: "indigo" },
  schedule: { label: "临时安排", tone: "amber" },
  secret: { label: "秘密认知", tone: "rose" },
};

const SCHEDULE_STATUS_META: Record<
  ScheduleStatus,
  { label: string; tone: "amber" | "emerald" | "default" | "rose" }
> = {
  pending: { label: "待办", tone: "amber" },
  completed: { label: "已完成", tone: "emerald" },
  cancelled: { label: "已取消", tone: "default" },
  expired: { label: "已过期", tone: "rose" },
};

interface MemoryFormState {
  editingId: number | null;
  content: string;
  memoryType: CharacterMemoryType;
  timeScope: string;
  scheduleStatus: ScheduleStatus;
  resolvedChapterId: number | null;
  sourceMode: "pre_story" | "chapter";
  chapterId: number | null;
  learnedBy: string;
  sourceQuote: string;
  knowerIds: number[];
}

export const CharacterTimelineModal: React.FC<CharacterTimelineModalProps> = ({
  novelUid,
  character,
  chapters,
  onClose,
}) => {
  const [selectedSort, setSelectedSort] = useState<number | null>(null);
  const [typeFilter, setTypeFilter] = useState<CharacterMemoryType | "all">(
    "all"
  );
  const [formOpen, setFormOpen] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [form, setForm] = useState<MemoryFormState>({
    editingId: null,
    content: "",
    memoryType: "daily",
    timeScope: "",
    scheduleStatus: "pending",
    resolvedChapterId: null,
    sourceMode: "pre_story",
    chapterId: chapters[0]?.id ?? null,
    learnedBy: "",
    sourceQuote: "",
    knowerIds: character ? [character.id] : [],
  });

  const { data: snapshot, isLoading } = useCharacterTimeline(
    novelUid,
    character?.id ?? null,
    selectedSort
  );
  const { data: allCharacters = [] } = useCharacters(novelUid);
  const createMut = useCreateCharacterMemory(novelUid);
  const updateMut = useUpdateCharacterMemory(novelUid);

  if (!character) return null;

  const characterOptions =
    allCharacters.length > 0 ? allCharacters : [character];

  const normalizedMemories: CharacterMemoryItem[] =
    snapshot?.character_memories && snapshot.character_memories.length > 0
      ? snapshot.character_memories
      : (snapshot?.known_secrets ?? []).map((sec, idx) => ({
          id: sec.id ?? idx + 1,
          content: sec.content ?? sec.secret,
          secret: sec.secret,
          memory_type: sec.memory_type ?? "secret",
          time_scope: sec.time_scope ?? "",
          schedule_status: sec.schedule_status ?? "pending",
          effective_schedule_status:
            sec.effective_schedule_status ?? sec.schedule_status ?? "pending",
          related_record_id: null,
          knower_ids: sec.knower_ids ?? [character.id],
          knower_names: sec.knower_names ?? [character.name],
          learned_by: sec.learned_by ?? "",
          chapter_id: sec.chapter_id ?? null,
          chapter_title: sec.chapter_title ?? "",
          chapter_display_index: sec.chapter_display_index ?? null,
          chapter_sort_order: null,
          story_time: sec.story_time ?? "",
          source_quote: sec.source_quote ?? "",
          origin: sec.origin ?? "manual",
          confirm_status: "confirmed",
          is_disabled: Boolean(sec.is_disabled),
          is_stale: false,
          is_effective: !sec.is_disabled,
          resolved_chapter_id: sec.resolved_chapter_id ?? null,
          resolved_chapter_title: sec.resolved_chapter_title ?? "",
          resolved_chapter_display_index:
            sec.resolved_chapter_display_index ?? null,
          resolved_story_time: "",
          resolved_quote: "",
          resolution_record_id: null,
          created_at: "",
        }));

  const visibleMemories = normalizedMemories.filter((m) =>
    typeFilter === "all" ? true : m.memory_type === typeFilter
  );

  const openCreateForm = () => {
    setFormError(null);
    setForm({
      editingId: null,
      content: "",
      memoryType: "daily",
      timeScope: "",
      scheduleStatus: "pending",
      resolvedChapterId: null,
      sourceMode: "pre_story",
      chapterId: chapters[0]?.id ?? null,
      learnedBy: "",
      sourceQuote: "",
      knowerIds: [character.id],
    });
    setFormOpen(true);
  };

  const openEditForm = (item: CharacterMemoryItem) => {
    setFormError(null);
    setForm({
      editingId: item.id,
      content: item.content || item.secret,
      memoryType: item.memory_type ?? "secret",
      timeScope: item.time_scope ?? "",
      scheduleStatus:
        item.effective_schedule_status ?? item.schedule_status ?? "pending",
      resolvedChapterId: item.resolved_chapter_id ?? null,
      sourceMode: item.chapter_id ? "chapter" : "pre_story",
      chapterId: item.chapter_id ?? chapters[0]?.id ?? null,
      learnedBy: item.learned_by ?? "",
      sourceQuote: item.source_quote ?? "",
      knowerIds:
        item.knower_ids && item.knower_ids.length > 0
          ? item.knower_ids
          : [character.id],
    });
    setFormOpen(true);
  };

  const toggleKnower = (cid: number) => {
    setForm((prev) => {
      const exists = prev.knowerIds.includes(cid);
      const next = exists
        ? prev.knowerIds.filter((id) => id !== cid)
        : [...prev.knowerIds, cid];
      return { ...prev, knowerIds: next };
    });
  };

  const handleSaveMemory = async () => {
    setFormError(null);
    const trimmedContent = form.content.trim();
    if (!trimmedContent) {
      setFormError("请填写记忆内容。");
      return;
    }
    if (form.knowerIds.length === 0) {
      setFormError("请至少选择一位知情人物。");
      return;
    }
    if (form.memoryType === "schedule" && !form.timeScope.trim()) {
      setFormError("临时安排必须填写适用时间说明（如“今天早八”“开学第二天早晨”）。");
      return;
    }
    if (form.sourceMode === "chapter" && !form.chapterId) {
      setFormError("请选择获知章节，或切换为“故事开始前已知”。");
      return;
    }

    try {
      const resolvedChapterId =
        form.sourceMode === "chapter" ? form.chapterId : null;
      if (form.editingId === null) {
        await createMut.mutateAsync({
          content: trimmedContent,
          memory_type: form.memoryType,
          time_scope: form.timeScope.trim(),
          schedule_status:
            form.memoryType === "schedule" ? form.scheduleStatus : "pending",
          knower_ids: form.knowerIds,
          learned_by: form.learnedBy.trim(),
          chapter_id: resolvedChapterId,
          source_quote: form.sourceQuote.trim(),
        });
      } else {
        await updateMut.mutateAsync({
          id: form.editingId,
          input: {
            content: trimmedContent,
            memory_type: form.memoryType,
            time_scope: form.timeScope.trim(),
            schedule_status:
              form.memoryType === "schedule" ? form.scheduleStatus : "pending",
            resolved_chapter_id:
              form.memoryType === "schedule" &&
              form.scheduleStatus !== "pending"
                ? form.resolvedChapterId
                : null,
            knower_ids: form.knowerIds,
            learned_by: form.learnedBy.trim(),
            chapter_id: resolvedChapterId,
            clear_chapter: form.sourceMode === "pre_story",
            source_quote: form.sourceQuote.trim(),
          },
        });
      }
      setFormOpen(false);
    } catch (err) {
      setFormError(
        err instanceof Error ? err.message : "保存人物记忆失败，请重试。"
      );
    }
  };

  const handleToggleDisable = (item: CharacterMemoryItem) => {
    updateMut.mutate({
      id: item.id,
      input: { is_disabled: !item.is_disabled },
    });
  };

  return (
    <Modal
      open={Boolean(character)}
      onClose={onClose}
      title={`人物状态时间轴 · ${character.name}（设计文档 4.4 & 6.3）`}
      maxWidthClass="max-w-2xl"
    >
      <div className="space-y-4 text-xs">
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-slate-50 p-3 dark:bg-slate-800/50">
          <div className="flex items-center gap-2 font-medium text-slate-700 dark:text-slate-200">
            <Clock className="h-4 w-4 text-indigo-600" />
            <span>选择观测章节节点：</span>
          </div>
          <select
            value={selectedSort ?? ""}
            onChange={(e) =>
              setSelectedSort(e.target.value ? Number(e.target.value) : null)
            }
            className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs dark:border-slate-700 dark:bg-slate-900"
          >
            <option value="">最新已确认状态（全书当前）</option>
            {chapters.map((ch) => (
              <option key={ch.id} value={ch.sort_order}>
                第 {ch.display_index} 章：{ch.title} (sort={ch.sort_order})
              </option>
            ))}
          </select>
        </div>

        {isLoading || !snapshot ? (
          <p className="text-slate-400">正在回溯时序状态...</p>
        ) : (
          <div className="space-y-4">
            {/* 基准外貌 + 外貌变化 */}
            <div className="rounded-xl border border-slate-200 p-3.5 dark:border-slate-800">
              <div className="flex items-center gap-1.5 font-semibold text-slate-800 dark:text-slate-200">
                <UserCheck className="h-4 w-4 text-indigo-600" />
                合成有效外貌（基准外貌 + 最新外貌变化）
              </div>
              <p className="mt-1.5 text-slate-600 dark:text-slate-300">
                {snapshot.effective_appearance || "暂无外貌描述"}
              </p>
            </div>

            {/* 人物各维度状态 */}
            <div className="rounded-xl border border-slate-200 p-3.5 dark:border-slate-800">
              <div className="font-semibold text-slate-800 dark:text-slate-200">
                当前维度状态
              </div>
              {Object.keys(snapshot.current_states).length === 0 ? (
                <p className="mt-1.5 text-slate-400">
                  该章节节点及之前尚无已确认的状态变更记录（保持初始人物卡状态）。
                </p>
              ) : (
                <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
                  {Object.entries(snapshot.current_states).map(([fld, val]) => (
                    <div
                      key={fld}
                      className="rounded-lg bg-slate-50 p-2.5 dark:bg-slate-800/60"
                    >
                      <span className="font-medium text-indigo-600 dark:text-indigo-400">
                        {STATE_FIELD_LABELS[fld] || fld}：
                      </span>
                      <span className="text-slate-700 dark:text-slate-200">
                        {val}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* 关系状态 */}
            <div className="rounded-xl border border-slate-200 p-3.5 dark:border-slate-800">
              <div className="flex items-center gap-1.5 font-semibold text-slate-800 dark:text-slate-200">
                <HeartHandshake className="h-4 w-4 text-rose-500" />
                人物关系快照 ({snapshot.relationships.length})
              </div>
              {snapshot.relationships.length === 0 ? (
                <p className="mt-1.5 text-slate-400">暂无已确认的关系变更记录。</p>
              ) : (
                <div className="mt-2 space-y-2">
                  {snapshot.relationships.map((rel, i) => (
                    <div
                      key={i}
                      className="flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2 dark:bg-slate-800/60"
                    >
                      <span>
                        <strong>{rel.char_a_name}</strong> ↔{" "}
                        <strong>{rel.char_b_name}</strong>：{rel.rel_type}
                      </span>
                      <div className="flex items-center gap-1.5">
                        {rel.intimacy !== null && (
                          <Badge tone="rose">亲密度 {rel.intimacy}/10</Badge>
                        )}
                        {rel.publicity && <Badge>{rel.publicity}</Badge>}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* 人物记忆（日常认知 / 临时安排 / 秘密认知） */}
            <div className="rounded-xl border border-slate-200 p-3.5 dark:border-slate-800">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-1.5 font-semibold text-slate-800 dark:text-slate-200">
                  <Eye className="h-4 w-4 text-emerald-600" />
                  人物记忆 · 日常认知 / 临时安排 / 秘密认知 ({normalizedMemories.length})
                </div>
                <Button size="sm" onClick={openCreateForm}>
                  <Plus className="h-3.5 w-3.5" />
                  新增记忆
                </Button>
              </div>
              <p className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">
                作者手动保存的记忆直接生效；可按章节节点回看当时的临时安排待办状态，或随时编辑、停用与恢复。
              </p>

              {/* 类型筛选 */}
              <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
                {(
                  [
                    ["all", "全部"],
                    ["daily", "日常认知"],
                    ["schedule", "临时安排"],
                    ["secret", "秘密认知"],
                  ] as const
                ).map(([key, label]) => (
                  <button
                    key={key}
                    type="button"
                    onClick={() => setTypeFilter(key)}
                    className={`rounded-lg px-2.5 py-1 text-[11px] font-medium cursor-pointer ${
                      typeFilter === key
                        ? "bg-indigo-600 text-white"
                        : "bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-300"
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>

              {/* 新增 / 编辑表单 */}
              {formOpen && (
                <div className="mt-3 space-y-3 rounded-xl border border-indigo-200 bg-indigo-50/40 p-3 dark:border-indigo-900 dark:bg-indigo-950/20">
                  <div className="flex items-center justify-between font-semibold text-slate-800 dark:text-slate-200">
                    <span>
                      {form.editingId === null
                        ? "新增人物记忆（保存后直接生效）"
                        : `编辑人物记忆 #${form.editingId}`}
                    </span>
                  </div>

                  <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
                    <div>
                      <label className="mb-1 block text-[11px] font-medium text-slate-600 dark:text-slate-300">
                        记忆类别
                      </label>
                      <select
                        value={form.memoryType}
                        onChange={(e) =>
                          setForm((prev) => ({
                            ...prev,
                            memoryType: e.target.value as CharacterMemoryType,
                          }))
                        }
                        className="w-full rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-xs dark:border-slate-700 dark:bg-slate-900"
                      >
                        <option value="daily">日常认知（偏好、习惯、常态认知）</option>
                        <option value="schedule">临时安排（日程、约定、待办事项）</option>
                        <option value="secret">秘密认知（隐情、关键秘密）</option>
                      </select>
                    </div>

                    <div>
                      <label className="mb-1 block text-[11px] font-medium text-slate-600 dark:text-slate-300">
                        适用时间说明
                        {form.memoryType === "schedule" && (
                          <span className="ml-1 text-rose-600">*必填</span>
                        )}
                      </label>
                      <input
                        type="text"
                        value={form.timeScope}
                        onChange={(e) =>
                          setForm((prev) => ({ ...prev, timeScope: e.target.value }))
                        }
                        placeholder={
                          form.memoryType === "schedule"
                            ? "例如：今天早八、开学第二天早晨"
                            : "可选，如：高三上学期、长期有效"
                        }
                        className="w-full rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-xs dark:border-slate-700 dark:bg-slate-900"
                      />
                    </div>
                  </div>

                  <div>
                    <label className="mb-1 block text-[11px] font-medium text-slate-600 dark:text-slate-300">
                      记忆内容
                    </label>
                    <input
                      type="text"
                      value={form.content}
                      onChange={(e) =>
                        setForm((prev) => ({ ...prev, content: e.target.value }))
                      }
                      placeholder="例如：裴南栀喜欢吃草莓味甜食 / 当天早八有高等数学课"
                      className="w-full rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-xs dark:border-slate-700 dark:bg-slate-900"
                    />
                  </div>

                  <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
                    <div>
                      <label className="mb-1 block text-[11px] font-medium text-slate-600 dark:text-slate-300">
                        获知时间节点
                      </label>
                      <select
                        value={form.sourceMode}
                        onChange={(e) =>
                          setForm((prev) => ({
                            ...prev,
                            sourceMode: e.target.value as "pre_story" | "chapter",
                          }))
                        }
                        className="w-full rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-xs dark:border-slate-700 dark:bg-slate-900"
                      >
                        <option value="pre_story">故事开始前已知</option>
                        <option value="chapter">具体获知章节</option>
                      </select>
                    </div>

                    {form.sourceMode === "chapter" && (
                      <div>
                        <label className="mb-1 block text-[11px] font-medium text-slate-600 dark:text-slate-300">
                          选择获知章节
                        </label>
                        <select
                          value={form.chapterId ?? ""}
                          onChange={(e) =>
                            setForm((prev) => ({
                              ...prev,
                              chapterId: e.target.value
                                ? Number(e.target.value)
                                : null,
                            }))
                          }
                          className="w-full rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-xs dark:border-slate-700 dark:bg-slate-900"
                        >
                          <option value="">请选择章节</option>
                          {chapters.map((ch) => (
                            <option key={ch.id} value={ch.id}>
                              第 {ch.display_index} 章《{ch.title}》
                            </option>
                          ))}
                        </select>
                      </div>
                    )}
                  </div>

                  {form.memoryType === "schedule" && (
                    <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
                      <div>
                        <label className="mb-1 block text-[11px] font-medium text-slate-600 dark:text-slate-300">
                          安排状态
                        </label>
                        <select
                          value={form.scheduleStatus}
                          onChange={(e) =>
                            setForm((prev) => ({
                              ...prev,
                              scheduleStatus: e.target.value as ScheduleStatus,
                            }))
                          }
                          className="w-full rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-xs dark:border-slate-700 dark:bg-slate-900"
                        >
                          <option value="pending">待办（生效中）</option>
                          <option value="completed">已完成</option>
                          <option value="cancelled">已取消</option>
                          <option value="expired">已过期</option>
                        </select>
                      </div>

                      {form.scheduleStatus !== "pending" && (
                        <div>
                          <label className="mb-1 block text-[11px] font-medium text-slate-600 dark:text-slate-300">
                            状态变更章节（可选，用于保留早期章节待办状态）
                          </label>
                          <select
                            value={form.resolvedChapterId ?? ""}
                            onChange={(e) =>
                              setForm((prev) => ({
                                ...prev,
                                resolvedChapterId: e.target.value
                                  ? Number(e.target.value)
                                  : null,
                              }))
                            }
                            className="w-full rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-xs dark:border-slate-700 dark:bg-slate-900"
                          >
                            <option value="">直接更新原记录</option>
                            {chapters.map((ch) => (
                              <option key={ch.id} value={ch.id}>
                                第 {ch.display_index} 章《{ch.title}》
                              </option>
                            ))}
                          </select>
                        </div>
                      )}
                    </div>
                  )}

                  <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
                    <div>
                      <label className="mb-1 block text-[11px] font-medium text-slate-600 dark:text-slate-300">
                        获知方式
                      </label>
                      <input
                        type="text"
                        value={form.learnedBy}
                        onChange={(e) =>
                          setForm((prev) => ({
                            ...prev,
                            learnedBy: e.target.value,
                          }))
                        }
                        placeholder="如：亲耳听到、亲眼看到、共同约定"
                        className="w-full rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-xs dark:border-slate-700 dark:bg-slate-900"
                      />
                    </div>
                    <div>
                      <label className="mb-1 block text-[11px] font-medium text-slate-600 dark:text-slate-300">
                        原文证据（可选）
                      </label>
                      <input
                        type="text"
                        value={form.sourceQuote}
                        onChange={(e) =>
                          setForm((prev) => ({
                            ...prev,
                            sourceQuote: e.target.value,
                          }))
                        }
                        placeholder="摘录正文证据原句"
                        className="w-full rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-xs dark:border-slate-700 dark:bg-slate-900"
                      />
                    </div>
                  </div>

                  <div>
                    <label className="mb-1 block text-[11px] font-medium text-slate-600 dark:text-slate-300">
                      知情人物（仅勾选人物在生成时拥有该记忆）
                    </label>
                    <div className="flex flex-wrap gap-2">
                      {characterOptions.map((c) => {
                        const checked = form.knowerIds.includes(c.id);
                        return (
                          <label
                            key={c.id}
                            className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs cursor-pointer ${
                              checked
                                ? "border-indigo-500 bg-indigo-50 text-indigo-800 dark:border-indigo-600 dark:bg-indigo-950/60 dark:text-indigo-200"
                                : "border-slate-200 bg-white text-slate-600 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300"
                            }`}
                          >
                            <input
                              type="checkbox"
                              checked={checked}
                              onChange={() => toggleKnower(c.id)}
                              className="h-3.5 w-3.5"
                            />
                            <span>{c.name}</span>
                          </label>
                        );
                      })}
                    </div>
                  </div>

                  {formError && (
                    <p className="rounded-lg bg-rose-50 px-2.5 py-1.5 text-[11px] text-rose-700 dark:bg-rose-950/40 dark:text-rose-300">
                      {formError}
                    </p>
                  )}

                  <div className="flex justify-end gap-2">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setFormOpen(false)}
                    >
                      取消
                    </Button>
                    <Button
                      size="sm"
                      onClick={handleSaveMemory}
                      disabled={createMut.isPending || updateMut.isPending}
                    >
                      {form.editingId === null ? "保存新增" : "保存修改"}
                    </Button>
                  </div>
                </div>
              )}

              {visibleMemories.length === 0 ? (
                <p className="mt-2.5 text-slate-400">
                  该章节节点前尚未记录此类人物记忆。
                </p>
              ) : (
                <ul className="mt-2.5 space-y-2">
                  {visibleMemories.map((mem) => {
                    const mType = mem.memory_type ?? "secret";
                    const typeMeta =
                      MEMORY_TYPE_META[mType] ?? MEMORY_TYPE_META.secret;
                    const effStatus =
                      mem.effective_schedule_status ??
                      mem.schedule_status ??
                      "pending";
                    const schedMeta =
                      SCHEDULE_STATUS_META[effStatus] ??
                      SCHEDULE_STATUS_META.pending;
                    const sourceLabel = mem.chapter_id
                      ? `第 ${mem.chapter_display_index ?? mem.chapter_id} 章${
                          mem.chapter_title ? `《${mem.chapter_title}》` : ""
                        }`
                      : "故事开始前已知";

                    return (
                      <li
                        key={mem.id}
                        className={`rounded-lg border px-3 py-2.5 ${
                          mem.is_disabled
                            ? "border-slate-200 bg-slate-100/70 text-slate-400 dark:border-slate-800 dark:bg-slate-900/40"
                            : "border-emerald-200/80 bg-emerald-50/50 text-slate-800 dark:border-emerald-900/60 dark:bg-emerald-950/30 dark:text-slate-100"
                        }`}
                      >
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <div className="flex flex-wrap items-center gap-1.5">
                            <Badge tone={typeMeta.tone}>{typeMeta.label}</Badge>
                            {mType === "schedule" && (
                              <Badge tone={schedMeta.tone}>
                                安排状态：{schedMeta.label}
                                {effStatus !== "pending" &&
                                mem.resolved_chapter_display_index
                                  ? `（第 ${mem.resolved_chapter_display_index} 章）`
                                  : ""}
                              </Badge>
                            )}
                            {mem.is_disabled ? (
                              <Badge tone="default">已停用</Badge>
                            ) : (
                              <Badge tone="emerald">生效中</Badge>
                            )}
                            <span className="text-[11px] text-slate-500 dark:text-slate-400">
                              来源：{sourceLabel}
                              {mem.story_time ? ` · ${mem.story_time}` : ""}
                            </span>
                          </div>

                          <div className="flex items-center gap-1">
                            <Button
                              variant="ghost"
                              size="sm"
                              className="h-6 px-2 text-[11px]"
                              onClick={() => openEditForm(mem)}
                            >
                              <Edit3 className="h-3 w-3" />
                              编辑
                            </Button>
                            <Button
                              variant="outline"
                              size="sm"
                              className="h-6 px-2 text-[11px]"
                              disabled={updateMut.isPending}
                              onClick={() => handleToggleDisable(mem)}
                            >
                              {mem.is_disabled ? (
                                <>
                                  <RotateCcw className="h-3 w-3" />
                                  恢复
                                </>
                              ) : (
                                <>
                                  <EyeOff className="h-3 w-3" />
                                  停用
                                </>
                              )}
                            </Button>
                          </div>
                        </div>

                        <div
                          className={`mt-1.5 font-semibold ${
                            mem.is_disabled ? "line-through" : ""
                          }`}
                        >
                          {mem.content || mem.secret}
                        </div>

                        <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-slate-600 dark:text-slate-300">
                          {mem.knower_names && mem.knower_names.length > 0 && (
                            <span>
                              知情者：{mem.knower_names.join("、")}
                            </span>
                          )}
                          {mem.learned_by && (
                            <span>获知方式：{mem.learned_by}</span>
                          )}
                          {mem.time_scope && (
                            <span>适用时间：{mem.time_scope}</span>
                          )}
                        </div>

                        {mem.source_quote && (
                          <p className="mt-1 border-l-2 border-emerald-300 pl-2 text-[11px] italic text-slate-500 dark:border-emerald-800 dark:text-slate-400">
                            “{mem.source_quote}”
                          </p>
                        )}
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          </div>
        )}
      </div>
    </Modal>
  );
};
