import React from "react";
import { Check, RotateCcw, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/Button";

export interface SceneReviewBarProps {
  sceneLabel: string;
  text: string;
  reasons: string[];
  instruction: string;
  isStreaming: boolean;
  onChangeInstruction: (value: string) => void;
  onAccept: () => void;
  onRewrite: () => void;
  onDiscard: () => void;
}

/**
 * B：单个场景生成完后的作者确认条。
 * 停在这里，不自动进入下一场；接受才继续，重写可带一句指令，丢弃则跳过本场。
 */
export const SceneReviewBar: React.FC<SceneReviewBarProps> = ({
  sceneLabel,
  text,
  reasons,
  instruction,
  isStreaming,
  onChangeInstruction,
  onAccept,
  onRewrite,
  onDiscard,
}) => (
  <section className="mt-3 space-y-2 rounded-xl border border-indigo-300 bg-indigo-50/70 p-3 text-xs dark:border-indigo-800 dark:bg-indigo-950/30">
    <div className="flex flex-wrap items-center justify-between gap-2">
      <span className="font-semibold text-indigo-900 dark:text-indigo-200">
        {sceneLabel} 已写完，请确认
      </span>
      <span className="text-[11px] text-indigo-700/80 dark:text-indigo-300/80">
        接受后才进入下一场；全部接受后统一合并保存
      </span>
    </div>

    {reasons.length > 0 && (
      <ul className="list-disc space-y-0.5 rounded-lg border border-amber-300 bg-amber-50 px-5 py-2 text-amber-800 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-200">
        {reasons.map((reason, index) => (
          <li key={`${index}-${reason}`}>{reason}</li>
        ))}
      </ul>
    )}

    <details className="rounded-lg border border-slate-200 bg-white/80 p-2 dark:border-slate-700 dark:bg-slate-900/60">
      <summary className="cursor-pointer text-[11px] text-slate-500 dark:text-slate-400">
        预览本场正文（{text.replace(/\s+/g, "").length} 字）
      </summary>
      <div className="mt-2 max-h-48 overflow-y-auto whitespace-pre-wrap leading-relaxed text-slate-700 dark:text-slate-200">
        {text}
      </div>
    </details>

    <div className="flex flex-wrap items-center gap-2">
      <input
        value={instruction}
        onChange={(event) => onChangeInstruction(event.target.value)}
        disabled={isStreaming}
        placeholder="可选：给本场重写一句指令，例如「少写心理，多写对话」"
        className="min-w-[220px] flex-1 rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-xs dark:border-slate-700 dark:bg-slate-950"
      />
      <Button size="sm" onClick={onAccept} disabled={isStreaming}>
        <Check className="h-3.5 w-3.5" />
        接受
      </Button>
      <Button
        variant="outline"
        size="sm"
        onClick={onRewrite}
        disabled={isStreaming || !instruction.trim()}
        title={instruction.trim() ? "用这句指令重写本场" : "请先填写重写指令"}
      >
        <RotateCcw className="h-3.5 w-3.5" />
        带指令重写本场
      </Button>
      <Button variant="ghost" size="sm" onClick={onDiscard} disabled={isStreaming}>
        <Trash2 className="h-3.5 w-3.5" />
        丢弃
      </Button>
    </div>
  </section>
);
