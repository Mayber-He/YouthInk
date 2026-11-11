import React, { useEffect, useState } from "react";
import { Check, Save, Sliders, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { useStyleTemplates } from "@/features/app-settings/api";
import { useUpdateNovel } from "./api";
import type { NovelDetail } from "@/types/api";
import { useUiStore } from "@/stores/uiStore";

interface ProjectInitiationViewProps {
  novel: NovelDetail;
}

export const ProjectInitiationView: React.FC<ProjectInitiationViewProps> = ({
  novel,
}) => {
  const { data: styles = [] } = useStyleTemplates();
  const updateMut = useUpdateNovel(novel.novel_uid);
  const setActiveSection = useUiStore((s) => s.setActiveSection);
  const openSettingsModal = useUiStore((s) => s.openSettingsModal);

  const [title, setTitle] = useState(novel.title);
  const [genre, setGenre] = useState(novel.genre ?? "校园");
  const [tone, setTone] = useState(novel.tone ?? "清新治愈");
  const [pov, setPov] = useState(novel.pov ?? "第三人称限知");
  const [protagonist, setProtagonist] = useState(novel.protagonist_concept ?? "");
  const [synopsis, setSynopsis] = useState(novel.synopsis ?? "");
  const [targetWords, setTargetWords] = useState(novel.target_words);
  const [wordsPerChapter, setWordsPerChapter] = useState(novel.words_per_chapter);
  const [romanceEnding, setRomanceEnding] = useState(novel.romance_ending ?? "HE");
  const [growthEnding, setGrowthEnding] = useState(novel.growth_ending ?? "HE");
  const [endingNote, setEndingNote] = useState(novel.ending_note ?? "");
  const [styleNote, setStyleNote] = useState(novel.style_note ?? "");
  const [styleTemplateId, setStyleTemplateId] = useState<number | null>(
    novel.style_template_id
  );
  const [savedBanner, setSavedBanner] = useState(false);

  useEffect(() => {
    setTitle(novel.title);
    setGenre(novel.genre ?? "校园");
    setTone(novel.tone ?? "清新治愈");
    setPov(novel.pov ?? "第三人称限知");
    setProtagonist(novel.protagonist_concept ?? "");
    setSynopsis(novel.synopsis ?? "");
    setTargetWords(novel.target_words);
    setWordsPerChapter(novel.words_per_chapter);
    setRomanceEnding(novel.romance_ending ?? "HE");
    setGrowthEnding(novel.growth_ending ?? "HE");
    setEndingNote(novel.ending_note ?? "");
    setStyleNote(novel.style_note ?? "");
    setStyleTemplateId(novel.style_template_id);
  }, [novel]);

  const selectedStyle = styles.find((s) => s.id === styleTemplateId) ?? styles[0];
  const activeProfile = selectedStyle?.style_profile ?? null;

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    await updateMut.mutateAsync({
      title: title.trim(),
      genre,
      tone,
      pov,
      protagonist_concept: protagonist,
      synopsis,
      target_words: targetWords,
      estimated_chapters: Math.max(1, Math.round(targetWords / wordsPerChapter)),
      words_per_chapter: wordsPerChapter,
      romance_ending: romanceEnding,
      growth_ending: growthEnding,
      ending_note: endingNote,
      style_note: styleNote,
      style_template_id: styleTemplateId,
    });
    setSavedBanner(true);
    setTimeout(() => setSavedBanner(false), 2000);
  };

  return (
    <div className="mx-auto max-w-4xl space-y-6 p-6">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 pb-4 dark:border-slate-800">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-lg font-bold text-slate-900 dark:text-slate-100">
              作品立项配置
            </h1>
            <Badge tone="indigo">{novel.novel_uid}</Badge>
          </div>
          <p className="mt-0.5 text-xs text-slate-500">
            立项信息与结构化六维文风档案将作为全书核心设定注入后续世界观、大纲与正文生成。
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            size="sm"
            onClick={() => setActiveSection("worldview")}
          >
            <Sparkles className="h-3.5 w-3.5 text-indigo-600" />
            下一步：构建世界观
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
                保存立项修改
              </>
            )}
          </Button>
        </div>
      </div>

      <form onSubmit={handleSave} className="space-y-5 text-xs">
        <div className="grid grid-cols-1 gap-4 rounded-xl border border-slate-200 bg-white p-5 sm:grid-cols-3 dark:border-slate-800 dark:bg-slate-900">
          <div className="sm:col-span-2">
            <label className="font-semibold text-slate-700 dark:text-slate-300">
              小说书名
            </label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
            />
          </div>
          <div>
            <div className="flex items-center justify-between">
              <label className="font-semibold text-slate-700 dark:text-slate-300">
                关联风格模板
              </label>
              <button
                type="button"
                onClick={() => openSettingsModal("styles")}
                className="inline-flex items-center gap-1 text-[11px] font-medium text-indigo-600 hover:underline dark:text-indigo-400 cursor-pointer"
              >
                <Sliders className="h-3 w-3" />
                样本学习 / 编辑档案
              </button>
            </div>
            <select
              value={styleTemplateId ?? ""}
              onChange={(e) =>
                setStyleTemplateId(e.target.value ? Number(e.target.value) : null)
              }
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
            >
              {styles.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}（{s.tone}）
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="font-semibold text-slate-700 dark:text-slate-300">题材</label>
            <input
              type="text"
              value={genre}
              onChange={(e) => setGenre(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-1.5 dark:border-slate-700 dark:bg-slate-950"
            />
          </div>
          <div>
            <label className="font-semibold text-slate-700 dark:text-slate-300">基调</label>
            <input
              type="text"
              value={tone}
              onChange={(e) => setTone(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-1.5 dark:border-slate-700 dark:bg-slate-950"
            />
          </div>
          <div>
            <label className="font-semibold text-slate-700 dark:text-slate-300">
              叙事视角
            </label>
            <select
              value={pov}
              onChange={(e) => setPov(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-1.5 dark:border-slate-700 dark:bg-slate-950"
            >
              {["第一人称", "第三人称限知", "第三人称全知", "多视角轮换"].map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
          </div>

          {activeProfile && (
            <div className="sm:col-span-3 rounded-xl border border-indigo-200/70 bg-indigo-50/40 p-3.5 dark:border-indigo-900/50 dark:bg-indigo-950/20">
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span className="font-bold text-indigo-950 dark:text-indigo-200">
                    当前生效六维文风档案：{selectedStyle?.name}
                  </span>
                  <Badge tone="indigo">
                    对白目标 {activeProfile.language.metrics.dialogue_ratio_pct}% · 短句{" "}
                    {activeProfile.language.metrics.short_sentence_pct}%
                  </Badge>
                </div>
                <button
                  type="button"
                  onClick={() => openSettingsModal("styles")}
                  className="text-[11px] font-medium text-indigo-600 hover:underline dark:text-indigo-400 cursor-pointer"
                >
                  导入参考小说片段或自定义六维特征 →
                </button>
              </div>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-3 text-[11px]">
                <div className="rounded-lg bg-white/80 p-2 dark:bg-slate-900/70">
                  <span className="font-semibold text-slate-700 dark:text-slate-200">
                    1. 语言表达：
                  </span>
                  <span className="text-slate-600 dark:text-slate-400">
                    {activeProfile.language.colloquial_level}；{activeProfile.language.sentence_length_ratio}
                  </span>
                </div>
                <div className="rounded-lg bg-white/80 p-2 dark:bg-slate-900/70">
                  <span className="font-semibold text-slate-700 dark:text-slate-200">
                    2. 叙事方式：
                  </span>
                  <span className="text-slate-600 dark:text-slate-400">
                    {activeProfile.narrative.scene_to_summary_ratio}
                  </span>
                </div>
                <div className="rounded-lg bg-white/80 p-2 dark:bg-slate-900/70">
                  <span className="font-semibold text-slate-700 dark:text-slate-200">
                    3. 人物对话：
                  </span>
                  <span className="text-slate-600 dark:text-slate-400">
                    {activeProfile.dialogue.subtext_technique}
                  </span>
                </div>
                <div className="rounded-lg bg-white/80 p-2 dark:bg-slate-900/70">
                  <span className="font-semibold text-slate-700 dark:text-slate-200">
                    4. 情绪表达：
                  </span>
                  <span className="text-slate-600 dark:text-slate-400">
                    {activeProfile.emotion.action_and_detail}
                  </span>
                </div>
                <div className="rounded-lg bg-white/80 p-2 dark:bg-slate-900/70">
                  <span className="font-semibold text-slate-700 dark:text-slate-200">
                    5. 章节节奏：
                  </span>
                  <span className="text-slate-600 dark:text-slate-400">
                    {activeProfile.pacing.conflict_progression}
                  </span>
                </div>
                <div className="rounded-lg bg-white/80 p-2 dark:bg-slate-900/70">
                  <span className="font-semibold text-slate-700 dark:text-slate-200">
                    6. 题材特征：
                  </span>
                  <span className="text-slate-600 dark:text-slate-400">
                    {activeProfile.genre_traits.characteristic_techniques}
                  </span>
                </div>
              </div>
            </div>
          )}
        </div>

        <div className="space-y-4 rounded-xl border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900">
          <div>
            <label className="font-semibold text-slate-700 dark:text-slate-300">
              主角概念设定
            </label>
            <input
              type="text"
              value={protagonist}
              onChange={(e) => setProtagonist(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-950"
            />
          </div>
          <div>
            <label className="font-semibold text-slate-700 dark:text-slate-300">
              故事梗概
            </label>
            <textarea
              rows={4}
              value={synopsis}
              onChange={(e) => setSynopsis(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 leading-relaxed dark:border-slate-700 dark:bg-slate-950"
            />
          </div>
        </div>

        <div className="grid grid-cols-1 gap-4 rounded-xl border border-slate-200 bg-white p-5 sm:grid-cols-4 dark:border-slate-800 dark:bg-slate-900">
          <div>
            <label className="font-semibold text-slate-700 dark:text-slate-300">
              目标总字数
            </label>
            <input
              type="number"
              value={targetWords}
              onChange={(e) => setTargetWords(Number(e.target.value) || 1000000)}
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-1.5 dark:border-slate-700 dark:bg-slate-950"
            />
          </div>
          <div>
            <label className="font-semibold text-slate-700 dark:text-slate-300">
              单章目标字数
            </label>
            <input
              type="number"
              value={wordsPerChapter}
              onChange={(e) => setWordsPerChapter(Number(e.target.value) || 2500)}
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-1.5 dark:border-slate-700 dark:bg-slate-950"
            />
          </div>
          <div>
            <label className="font-semibold text-slate-700 dark:text-slate-300">
              感情线结局
            </label>
            <select
              value={romanceEnding}
              onChange={(e) => setRomanceEnding(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-1.5 dark:border-slate-700 dark:bg-slate-950"
            >
              {["HE", "BE", "开放式", "遗憾向", "自定义"].map((opt) => (
                <option key={opt} value={opt}>
                  {opt}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="font-semibold text-slate-700 dark:text-slate-300">
              成长线结局
            </label>
            <select
              value={growthEnding}
              onChange={(e) => setGrowthEnding(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-1.5 dark:border-slate-700 dark:bg-slate-950"
            >
              {["HE", "BE", "开放式", "遗憾向", "自定义"].map((opt) => (
                <option key={opt} value={opt}>
                  {opt}
                </option>
              ))}
            </select>
          </div>
          <div className="sm:col-span-2">
            <label className="font-semibold text-slate-700 dark:text-slate-300">
              结局补充说明
            </label>
            <input
              type="text"
              value={endingNote}
              onChange={(e) => setEndingNote(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-1.5 dark:border-slate-700 dark:bg-slate-950"
            />
          </div>
          <div className="sm:col-span-2">
            <label className="font-semibold text-slate-700 dark:text-slate-300">
              文风补充说明
            </label>
            <input
              type="text"
              value={styleNote}
              onChange={(e) => setStyleNote(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-1.5 dark:border-slate-700 dark:bg-slate-950"
            />
          </div>
        </div>
      </form>
    </div>
  );
};
