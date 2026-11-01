import React, { useState } from "react";
import { AlertTriangle, Check, CheckCircle2, ShieldAlert, Sparkles, Wand2, X } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import type { CharacterItem } from "@/types/api";
import type { AiSmellHit, RewriteActionType, SelectionCritiqueResult } from "../types";

interface SelectionToolbarProps {
  selectedText: string;
  characters: CharacterItem[];
  aiSmellHits: AiSmellHit[];
  hasScannedSmell?: boolean;
  smellError?: string | null;
  isStreaming: boolean;
  onOpenSupplement: () => void;
  onRewriteSelection: (
    actionType: RewriteActionType,
    targetCharId: number | null,
    instruction: string
  ) => void;
  onRewriteSmellHit: (hit: AiSmellHit) => void;
  onApplySmellRewrite: (hit: AiSmellHit) => void;
  onFocusSmellHit?: (hit: AiSmellHit) => void;
  onDismissSmell?: () => void;
  onCritiqueSelection?: () => void;
  isCritiquing?: boolean;
  critiqueResult?: SelectionCritiqueResult | null;
  onApplyCritiqueSuggestion?: (suggestion: string) => void;
  onDismissCritique?: () => void;
}

export const SelectionToolbar: React.FC<SelectionToolbarProps> = ({
  selectedText,
  characters,
  aiSmellHits,
  hasScannedSmell = false,
  smellError,
  isStreaming,
  onOpenSupplement,
  onRewriteSelection,
  onRewriteSmellHit,
  onApplySmellRewrite,
  onFocusSmellHit,
  onDismissSmell,
  onCritiqueSelection,
  isCritiquing = false,
  critiqueResult = null,
  onApplyCritiqueSuggestion,
  onDismissCritique,
}) => {
  const [targetCharId, setTargetCharId] = useState<number | null>(null);
  const [customNote, setCustomNote] = useState("");

  return (
    <div className="space-y-2">
      {/* 选中文字浮动操作栏（设计文档 6.4：改写、扩写、缩写、润色、换成某人的语气、逻辑挑刺） */}
      {selectedText.trim().length > 0 && (
        <div className="flex flex-wrap items-center gap-2 rounded-xl border border-indigo-300 bg-indigo-50/90 px-3.5 py-2 text-xs shadow-sm dark:border-indigo-800 dark:bg-indigo-950/70">
          <Badge tone="indigo">已选 {selectedText.length} 字</Badge>
          {(
            [
              ["rewrite", "改写"],
              ["expand", "扩写"],
              ["shorten", "缩写"],
              ["polish", "去AI味润色"],
            ] as const
          ).map(([act, label]) => (
            <Button
              key={act}
              variant="secondary"
              size="sm"
              disabled={isStreaming}
              onClick={() => onRewriteSelection(act, null, customNote)}
            >
              <Wand2 className="h-3 w-3 text-indigo-600" />
              {label}
            </Button>
          ))}

          <div className="flex items-center gap-1 border-l border-indigo-200 pl-2 dark:border-indigo-800">
            <select
              value={targetCharId ?? ""}
              onChange={(e) =>
                setTargetCharId(e.target.value ? Number(e.target.value) : null)
              }
              className="rounded border border-slate-300 bg-white px-2 py-1 text-xs dark:border-slate-700 dark:bg-slate-900"
            >
              <option value="">选择角色语气...</option>
              {characters.map((c) => (
                <option key={c.id} value={c.id}>
                  换成【{c.name}】语气
                </option>
              ))}
            </select>
            <Button
              variant="secondary"
              size="sm"
              disabled={isStreaming || !targetCharId}
              onClick={() =>
                onRewriteSelection("tone_shift", targetCharId, customNote)
              }
            >
              换语气
            </Button>
          </div>

          {onCritiqueSelection && (
            <Button
              variant="secondary"
              size="sm"
              disabled={isStreaming || isCritiquing}
              onClick={onCritiqueSelection}
              title="排查所选文字是否存在时间悖论、物理状态逆转、超知读心等常理逻辑漏洞"
            >
              <ShieldAlert className="h-3 w-3 text-amber-600 dark:text-amber-400" />
              {isCritiquing ? "排查中..." : "逻辑挑刺"}
            </Button>
          )}

          <input
            type="text"
            placeholder="附加改写要求..."
            value={customNote}
            onChange={(e) => setCustomNote(e.target.value)}
            className="min-w-36 flex-1 rounded border border-slate-300 bg-white px-2 py-1 text-xs dark:border-slate-700 dark:bg-slate-900"
          />
        </div>
      )}

      <div className="flex">
        <Button
          variant="outline"
          size="sm"
          disabled={isStreaming}
          onClick={onOpenSupplement}
          title="在正文光标位置补充一段内容，先预览再插入"
        >
          <Sparkles className="h-3.5 w-3.5 text-indigo-600" />
          补充内容
        </Button>
      </div>

      {/* 选区逻辑挑刺结果卡片（仅渲染一次） */}
      {critiqueResult && (
        <div
          className={`rounded-xl border p-3 text-xs ${
            critiqueResult.has_issue
              ? "border-amber-300 bg-amber-50/90 dark:border-amber-800 dark:bg-amber-950/70"
              : "border-emerald-300 bg-emerald-50/90 dark:border-emerald-800 dark:bg-emerald-950/70"
          }`}
        >
          <div className="flex items-start justify-between gap-2">
            <div className="space-y-1.5 flex-1">
              <div className="flex items-center gap-2">
                {critiqueResult.has_issue ? (
                  <>
                    <ShieldAlert className="h-4 w-4 shrink-0 text-amber-600 dark:text-amber-400" />
                    <span className="font-bold text-amber-900 dark:text-amber-200">
                      发现逻辑/常理漏洞：{critiqueResult.issue_label || "常理矛盾"}
                    </span>
                  </>
                ) : (
                  <>
                    <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-600 dark:text-emerald-400" />
                    <span className="font-bold text-emerald-900 dark:text-emerald-200">
                      逻辑检验通过
                    </span>
                  </>
                )}
              </div>
              <p className="text-slate-700 dark:text-slate-300 leading-relaxed">
                {critiqueResult.description}
              </p>
              {critiqueResult.has_issue && critiqueResult.suggestion && (
                <div className="mt-2 rounded-lg border border-amber-200 bg-white/90 p-2.5 dark:border-slate-700 dark:bg-slate-900">
                  <div className="font-semibold text-slate-800 dark:text-slate-200 mb-1">
                    修改建议：
                  </div>
                  <div className="text-slate-700 dark:text-slate-300 mb-2 select-text whitespace-pre-wrap">
                    {critiqueResult.suggestion}
                  </div>
                  <Button
                    size="sm"
                    variant="primary"
                    disabled={isStreaming}
                    onClick={() => onApplyCritiqueSuggestion?.(critiqueResult.suggestion)}
                  >
                    <Check className="h-3 w-3 mr-1" />
                    采纳并替换原文
                  </Button>
                </div>
              )}
            </div>
            {onDismissCritique && (
              <button
                type="button"
                onClick={onDismissCritique}
                className="rounded p-1 text-slate-400 hover:bg-slate-200 hover:text-slate-600 cursor-pointer dark:hover:bg-slate-800"
                title="关闭挑刺结果"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            )}
          </div>
        </div>
      )}

      {/* 模型 AI 味分析反馈 */}
      {smellError && (
        <div className="flex items-start gap-2 rounded-xl border border-rose-200 bg-rose-50 px-3.5 py-2.5 text-xs text-rose-800 dark:border-rose-900/50 dark:bg-rose-950/30 dark:text-rose-300">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-rose-600" />
          <span>模型检测失败：{smellError}</span>
        </div>
      )}
      {hasScannedSmell && aiSmellHits.length === 0 && (
        <div className="flex items-center justify-between rounded-xl border border-emerald-200 bg-emerald-50/70 px-3.5 py-2.5 text-xs text-emerald-800 dark:border-emerald-900/50 dark:bg-emerald-950/30 dark:text-emerald-300">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-600" />
            <span>
              <strong>模型分析完成：</strong>
              未发现明显的模板化或机械化表达（模型判断仅供参考）。如需修改某段文字，可在下方划选后点击「去AI味润色」。
            </span>
          </div>
          {onDismissSmell && (
            <button
              type="button"
              onClick={onDismissSmell}
              className="ml-2 rounded p-1 text-emerald-600 hover:bg-emerald-100 cursor-pointer"
              title="关闭提示"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      )}

      {/* 模型 AI 味分析结果 */}
      {aiSmellHits.length > 0 && (
        <div className="rounded-xl border border-amber-200 bg-amber-50/70 p-3 text-xs dark:border-amber-900/50 dark:bg-amber-950/30">
          <div className="flex items-center justify-between font-semibold text-amber-900 dark:text-amber-300">
            <div className="flex items-center gap-1.5">
              <AlertTriangle className="h-4 w-4 text-amber-600" />
              <span>
                模型发现 {aiSmellHits.length} 处值得检查的表达（点击定位原文；改写需手动触发）：
              </span>
            </div>
            {onDismissSmell && (
              <button
                type="button"
                onClick={onDismissSmell}
                className="rounded p-1 text-amber-700 hover:bg-amber-100 cursor-pointer"
                title="收起检测结果"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            )}
          </div>
          <div className="mt-2 flex flex-wrap gap-2">
            {aiSmellHits.map((hit, idx) => (
              <div
                key={`${hit.start_index}-${idx}`}
                className="w-full rounded-lg border border-amber-300/80 bg-white p-2.5 dark:border-amber-800 dark:bg-slate-900"
              >
                <div className="flex flex-wrap items-center gap-1.5">
                  <Badge tone="amber">{hit.category}</Badge>
                  <button
                    type="button"
                    onClick={() => onFocusSmellHit?.(hit)}
                    className="underline decoration-amber-500 decoration-wavy font-medium text-slate-800 hover:text-indigo-600 cursor-pointer dark:text-slate-200"
                    title="点击在编辑器中定位高亮原文"
                  >
                    「{hit.matched_text}」
                  </button>
                </div>
                <p className="mt-1 text-[11px] leading-relaxed text-slate-600 dark:text-slate-400">
                  {hit.reason}{hit.suggestion ? ` 修改方向：${hit.suggestion}` : ""}
                </p>
                {hit.suggested_rewrite && (
                  <div className="mt-2 rounded-lg border border-amber-200 bg-amber-50/70 p-2 dark:border-amber-900/60 dark:bg-amber-950/20">
                    <div className="mb-1 font-semibold text-slate-800 dark:text-slate-200">建议修改后的片段：</div>
                    <p className="whitespace-pre-wrap leading-relaxed text-slate-700 dark:text-slate-300">
                      {hit.suggested_rewrite}
                    </p>
                    <Button
                      size="sm"
                      variant="primary"
                      disabled={isStreaming}
                      className="mt-2"
                      onClick={() => onApplySmellRewrite(hit)}
                    >
                      <Check className="mr-1 h-3 w-3" />
                      采纳并替换原文
                    </Button>
                  </div>
                )}
                <button
                  type="button"
                  disabled={isStreaming}
                  onClick={() => onRewriteSmellHit(hit)}
                  className="mt-2 inline-flex items-center gap-0.5 rounded bg-indigo-50 px-1.5 py-0.5 text-[11px] font-medium text-indigo-700 hover:bg-indigo-100 cursor-pointer"
                >
                  <Sparkles className="h-3 w-3" />
                  重新生成改写
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
