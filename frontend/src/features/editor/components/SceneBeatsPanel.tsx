import React, { useState } from "react";
import { Loader2, Play, Plus, Sparkles, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import type { CharacterItem, LocationItem } from "@/types/api";
import type { SceneItem } from "../types";
import {
  useCreateScene,
  useDeleteScene,
  useGenerateScenes,
  useUpdateScene,
} from "../api";

interface SceneBeatsPanelProps {
  novelUid: string;
  chapterId: number;
  scenes: SceneItem[];
  characters: CharacterItem[];
  locations: LocationItem[];
  activeSceneId: number | null;
  isStreaming: boolean;
  onSelectScene: (sceneId: number | null) => void;
  onWriteScene: (scene: SceneItem) => void;
  onStartWriting: () => void;
}

export const SceneBeatsPanel: React.FC<SceneBeatsPanelProps> = ({
  novelUid,
  chapterId,
  scenes,
  characters,
  locations,
  activeSceneId,
  isStreaming,
  onSelectScene,
  onWriteScene,
  onStartWriting,
}) => {
  const createMut = useCreateScene(novelUid, chapterId);
  const updateMut = useUpdateScene(novelUid, chapterId);
  const deleteMut = useDeleteScene(novelUid, chapterId);
  const genMut = useGenerateScenes(novelUid, chapterId);

  const [newBeat, setNewBeat] = useState("");
  const [targetWords, setTargetWords] = useState(800);

  const insertMention = (name: string) => {
    setNewBeat((prev) => `${prev}${prev.endsWith(" ") || !prev ? "" : " "}@${name} `);
  };

  const handleAddScene = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newBeat.trim()) return;
    await createMut.mutateAsync({
      beat: newBeat.trim(),
      target_words: targetWords,
    });
    setNewBeat("");
  };

  return (
    <div className="space-y-4 text-xs">
      <div className="flex items-center justify-between">
        <span className="font-semibold text-slate-800 dark:text-slate-200">
          场景节拍 ({scenes.length})
        </span>
        <div className="flex items-center gap-1.5">
          <Button
            size="sm"
            disabled={genMut.isPending}
            onClick={() => genMut.mutate({ scene_count: 3, instruction: "" })}
          >
            {genMut.isPending ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Sparkles className="h-3.5 w-3.5" />
            )}
            AI 拆解细纲
          </Button>
          <Button
            size="sm"
            disabled={isStreaming || scenes.length === 0}
            onClick={onStartWriting}
            title="按当前节拍逐场生成正文"
          >
            <Play className="h-3.5 w-3.5" />
            开始写
          </Button>
        </div>
      </div>

      {/* @人物 / @地点 快捷引用胶囊（设计文档 6.4） */}
      {(characters.length > 0 || locations.length > 0) && (
        <div className="space-y-1.5 rounded-lg bg-slate-50 p-2.5 dark:bg-slate-800/50">
          <div className="text-[10px] font-medium text-slate-400">
            点击快捷插入 @人物 / @地点 关联：
          </div>
          <div className="flex flex-wrap gap-1">
            {characters.slice(0, 6).map((c) => (
              <button
                key={`c-${c.id}`}
                type="button"
                onClick={() => insertMention(c.name)}
                className="rounded bg-indigo-50 px-1.5 py-0.5 text-[11px] font-medium text-indigo-700 hover:bg-indigo-100 dark:bg-indigo-950/60 dark:text-indigo-300 cursor-pointer"
              >
                @{c.name}
              </button>
            ))}
            {locations.slice(0, 4).map((l) => (
              <button
                key={`l-${l.id}`}
                type="button"
                onClick={() => insertMention(l.name)}
                className="rounded bg-emerald-50 px-1.5 py-0.5 text-[11px] font-medium text-emerald-700 hover:bg-emerald-100 dark:bg-emerald-950/60 dark:text-emerald-300 cursor-pointer"
              >
                @{l.name}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* 新增场景节拍 */}
      <form onSubmit={handleAddScene} className="space-y-2">
        <textarea
          rows={2}
          placeholder="输入场景节拍（如：@林夏 在 @广播站 试音，偶遇 @陆川）..."
          value={newBeat}
          onChange={(e) => setNewBeat(e.target.value)}
          className="w-full rounded-lg border border-slate-300 bg-white p-2 text-xs dark:border-slate-700 dark:bg-slate-950"
        />
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <span className="text-[11px] text-slate-500">目标字数:</span>
            <input
              type="number"
              step={100}
              value={targetWords}
              onChange={(e) => setTargetWords(Number(e.target.value) || 800)}
              className="w-16 rounded border border-slate-300 px-1.5 py-0.5 text-xs dark:border-slate-700 dark:bg-slate-950"
            />
          </div>
          <Button type="submit" variant="outline" size="sm">
            <Plus className="h-3.5 w-3.5" />
            添加场景
          </Button>
        </div>
      </form>

      {/* 场景卡片列表 */}
      <div className="space-y-2.5">
        {scenes.map((scene, idx) => {
          const isSelected = activeSceneId === scene.id;
          return (
            <div
              key={scene.id}
              onClick={() => onSelectScene(scene.id)}
              className={`rounded-xl border p-3 transition-colors cursor-pointer ${
                isSelected
                  ? "border-indigo-400 bg-indigo-50/40 dark:border-indigo-700 dark:bg-indigo-950/30"
                  : "border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900"
              }`}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1.5">
                  <span className="font-semibold text-indigo-600 dark:text-indigo-400">
                    场景 {idx + 1}
                  </span>
                  <Badge>{scene.target_words} 字</Badge>
                </div>
                <div className="flex items-center gap-1">
                  <Button
                    size="sm"
                    disabled={isStreaming}
                    onClick={(e) => {
                      e.stopPropagation();
                      onWriteScene(scene);
                    }}
                  >
                    <Play className="h-3 w-3" />
                    续写此景
                  </Button>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      deleteMut.mutate(scene.id);
                    }}
                    className="rounded p-1 text-slate-400 hover:bg-rose-50 hover:text-rose-600 cursor-pointer"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>

              <textarea
                rows={2}
                defaultValue={scene.beat}
                onClick={(e) => e.stopPropagation()}
                onBlur={(e) => {
                  const val = e.target.value.trim();
                  if (val && val !== scene.beat) {
                    updateMut.mutate({ sceneId: scene.id, input: { beat: val } });
                  }
                }}
                className="mt-2 w-full rounded border border-transparent bg-slate-50/80 p-1.5 text-xs leading-relaxed text-slate-700 focus:border-indigo-400 focus:bg-white focus:outline-none dark:bg-slate-950/60 dark:text-slate-200"
              />
            </div>
          );
        })}
      </div>
    </div>
  );
};
