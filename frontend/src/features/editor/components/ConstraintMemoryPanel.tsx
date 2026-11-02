import React from "react";
import { Ban, RotateCcw, ShieldAlert } from "lucide-react";
import { Badge } from "@/components/ui/Badge";
import {
  useChapterActiveConstraints,
  useUpdateConstraint,
} from "@/features/settings-entity/api";
import type { ConstraintItem } from "@/types/api";
import type { ContextPreview } from "../types";

const FACT_BLOCK_KEY = "foreshadowing_and_facts";

const STATUS_LABEL: Record<ConstraintItem["status"], string> = {
  active: "生效中",
  resolved: "已解除",
  violated: "已违反",
};

const SCOPE_LABEL: Record<ConstraintItem["target_type"], string> = {
  character: "人物",
  location: "地点",
  worldview: "世界观",
  chapter: "章节",
  novel: "全书",
};

interface ConstraintMemoryPanelProps {
  novelUid: string;
  chapterId: number;
  preview: ContextPreview | undefined;
  isLoading: boolean;
  disabledKeys: string[];
  onToggleKey: (key: string) => void;
}

/**
 * C：只读面板。
 * - 列出本章实际生效的约束（来自与上下文组装器相同的 active-constraints 接口），
 *   作者可把某条标记为已解除，或重新激活。
 * - 列出本章会注入的事实与伏笔（直接显示注入块内容），可按整块停用/恢复。
 * 逐条停用需要改上下文注入逻辑，本次不改生成链路，因此只提供块级开关。
 */
export const ConstraintMemoryPanel: React.FC<ConstraintMemoryPanelProps> = ({
  novelUid,
  chapterId,
  preview,
  isLoading,
  disabledKeys,
  onToggleKey,
}) => {
  const { data: constraints = [], isLoading: constraintsLoading } =
    useChapterActiveConstraints(novelUid, chapterId);
  const updateMut = useUpdateConstraint(novelUid);

  const factBlock = preview?.blocks.find((block) => block.key === FACT_BLOCK_KEY);
  const factInjected = Boolean(factBlock) && !disabledKeys.includes(FACT_BLOCK_KEY);
  const factLines =
    factBlock?.content
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean) ?? [];

  return (
    <div className="space-y-4 text-xs">
      <section className="space-y-2">
        <div className="flex items-center justify-between">
          <span className="flex items-center gap-1.5 font-semibold text-slate-800 dark:text-slate-200">
            <ShieldAlert className="h-3.5 w-3.5 text-rose-500" />
            本章生效约束 ({constraints.length})
          </span>
          <span className="text-[11px] text-slate-400">停用后不再注入本章</span>
        </div>

        {constraintsLoading ? (
          <p className="text-slate-400">正在加载本章约束...</p>
        ) : constraints.length === 0 ? (
          <p className="rounded-lg border border-dashed border-slate-200 p-3 text-center text-slate-400 dark:border-slate-800">
            本章暂无生效中的约束
          </p>
        ) : (
          constraints.map((constraint) => {
            const isActive = constraint.status === "active";
            return (
              <div
                key={constraint.id}
                className={`space-y-1.5 rounded-lg border p-2.5 ${
                  isActive
                    ? "border-rose-200/70 bg-rose-50/50 dark:border-rose-900/40 dark:bg-rose-950/20"
                    : "border-slate-200 bg-slate-50 opacity-70 dark:border-slate-800 dark:bg-slate-900"
                }`}
              >
                <div className="flex flex-wrap items-center gap-1.5">
                  <Badge tone={isActive ? "rose" : "default"}>{STATUS_LABEL[constraint.status]}</Badge>
                  <Badge tone={constraint.severity === "hard" ? "amber" : "indigo"}>
                    {constraint.severity === "hard" ? "硬" : "软"}
                  </Badge>
                  <Badge>{SCOPE_LABEL[constraint.target_type]}</Badge>
                  {constraint.target_name && (
                    <span className="text-[11px] text-slate-500">「{constraint.target_name}」</span>
                  )}
                  <button
                    type="button"
                    disabled={updateMut.isPending}
                    onClick={() =>
                      updateMut.mutate({
                        id: constraint.id,
                        input: { status: isActive ? "resolved" : "active" },
                      })
                    }
                    className="ml-auto inline-flex cursor-pointer items-center gap-1 rounded px-1.5 py-0.5 text-[11px] text-slate-500 underline-offset-2 hover:bg-white hover:text-slate-800 disabled:cursor-not-allowed disabled:opacity-50 dark:hover:bg-slate-800 dark:hover:text-slate-200"
                  >
                    {isActive ? (
                      <>
                        <Ban className="h-3 w-3" /> 停用
                      </>
                    ) : (
                      <>
                        <RotateCcw className="h-3 w-3" /> 恢复
                      </>
                    )}
                  </button>
                </div>
                <p className="leading-relaxed text-slate-700 dark:text-slate-300">{constraint.content}</p>
              </div>
            );
          })
        )}
      </section>

      <section className="space-y-2">
        <div className="flex items-center justify-between">
          <span className="font-semibold text-slate-800 dark:text-slate-200">
            本章注入的事实与伏笔
          </span>
          {factBlock && (
            <label className="flex cursor-pointer items-center gap-1.5 text-[11px] text-slate-500 dark:text-slate-400">
              <input
                type="checkbox"
                checked={factInjected}
                onChange={() => onToggleKey(FACT_BLOCK_KEY)}
                className="rounded border-slate-300"
              />
              本章注入
            </label>
          )}
        </div>

        {isLoading || !preview ? (
          <p className="text-slate-400">正在计算本章注入内容...</p>
        ) : !factBlock ? (
          <p className="rounded-lg border border-dashed border-slate-200 p-3 text-center text-slate-400 dark:border-slate-800">
            当前没有可显示的伏笔/事实注入块
          </p>
        ) : (
          <div
            className={`space-y-1.5 rounded-lg border p-2.5 ${
              factInjected
                ? "border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900"
                : "border-slate-200/60 bg-slate-50/60 opacity-60 dark:border-slate-800/60 dark:bg-slate-950/40"
            }`}
          >
            <p className="text-[11px] text-slate-400">
              {factInjected ? "以下内容会随本章提示词一起注入模型" : "已停用：本章不会注入该块"}
            </p>
            {factLines.map((line, index) => (
              <p key={`${index}-${line}`} className="leading-relaxed text-slate-700 dark:text-slate-300">
                {line}
              </p>
            ))}
            <p className="pt-1 text-[11px] text-slate-400">
              这里按整块停用；需要逐条调整伏笔状态请到「伏笔台账」处理。
            </p>
          </div>
        )}
      </section>
    </div>
  );
};
