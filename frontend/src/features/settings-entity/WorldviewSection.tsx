import React, { useState } from "react";
import { Loader2, Plus, Sparkles, Trash2, Wand2 } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { LockToggle } from "@/components/common/LockToggle";
import { EmptyState } from "@/components/common/EmptyState";
import { useUiStore } from "@/stores/uiStore";
import type { WorldviewCategory } from "@/types/api";
import {
  useCreateWorldview,
  useDeleteWorldview,
  useGenerateWorldview,
  useRewriteWorldview,
  useUpdateWorldview,
  useWorldview,
} from "./api";

const CATEGORY_LABELS: Record<WorldviewCategory, string> = {
  era: "时代背景",
  city: "城市风貌",
  school: "学校生态",
  rules: "规则制度",
  culture: "流行文化",
  term: "专有名词",
};

interface WorldviewSectionProps {
  novelUid: string;
}

export const WorldviewSection: React.FC<WorldviewSectionProps> = ({
  novelUid,
}) => {
  const { data: entries = [], isLoading } = useWorldview(novelUid);
  const createMut = useCreateWorldview(novelUid);
  const updateMut = useUpdateWorldview(novelUid);
  const deleteMut = useDeleteWorldview(novelUid);
  const genMut = useGenerateWorldview(novelUid);
  const rewriteMut = useRewriteWorldview(novelUid);
  const setActiveSection = useUiStore((s) => s.setActiveSection);

  const [newCat, setNewCat] = useState<WorldviewCategory>("school");
  const [newContent, setNewContent] = useState("");
  const [aiInstruction, setAiInstruction] = useState("");
  const [rewriteId, setRewriteId] = useState<number | null>(null);
  const [rewritePrompt, setRewritePrompt] = useState("");
  const [errMsg, setErrMsg] = useState<string | null>(null);

  const handleGenerateAll = async () => {
    setErrMsg(null);
    try {
      await genMut.mutateAsync({ instruction: aiInstruction, count: 6 });
    } catch (err) {
      setErrMsg(err instanceof Error ? err.message : "生成失败");
    }
  };

  const handleAddManual = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newContent.trim()) return;
    await createMut.mutateAsync({
      category: newCat,
      content: newContent.trim(),
      locked: true,
    });
    setNewContent("");
  };

  const handleRewrite = async (id: number) => {
    if (!rewritePrompt.trim()) return;
    setErrMsg(null);
    try {
      await rewriteMut.mutateAsync({ id, instruction: rewritePrompt.trim() });
      setRewriteId(null);
      setRewritePrompt("");
    } catch (err) {
      setErrMsg(err instanceof Error ? err.message : "重写失败");
    }
  };

  return (
    <div className="mx-auto max-w-5xl space-y-6 p-6">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 pb-4 dark:border-slate-800">
        <div>
          <h1 className="text-lg font-bold text-slate-900 dark:text-slate-100">
            世界观设定（生成 → 编辑 → 锁定）
          </h1>
          <p className="mt-0.5 text-xs text-slate-500">
            已锁定的条目在点击「AI 生成全部」时将受到保护不会被覆盖。
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            size="sm"
            onClick={() => setActiveSection("characters")}
          >
            下一步：设计人物卡
          </Button>
        </div>
      </div>

      {/* AI 生成控制栏 */}
      <div className="flex flex-wrap items-center gap-2 rounded-xl border border-indigo-200/80 bg-indigo-50/50 p-3.5 dark:border-indigo-900/50 dark:bg-indigo-950/30">
        <input
          type="text"
          placeholder="可选：输入世界观生成偏好（如：2016年南方沿海重点高中，强调夏日竞赛集训氛围）"
          value={aiInstruction}
          onChange={(e) => setAiInstruction(e.target.value)}
          className="flex-1 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs dark:border-slate-700 dark:bg-slate-900"
        />
        <Button
          size="sm"
          disabled={genMut.isPending}
          onClick={handleGenerateAll}
        >
          {genMut.isPending ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Sparkles className="h-3.5 w-3.5" />
          )}
          AI 生成未锁定世界观
        </Button>
      </div>

      {errMsg && (
        <div className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">
          {errMsg}
        </div>
      )}

      {/* 手动新增 */}
      <form
        onSubmit={handleAddManual}
        className="flex flex-wrap items-center gap-2 rounded-xl border border-slate-200 bg-white p-3.5 text-xs dark:border-slate-800 dark:bg-slate-900"
      >
        <select
          value={newCat}
          onChange={(e) => setNewCat(e.target.value as WorldviewCategory)}
          className="rounded-lg border border-slate-300 px-2.5 py-1.5 dark:border-slate-700 dark:bg-slate-950"
        >
          {(Object.keys(CATEGORY_LABELS) as WorldviewCategory[]).map((cat) => (
            <option key={cat} value={cat}>
              {CATEGORY_LABELS[cat]}
            </option>
          ))}
        </select>
        <input
          type="text"
          placeholder="手动添加一条世界观设定（默认自动锁定）..."
          value={newContent}
          onChange={(e) => setNewContent(e.target.value)}
          className="flex-1 rounded-lg border border-slate-300 px-3 py-1.5 dark:border-slate-700 dark:bg-slate-950"
        />
        <Button type="submit" variant="outline" size="sm">
          <Plus className="h-3.5 w-3.5" />
          新增条目
        </Button>
      </form>

      {/* 条目卡片列表 */}
      {isLoading ? (
        <p className="text-xs text-slate-400">加载中...</p>
      ) : entries.length === 0 ? (
        <EmptyState
          title="尚未生成世界观条目"
          description="点击上方「AI 生成未锁定世界观」或手动添加时代背景、城市、学校与专有名词。"
        />
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {entries.map((entry) => (
            <div
              key={entry.id}
              className="flex flex-col justify-between rounded-xl border border-slate-200 bg-white p-4 shadow-2xs dark:border-slate-800 dark:bg-slate-900"
            >
              <div className="space-y-2.5">
                <div className="flex items-center justify-between">
                  <Badge tone="indigo">{CATEGORY_LABELS[entry.category]}</Badge>
                  <div className="flex items-center gap-1.5">
                    <LockToggle
                      locked={entry.locked}
                      onToggle={(next) =>
                        updateMut.mutate({ id: entry.id, input: { locked: next } })
                      }
                    />
                    <button
                      type="button"
                      onClick={() =>
                        setRewriteId(rewriteId === entry.id ? null : entry.id)
                      }
                      title="AI 按修改意见重写此条"
                      className="rounded-md p-1 text-slate-400 hover:bg-slate-100 hover:text-indigo-600 cursor-pointer"
                    >
                      <Wand2 className="h-3.5 w-3.5" />
                    </button>
                    <button
                      type="button"
                      onClick={() => deleteMut.mutate(entry.id)}
                      className="rounded-md p-1 text-slate-400 hover:bg-rose-50 hover:text-rose-600 cursor-pointer"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>

                <textarea
                  rows={3}
                  defaultValue={entry.content}
                  onBlur={(e) => {
                    const val = e.target.value.trim();
                    if (val && val !== entry.content) {
                      updateMut.mutate({ id: entry.id, input: { content: val } });
                    }
                  }}
                  className="w-full rounded-lg border border-transparent bg-slate-50/70 p-2 text-xs leading-relaxed text-slate-800 focus:border-indigo-400 focus:bg-white focus:outline-none dark:bg-slate-950/60 dark:text-slate-200"
                />

                {rewriteId === entry.id && (
                  <div className="flex items-center gap-2 pt-1">
                    <input
                      type="text"
                      placeholder="输入修改意见，让 AI 重写此条..."
                      value={rewritePrompt}
                      onChange={(e) => setRewritePrompt(e.target.value)}
                      className="flex-1 rounded-md border border-slate-300 px-2.5 py-1 text-xs dark:border-slate-700 dark:bg-slate-950"
                    />
                    <Button
                      size="sm"
                      disabled={rewriteMut.isPending}
                      onClick={() => handleRewrite(entry.id)}
                    >
                      {rewriteMut.isPending ? "重写中..." : "确定"}
                    </Button>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
