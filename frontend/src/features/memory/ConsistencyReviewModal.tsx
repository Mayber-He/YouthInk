import React from "react";
import { AlertTriangle, CheckCircle2, HelpCircle } from "lucide-react";
import { Modal } from "@/components/ui/Modal";
import { Badge } from "@/components/ui/Badge";
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
}

const TYPE_LABEL: Record<ConsistencyIssue["check_type"], string> = {
  constraint: "约束",
  fact: "事实",
  character: "人物",
  common_sense: "常理逻辑",
  continuity: "跨章连贯",
};

const IssueCard: React.FC<{ issue: ConsistencyIssue }> = ({ issue }) => {
  const isViolation = issue.verdict === "violation";
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
        <blockquote className="mt-2 border-l-2 border-slate-300 pl-3 text-xs text-slate-600 italic dark:border-slate-700 dark:text-slate-400">
          {issue.evidence_quote}
        </blockquote>
      )}
      {issue.suggestion && (
        <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
          <span className="font-medium">修改建议：</span>
          {issue.suggestion}
        </p>
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
        {review.issue_count === 0 ? (
          <p className="text-xs text-slate-500 dark:text-slate-400">
            本次审查覆盖了生效中的约束清单、已确认事实、出场人物核心属性及情境常理逻辑（环境熟悉度、人际初见边界、限知视角边界、时空物理连续性、在场状态），未发现冲突。
          </p>
        ) : (
          <div className="space-y-3">
            {review.issues.map((issue, idx) => (
              <IssueCard key={idx} issue={issue} />
            ))}
            <p className="flex items-start gap-1.5 text-[11px] text-slate-400">
              <HelpCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              审查只标红、不自动修改。请人工核对后手动改文；若判定有误，可在设定页调整或解除对应约束。
            </p>
          </div>
        )}
      </div>
    )}
  </Modal>
);
