/** Global TypeScript types mapped from backend Pydantic schemas. */

export interface ApiErrorDetail {
  code: string;
  message: string;
  detail?: unknown;
}

export interface LlmProfile {
  id: number;
  name: string;
  base_url: string;
  model: string;
  api_key_masked: string;
  is_default: boolean;
  created_at: string;
}

export interface LlmProfileCreateInput {
  name: string;
  base_url: string;
  model: string;
  api_key: string;
  is_default?: boolean;
}

export interface LlmProfileUpdateInput {
  name?: string;
  base_url?: string;
  model?: string;
  api_key?: string;
  is_default?: boolean;
}

export interface LlmConnectionTestInput {
  profile_id?: number;
  base_url?: string;
  model?: string;
  api_key?: string;
  prompt?: string;
}

export interface LlmConnectionTestResult {
  ok: boolean;
  model: string;
  reply: string;
  elapsed_ms: number;
  input_tokens: number;
  output_tokens: number;
}

export interface TaskModelAssignments {
  writing: number | null;
  planning: number | null;
  extract: number | null;
}

export interface PromptTemplateItem {
  task_type: string;
  description: string;
  content: string;
  version: string;
  is_overridden: boolean;
  updated_at: string | null;
}

export interface StyleTemplate {
  id: number;
  name: string;
  is_builtin: boolean;
  pov: string;
  tense_feel: string;
  tone: string;
  sentence_pref: string;
  dialogue_ratio: string;
  desc_focus: string;
  pacing: string;
  example_paras: string[];
  forbidden_exprs: string[];
  created_at: string;
  updated_at: string;
}

export interface TrustModeSettings {
  enabled: boolean;
  auto_confirm_facts: boolean;
  auto_confirm_foreshadow_hint: boolean;
  auto_confirm_char_state: boolean;
  auto_confirm_relationship: boolean;
  auto_confirm_cognitive: boolean;
  auto_confirm_foreshadow_plant_recover: boolean;
}

export interface EmbeddingModelStatus {
  model_id: string;
  ready: boolean;
  status: "not_downloaded" | "downloading" | "ready" | "error";
  progress: number;
  download_source: "modelscope" | "hf_mirror" | "huggingface";
  local_path: string;
  message: string;
}

export interface NovelDetail {
  novel_uid: string;
  id: number;
  title: string;
  genre: string | null;
  tone: string | null;
  pov: string | null;
  protagonist_concept: string | null;
  synopsis: string | null;
  target_words: number;
  estimated_chapters: number | null;
  words_per_chapter: number;
  romance_ending: string | null;
  growth_ending: string | null;
  ending_note: string | null;
  style_note: string | null;
  style_template_id: number | null;
  total_chapters: number;
  finalized_chapters: number;
  current_words: number;
  pending_confirm_count: number;
  created_at: string;
  updated_at: string;
}

export interface NovelCreateInput {
  title: string;
  genre: string;
  tone: string;
  pov: string;
  protagonist_concept: string;
  synopsis: string;
  target_words: number;
  estimated_chapters: number;
  words_per_chapter: number;
  romance_ending: string;
  growth_ending: string;
  ending_note: string;
  style_note: string;
  style_template_id: number | null;
}

export type NovelUpdateInput = Partial<NovelCreateInput>;

export interface BackupInfo {
  filename: string;
  size_bytes: number;
  created_at: string;
}

export type WorkbenchSection =
  | "initiation"
  | "worldview"
  | "characters"
  | "locations"
  | "main_plot"
  | "outline"
  | "writing"
  | "foreshadowing"
  | "pending_queue";

export * from "./entities";
export * from "./outline";
