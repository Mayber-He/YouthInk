import React, { useState } from "react";
import { Loader2, Plus, Sparkles, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/common/EmptyState";
import { ConfirmModal } from "@/components/ui/ConfirmModal";
import { useUiStore } from "@/stores/uiStore";
import type { ArcTreeNode, ChapterItem } from "@/types/api";
import {
  useCreateArc,
  useCreateChapter,
  useCreateVolume,
  useDeleteArc,
  useDeleteChapter,
  useDeleteVolume,
  useGenerateArcChapters,
  useGenerateStructure,
  useOutlineTree,
  useReorderChapter,
  useUpdateChapter,
} from "./api";
import { ArcCard } from "./ArcCard";

interface OutlineSectionProps {
  novelUid: string;
}

export const OutlineSection: React.FC<OutlineSectionProps> = ({ novelUid }) => {
  const { data: tree, isLoading } = useOutlineTree(novelUid);
  const createVolMut = useCreateVolume(novelUid);
  const deleteVolMut = useDeleteVolume(novelUid);
  const createArcMut = useCreateArc(novelUid);
  const deleteArcMut = useDeleteArc(novelUid);
  const createChMut = useCreateChapter(novelUid);
  const updateChMut = useUpdateChapter(novelUid);
  const reorderChMut = useReorderChapter(novelUid);
  const deleteChMut = useDeleteChapter(novelUid);
  const genStructureMut = useGenerateStructure(novelUid);
  const genArcChMut = useGenerateArcChapters(novelUid);

  const { setSelectedChapterId, setActiveSection } = useUiStore();

  const [volCount, setVolCount] = useState(3);
  const [arcsPerVol, setArcsPerVol] = useState(2);
  const [aiInstruction, setAiInstruction] = useState("");
  const [errMsg, setErrMsg] = useState<string | null>(null);
  const [arcToRegenerate, setArcToRegenerate] = useState<ArcTreeNode | null>(null);
  const [confirmStructureReset, setConfirmStructureReset] = useState(false);

  const showMutationError = (err: unknown, fallback: string) => {
    setErrMsg(err instanceof Error ? err.message : fallback);
  };

  const handleUpdateChapter = async (
    chapterId: number,
    input: Partial<{ title: string; synopsis: string; locked: boolean }>
  ) => {
    setErrMsg(null);
    try {
      await updateChMut.mutateAsync({ id: chapterId, input });
    } catch (err) {
      showMutationError(err, "更新章节失败");
    }
  };

  const handleReorderChapter = (input: {
    target_id: number;
    prev_sort_order: number | null;
    next_sort_order: number | null;
  }) => {
    setErrMsg(null);
    void reorderChMut.mutateAsync(input).catch((err: unknown) => {
      showMutationError(err, "调整章节顺序失败");
    });
  };

  const handleGenerateStructure = async () => {
    setErrMsg(null);
    try {
      await genStructureMut.mutateAsync({
        volume_count: volCount,
        arcs_per_volume: arcsPerVol,
        instruction: aiInstruction,
      });
      setSelectedChapterId(null);
    } catch (err) {
      setErrMsg(err instanceof Error ? err.message : "生成分卷与情节弧失败");
    }
  };

  const requestGenerateStructure = () => {
    if (tree && tree.volumes.length > 0) {
      setConfirmStructureReset(true);
      return;
    }
    void handleGenerateStructure();
  };

  const generateArcChapters = async (arcId: number) => {
    setErrMsg(null);
    try {
      await genArcChMut.mutateAsync({ arcId });
    } catch (err) {
      showMutationError(err, "生成章节大纲失败");
    }
  };

  const handleGenerateArcChapters = (arc: ArcTreeNode) => {
    if (arc.chapters.length > 0) {
      setArcToRegenerate(arc);
      return;
    }
    void generateArcChapters(arc.id);
  };

  const handleMoveChapter = (
    chapters: ChapterItem[],
    index: number,
    direction: "up" | "down"
  ) => {
    const target = chapters[index];
    if (!target) return;
    if (direction === "up" && index > 0) {
      const prevPrev = index >= 2 ? chapters[index - 2].sort_order : null;
      const prev = chapters[index - 1].sort_order;
      handleReorderChapter({
        target_id: target.id,
        prev_sort_order: prevPrev,
        next_sort_order: prev,
      });
    } else if (direction === "down" && index < chapters.length - 1) {
      const next = chapters[index + 1].sort_order;
      const nextNext =
        index + 2 < chapters.length ? chapters[index + 2].sort_order : null;
      handleReorderChapter({
        target_id: target.id,
        prev_sort_order: next,
        next_sort_order: nextNext,
      });
    }
  };

  if (isLoading || !tree) {
    return <p className="p-6 text-xs text-slate-400">正在加载全书目录树...</p>;
  }

  const allArcs = tree.volumes.flatMap((volume) => volume.arcs);
  const allChapters = allArcs.flatMap((arc) => arc.chapters);

  return (
    <div className="mx-auto max-w-5xl space-y-6 p-6">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 pb-4 dark:border-slate-800">
        <div>
          <h1 className="text-lg font-bold text-slate-900 dark:text-slate-100">
            分卷 · 情节弧 · 章节目录（浮点排序 & 按弧滚动生成）
          </h1>
          <p className="mt-0.5 text-xs text-slate-500">
            共 {tree.volumes.length} 卷 · {tree.total_chapters} 章。章节排序号与显示「第几章」解耦，插入或移动章节不影响引用。
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() =>
            createVolMut.mutate({
              title: `第 ${tree.volumes.length + 1} 卷：新分卷`,
              synopsis: "",
              goal: "",
            })
          }
        >
          <Plus className="h-3.5 w-3.5" />
          手动新建分卷
        </Button>
      </div>

      {/* AI 生成分卷与情节弧 */}
      <div className="flex flex-wrap items-center gap-2.5 rounded-xl border border-indigo-200/80 bg-indigo-50/50 p-3.5 text-xs dark:border-indigo-900/50 dark:bg-indigo-950/30">
        <span className="font-medium text-slate-700 dark:text-slate-300">
          分卷数：
        </span>
        <input
          type="number"
          min={1}
          max={10}
          value={volCount}
          onChange={(e) => setVolCount(Number(e.target.value) || 3)}
          className="w-14 rounded-lg border border-slate-300 bg-white px-2 py-1 dark:border-slate-700 dark:bg-slate-900"
        />
        <span className="font-medium text-slate-700 dark:text-slate-300">
          每卷情节弧：
        </span>
        <input
          type="number"
          min={1}
          max={6}
          value={arcsPerVol}
          onChange={(e) => setArcsPerVol(Number(e.target.value) || 2)}
          className="w-14 rounded-lg border border-slate-300 bg-white px-2 py-1 dark:border-slate-700 dark:bg-slate-900"
        />
        <input
          type="text"
          placeholder="可选：补充结构偏好（如：按高一上、高二、高三毕业三阶段划分）"
          value={aiInstruction}
          onChange={(e) => setAiInstruction(e.target.value)}
          className="flex-1 rounded-lg border border-slate-300 bg-white px-3 py-1.5 dark:border-slate-700 dark:bg-slate-900"
        />
        <Button
          size="sm"
          disabled={genStructureMut.isPending}
          onClick={requestGenerateStructure}
        >
          {genStructureMut.isPending ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Sparkles className="h-3.5 w-3.5" />
          )}
          {tree.volumes.length > 0
            ? "清空并重新生成分卷与情节弧"
            : "AI 生成分卷与情节弧"}
        </Button>
      </div>

      <p className="-mt-4 text-xs text-slate-500">
        章节数按本弧的独立事件和剧情转折规划；没有新推进的日常过场会合并处理。
      </p>

      {errMsg && (
        <div className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">
          {errMsg}
        </div>
      )}

      {tree.volumes.length === 0 ? (
        <EmptyState
          title="尚未规划分卷与章节目录"
          description="点击上方「AI 生成分卷与情节弧」，随后在每个情节弧内一键滚动生成章节目录。"
        />
      ) : (
        <div className="space-y-6">
          {tree.volumes.map((vol) => (
            <div
              key={vol.id}
              className="rounded-2xl border border-slate-200 bg-white p-5 shadow-2xs dark:border-slate-800 dark:bg-slate-900"
            >
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-3 dark:border-slate-800">
                <div>
                  <h2 className="text-base font-bold text-slate-900 dark:text-slate-100">
                    {vol.title}
                  </h2>
                  {vol.synopsis && (
                    <p className="mt-0.5 text-xs text-slate-500">{vol.synopsis}</p>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() =>
                      createArcMut.mutate({
                        volume_id: vol.id,
                        title: `新情节弧 ${vol.arcs.length + 1}`,
                      })
                    }
                  >
                    <Plus className="h-3.5 w-3.5" />
                    添加情节弧
                  </Button>
                  <button
                    type="button"
                    onClick={() => deleteVolMut.mutate(vol.id)}
                    className="rounded-md p-1.5 text-slate-400 hover:bg-rose-50 hover:text-rose-600 cursor-pointer"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              </div>

              <div className="mt-4 space-y-4">
                {vol.arcs.map((arc) => (
                  <ArcCard
                    key={arc.id}
                    arc={arc}
                    isGenerating={genArcChMut.isPending}
                    onGenerateChapters={() => handleGenerateArcChapters(arc)}
                    onCreateChapter={(arcId) =>
                      createChMut.mutate({
                        arc_id: arcId,
                        title: "新章节",
                        locked: true,
                      })
                    }
                    onDeleteArc={(arcId) => deleteArcMut.mutate(arcId)}
                    onUpdateChapter={(chId, input) =>
                      void handleUpdateChapter(chId, input)
                    }
                    onMoveChapter={handleMoveChapter}
                    onOpenWriting={(chId) => {
                      setSelectedChapterId(chId);
                      setActiveSection("writing");
                    }}
                    onDeleteChapter={(chId) => deleteChMut.mutate(chId)}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
      <ConfirmModal
        open={confirmStructureReset}
        onClose={() => setConfirmStructureReset(false)}
        onConfirm={() => void handleGenerateStructure()}
        title="清空并重新生成全书目录？"
        description={`现有 ${tree.volumes.length} 卷、${allArcs.length} 条情节弧、${tree.total_chapters} 章将全部清除；其中 ${allChapters.filter((chapter) => chapter.word_count > 0).length} 章已有正文，${allChapters.filter((chapter) => chapter.status === "final").length} 章已定稿。章节版本、场景、章节记忆、摘要和向量索引也会清除。只有新结构生成并校验成功后才会替换；生成失败时现有内容保留。`}
        confirmText="清空并重新生成"
        confirmVariant="danger"
      />
      <ConfirmModal
        open={arcToRegenerate !== null}
        onClose={() => setArcToRegenerate(null)}
        onConfirm={() => {
          if (arcToRegenerate) void generateArcChapters(arcToRegenerate.id);
        }}
        title="重新生成本弧章节？"
        description={
          arcToRegenerate
            ? `「${arcToRegenerate.title}」的 ${arcToRegenerate.chapters.length} 个章节将全部清除，其中 ${arcToRegenerate.chapters.filter((chapter) => chapter.word_count > 0).length} 章已有正文，${arcToRegenerate.chapters.filter((chapter) => chapter.status === "final").length} 章已定稿。相关版本和章节记忆也会清除；其他情节弧保留，但后续章节会标记为上下文待更新。`
            : ""
        }
        confirmText="清除并重新生成"
        confirmVariant="danger"
      />
    </div>
  );
};
