import React, { useState } from "react";
import { Loader2, Plus, Sparkles, Trash2, Wand2 } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { LockToggle } from "@/components/common/LockToggle";
import { EmptyState } from "@/components/common/EmptyState";
import { useUiStore } from "@/stores/uiStore";
import {
  useCreateLocation,
  useDeleteLocation,
  useGenerateLocations,
  useLocations,
  useRewriteLocation,
  useUpdateLocation,
} from "./api";

interface LocationsSectionProps {
  novelUid: string;
}

export const LocationsSection: React.FC<LocationsSectionProps> = ({
  novelUid,
}) => {
  const { data: locations = [], isLoading } = useLocations(novelUid);
  const createMut = useCreateLocation(novelUid);
  const updateMut = useUpdateLocation(novelUid);
  const deleteMut = useDeleteLocation(novelUid);
  const genMut = useGenerateLocations(novelUid);
  const rewriteMut = useRewriteLocation(novelUid);
  const setActiveSection = useUiStore((s) => s.setActiveSection);

  const [aiInstruction, setAiInstruction] = useState("");
  const [newName, setNewName] = useState("");
  const [newType, setNewType] = useState("校园场所");
  const [rewriteId, setRewriteId] = useState<number | null>(null);
  const [rewritePrompt, setRewritePrompt] = useState("");
  const [errMsg, setErrMsg] = useState<string | null>(null);

  const handleGenerate = async () => {
    setErrMsg(null);
    try {
      await genMut.mutateAsync({ instruction: aiInstruction, count: 4 });
    } catch (err) {
      setErrMsg(err instanceof Error ? err.message : "生成地点失败");
    }
  };

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newName.trim()) return;
    await createMut.mutateAsync({
      name: newName.trim(),
      type: newType.trim() || "校园场所",
      locked: true,
    });
    setNewName("");
  };

  const handleRewrite = async (id: number) => {
    if (!rewritePrompt.trim()) return;
    setErrMsg(null);
    try {
      await rewriteMut.mutateAsync({ id, instruction: rewritePrompt.trim() });
      setRewriteId(null);
      setRewritePrompt("");
    } catch (err) {
      setErrMsg(err instanceof Error ? err.message : "重写地点失败");
    }
  };

  return (
    <div className="mx-auto max-w-5xl space-y-6 p-6">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 pb-4 dark:border-slate-800">
        <div>
          <h1 className="text-lg font-bold text-slate-900 dark:text-slate-100">
            地点与感官细节设定
          </h1>
          <p className="mt-0.5 text-xs text-slate-500">
            每个核心场景包含声音、气味、光线等感官细节，写作时自动根据场景地点注入上下文。
          </p>
        </div>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => setActiveSection("main_plot")}
        >
          下一步：规划主线剧情
        </Button>
      </div>

      {/* AI 生成 */}
      <div className="flex flex-wrap items-center gap-2 rounded-xl border border-indigo-200/80 bg-indigo-50/50 p-3.5 dark:border-indigo-900/50 dark:bg-indigo-950/30">
        <input
          type="text"
          placeholder="可选：补充地点偏好（如：老城区书店、画室天台、放学必经的跨江大桥）"
          value={aiInstruction}
          onChange={(e) => setAiInstruction(e.target.value)}
          className="flex-1 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs dark:border-slate-700 dark:bg-slate-900"
        />
        <Button size="sm" disabled={genMut.isPending} onClick={handleGenerate}>
          {genMut.isPending ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Sparkles className="h-3.5 w-3.5" />
          )}
          AI 生成未锁定地点
        </Button>
      </div>

      {errMsg && (
        <div className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">
          {errMsg}
        </div>
      )}

      {/* 手动新增 */}
      <form
        onSubmit={handleAdd}
        className="flex flex-wrap items-center gap-2 rounded-xl border border-slate-200 bg-white p-3.5 text-xs dark:border-slate-800 dark:bg-slate-900"
      >
        <input
          type="text"
          placeholder="类型（如：校园场所 / 街道）"
          value={newType}
          onChange={(e) => setNewType(e.target.value)}
          className="w-36 rounded-lg border border-slate-300 px-2.5 py-1.5 dark:border-slate-700 dark:bg-slate-950"
        />
        <input
          type="text"
          placeholder="地点名称（如：实验楼三楼画室）..."
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          className="flex-1 rounded-lg border border-slate-300 px-3 py-1.5 dark:border-slate-700 dark:bg-slate-950"
        />
        <Button type="submit" variant="outline" size="sm">
          <Plus className="h-3.5 w-3.5" />
          新增地点
        </Button>
      </form>

      {isLoading ? (
        <p className="text-xs text-slate-400">加载中...</p>
      ) : locations.length === 0 ? (
        <EmptyState
          title="尚未创建故事地点"
          description="点击「AI 生成未锁定地点」或手动添加教室、操场、街道等核心场所。"
        />
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {locations.map((loc) => (
            <div
              key={loc.id}
              className="space-y-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-2xs dark:border-slate-800 dark:bg-slate-900"
            >
              <div className="flex items-center justify-between border-b border-slate-100 pb-2 dark:border-slate-800">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-bold text-slate-900 dark:text-slate-100">
                    {loc.name}
                  </span>
                  <Badge tone="indigo">{loc.type || "场所"}</Badge>
                </div>
                <div className="flex items-center gap-1.5">
                  <LockToggle
                    locked={loc.locked}
                    onToggle={(next) =>
                      updateMut.mutate({ id: loc.id, input: { locked: next } })
                    }
                  />
                  <button
                    type="button"
                    onClick={() =>
                      setRewriteId(rewriteId === loc.id ? null : loc.id)
                    }
                    className="rounded-md p-1 text-slate-400 hover:bg-slate-100 hover:text-indigo-600 cursor-pointer"
                  >
                    <Wand2 className="h-3.5 w-3.5" />
                  </button>
                  <button
                    type="button"
                    onClick={() => deleteMut.mutate(loc.id)}
                    className="rounded-md p-1 text-slate-400 hover:bg-rose-50 hover:text-rose-600 cursor-pointer"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>

              <div className="space-y-2 text-xs">
                <div>
                  <label className="text-[11px] font-medium text-slate-500">
                    空间与环境描述
                  </label>
                  <textarea
                    rows={2}
                    defaultValue={loc.description}
                    onBlur={(e) => {
                      const val = e.target.value.trim();
                      if (val !== loc.description) {
                        updateMut.mutate({
                          id: loc.id,
                          input: { description: val },
                        });
                      }
                    }}
                    className="mt-0.5 w-full rounded-lg border border-slate-200 bg-slate-50/70 p-2 text-xs dark:border-slate-800 dark:bg-slate-950"
                  />
                </div>
                <div>
                  <label className="text-[11px] font-medium text-slate-500">
                    感官细节（声音、气味、光线）
                  </label>
                  <textarea
                    rows={2}
                    defaultValue={loc.sensory_details}
                    onBlur={(e) => {
                      const val = e.target.value.trim();
                      if (val !== loc.sensory_details) {
                        updateMut.mutate({
                          id: loc.id,
                          input: { sensory_details: val },
                        });
                      }
                    }}
                    className="mt-0.5 w-full rounded-lg border border-slate-200 bg-slate-50/70 p-2 text-xs dark:border-slate-800 dark:bg-slate-950"
                  />
                </div>
              </div>

              {rewriteId === loc.id && (
                <div className="flex items-center gap-2 pt-1">
                  <input
                    type="text"
                    placeholder="输入修改意见，让 AI 重写该地点..."
                    value={rewritePrompt}
                    onChange={(e) => setRewritePrompt(e.target.value)}
                    className="flex-1 rounded-md border border-slate-300 px-2.5 py-1 text-xs dark:border-slate-700 dark:bg-slate-950"
                  />
                  <Button
                    size="sm"
                    disabled={rewriteMut.isPending}
                    onClick={() => handleRewrite(loc.id)}
                  >
                    {rewriteMut.isPending ? "重写中..." : "确定"}
                  </Button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
