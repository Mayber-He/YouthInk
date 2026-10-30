import React, { useState } from "react";
import { Clock, Loader2, Plus, Sparkles, Trash2, Wand2 } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { LockToggle } from "@/components/common/LockToggle";
import { EmptyState } from "@/components/common/EmptyState";
import { useOutlineTree } from "@/features/outline/api";
import { useUiStore } from "@/stores/uiStore";
import type { CharacterItem, CharacterRole } from "@/types/api";
import {
  useCharacters,
  useCreateCharacter,
  useDeleteCharacter,
  useGenerateCharacters,
  useRewriteCharacter,
  useUpdateCharacter,
} from "./api";
import { CharacterTimelineModal } from "./CharacterTimelineModal";

const ROLE_LABELS: Record<CharacterRole, string> = {
  female_lead: "女主",
  male_lead: "男主",
  major: "重要配角",
  minor: "配角",
  extra: "路人",
};

interface CharactersSectionProps {
  novelUid: string;
}

export const CharactersSection: React.FC<CharactersSectionProps> = ({
  novelUid,
}) => {
  const { data: chars = [], isLoading } = useCharacters(novelUid);
  const { data: outline } = useOutlineTree(novelUid);
  const createMut = useCreateCharacter(novelUid);
  const updateMut = useUpdateCharacter(novelUid);
  const deleteMut = useDeleteCharacter(novelUid);
  const genMut = useGenerateCharacters(novelUid);
  const rewriteMut = useRewriteCharacter(novelUid);
  const setActiveSection = useUiStore((s) => s.setActiveSection);

  const [aiInstruction, setAiInstruction] = useState("");
  const [newName, setNewName] = useState("");
  const [newRole, setNewRole] = useState<CharacterRole>("major");
  const [rewriteId, setRewriteId] = useState<number | null>(null);
  const [rewritePrompt, setRewritePrompt] = useState("");
  const [timelineChar, setTimelineChar] = useState<CharacterItem | null>(null);
  const [errMsg, setErrMsg] = useState<string | null>(null);

  const allChapters =
    outline?.volumes.flatMap((v) => v.arcs.flatMap((a) => a.chapters)) ?? [];

  const handleGenerate = async () => {
    setErrMsg(null);
    try {
      await genMut.mutateAsync({ instruction: aiInstruction, count: 4 });
    } catch (err) {
      setErrMsg(err instanceof Error ? err.message : "生成人物卡失败");
    }
  };

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newName.trim()) return;
    await createMut.mutateAsync({
      name: newName.trim(),
      role: newRole,
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
      setErrMsg(err instanceof Error ? err.message : "重写人物卡失败");
    }
  };

  return (
    <div className="mx-auto max-w-5xl space-y-6 p-6">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 pb-4 dark:border-slate-800">
        <div>
          <h1 className="text-lg font-bold text-slate-900 dark:text-slate-100">
            人物卡设定与状态时间轴
          </h1>
          <p className="mt-0.5 text-xs text-slate-500">
            静态基准外貌与性格内核。点击人物卡上的「状态时间轴」可回溯任意章节时的状态、关系与认知。
          </p>
        </div>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => setActiveSection("locations")}
        >
          下一步：设计地点场景
        </Button>
      </div>

      {/* AI 生成 */}
      <div className="flex flex-wrap items-center gap-2 rounded-xl border border-indigo-200/80 bg-indigo-50/50 p-3.5 dark:border-indigo-900/50 dark:bg-indigo-950/30">
        <input
          type="text"
          placeholder="可选：补充人物生成要求（如：增加一位嘴硬心软的闺蜜和一位美术集训班竞争对手）"
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
          AI 生成未锁定人物卡
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
        <select
          value={newRole}
          onChange={(e) => setNewRole(e.target.value as CharacterRole)}
          className="rounded-lg border border-slate-300 px-2.5 py-1.5 dark:border-slate-700 dark:bg-slate-950"
        >
          {(Object.keys(ROLE_LABELS) as CharacterRole[]).map((r) => (
            <option key={r} value={r}>
              {ROLE_LABELS[r]}
            </option>
          ))}
        </select>
        <input
          type="text"
          placeholder="输入新角色姓名（如：林夏）..."
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          className="flex-1 rounded-lg border border-slate-300 px-3 py-1.5 dark:border-slate-700 dark:bg-slate-950"
        />
        <Button type="submit" variant="outline" size="sm">
          <Plus className="h-3.5 w-3.5" />
          新增角色
        </Button>
      </form>

      {isLoading ? (
        <p className="text-xs text-slate-400">加载中...</p>
      ) : chars.length === 0 ? (
        <EmptyState
          title="尚未创建人物卡"
          description="点击「AI 生成未锁定人物卡」或手动添加男女主及重要配角。"
        />
      ) : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {chars.map((c) => (
            <div
              key={c.id}
              className="space-y-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-2xs dark:border-slate-800 dark:bg-slate-900"
            >
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-2.5 dark:border-slate-800">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-bold text-slate-900 dark:text-slate-100">
                    {c.name}
                  </span>
                  <Badge
                    tone={
                      c.role === "female_lead" || c.role === "male_lead"
                        ? "indigo"
                        : "default"
                    }
                  >
                    {ROLE_LABELS[c.role]}
                  </Badge>
                  {c.initial_age && <Badge>{c.initial_age}</Badge>}
                </div>
                <div className="flex items-center gap-1.5">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setTimelineChar(c)}
                  >
                    <Clock className="h-3.5 w-3.5 text-indigo-600" />
                    状态时间轴
                  </Button>
                  <LockToggle
                    locked={c.locked}
                    onToggle={(next) =>
                      updateMut.mutate({ id: c.id, input: { locked: next } })
                    }
                  />
                  <button
                    type="button"
                    onClick={() => setRewriteId(rewriteId === c.id ? null : c.id)}
                    title="AI 按修改意见重写"
                    className="rounded-md p-1 text-slate-400 hover:bg-slate-100 hover:text-indigo-600 cursor-pointer"
                  >
                    <Wand2 className="h-3.5 w-3.5" />
                  </button>
                  <button
                    type="button"
                    onClick={() => deleteMut.mutate(c.id)}
                    className="rounded-md p-1 text-slate-400 hover:bg-rose-50 hover:text-rose-600 cursor-pointer"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>

              <div className="grid grid-cols-1 gap-2.5 text-xs sm:grid-cols-2">
                {(
                  [
                    ["appearance", "外貌基准"],
                    ["personality", "性格内核"],
                    ["speech_style", "说话风格与口头禅"],
                    ["background", "家庭背景与过往"],
                    ["arc_design", "人物成长弧光"],
                  ] as const
                ).map(([field, label]) => (
                  <div
                    key={field}
                    className={field === "arc_design" ? "sm:col-span-2" : ""}
                  >
                    <label className="text-[11px] font-medium text-slate-500">
                      {label}
                    </label>
                    <textarea
                      rows={2}
                      defaultValue={c[field]}
                      onBlur={(e) => {
                        const val = e.target.value.trim();
                        if (val !== c[field]) {
                          updateMut.mutate({ id: c.id, input: { [field]: val } });
                        }
                      }}
                      className="mt-0.5 w-full rounded-lg border border-slate-200 bg-slate-50/70 p-2 text-xs text-slate-800 focus:border-indigo-400 focus:bg-white focus:outline-none dark:border-slate-800 dark:bg-slate-950 dark:text-slate-200"
                    />
                  </div>
                ))}
              </div>

              {rewriteId === c.id && (
                <div className="flex items-center gap-2 pt-1">
                  <input
                    type="text"
                    placeholder="输入修改意见，让 AI 重写该人物卡..."
                    value={rewritePrompt}
                    onChange={(e) => setRewritePrompt(e.target.value)}
                    className="flex-1 rounded-md border border-slate-300 px-2.5 py-1 text-xs dark:border-slate-700 dark:bg-slate-950"
                  />
                  <Button
                    size="sm"
                    disabled={rewriteMut.isPending}
                    onClick={() => handleRewrite(c.id)}
                  >
                    {rewriteMut.isPending ? "重写中..." : "确定"}
                  </Button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      <CharacterTimelineModal
        novelUid={novelUid}
        character={timelineChar}
        chapters={allChapters}
        onClose={() => setTimelineChar(null)}
      />
    </div>
  );
};
