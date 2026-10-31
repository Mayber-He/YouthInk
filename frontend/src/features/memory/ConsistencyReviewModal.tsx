import React, { useState } from "react";
import { AlertTriangle, Check, CheckCircle2, HelpCircle, Sparkles } from "lucide-react";
import { Modal } from "@/components/ui/Modal";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import type {
  ConsistencyIssue,
  ConsistencyReviewResponse,
} from "./types";

interface Props {
  open: boolean;
  onClose: () => void;
  review: ConsistencyReviewResponse | null;
  running: boolean;
  error: string | null;
  onApplyRewrite?: (evidence: string, rewrite: string) => boolean | void;
}

const TYPE_LABEL: Record<ConsistencyIssue["check_type"], string> = {
  constraint: "约束",
  fact: "事实",
  character: "人物",
  common_sense: "常理逻辑",
  continuity: "跨章连贯",
};

const IssueCard: React.FC<{
  issue: ConsistencyIssue;
  onApplyRewrite?: (evidence: string, rewrite: string) => boolean | void;
}> = ({ issue, onApplyRewrite }) => {
  const isViolation = issue.verdict === "violation";
  const [applied, setApplied] = useState(false);
  const [applyError, setApplyError] = useState(false);

  const handleApply = () => {
    if (!issue.evidence_quote || !issue.suggested_rewrite || !onApplyRewrite) return;
    const ok = onApplyRewrite(issue.evidence_quote, issue.suggested_rewrite);
    if (ok === false) {
      setApplyError(true);
    } else {
      setApplied(true);
      setApplyError(false);
    }
  };

  return (
    <div
      className={`rounded-lg border p-4 ${
        isViolation
          ? "border-rose-200 bg-rose-50/60 dark:border-rose-900 dark:bg-rose-950/30"
          : "border-amber-200 bg-amber-50/60 dark:border-amber-900 dark:bg-amber-950/30"
      }`}
    >
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={isViolation ? "rose" : "amber"}>
          {isViolation ? "违反" : "可疑"}
        </Badge>
        <Badge tone="default">{TYPE_LABEL[issue.check_type] ?? "其他"}</Badge>
        {issue.ref_label && (
          <span className="text-xs text-slate-500 dark:text-slate-400">
            {issue.ref_label}
          </span>
        )}
      </div>
      <p className="mt-2 text-sm font-medium text-slate-800 dark:text-slate-100">
        {issue.description}
      </p>
      {issue.evidence_quote && (
        <div className="mt-2">
          <span className="text-[11px] font-medium text-slate-500 dark:text-slate-400">问题原文：</span>
          <blockquote className="mt-1 border-l-2 border-slate-300 pl-3 text-xs text-slate-600 italic dark:border-slate-700 dark:text-slate-400">
            {issue.evidence_quote}
          </blockquote>
        </div>
      )}
      {issue.suggestion && (
        <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
          <span className="font-medium">修改思路：</span>
          {issue.suggestion}
        </p>
      )}

      {issue.suggested_rewrite && (
        <div className="mt-3 rounded-lg border border-indigo-200 bg-white/90 p-3 shadow-2xs dark:border-indigo-900/60 dark:bg-slate-900/90">
          <div className="flex items-center justify-between gap-2">
            <span className="text-xs font-semibold text-indigo-700 dark:text-indigo-300">
              推荐修改片段：
            </span>
            {onApplyRewrite && (
              <Button
                size="sm"
                variant={applied ? "outline" : "primary"}
                disabled={applied}
                onClick={handleApply}
                className="h-6 gap-1 px-2.5 text-xs cursor-pointer"
              >
                {applied ? (
                  <>
                    <Check className="h-3 w-3 text-emerald-600" />
                    <span className="text-emerald-700 dark:text-emerald-400">已替换入正文</span>
                  </>
                ) : (
                  <>
                    <Sparkles className="h-3 w-3" />
                    采纳并替换正文
                  </>
                )}
              </Button>
            )}
          </div>
          <div className="mt-1.5 rounded border border-indigo-100 bg-indigo-50/50 p-2 text-xs font-serif leading-relaxed text-slate-800 dark:border-indigo-950 dark:bg-indigo-950/40 dark:text-slate-200">
            {issue.suggested_rewrite}
          </div>
          {applyError && (
            <p className="mt-1 text-[11px] text-rose-500">
              未能自动在当前正文中精确匹配原句（可能局部文字已被编辑），请手动定位修改。
            </p>
          )}
        </div>
      )}
    </div>
  );
};

export const ConsistencyReviewModal: React.FC<Props> = ({
  open,
  onClose,
  review,
  running,
  error,
  onApplyRewrite,
}) => (
  <Modal open={open} onClose={onClose} title="一致性审查报告" maxWidthClass="max-w-3xl">
    {running && (
      <div className="flex items-center gap-3 py-8 text-sm text-slate-500">
        <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-slate-300 border-t-indigo-500" />
        审查员正在逐项核对检查表与情境常理，请稍候……
      </div>
    )}
    {!running && error && (
      <div className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
        审查失败：{error}
      </div>
    )}
    {!running && !error && review && (
      <div className="space-y-4">
        <div className="flex items-center gap-2">
          {review.issue_count === 0 ? (
            <>
              <CheckCircle2 className="h-5 w-5 text-emerald-500" />
              <p className="text-sm font-medium text-emerald-700 dark:text-emerald-300">
                {review.summary}
              </p>
            </>
          ) : (
            <>
              <AlertTriangle className="h-5 w-5 text-rose-500" />
              <p className="text-sm font-medium text-slate-800 dark:text-slate-100">
                {review.summary}
              </p>
            </>
          )}
          <span className="ml-auto text-[11px] text-slate-400">
            {review.model} · {review.created_at}
          </span>
        </div>
        {review.is_stale && (
          <p className="rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:bg-amber-950/30 dark:text-amber-200">
            本次审查之后章节正文或前文发生过修改，审查结果已过期，请重新审查。
          </p>
        )}
        {review.issue_count === 0 ? (
          <p className="text-xs text-slate-500 dark:text-slate-400">
            本次审查覆盖了生效中的约束清单、已确认事实、出场人物核心属性及情境常理逻辑（环境熟悉度、人际初见边界、限知视角边界、时空物理连续性、在场状态），未发现冲突。
          </p>
        ) : (
          <div className="space-y-3">
            {review.issues.map((issue, idx) => (
              <IssueCard key={idx} issue={issue} onApplyRewrite={onApplyRewrite} />
            ))}
            <p className="flex items-start gap-1.5 text-[11px] text-slate-400">
              <HelpCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              点击「采纳并替换正文」可将推荐修改片段一键写入正文并保存新版本，您亦可随时在编辑器中做进一步润色。
            </p>
          </div>
        )}
      </div>
    )}
  </Modal>
);
