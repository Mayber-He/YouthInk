import React, { useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, HelpCircle, Sparkles } from "lucide-react";
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
  onApplyRewrite?: (issueIndices: number[]) => Promise<boolean>;
}

const TYPE_LABEL: Record<ConsistencyIssue["check_type"], string> = {
  constraint: "约束",
  fact: "事实",
  character: "人物",
  common_sense: "常理逻辑",
  continuity: "跨章连贯",
  prose: "表达与删冗",
};

const IssueCard: React.FC<{
  issue: ConsistencyIssue;
  issueIndex: number;
  onApplyRewrite?: (issueIndex: number) => void;
  selected: boolean;
  disabled: boolean;
  onToggle?: () => void;
}> = ({ issue, issueIndex, onApplyRewrite, selected, disabled, onToggle }) => {
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
        {onToggle && (
          <input
            type="checkbox"
            aria-label={`选择建议 ${issueIndex + 1}`}
            checked={selected}
            disabled={disabled}
            onChange={onToggle}
            className="h-4 w-4 accent-indigo-600"
          />
        )}
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
      {issue.historical_evidence && (
        <div className="mt-2">
          <span className="text-[11px] font-medium text-indigo-600 dark:text-indigo-400">历史参考依据：</span>
          <blockquote className="mt-1 border-l-2 border-indigo-300 pl-3 text-xs text-slate-600 italic dark:border-indigo-800 dark:text-slate-400">
            {issue.historical_evidence}
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
                variant="primary"
                disabled={disabled}
                onClick={() => onApplyRewrite(issueIndex)}
                className="h-6 gap-1 px-2.5 text-xs cursor-pointer"
              >
                <Sparkles className="h-3 w-3" />
                采纳并保存、复核
              </Button>
            )}
          </div>
          <div className="mt-1.5 rounded border border-indigo-100 bg-indigo-50/50 p-2 text-xs font-serif leading-relaxed text-slate-800 dark:border-indigo-950 dark:bg-indigo-950/40 dark:text-slate-200">
            {issue.suggested_rewrite}
          </div>
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
}) => {
  const [selected, setSelected] = useState<number[]>([]);
  const [applying, setApplying] = useState(false);
  const [applyError, setApplyError] = useState("");
  useEffect(() => {
    setSelected([]);
    setApplyError("");
  }, [open, review?.id]);

  const eligible = review && !review.is_stale && onApplyRewrite
    ? review.issues.flatMap((issue, index) =>
      issue.evidence_quote.trim() && issue.suggested_rewrite?.trim() ? [index] : [])
    : [];
  const selectedIndices = selected.filter((index) => eligible.includes(index));
  const handleApply = async (indices: number[]) => {
    if (!onApplyRewrite || applying || running || !indices.length) return;
    setApplying(true);
    setApplyError("");
    try {
      const ok = await onApplyRewrite(indices);
      if (!ok) throw new Error("当前正文已变化或正在生成，请保存后重新审查。");
      setSelected([]);
    } catch (error) {
      setApplyError(error instanceof Error ? error.message : "保存失败，请重试。");
    } finally {
      setApplying(false);
    }
  };

  return (
  <Modal open={open} onClose={onClose} title="一致性审查报告" maxWidthClass="max-w-3xl">
    {(running || applying) && (
      <div className="flex items-center gap-3 py-8 text-sm text-slate-500">
        <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-slate-300 border-t-indigo-500" />
        {applying ? "正在保存所选建议并复核，请稍候……" : "审查员正在逐项核对检查表与情境常理，请稍候……"}
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
        {eligible.length > 0 && (
          <div className="flex flex-wrap items-center gap-2 rounded-lg border border-slate-200 p-3 dark:border-slate-700">
            <Button size="sm" variant="outline" disabled={applying} onClick={() => setSelected(eligible)}>全选</Button>
            <Button size="sm" variant="ghost" disabled={applying || !selectedIndices.length} onClick={() => setSelected([])}>取消全选</Button>
            <Button size="sm" disabled={applying || !selectedIndices.length} onClick={() => void handleApply(selectedIndices)}>
              采用所选（{selectedIndices.length}）
            </Button>
          </div>
        )}
        {applyError && <p role="alert" className="text-xs text-rose-500">{applyError}</p>}
        {review.issue_count === 0 ? (
          <p className="text-xs text-slate-500 dark:text-slate-400">
            本次审查覆盖了生效中的约束清单、已确认事实、出场人物核心属性及情境常理逻辑（环境熟悉度、人际初见边界、限知视角边界、时空物理连续性、在场状态），未发现冲突。
          </p>
        ) : (
          <div className="space-y-3">
            {review.issues.map((issue, idx) => (
              <IssueCard
                key={`${review.id}-${idx}`}
                issue={issue}
                issueIndex={idx}
                selected={selectedIndices.includes(idx)}
                disabled={applying}
                onToggle={eligible.includes(idx) ? () => setSelected((prev) =>
                  prev.includes(idx) ? prev.filter((index) => index !== idx) : [...prev, idx]) : undefined}
                onApplyRewrite={eligible.includes(idx) ? (index) => void handleApply([index]) : undefined}
              />
            ))}
            <p className="flex items-start gap-1.5 text-[11px] text-slate-400">
              <HelpCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              采纳前请对照原文和建议。采纳后保留旧版本、保存新版本并重新审查；可疑项和表达建议由您判断，不会自动套用。
            </p>
          </div>
        )}
      </div>
    )}
  </Modal>
  );
};
