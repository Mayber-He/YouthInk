import React from "react";
import { AlertCircle, Check, CheckCircle2, ChevronRight, Eye, Loader2, ShieldAlert, Sparkles, X } from "lucide-react";
import { Button } from "@/components/ui/Button";

export type WritingPipelineStep =
  | "idle"
  | "assembling" // 组装提示词
  | "connecting" // 调用模型
  | "generating" // 正文生成
  | "reviewing"  // 逻辑与一致性检查
  | "completed"; // 流程完成

interface WritingPipelineBarProps {
  currentStep: WritingPipelineStep;
  modelName?: string;
  generatedWordCount?: number;
  issueCount?: number;
  violationCount?: number;
  reviewSummary?: string | null;
  reviewError?: string | null;
  onOpenReviewDetail?: () => void;
  onRetryReview?: () => void;
  onDismiss?: () => void;
}

const STEPS = [
  { key: "assembling", label: "组装提示词", desc: "加载人设/时序/常理铁律" },
  { key: "connecting", label: "调用模型", desc: "建立大模型长文本通道" },
  { key: "generating", label: "正文生成", desc: "流式输出小说正文" },
  { key: "reviewing", label: "逻辑与一致性检查", desc: "常理/跨章/事实自动质检" },
] as const;

export const WritingPipelineBar: React.FC<WritingPipelineBarProps> = ({
  currentStep,
  modelName,
  generatedWordCount = 0,
  issueCount = 0,
  violationCount = 0,
  reviewSummary,
  reviewError,
  onOpenReviewDetail,
  onRetryReview,
  onDismiss,
}) => {
  if (currentStep === "idle") return null;

  const getStepStatus = (stepKey: string) => {
    const order = ["assembling", "connecting", "generating", "reviewing", "completed"];
    const currentIndex = order.indexOf(currentStep);
    const stepIndex = order.indexOf(stepKey);

    if (currentStep === "completed" || stepIndex < currentIndex) {
      return "done";
    }
    if (stepIndex === currentIndex) {
      return "active";
    }
    return "pending";
  };

  return (
    <div className="mt-3 rounded-xl border border-indigo-200 bg-white p-3.5 shadow-xs dark:border-indigo-900/60 dark:bg-slate-900">
      {/* 步骤条指示器 */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-3 dark:border-slate-800">
        <div className="flex flex-wrap items-center gap-2 sm:gap-3 text-xs">
          {STEPS.map((step, idx) => {
            const status = getStepStatus(step.key);
            return (
              <React.Fragment key={step.key}>
                <div className="flex items-center gap-1.5">
                  <div
                    className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] font-bold transition-colors ${
                      status === "done"
                        ? "bg-emerald-500 text-white"
                        : status === "active"
                        ? "bg-indigo-600 text-white ring-2 ring-indigo-200 dark:ring-indigo-900"
                        : "bg-slate-100 text-slate-400 dark:bg-slate-800"
                    }`}
                  >
                    {status === "done" ? (
                      <Check className="h-3 w-3" />
                    ) : status === "active" ? (
                      <Loader2 className="h-3 w-3 animate-spin" />
                    ) : (
                      idx + 1
                    )}
                  </div>
                  <div className="flex flex-col">
                    <span
                      className={`font-semibold ${
                        status === "active"
                          ? "text-indigo-600 dark:text-indigo-400"
                          : status === "done"
                          ? "text-slate-800 dark:text-slate-200"
                          : "text-slate-400"
                      }`}
                    >
                      {step.label}
                    </span>
                  </div>
                </div>
                {idx < STEPS.length - 1 && (
                  <ChevronRight className="h-3.5 w-3.5 text-slate-300 dark:text-slate-700" />
                )}
              </React.Fragment>
            );
          })}
        </div>

        {onDismiss && (currentStep === "completed") && (
          <button
            type="button"
            onClick={onDismiss}
            className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600 cursor-pointer dark:hover:bg-slate-800"
            title="关闭状态条"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        )}
      </div>

      {/* 步骤详细运行状态与结果展现 */}
      <div className="mt-2.5 flex flex-wrap items-center justify-between gap-2 text-xs">
        {currentStep === "assembling" && (
          <div className="flex items-center gap-2 text-indigo-600 dark:text-indigo-400">
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            <span>正在组装六层提示词：挂载出场人物卡、生效硬约束、前文与下一章时序边界...</span>
          </div>
        )}

        {currentStep === "connecting" && (
          <div className="flex items-center gap-2 text-indigo-600 dark:text-indigo-400">
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            <span>
              已连接大模型服务 {modelName ? `(${modelName})` : ""}，等待建立首字流式输出通道...
            </span>
          </div>
        )}

        {currentStep === "generating" && (
          <div className="flex items-center gap-2 text-indigo-600 dark:text-indigo-400">
            <Sparkles className="h-3.5 w-3.5 animate-pulse text-indigo-500" />
            <span>
              正在流式生成正文... 已实时生成{" "}
              <strong className="font-mono text-indigo-700 dark:text-indigo-300">
                {generatedWordCount.toLocaleString()}
              </strong>{" "}
              字
            </span>
          </div>
        )}

        {currentStep === "reviewing" && (
          <div className="flex items-center gap-2 text-amber-700 dark:text-amber-400">
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            <span>正文已生成并入库，正在全自动执行常理逻辑与跨章一致性检查 (Checklist A~E)...</span>
          </div>
        )}

        {currentStep === "completed" && (
          <div className="flex w-full flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              {reviewError ? (
                <div className="flex items-center gap-2 text-rose-600 dark:text-rose-400">
                  <AlertCircle className="h-4 w-4 shrink-0" />
                  <span className="font-medium">自动质检异常：{reviewError}</span>
                  {onRetryReview && (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={onRetryReview}
                      className="h-6 gap-1 border-rose-300 bg-rose-50 px-2 text-xs text-rose-700 hover:bg-rose-100 dark:border-rose-800 dark:bg-rose-950/40 dark:text-rose-300"
                    >
                      重试质检
                    </Button>
                  )}
                </div>
              ) : issueCount === 0 ? (
                <>
                  <CheckCircle2 className="h-4 w-4 text-emerald-600 dark:text-emerald-400" />
                  <span className="font-semibold text-emerald-800 dark:text-emerald-300">
                    正文生成与全套检查完成：未发现逻辑冲突与设定违背，逻辑完全自洽。
                  </span>
                </>
              ) : (
                <>
                  <ShieldAlert className="h-4 w-4 shrink-0 text-amber-600 dark:text-amber-400" />
                  <div className="flex flex-col">
                    <span className="font-semibold text-amber-900 dark:text-amber-200">
                      自动质检报告：发现 {issueCount} 项需关注的常理或一致性问题
                      {violationCount > 0 ? `（含 ${violationCount} 处明显冲突）` : ""}
                    </span>
                    {reviewSummary && (
                      <span className="mt-0.5 line-clamp-1 text-[11px] text-amber-700/80 dark:text-amber-400/80">
                        {reviewSummary}
                      </span>
                    )}
                  </div>
                </>
              )}
            </div>

            {issueCount > 0 && onOpenReviewDetail && (
              <Button
                variant="outline"
                size="sm"
                onClick={onOpenReviewDetail}
                className="gap-1 border-amber-300 bg-amber-50/70 text-amber-900 hover:bg-amber-100 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-300"
              >
                <Eye className="h-3 w-3" />
                查看质检详情与修改建议
              </Button>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
