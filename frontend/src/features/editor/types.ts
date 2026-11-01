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
