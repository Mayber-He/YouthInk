import React, { useEffect, useState } from "react";
import { Check, Loader2, Plus, Save, Sparkles, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { LockToggle } from "@/components/common/LockToggle";
import { useUiStore } from "@/stores/uiStore";
import type { TurningPointItem } from "@/types/api";
import {
  useGenerateMainPlot,
  useMainPlot,
  useUpdateMainPlot,
} from "./api";

interface MainPlotSectionProps {
  novelUid: string;
}

export const MainPlotSection: React.FC<MainPlotSectionProps> = ({
  novelUid,
}) => {
  const { data: plot, isLoading } = useMainPlot(novelUid);
  const updateMut = useUpdateMainPlot(novelUid);
  const genMut = useGenerateMainPlot(novelUid);
  const setActiveSection = useUiStore((s) => s.setActiveSection);

  const [coreConflict, setCoreConflict] = useState("");
  const [romanceArc, setRomanceArc] = useState("");
  const [growthArc, setGrowthArc] = useState("");
  const [turningPts, setTurningPts] = useState<TurningPointItem[]>([]);
  const [aiInstruction, setAiInstruction] = useState("");
  const [savedBanner, setSavedBanner] = useState(false);
  const [errMsg, setErrMsg] = useState<string | null>(null);

  useEffect(() => {
    if (plot) {
      setCoreConflict(plot.core_conflict);
      setRomanceArc(plot.romance_arc);
      setGrowthArc(plot.growth_arc);
      setTurningPts(plot.key_turning_pts);
    }
  }, [plot]);

  const handleSave = async () => {
    await updateMut.mutateAsync({
      core_conflict: coreConflict,
      romance_arc: romanceArc,
      growth_arc: growthArc,
      key_turning_pts: turningPts,
    });
    setSavedBanner(true);
    setTimeout(() => setSavedBanner(false), 2000);
  };

  const handleGenerate = async () => {
    setErrMsg(null);
    try {
      await genMut.mutateAsync({ instruction: aiInstruction });
    } catch (err) {
      setErrMsg(err instanceof Error ? err.message : "生成主线失败");
    }
  };

  if (isLoading || !plot) {
    return <p className="p-6 text-xs text-slate-400">加载主线剧情中...</p>;
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6 p-6">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 pb-4 dark:border-slate-800">
        <div>
          <h1 className="text-lg font-bold text-slate-900 dark:text-slate-100">
            主线剧情脉络（核心冲突 / 感情线 / 成长线 / 关键转折点）
          </h1>
          <p className="mt-0.5 text-xs text-slate-500">
            锁定主线后，下游分卷与情节弧目录将严格围绕此主线展开。
          </p>
        </div>
        <div className="flex items-center gap-2">
          <LockToggle
            locked={plot.locked}
            onToggle={(next) => updateMut.mutate({ locked: next })}
          />
          <Button
            variant="secondary"
            size="sm"
            onClick={() => setActiveSection("outline")}
          >
            下一步：分卷与章节目录
          </Button>
          <Button size="sm" onClick={handleSave} disabled={updateMut.isPending}>
            {savedBanner ? (
              <>
                <Check className="h-3.5 w-3.5" />
                已保存
              </>
            ) : (
              <>
                <Save className="h-3.5 w-3.5" />
                保存主线
              </>
            )}
          </Button>
        </div>
      </div>

      {/* AI 生成 */}
      <div className="flex flex-wrap items-center gap-2 rounded-xl border border-indigo-200/80 bg-indigo-50/50 p-3.5 dark:border-indigo-900/50 dark:bg-indigo-950/30">
        <input
          type="text"
          placeholder="可选：补充主线构想（如：高二冬季艺考集训产生分歧，高考前夕天台和解）"
          value={aiInstruction}
          onChange={(e) => setAiInstruction(e.target.value)}
          className="flex-1 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs dark:border-slate-700 dark:bg-slate-900"
        />
        <Button
          size="sm"
          disabled={genMut.isPending || plot.locked}
          onClick={handleGenerate}
        >
          {genMut.isPending ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Sparkles className="h-3.5 w-3.5" />
          )}
          {plot.locked ? "主线已锁定" : "AI 生成主线剧情"}
        </Button>
      </div>

      {errMsg && (
        <div className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">
          {errMsg}
        </div>
      )}

      <div className="space-y-4 rounded-2xl border border-slate-200 bg-white p-5 text-xs dark:border-slate-800 dark:bg-slate-900">
        <div>
          <label className="font-semibold text-slate-700 dark:text-slate-300">
            全书核心矛盾冲突
          </label>
          <textarea
            rows={3}
            value={coreConflict}
            onChange={(e) => setCoreConflict(e.target.value)}
            className="mt-1 w-full rounded-lg border border-slate-300 p-2.5 leading-relaxed dark:border-slate-700 dark:bg-slate-950"
          />
        </div>
        <div>
          <label className="font-semibold text-slate-700 dark:text-slate-300">
            感情线走向
          </label>
          <textarea
            rows={3}
            value={romanceArc}
            onChange={(e) => setRomanceArc(e.target.value)}
            className="mt-1 w-full rounded-lg border border-slate-300 p-2.5 leading-relaxed dark:border-slate-700 dark:bg-slate-950"
          />
        </div>
        <div>
          <label className="font-semibold text-slate-700 dark:text-slate-300">
            成长线走向
          </label>
          <textarea
            rows={3}
            value={growthArc}
            onChange={(e) => setGrowthArc(e.target.value)}
            className="mt-1 w-full rounded-lg border border-slate-300 p-2.5 leading-relaxed dark:border-slate-700 dark:bg-slate-950"
          />
        </div>

        {/* 关键转折点 */}
        <div className="space-y-2 pt-2">
          <div className="flex items-center justify-between">
            <label className="font-semibold text-slate-700 dark:text-slate-300">
              关键转折点 ({turningPts.length})
            </label>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() =>
                setTurningPts([...turningPts, { desc: "", chapter_sort: null }])
              }
            >
              <Plus className="h-3.5 w-3.5" />
              添加转折点
            </Button>
          </div>
          {turningPts.map((pt, idx) => (
            <div key={idx} className="flex items-center gap-2">
              <input
                type="number"
                placeholder="预计章序"
                value={pt.chapter_sort ?? ""}
                onChange={(e) => {
                  const next = [...turningPts];
                  next[idx] = {
                    ...pt,
                    chapter_sort: e.target.value ? Number(e.target.value) : null,
                  };
                  setTurningPts(next);
                }}
                className="w-24 rounded-lg border border-slate-300 px-2.5 py-1.5 dark:border-slate-700 dark:bg-slate-950"
              />
              <input
                type="text"
                placeholder="转折事件描述..."
                value={pt.desc}
                onChange={(e) => {
                  const next = [...turningPts];
                  next[idx] = { ...pt, desc: e.target.value };
                  setTurningPts(next);
                }}
                className="flex-1 rounded-lg border border-slate-300 px-3 py-1.5 dark:border-slate-700 dark:bg-slate-950"
              />
              <button
                type="button"
                onClick={() =>
                  setTurningPts(turningPts.filter((_, i) => i !== idx))
                }
                className="rounded-md p-1.5 text-slate-400 hover:bg-rose-50 hover:text-rose-600 cursor-pointer"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
