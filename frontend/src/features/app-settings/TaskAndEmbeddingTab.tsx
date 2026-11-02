import React from "react";
import { Cpu, RefreshCw, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import {
  useEmbeddingStatus,
  useLlmProfiles,
  useTaskAssignments,
  useTriggerEmbeddingDownload,
  useTrustMode,
  useUpdateTaskAssignments,
  useUpdateTrustMode,
} from "./api";

export const TaskAndEmbeddingTab: React.FC = () => {
  const { data: profiles = [] } = useLlmProfiles();
  const { data: assignments } = useTaskAssignments();
  const updateAssignMut = useUpdateTaskAssignments();

  const { data: trustMode } = useTrustMode();
  const updateTrustMut = useUpdateTrustMode();

  const { data: embStatus } = useEmbeddingStatus();
  const downloadEmbMut = useTriggerEmbeddingDownload();

  const handleAssignChange = (
    category: "writing" | "planning" | "extract",
    value: string
  ) => {
    if (!assignments) return;
    const nextId = value ? Number(value) : null;
    updateAssignMut.mutate({
      ...assignments,
      [category]: nextId,
    });
  };

  return (
    <div className="space-y-6">
      {/* 1. 按任务类别分配模型 */}
      <div className="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
        <div className="flex items-center gap-2">
          <Cpu className="h-4 w-4 text-indigo-600" />
          <h3 className="text-sm font-semibold">按任务类别分配模型（设计文档 2.3）</h3>
        </div>
        <p className="mt-1 text-xs text-slate-500">
          未单独指定时自动回退使用默认模型档案。
        </p>

        <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
          {(
            [
              {
                key: "writing",
                label: "正文写作与润色",
                hint: "推荐最强旗舰模型",
              },
              {
                key: "planning",
                label: "大纲、人设与世界观",
                hint: "推荐强逻辑推理模型",
              },
              {
                key: "extract",
                label: "摘要、抽取与 JSON 修复",
                hint: "推荐高性价比快速模型",
              },
            ] as const
          ).map((item) => (
            <div
              key={item.key}
              className="rounded-lg border border-slate-200 p-3 dark:border-slate-800"
            >
              <div className="text-xs font-medium text-slate-800 dark:text-slate-200">
                {item.label}
              </div>
              <div className="text-[11px] text-slate-400">{item.hint}</div>
              <select
                value={assignments?.[item.key] ?? ""}
                onChange={(e) => handleAssignChange(item.key, e.target.value)}
                className="mt-2 w-full rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-xs dark:border-slate-700 dark:bg-slate-950"
              >
                <option value="">跟随默认档案</option>
                {profiles.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name} ({p.model})
                  </option>
                ))}
              </select>
            </div>
          ))}
        </div>
      </div>

      {/* 2. 记忆信任模式 */}
      {trustMode && (
        <div className="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <ShieldCheck className="h-4 w-4 text-emerald-600" />
              <h3 className="text-sm font-semibold">记忆信任模式（设计文档 5.5）</h3>
            </div>
            <label className="inline-flex items-center gap-2 text-xs font-medium">
              <input
                type="checkbox"
                checked={trustMode.enabled}
                onChange={(e) =>
                  updateTrustMut.mutate({ ...trustMode, enabled: e.target.checked })
                }
              />
              启用信任模式
            </label>
          </div>
          <p className="mt-1 text-xs text-slate-500">
            开启后，客观事实和伏笔暗示自动确认入库；人物状态、关系、认知变更默认需人工确认以防幻觉放大。
          </p>
          {trustMode.enabled && (
            <div className="mt-3 grid grid-cols-2 gap-2 text-xs sm:grid-cols-3">
              {(
                [
                  ["auto_confirm_facts", "事实抽取自动确认"],
                  ["auto_confirm_foreshadow_hint", "伏笔暗示自动确认"],
                  ["auto_confirm_char_state", "人物状态变更自动确认"],
                  ["auto_confirm_relationship", "人物关系变更自动确认"],
                  ["auto_confirm_cognitive", "认知记录自动确认"],
                  ["auto_confirm_foreshadow_plant_recover", "伏笔埋下/回收自动确认"],
                ] as const
              ).map(([field, label]) => (
                <label
                  key={field}
                  className="flex items-center gap-1.5 text-slate-600 dark:text-slate-300"
                >
                  <input
                    type="checkbox"
                    checked={trustMode[field]}
                    onChange={(e) =>
                      updateTrustMut.mutate({
                        ...trustMode,
                        [field]: e.target.checked,
                      })
                    }
                  />
                  {label}
                </label>
              ))}
            </div>
          )}
        </div>
      )}

      {/* 3. 本地 Embedding 模型 */}
      {embStatus && (
        <div className="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
          <div className="flex items-center justify-between">
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-semibold">
                  本地 Embedding 模型 ({embStatus.model_id})
                </h3>
                <Badge tone={embStatus.ready ? "emerald" : "amber"}>
                  {embStatus.ready ? "已就绪" : "待准备"}
                </Badge>
              </div>
              <p className="mt-1 text-xs text-slate-500">
                存放路径：<code className="font-mono">{embStatus.local_path}</code>
              </p>
              <p className="mt-0.5 text-xs text-slate-400">{embStatus.message}</p>
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={downloadEmbMut.isPending}
                onClick={() => downloadEmbMut.mutate(embStatus.download_source)}
              >
                <RefreshCw className="h-3.5 w-3.5" />
                重新检查模型
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
