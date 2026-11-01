import React from "react";
import { Badge } from "@/components/ui/Badge";
import type { ContextPreview } from "../types";

interface ContextPreviewPanelProps {
  preview: ContextPreview | undefined;
  isLoading: boolean;
  disabledKeys: string[];
  customContext: string;
  onToggleKey: (key: string) => void;
  onChangeCustomContext: (val: string) => void;
}

export const ContextPreviewPanel: React.FC<ContextPreviewPanelProps> = ({
  preview,
  isLoading,
  disabledKeys,
  customContext,
  onToggleKey,
  onChangeCustomContext,
}) => {
  if (isLoading || !preview) {
    return <p className="text-xs text-slate-400">正在计算上下文与 Token 预算...</p>;
  }

  const ratio = Math.min(100, Math.round((preview.total_tokens / preview.budget_tokens) * 100));

  return (
    <div className="space-y-4 text-xs">
      {preview.warnings?.map((warning) => (
        <p key={warning} role="alert" className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-amber-800 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-200">
          {warning}
        </p>
      ))}
      <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 dark:border-slate-800 dark:bg-slate-800/40">
        <div className="flex items-center justify-between font-semibold">
          <span>上下文 Token 预算</span>
          <Badge tone={ratio > 85 ? "amber" : "indigo"}>
            {preview.total_tokens.toLocaleString()} / {preview.budget_tokens.toLocaleString()}
          </Badge>
        </div>
        <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700">
          <div
            className="h-full bg-indigo-600 transition-all"
            style={{ width: `${ratio}%` }}
          />
        </div>
        <p className="mt-1.5 text-[11px] text-slate-500">
          可勾选或取消以下上下文模块，生成时将严格按勾选内容注入模型（设计文档 1.3 & 5.3）。
        </p>
      </div>

      <div className="space-y-2.5">
        {preview.blocks.map((block) => {
          const checked = !disabledKeys.includes(block.key);
          return (
            <div
              key={block.key}
              className={`rounded-xl border p-3 transition-opacity ${
                checked
                  ? "border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900"
                  : "border-slate-200/50 bg-slate-50/50 opacity-60 dark:border-slate-800/50"
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <label className="flex items-center gap-2 font-medium text-slate-800 dark:text-slate-200 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => onToggleKey(block.key)}
                    className="rounded border-slate-300"
                  />
                  <span>{block.label}</span>
                </label>
                <Badge tone={checked ? "indigo" : "default"}>
                  {block.tokens} tok
                </Badge>
              </div>
              <pre className="mt-2 max-h-28 overflow-y-auto whitespace-pre-wrap rounded bg-slate-50 p-2 font-sans text-[11px] leading-relaxed text-slate-600 dark:bg-slate-950 dark:text-slate-400">
                {block.content}
              </pre>
            </div>
          );
        })}
      </div>

      <div>
        <label className="font-semibold text-slate-700 dark:text-slate-300">
          手动补充参考上下文（可选）
        </label>
        <textarea
          rows={3}
          placeholder="在此临时填入希望模型参考的细节或台词灵感..."
          value={customContext}
          onChange={(e) => onChangeCustomContext(e.target.value)}
          className="mt-1 w-full rounded-lg border border-slate-300 bg-white p-2 text-xs dark:border-slate-700 dark:bg-slate-950"
        />
      </div>
    </div>
  );
};
