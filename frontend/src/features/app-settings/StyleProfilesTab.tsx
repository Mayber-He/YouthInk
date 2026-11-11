import React, { useEffect, useState } from "react";
import { Check, Plus, Save, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import type { StyleProfile, StyleTemplate } from "@/types/api";
import {
  useAnalyzeStyleExcerpt,
  useCreateStyleTemplate,
  useStyleTemplates,
  useUpdateStyleTemplate,
} from "./api";

const EMPTY_PROFILE: StyleProfile = {
  version: "1.0",
  source_type: "user_custom",
  language: {
    colloquial_level: "自然口语化（三分书面七分白话，贴近当代青年日常语感）",
    sentence_length_ratio: "短句约45%、中句约40%、长句约15%，交锋处多用短促断句",
    rhetoric_density: "低密度克制修辞，拒绝堆砌伪文艺比喻",
    paragraph_rhythm: "单句成段与2-4句短段交替",
    metrics: {
      char_count: 0,
      paragraph_count: 0,
      sentence_count: 0,
      avg_paragraph_chars: 0,
      single_line_para_ratio: 0,
      avg_sentence_chars: 0,
      short_sentence_pct: 0,
      medium_sentence_pct: 0,
      long_sentence_pct: 0,
      dialogue_ratio_pct: 0,
      colloquial_per_kchars: 0,
      rhetoric_per_kchars: 0,
    },
  },
  narrative: {
    pov_mode: "第三人称贴身限知",
    info_release: "先呈现反常细节与半截话，延迟解释背景原因",
    scene_to_summary_ratio: "实时场景80% : 简明过渡概述20%",
    transition_style: "以动作结果或时间切口直接跳切，省略走路/排队流水账",
  },
  dialogue: {
    dialogue_rhythm: "快慢错落、有来有回，禁止单字“嗯/行/好”敷衍",
    subtext_technique: "话只说七分，靠反问、岔开话题或顺手动作传递潜台词",
    interaction_texture: "对话夹杂顺手生活化动作，避免站桩问答",
  },
  emotion: {
    action_and_detail: "用具体停顿或视线转移代替情绪标签，严禁复读“拇指悬在屏幕”",
    inner_monologue_ratio: "心理活动控制在1-2句内，禁止原地复盘已知事实",
    whitespace_and_restraint: "关键情绪节点留白，点到动作或半句对白即止",
  },
  pacing: {
    opening_setup: "开门见山切入正在发生的互动或小状况",
    conflict_progression: "靠信息差与性格反差层层推进拉扯",
    turning_point: "中后段通过细节破绽或态度松动改变心理距离",
    closing_hook: "收在有余味的台词或干脆行动上，严禁升华主题",
  },
  genre_traits: {
    genre_name: "青春校园",
    core_appeal: "少年感、熟人/半熟人拉扯与鲜活生活烟火气",
    characteristic_techniques: "用顺手小动作和接梗拆台体现亲疏变化",
    genre_taboos: [
      "禁止把报到、排队、填表写成办事流程说明书",
      "禁止男主沦为只会回“嗯/行/好”的单字复读机",
    ],
  },
  anti_ai_rules: [
    "禁止连续使用“拇指悬在屏幕上/把手机屏幕朝下扣在桌面/眉心挤出浅褶”等高频AI习惯动作",
  ],
};

export const StyleProfilesTab: React.FC = () => {
  const { data: styles = [] } = useStyleTemplates();
  const updateMut = useUpdateStyleTemplate();
  const createMut = useCreateStyleTemplate();
  const analyzeMut = useAnalyzeStyleExcerpt();

  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [profile, setProfile] = useState<StyleProfile>(EMPTY_PROFILE);
  const [forbiddenText, setForbiddenText] = useState("");
  const [savedNotice, setSavedNotice] = useState<string | null>(null);

  const [refText, setRefText] = useState("");
  const [refGenre, setRefGenre] = useState("校园");
  const [newTplName, setNewTplName] = useState("");
  const [saveMode, setSaveMode] = useState<"update" | "create">("update");
  const [useLlm, setUseLlm] = useState(true);
  const [analysisNotes, setAnalysisNotes] = useState<string[]>([]);

  const currentTpl: StyleTemplate | undefined = styles.find((s) => s.id === selectedId) ?? styles[0];

  useEffect(() => {
    if (currentTpl && selectedId === null) {
      setSelectedId(currentTpl.id);
    }
  }, [currentTpl, selectedId]);

  useEffect(() => {
    if (!currentTpl) return;
    setProfile(currentTpl.style_profile ?? EMPTY_PROFILE);
    setForbiddenText((currentTpl.forbidden_exprs ?? []).join("、"));
  }, [currentTpl?.id, currentTpl?.updated_at]);

  const handleAnalyzeExcerpt = async () => {
    if (refText.trim().length < 60) return;
    setAnalysisNotes([]);
    const res = await analyzeMut.mutateAsync({
      reference_text: refText.trim(),
      genre: refGenre,
      template_name: newTplName.trim() || `${refGenre}样本习得文风`,
      save_as_template: saveMode === "create",
      target_template_id: saveMode === "update" && currentTpl ? currentTpl.id : null,
      use_llm: useLlm,
    });
    setProfile(res.style_profile);
    setAnalysisNotes(res.analysis_notes);
    if (res.saved_template_id) {
      setSelectedId(res.saved_template_id);
    }
  };

  const handleSaveProfile = async () => {
    if (!currentTpl) return;
    const forbidden = forbiddenText
      .split(/[、,，\n]+/)
      .map((s) => s.trim())
      .filter(Boolean);
    await updateMut.mutateAsync({
      id: currentTpl.id,
      input: {
        forbidden_exprs: forbidden,
        style_profile: { ...profile, source_type: "user_custom" },
      },
    });
    setSavedNotice("文风档案已保存，将在后续章节生成与文风审查中生效");
    setTimeout(() => setSavedNotice(null), 2500);
  };

  const handleCreateBlank = async () => {
    const name = prompt("请输入新文风档案名称：", "自定义网文文风");
    if (!name || !name.trim()) return;
    const created = await createMut.mutateAsync({
      name: name.trim(),
      style_profile: EMPTY_PROFILE,
    });
    setSelectedId(created.id);
  };

  const m = profile.language.metrics;

  return (
    <div className="max-h-[72vh] space-y-5 overflow-y-auto pr-1 text-xs">
      {/* 顶部：导入参考小说片段自动学习 */}
      <div className="rounded-xl border border-indigo-200 bg-indigo-50/40 p-4 dark:border-indigo-900/60 dark:bg-indigo-950/20">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h3 className="text-sm font-bold text-slate-900 dark:text-slate-100">
              导入参考小说片段 · 自动提炼六维文风档案
            </h3>
            <p className="mt-0.5 text-[11px] text-slate-500">
              粘贴 60～30,000 字你喜欢的参考小说片段，系统自动分析句长分布、对白占比、潜台词与留白特征（内置 7-gram 防抄袭清洗，绝不复制原句或情节）。
            </p>
          </div>
          <Badge tone="indigo">Phase 3 文风学习引擎</Badge>
        </div>

        <textarea
          rows={4}
          value={refText}
          onChange={(e) => setRefText(e.target.value)}
          placeholder="在此粘贴你喜欢的中文网络小说正文片段（至少 60 字，建议 300～2000 字）..."
          className="mt-3 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs leading-relaxed dark:border-slate-700 dark:bg-slate-900"
        />

        <div className="mt-2.5 flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <label className="font-medium text-slate-600 dark:text-slate-300">题材：</label>
            <select
              value={refGenre}
              onChange={(e) => setRefGenre(e.target.value)}
              className="rounded-lg border border-slate-300 bg-white px-2.5 py-1 dark:border-slate-700 dark:bg-slate-900"
            >
              {["校园", "都市", "恋爱", "玄幻"].map((g) => (
                <option key={g} value={g}>{g}</option>
              ))}
            </select>

            <select
              value={saveMode}
              onChange={(e) => setSaveMode(e.target.value as "update" | "create")}
              className="rounded-lg border border-slate-300 bg-white px-2.5 py-1 dark:border-slate-700 dark:bg-slate-900"
            >
              <option value="update">覆盖更新当前选中模板（{currentTpl?.name ?? "默认"}）</option>
              <option value="create">另存为新文风模板</option>
            </select>

            {saveMode === "create" && (
              <input
                type="text"
                value={newTplName}
                onChange={(e) => setNewTplName(e.target.value)}
                placeholder="新模板名称（如：轻快毒舌校园风）"
                className="rounded-lg border border-slate-300 bg-white px-2.5 py-1 dark:border-slate-700 dark:bg-slate-900"
              />
            )}

            <label className="inline-flex items-center gap-1.5 rounded-lg border border-indigo-200 bg-white px-2.5 py-1 text-[11px] font-medium text-indigo-700 dark:border-indigo-800 dark:bg-slate-900 dark:text-indigo-300 cursor-pointer">
              <input
                type="checkbox"
                checked={useLlm}
                onChange={(e) => setUseLlm(e.target.checked)}
                className="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
              />
              使用当前配置的 LLM 深度分析样本
            </label>
          </div>

          <Button
            size="sm"
            disabled={refText.trim().length < 60 || analyzeMut.isPending}
            onClick={() => void handleAnalyzeExcerpt()}
          >
            <Sparkles className="h-3.5 w-3.5" />
            {analyzeMut.isPending
              ? useLlm
                ? "正在调用 LLM 提炼..."
                : "正在统计提炼..."
              : "提取六维文风档案"}
          </Button>
        </div>

        {analysisNotes.length > 0 && (
          <div className="mt-2 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-[11px] text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-300">
            {analysisNotes.join(" ")}
          </div>
        )}
      </div>

      {/* 下部：选择与编辑结构化 Style Profile */}
      <div className="space-y-4 rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 pb-3 dark:border-slate-800">
          <div className="flex items-center gap-2">
            <span className="font-bold text-slate-800 dark:text-slate-100">当前编辑模板：</span>
            <select
              value={currentTpl?.id ?? ""}
              onChange={(e) => setSelectedId(Number(e.target.value))}
              className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 font-semibold dark:border-slate-700 dark:bg-slate-950"
            >
              {styles.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name} ({s.style_profile?.source_type === "reference_excerpt" ? "样本习得" : s.is_builtin ? "内置" : "自定义"})
                </option>
              ))}
            </select>
            <Button variant="outline" size="sm" onClick={() => void handleCreateBlank()}>
              <Plus className="h-3.5 w-3.5" />
              新建模板
            </Button>
          </div>

          <div className="flex items-center gap-2">
            {savedNotice && (
              <span className="inline-flex items-center gap-1 text-emerald-600">
                <Check className="h-3.5 w-3.5" />
                {savedNotice}
              </span>
            )}
            <Button size="sm" onClick={() => void handleSaveProfile()} disabled={updateMut.isPending}>
              <Save className="h-3.5 w-3.5" />
              保存文风档案修改
            </Button>
          </div>
        </div>

        {m && m.char_count > 0 && (
          <div className="flex flex-wrap gap-2 rounded-lg bg-slate-50 px-3 py-2 text-[11px] text-slate-600 dark:bg-slate-950 dark:text-slate-400">
            <span>样本字数：<b>{m.char_count}</b></span>
            <span>· 平均句长：<b>{m.avg_sentence_chars} 字</b></span>
            <span>· 短句占比：<b>{m.short_sentence_pct}%</b></span>
            <span>· 对白占比：<b>{m.dialogue_ratio_pct}%</b></span>
            <span>· 单行短段占比：<b>{m.single_line_para_ratio}%</b></span>
            <span>· 千字口语词：<b>{m.colloquial_per_kchars}</b></span>
          </div>
        )}

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div className="space-y-2 rounded-lg border border-slate-200 p-3 dark:border-slate-800">
            <div className="font-bold text-indigo-700 dark:text-indigo-400">1. 语言表达（口语度 / 句长比 / 修辞密度）</div>
            <input
              type="text"
              value={profile.language.colloquial_level}
              onChange={(e) => setProfile({ ...profile, language: { ...profile.language, colloquial_level: e.target.value } })}
              className="w-full rounded border border-slate-300 px-2.5 py-1 dark:border-slate-700 dark:bg-slate-950"
              placeholder="口语化程度"
            />
            <input
              type="text"
              value={profile.language.sentence_length_ratio}
              onChange={(e) => setProfile({ ...profile, language: { ...profile.language, sentence_length_ratio: e.target.value } })}
              className="w-full rounded border border-slate-300 px-2.5 py-1 dark:border-slate-700 dark:bg-slate-950"
              placeholder="长短句比例"
            />
            <input
              type="text"
              value={profile.language.rhetoric_density}
              onChange={(e) => setProfile({ ...profile, language: { ...profile.language, rhetoric_density: e.target.value } })}
              className="w-full rounded border border-slate-300 px-2.5 py-1 dark:border-slate-700 dark:bg-slate-950"
              placeholder="修辞密度"
            />
          </div>

          <div className="space-y-2 rounded-lg border border-slate-200 p-3 dark:border-slate-800">
            <div className="font-bold text-indigo-700 dark:text-indigo-400">2. 叙事方式（视角 / 信息释放 / 场景概述比）</div>
            <input
              type="text"
              value={profile.narrative.pov_mode}
              onChange={(e) => setProfile({ ...profile, narrative: { ...profile.narrative, pov_mode: e.target.value } })}
              className="w-full rounded border border-slate-300 px-2.5 py-1 dark:border-slate-700 dark:bg-slate-950"
              placeholder="视角距离"
            />
            <input
              type="text"
              value={profile.narrative.scene_to_summary_ratio}
              onChange={(e) => setProfile({ ...profile, narrative: { ...profile.narrative, scene_to_summary_ratio: e.target.value } })}
              className="w-full rounded border border-slate-300 px-2.5 py-1 dark:border-slate-700 dark:bg-slate-950"
              placeholder="场景与概述比例"
            />
            <input
              type="text"
              value={profile.narrative.transition_style}
              onChange={(e) => setProfile({ ...profile, narrative: { ...profile.narrative, transition_style: e.target.value } })}
              className="w-full rounded border border-slate-300 px-2.5 py-1 dark:border-slate-700 dark:bg-slate-950"
              placeholder="转场过渡方式"
            />
          </div>

          <div className="space-y-2 rounded-lg border border-slate-200 p-3 dark:border-slate-800">
            <div className="font-bold text-indigo-700 dark:text-indigo-400">3. 人物对话（对白节奏 / 潜台词 / 互动感）</div>
            <input
              type="text"
              value={profile.dialogue.dialogue_rhythm}
              onChange={(e) => setProfile({ ...profile, dialogue: { ...profile.dialogue, dialogue_rhythm: e.target.value } })}
              className="w-full rounded border border-slate-300 px-2.5 py-1 dark:border-slate-700 dark:bg-slate-950"
              placeholder="对白节奏"
            />
            <input
              type="text"
              value={profile.dialogue.subtext_technique}
              onChange={(e) => setProfile({ ...profile, dialogue: { ...profile.dialogue, subtext_technique: e.target.value } })}
              className="w-full rounded border border-slate-300 px-2.5 py-1 dark:border-slate-700 dark:bg-slate-950"
              placeholder="潜台词方式"
            />
            <input
              type="text"
              value={profile.dialogue.interaction_texture}
              onChange={(e) => setProfile({ ...profile, dialogue: { ...profile.dialogue, interaction_texture: e.target.value } })}
              className="w-full rounded border border-slate-300 px-2.5 py-1 dark:border-slate-700 dark:bg-slate-950"
              placeholder="角色互动细节"
            />
          </div>

          <div className="space-y-2 rounded-lg border border-slate-200 p-3 dark:border-slate-800">
            <div className="font-bold text-indigo-700 dark:text-indigo-400">4. 情绪表达（动作细节 / 心理克制 / 留白）</div>
            <input
              type="text"
              value={profile.emotion.action_and_detail}
              onChange={(e) => setProfile({ ...profile, emotion: { ...profile.emotion, action_and_detail: e.target.value } })}
              className="w-full rounded border border-slate-300 px-2.5 py-1 dark:border-slate-700 dark:bg-slate-950"
              placeholder="动作与细节方式"
            />
            <input
              type="text"
              value={profile.emotion.inner_monologue_ratio}
              onChange={(e) => setProfile({ ...profile, emotion: { ...profile.emotion, inner_monologue_ratio: e.target.value } })}
              className="w-full rounded border border-slate-300 px-2.5 py-1 dark:border-slate-700 dark:bg-slate-950"
              placeholder="心理描写控制"
            />
            <input
              type="text"
              value={profile.emotion.whitespace_and_restraint}
              onChange={(e) => setProfile({ ...profile, emotion: { ...profile.emotion, whitespace_and_restraint: e.target.value } })}
              className="w-full rounded border border-slate-300 px-2.5 py-1 dark:border-slate-700 dark:bg-slate-950"
              placeholder="留白与克制要求"
            />
          </div>

          <div className="space-y-2 rounded-lg border border-slate-200 p-3 dark:border-slate-800">
            <div className="font-bold text-indigo-700 dark:text-indigo-400">5. 章节节奏（铺垫 / 冲突 / 转折 / 收尾）</div>
            <input
              type="text"
              value={profile.pacing.opening_setup}
              onChange={(e) => setProfile({ ...profile, pacing: { ...profile.pacing, opening_setup: e.target.value } })}
              className="w-full rounded border border-slate-300 px-2.5 py-1 dark:border-slate-700 dark:bg-slate-950"
              placeholder="开篇铺垫"
            />
            <input
              type="text"
              value={profile.pacing.turning_point}
              onChange={(e) => setProfile({ ...profile, pacing: { ...profile.pacing, turning_point: e.target.value } })}
              className="w-full rounded border border-slate-300 px-2.5 py-1 dark:border-slate-700 dark:bg-slate-950"
              placeholder="转折设计"
            />
            <input
              type="text"
              value={profile.pacing.closing_hook}
              onChange={(e) => setProfile({ ...profile, pacing: { ...profile.pacing, closing_hook: e.target.value } })}
              className="w-full rounded border border-slate-300 px-2.5 py-1 dark:border-slate-700 dark:bg-slate-950"
              placeholder="收尾钩子"
            />
          </div>

          <div className="space-y-2 rounded-lg border border-slate-200 p-3 dark:border-slate-800">
            <div className="font-bold text-indigo-700 dark:text-indigo-400">6. 题材特征与禁用套话词表</div>
            <input
              type="text"
              value={profile.genre_traits.characteristic_techniques}
              onChange={(e) =>
                setProfile({
                  ...profile,
                  genre_traits: { ...profile.genre_traits, characteristic_techniques: e.target.value },
                })
              }
              className="w-full rounded border border-slate-300 px-2.5 py-1 dark:border-slate-700 dark:bg-slate-950"
              placeholder="题材核心技法"
            />
            <input
              type="text"
              value={profile.genre_traits.genre_taboos.join("；")}
              onChange={(e) =>
                setProfile({
                  ...profile,
                  genre_traits: {
                    ...profile.genre_traits,
                    genre_taboos: e.target.value.split(/[；;\n]+/).map((s) => s.trim()).filter(Boolean),
                  },
                })
              }
              className="w-full rounded border border-slate-300 px-2.5 py-1 dark:border-slate-700 dark:bg-slate-950"
              placeholder="题材避坑禁忌（用分号分隔）"
            />
            <input
              type="text"
              value={forbiddenText}
              onChange={(e) => setForbiddenText(e.target.value)}
              className="w-full rounded border border-slate-300 px-2.5 py-1 dark:border-slate-700 dark:bg-slate-950"
              placeholder="禁用套话词表（如：不由得、嘴角勾起一抹弧度）"
            />
          </div>
        </div>
      </div>
    </div>
  );
};
