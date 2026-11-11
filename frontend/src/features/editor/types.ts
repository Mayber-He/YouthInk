/** Types for M3 Editor, Scene Beats, Version History, Context Preview, AI Smell, and Style Review. */

import type { ChapterItem, LanguageMetrics } from "@/types/api";

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

export interface StyleSpanIssue {
  issue_type: string;
  dimension: string;
  severity: "high" | "medium" | "low";
  paragraph_index: number;
  evidence_quote: string;
  reason: string;
  rewrite_directive: string;
  suggested_rewrite: string;
}

export interface StyleReviewResult {
  chapter_id: number;
  total_issues: number;
  dimension_scores: Record<string, number>;
  pacing_mode: string;
  issues: StyleSpanIssue[];
  metrics: LanguageMetrics;
  summary: string;
}

export interface StyleSpanRewriteResult {
  original_text: string;
  rewritten_text: string;
  replaced_count: number;
  skipped_count: number;
  replacements: Array<{
    issue_type: string;
    original_span: string;
    replacement_span: string;
  }>;
  warnings: string[];
}
