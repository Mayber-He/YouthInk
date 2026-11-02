/** Types for M3 Editor, Scene Beats, Version History, Context Preview, and AI Smell. */

import type { ChapterItem } from "@/types/api";

export interface SceneItem {
  id: number;
  chapter_id: number;
  sort_order: number;
  beat: string;
  pov_character: number | null;
  location_id: number | null;
  character_ids: number[];
  story_time: string;
  target_words: number;
  created_at: string;
  updated_at: string;
}

export interface ChapterVersionItem {
  id: number;
  chapter_id: number;
  version: number;
  content: string;
  source: "ai" | "manual";
  word_count: number;
  created_at: string;
}

export interface ChapterWorkspace {
  chapter: ChapterItem;
  latest_content: string;
  latest_version: number;
  scenes: SceneItem[];
  versions: ChapterVersionItem[];
}

export interface ContextBlockItem {
  key: string;
  label: string;
  priority: "required" | "optional";
  enabled: boolean;
  tokens: number;
  content: string;
}

export interface ContextPreview {
  chapter_id: number;
  scene_id: number | null;
  total_tokens: number;
  budget_tokens: number;
  blocks: ContextBlockItem[];
  warnings?: string[];
}

export interface AiSmellHit {
  matched_text: string;
  category: string;
  reason: string;
  suggestion: string;
  suggested_rewrite: string;
  start_index: number;
  end_index: number;
}

export interface AiSmellScanResult {
  total_hits: number;
  hits: AiSmellHit[];
}

/** T5: 场景正文生成后的确定性重复检测结果。 */
export interface RepetitionCheckResult {
  triggered: boolean;
  // none 未超阈值 | rewritten 已自动重写一次且复检通过
  // | kept_with_warning 重写后仍超标（或关闭了自动重写），保留文本并警告
  // | rewrite_failed 自动重写失败，保留原文
  // | supplemented 关键选择场景已按开关补写一句内心判断
  action: "none" | "rewritten" | "kept_with_warning" | "rewrite_failed" | "supplemented";
  final_text: string;
  reasons: string[];
  warnings: string[];
  advisories?: string[];
  check_ids: number[];
}

export type RewriteActionType =
  | "rewrite"
  | "expand"
  | "shorten"
  | "polish"
  | "tone_shift";


export interface SelectionCritiqueResult {
  has_issue: boolean;
  issue_type: string | null;
  issue_label: string | null;
  description: string;
  suggestion: string;
}
