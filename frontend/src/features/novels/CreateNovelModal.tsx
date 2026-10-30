import React, { useState } from "react";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { useStyleTemplates } from "@/features/app-settings/api";
import { useCreateNovel } from "./api";
import type { NovelDetail } from "@/types/api";

interface CreateNovelModalProps {
  open: boolean;
  onClose: () => void;
  onCreated: (novel: NovelDetail) => void;
}

export const CreateNovelModal: React.FC<CreateNovelModalProps> = ({
  open,
  onClose,
  onCreated,
}) => {
  const { data: styles = [] } = useStyleTemplates();
  const createMut = useCreateNovel();

  const [title, setTitle] = useState("");
  const [genre, setGenre] = useState("校园");
  const [tone, setTone] = useState("清新治愈");
  const [pov, setPov] = useState("第三人称限知");
  const [protagonistConcept, setProtagonistConcept] = useState("");
  const [synopsis, setSynopsis] = useState("");
  const [targetWords, setTargetWords] = useState(1000000);
  const [wordsPerChapter, setWordsPerChapter] = useState(2500);
  const [romanceEnding, setRomanceEnding] = useState("HE");
  const [growthEnding, setGrowthEnding] = useState("HE");
  const [endingNote, setEndingNote] = useState("");
  const [styleNote, setStyleNote] = useState("");
  const [styleTemplateId, setStyleTemplateId] = useState<number | null>(1);
  const [error, setError] = useState<string | null>(null);

  const estimatedChapters = Math.max(1, Math.round(targetWords / wordsPerChapter));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!title.trim()) {
      setError("请输入小说书名");
      return;
    }
    try {
      const created = await createMut.mutateAsync({
        title: title.trim(),
        genre,
        tone,
        pov,
        protagonist_concept: protagonistConcept.trim(),
        synopsis: synopsis.trim(),
        target_words: targetWords,
        estimated_chapters: estimatedChapters,
        words_per_chapter: wordsPerChapter,
        romance_ending: romanceEnding,
        growth_ending: growthEnding,
        ending_note: endingNote.trim(),
        style_note: styleNote.trim(),
        style_template_id: styleTemplateId,
      });
      onCreated(created);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "创建作品失败");
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="新建青春小说立项（设计文档 4.1）"
      maxWidthClass="max-w-3xl"
    >
      <form onSubmit={handleSubmit} className="space-y-4 text-xs">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div className="sm:col-span-2">
            <label className="font-medium text-slate-700 dark:text-slate-300">
              书名 *
            </label>
            <input
              type="text"
              required
              placeholder="如：盛夏的柠檬汽水"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
            />
          </div>

          <div>
            <label className="font-medium text-slate-700 dark:text-slate-300">题材</label>
            <select
              value={genre}
              onChange={(e) => setGenre(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 dark:border-slate-700 dark:bg-slate-950"
            >
              {["校园", "都市青春", "成长群像", "双向暗恋", "破镜重圆", "青梅竹马"].map(
                (g) => (
                  <option key={g} value={g}>
                    {g}
                  </option>
                )
              )}
            </select>
          </div>

          <div>
            <label className="font-medium text-slate-700 dark:text-slate-300">基调</label>
            <select
              value={tone}
              onChange={(e) => setTone(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 dark:border-slate-700 dark:bg-slate-950"
            >
              {["清新治愈", "细腻文艺", "轻松搞笑", "现实向", "微虐酸甜"].map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="font-medium text-slate-700 dark:text-slate-300">
              叙事视角
            </label>
            <select
              value={pov}
              onChange={(e) => setPov(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 dark:border-slate-700 dark:bg-slate-950"
            >
              {["第一人称", "第三人称限知", "第三人称全知", "多视角轮换"].map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="font-medium text-slate-700 dark:text-slate-300">
              关联风格模板
            </label>
            <select
              value={styleTemplateId ?? ""}
              onChange={(e) =>
                setStyleTemplateId(e.target.value ? Number(e.target.value) : null)
              }
              className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 dark:border-slate-700 dark:bg-slate-950"
            >
              {styles.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}（{s.tone} · {s.pacing}）
                </option>
              ))}
            </select>
          </div>
        </div>

        <div>
          <label className="font-medium text-slate-700 dark:text-slate-300">
            主角概念设定
          </label>
          <input
            type="text"
            placeholder="如：慢热清醒的插画特长生林夏 × 外冷内热的竞赛保送生陆川"
            value={protagonistConcept}
            onChange={(e) => setProtagonistConcept(e.target.value)}
            className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 dark:border-slate-700 dark:bg-slate-950"
          />
        </div>

        <div>
          <label className="font-medium text-slate-700 dark:text-slate-300">
            故事梗概（一句话或大致构想）
          </label>
          <textarea
            rows={3}
            placeholder="填写大致构想，后续可据此一键依次生成世界观、人物、地点与全书目录..."
            value={synopsis}
            onChange={(e) => setSynopsis(e.target.value)}
            className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 dark:border-slate-700 dark:bg-slate-950"
          />
        </div>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-4">
          <div>
            <label className="font-medium text-slate-700 dark:text-slate-300">
              目标总字数
            </label>
            <input
              type="number"
              step={50000}
              value={targetWords}
              onChange={(e) => setTargetWords(Number(e.target.value) || 1000000)}
              className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-1.5 dark:border-slate-700 dark:bg-slate-950"
            />
          </div>
          <div>
            <label className="font-medium text-slate-700 dark:text-slate-300">
              单章字数
            </label>
            <input
              type="number"
              step={500}
              value={wordsPerChapter}
              onChange={(e) => setWordsPerChapter(Number(e.target.value) || 2500)}
              className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-1.5 dark:border-slate-700 dark:bg-slate-950"
            />
          </div>
          <div>
            <label className="font-medium text-slate-700 dark:text-slate-300">
              感情线结局
            </label>
            <select
              value={romanceEnding}
              onChange={(e) => setRomanceEnding(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-1.5 dark:border-slate-700 dark:bg-slate-950"
            >
              {["HE", "BE", "开放式", "遗憾向", "自定义"].map((opt) => (
                <option key={opt} value={opt}>
                  {opt}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="font-medium text-slate-700 dark:text-slate-300">
              成长线结局
            </label>
            <select
              value={growthEnding}
              onChange={(e) => setGrowthEnding(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-1.5 dark:border-slate-700 dark:bg-slate-950"
            >
              {["HE", "BE", "开放式", "遗憾向", "自定义"].map((opt) => (
                <option key={opt} value={opt}>
                  {opt}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div>
            <label className="font-medium text-slate-700 dark:text-slate-300">
              结局补充说明
            </label>
            <input
              type="text"
              placeholder="如：高考后各自去往不同城市，大四重逢"
              value={endingNote}
              onChange={(e) => setEndingNote(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-1.5 dark:border-slate-700 dark:bg-slate-950"
            />
          </div>
          <div>
            <label className="font-medium text-slate-700 dark:text-slate-300">
              文风补充说明
            </label>
            <input
              type="text"
              placeholder="如：多用南方初夏感官意象，少用心理独白"
              value={styleNote}
              onChange={(e) => setStyleNote(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-1.5 dark:border-slate-700 dark:bg-slate-950"
            />
          </div>
        </div>

        {error && <p className="text-xs text-rose-600">{error}</p>}

        <div className="flex items-center justify-between border-t border-slate-200 pt-4 dark:border-slate-800">
          <span className="text-xs text-slate-500">
            预计共 <strong>{estimatedChapters}</strong> 章（独立目录存储 novel.db）
          </span>
          <div className="flex items-center gap-2">
            <Button type="button" variant="outline" onClick={onClose}>
              取消
            </Button>
            <Button type="submit" disabled={createMut.isPending}>
              {createMut.isPending ? "创建中..." : "创建并进入工作台"}
            </Button>
          </div>
        </div>
      </form>
    </Modal>
  );
};
