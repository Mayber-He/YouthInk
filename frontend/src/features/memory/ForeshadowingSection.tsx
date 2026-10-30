import React, { useState } from "react";
import { GitBranch, Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/common/EmptyState";
import {
  useCreateForeshadow,
  useDeleteForeshadow,
  useForeshadowingList,
  useUpdateForeshadow,
} from "./api";
import type { ForeshadowStatus } from "./types";

interface ForeshadowingSectionProps {
  novelUid: string;
}

const STATUS_META: Record<
  ForeshadowStatus,
  { label: string; tone: "amber" | "indigo" | "emerald" | "default" }
> = {
  planted: { label: "已埋设", tone: "amber" },
  hinted: { label: "已暗示推进", tone: "indigo" },
  recovered: { label: "已回收", tone: "emerald" },
  abandoned: { label: "已废弃", tone: "default" },
};

export const ForeshadowingSection: React.FC<ForeshadowingSectionProps> = ({
  novelUid,
}) => {
  const [statusFilter, setStatusFilter] = useState<string>("");
  const { data: items = [], isLoading } = useForeshadowingList(
    novelUid,
    statusFilter || undefined
  );
  const createMut = useCreateForeshadow(novelUid);
  const updateMut = useUpdateForeshadow(novelUid);
  const deleteMut = useDeleteForeshadow(novelUid);

  const [newDesc, setNewDesc] = useState("");
  const [newStart, setNewStart] = useState("");
  const [newEnd, setNewEnd] = useState("");

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newDesc.trim()) return;
    await createMut.mutateAsync({
      description: newDesc.trim(),
      plan_recover_start: newStart ? Number(newStart) : null,
      plan_recover_end: newEnd ? Number(newEnd) : null,
      status: "planted",
    });
    setNewDesc("");
    setNewStart("");
    setNewEnd("");
  };

  return (
    <div className="mx-auto max-w-5xl space-y-6 p-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="flex items-center gap-2 text-lg font-bold text-slate-900 dark:text-slate-100">
            <GitBranch className="h-5 w-5 text-indigo-600" />
            伏笔台账管理
          </h2>
          <p className="mt-0.5 text-xs text-slate-500">
            追踪全书埋设伏笔、计划回收章节区间与当前状态；未回收伏笔会自动提醒注入目标章节上下文。
          </p>
        </div>

        <div className="flex items-center gap-1.5">
          {[
            ["", "全部"],
            ["planted", "已埋设"],
            ["hinted", "已暗示"],
            ["recovered", "已回收"],
            ["abandoned", "已废弃"],
          ].map(([key, label]) => (
            <button
              key={key}
              type="button"
              onClick={() => setStatusFilter(key)}
              className={`rounded-lg px-2.5 py-1 text-xs font-medium transition-colors cursor-pointer ${
                statusFilter === key
                  ? "bg-indigo-600 text-white"
                  : "bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-300"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* 新增伏笔表单 */}
      <form
        onSubmit={handleAdd}
        className="flex flex-wrap items-end gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-2xs dark:border-slate-800 dark:bg-slate-900"
      >
        <div className="min-w-[260px] flex-1">
          <label className="mb-1 block text-xs font-medium text-slate-600 dark:text-slate-300">
            新增伏笔描述
          </label>
          <input
            type="text"
            value={newDesc}
            onChange={(e) => setNewDesc(e.target.value)}
            placeholder="例如：林栀在旧琴房捡到的匿名乐谱背面写着沈倦的缩写..."
            className="w-full rounded-lg border border-slate-200 px-3 py-1.5 text-xs dark:border-slate-700 dark:bg-slate-800"
          />
        </div>
        <div className="w-28">
          <label className="mb-1 block text-xs font-medium text-slate-600 dark:text-slate-300">
            计划回收起始章
          </label>
          <input
            type="number"
            min={1}
            value={newStart}
            onChange={(e) => setNewStart(e.target.value)}
            placeholder="如 15"
            className="w-full rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs dark:border-slate-700 dark:bg-slate-800"
          />
        </div>
        <div className="w-28">
          <label className="mb-1 block text-xs font-medium text-slate-600 dark:text-slate-300">
            计划回收截止章
          </label>
          <input
            type="number"
            min={1}
            value={newEnd}
            onChange={(e) => setNewEnd(e.target.value)}
            placeholder="如 25"
            className="w-full rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs dark:border-slate-700 dark:bg-slate-800"
          />
        </div>
        <Button type="submit" size="sm" disabled={createMut.isPending}>
          <Plus className="h-3.5 w-3.5" />
          {createMut.isPending ? "登记中..." : "登记伏笔"}
        </Button>
      </form>

      {isLoading ? (
        <p className="text-xs text-slate-400">正在加载伏笔台账...</p>
      ) : items.length === 0 ? (
        <EmptyState
          title="暂无伏笔记录"
          description="可在上方手动登记全书伏笔，或在章节定稿时由 AI 自动识别并抽取伏笔。"
        />
      ) : (
        <div className="space-y-3">
          {items.map((item) => {
            const meta = STATUS_META[item.status] ?? STATUS_META.planted;
            return (
              <div
                key={item.id}
                className="flex flex-wrap items-start justify-between gap-4 rounded-xl border border-slate-200 bg-white p-4 shadow-2xs dark:border-slate-800 dark:bg-slate-900"
              >
                <div className="space-y-1.5 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge tone={meta.tone}>{meta.label}</Badge>
                    {item.planted_chapter_title && (
                      <span className="text-xs text-slate-500">
                        埋设于：《{item.planted_chapter_title}》
                      </span>
                    )}
                    {(item.plan_recover_start || item.plan_recover_end) && (
                      <span className="rounded bg-slate-100 px-2 py-0.5 text-[11px] text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                        计划回收：第 {item.plan_recover_start ?? "?"} ~{" "}
                        {item.plan_recover_end ?? "?"} 章
                      </span>
                    )}
                    {item.confirm_status === "pending" && (
                      <Badge tone="rose">待确认</Badge>
                    )}
                  </div>
                  <p className="text-sm font-medium text-slate-800 dark:text-slate-100">
                    {item.description}
                  </p>
                  {item.source_quote && (
                    <p className="border-l-2 border-indigo-300 pl-2.5 text-xs italic text-slate-500">
                      原文引用：“{item.source_quote}”
                    </p>
                  )}
                </div>

                <div className="flex items-center gap-2">
                  <select
                    value={item.status}
                    onChange={(e) =>
                      updateMut.mutate({
                        id: item.id,
                        status: e.target.value as ForeshadowStatus,
                        confirm_status: "confirmed",
                      })
                    }
                    className="rounded-lg border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs dark:border-slate-700 dark:bg-slate-800"
                  >
                    <option value="planted">已埋设</option>
                    <option value="hinted">已暗示推进</option>
                    <option value="recovered">已回收</option>
                    <option value="abandoned">已废弃</option>
                  </select>
                  <button
                    type="button"
                    onClick={() => deleteMut.mutate(item.id)}
                    className="rounded-lg p-1.5 text-slate-400 hover:bg-rose-50 hover:text-rose-600 cursor-pointer"
                    title="删除伏笔"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
