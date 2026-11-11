import React from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Crosshair,
  Sliders,
  Sparkles,
  Wand2,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { useUiStore } from "@/stores/uiStore";
import type { StyleReviewResult, StyleSpanIssue } from "../types";

interface StyleReviewPanelProps {
  review: StyleReviewResult | null;
  isReviewing: boolean;
  isRewriting: boolean;
  error: string | null;
  rewriteBanner: string | null;
  onRunReview: () => void;
  onRewriteAllSpans: () => void;
  onApplySingleSpan: (issue: StyleSpanIssue) => void;
  onFocusSpan: (quote: string) => void;
}

const PACING_LABELS: Record<string, string> = {
  dialogue_spar: "高频互动拉扯",
  key_choice_turning: "暗涌破绽与抉择",
  emotional_undertow: "情绪暗涌与留白",
  incident_progression: "现场事件推进",
};

const SCORE_LABELS: Record<string, string> = {
  naturalness: "阅读自然度",
  anti_ai_tone: "去AI腔程度",
  dialogue_quality: "人物对话质量",
  emotional_impact: "情绪感染力",
  plot_continuity: "剧情连贯性",
  pacing_control: "节奏控制",
  genre_fit: "题材适配性",
  profile_match: "文风档案匹配度",
};

export const StyleReviewPanel: React.FC<StyleReviewPanelProps> = ({
  review,
  isReviewing,
  isRewriting,
  error,
  rewriteBanner,
  onRunReview,
  onRewriteAllSpans,
  onApplySingleSpan,
  onFocusSpan,
}) => {
  const openSettingsModal = useUiStore((s) => s.openSettingsModal);

  return (
    <div className="space-y-4 text-xs">
      <div className="rounded-xl border border-slate-200 bg-slate-50/70 p-3 dark:border-slate-800 dark:bg-slate-950/50">
        <div className="flex items-center justify-between gap-2">
          <div>
            <h4 className="font-bold text-slate-800 dark:text-slate-100">
              十维文风审查与外科手术式微改
            </h4>
            <p className="mt-0.5 text-[11px] text-slate-500">
              针对生成正文检测总结腔、情绪直白点破、单字空洞对白与段尾感悟，仅重写病灶片段，保护关键剧情与伏笔。
            </p>
          </div>
          <button
            type="button"
            onClick={() => openSettingsModal("styles")}
            className="inline-flex shrink-0 items-center gap-1 rounded-lg border border-slate-200 bg-white px-2 py-1 text-[11px] font-medium text-indigo-600 hover:bg-indigo-50 dark:border-slate-700 dark:bg-slate-900 dark:text-indigo-400 cursor-pointer"
          >
            <Sliders className="h-3 w-3" />
            文风档案
          </button>
        </div>

        <div className="mt-3 flex flex-wrap gap-2">
          <Button
            size="sm"
            disabled={isReviewing || isRewriting}
            onClick={onRunReview}
          >
            <Sparkles className="h-3.5 w-3.5" />
            {isReviewing ? "文风诊脉中..." : "运行十维文风诊脉"}
          </Button>

          {review && review.issues.length > 0 && (
            <Button
              size="sm"
              variant="secondary"
              disabled={isReviewing || isRewriting}
              onClick={onRewriteAllSpans}
            >
              <Wand2 className="h-3.5 w-3.5" />
              {isRewriting
                ? "局部微改中..."
                : `一键局部微改 (${review.issues.length} 处)`}
            </Button>
          )}
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-rose-700 dark:border-rose-900/50 dark:bg-rose-950/30 dark:text-rose-300">
          {error}
        </div>
      )}

      {rewriteBanner && (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-emerald-700 dark:border-emerald-900/50 dark:bg-emerald-950/30 dark:text-emerald-300">
          {rewriteBanner}
        </div>
      )}

      {!review && !isReviewing && (
        <div className="rounded-xl border border-dashed border-slate-200 p-6 text-center text-slate-400 dark:border-slate-800">
          点击上方「运行十维文风诊脉」扫描当前章节的 AI 文风痕迹与叙事节奏。
        </div>
      )}

      {review && (
        <>
          <div className="rounded-xl border border-slate-200 bg-white p-3 space-y-2.5 dark:border-slate-800 dark:bg-slate-900">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="font-semibold text-slate-700 dark:text-slate-200">
                动态叙事节奏档位
              </span>
              <Badge tone="indigo">
                {PACING_LABELS[review.pacing_mode] || review.pacing_mode}
              </Badge>
            </div>
            <p className="text-[11px] leading-relaxed text-slate-600 dark:text-slate-300">
              {review.summary}
            </p>

            <div className="grid grid-cols-2 gap-1.5 pt-1 text-[11px]">
              <div className="rounded-lg bg-slate-50 px-2.5 py-1.5 dark:bg-slate-950">
                <span className="text-slate-400">对白占比：</span>
                <span className="font-semibold text-slate-700 dark:text-slate-200">
                  {review.metrics.dialogue_ratio_pct}%
                </span>
              </div>
              <div className="rounded-lg bg-slate-50 px-2.5 py-1.5 dark:bg-slate-950">
                <span className="text-slate-400">短句占比：</span>
                <span className="font-semibold text-slate-700 dark:text-slate-200">
                  {review.metrics.short_sentence_pct}%
                </span>
              </div>
              <div className="rounded-lg bg-slate-50 px-2.5 py-1.5 dark:bg-slate-950">
                <span className="text-slate-400">平均句长：</span>
                <span className="font-semibold text-slate-700 dark:text-slate-200">
                  {review.metrics.avg_sentence_chars} 字
                </span>
              </div>
              <div className="rounded-lg bg-slate-50 px-2.5 py-1.5 dark:bg-slate-950">
                <span className="text-slate-400">单行短段：</span>
                <span className="font-semibold text-slate-700 dark:text-slate-200">
                  {Math.round(review.metrics.single_line_para_ratio * 100)}%
                </span>
              </div>
            </div>

            {Object.keys(review.dimension_scores).length > 0 && (
              <div className="border-t border-slate-100 pt-2 dark:border-slate-800">
                <div className="mb-1.5 flex items-center justify-between">
                  <span className="font-semibold text-slate-600 dark:text-slate-300">
                    八维参考评分
                  </span>
                  <span className="text-[10px] text-slate-400">
                    仅供参考，不替代人工阅读判断
                  </span>
                </div>
                <div className="grid grid-cols-2 gap-1.5">
                  {Object.entries(review.dimension_scores).map(([key, val]) => (
                    <div
                      key={key}
                      className="flex items-center justify-between rounded bg-slate-50 px-2 py-1 text-[11px] dark:bg-slate-950"
                    >
                      <span className="text-slate-500">
                        {SCORE_LABELS[key] || key}
                      </span>
                      <span
                        className={`font-bold ${
                          val >= 80
                            ? "text-emerald-600"
                            : val >= 65
                            ? "text-amber-600"
                            : "text-rose-600"
                        }`}
                      >
                        {val}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {review.issues.length === 0 ? (
            <div className="flex items-center gap-2 rounded-xl border border-emerald-200 bg-emerald-50/70 p-3 text-emerald-700 dark:border-emerald-900/50 dark:bg-emerald-950/30 dark:text-emerald-300">
              <CheckCircle2 className="h-4 w-4 shrink-0" />
              <span>本章未检出明显 AI 腔病灶片段，文风自然度良好。</span>
            </div>
          ) : (
            <div className="space-y-2.5">
              <div className="flex items-center justify-between">
                <span className="font-semibold text-slate-700 dark:text-slate-300">
                  待微改病灶片段 ({review.issues.length})
                </span>
                <span className="text-[11px] text-slate-400">
                  点击原文可定位至编辑器
                </span>
              </div>

              {review.issues.map((issue, idx) => (
                <div
                  key={`${issue.paragraph_index}-${idx}`}
                  className="rounded-xl border border-slate-200 bg-white p-3 space-y-2 dark:border-slate-800 dark:bg-slate-900"
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-1.5">
                      <AlertTriangle
                        className={`h-3.5 w-3.5 ${
                          issue.severity === "high"
                            ? "text-rose-500"
                            : issue.severity === "medium"
                            ? "text-amber-500"
                            : "text-slate-400"
                        }`}
                      />
                      <span className="font-bold text-slate-800 dark:text-slate-100">
                        {issue.dimension}
                      </span>
                    </div>
                    <Badge
                      tone={
                        issue.severity === "high"
                          ? "rose"
                          : issue.severity === "medium"
                          ? "amber"
                          : "default"
                      }
                    >
                      第 {issue.paragraph_index + 1} 段 · {issue.severity}
                    </Badge>
                  </div>

                  <div
                    onClick={() => onFocusSpan(issue.evidence_quote)}
                    title="点击在编辑器中定位该片段"
                    className="cursor-pointer rounded-lg border border-rose-200/70 bg-rose-50/50 p-2 text-[11px] leading-relaxed text-slate-700 hover:bg-rose-50 dark:border-rose-900/40 dark:bg-rose-950/20 dark:text-slate-200"
                  >
                    <div className="mb-0.5 flex items-center justify-between text-[10px] text-rose-600 dark:text-rose-400">
                      <span>病灶原文片段</span>
                      <span className="inline-flex items-center gap-0.5">
                        <Crosshair className="h-2.5 w-2.5" /> 定位
                      </span>
                    </div>
                    “{issue.evidence_quote}”
                  </div>

                  <p className="text-[11px] text-slate-500 dark:text-slate-400">
                    <strong className="text-slate-600 dark:text-slate-300">
                      诊断原因：
                    </strong>
                    {issue.reason}
                  </p>

                  {issue.rewrite_directive && (
                    <p className="text-[11px] text-indigo-600 dark:text-indigo-400">
                      <strong>改写指令：</strong>
                      {issue.rewrite_directive}
                    </p>
                  )}

                  {issue.suggested_rewrite && (
                    <div className="rounded-lg border border-emerald-200/80 bg-emerald-50/50 p-2 text-[11px] leading-relaxed text-slate-800 dark:border-emerald-900/40 dark:bg-emerald-950/20 dark:text-slate-100">
                      <div className="mb-1 flex items-center justify-between">
                        <span className="text-[10px] font-semibold text-emerald-700 dark:text-emerald-400">
                          局部微改建议
                        </span>
                        <button
                          type="button"
                          onClick={() => onApplySingleSpan(issue)}
                          className="rounded bg-emerald-600 px-2 py-0.5 text-[10px] font-medium text-white hover:bg-emerald-500 cursor-pointer"
                        >
                          仅替换此片段
                        </button>
                      </div>
                      {issue.suggested_rewrite}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
};
