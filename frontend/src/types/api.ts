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

export interface LanguageMetrics {
  char_count: number;
  paragraph_count: number;
  sentence_count: number;
  avg_paragraph_chars: number;
  single_line_para_ratio: number;
  avg_sentence_chars: number;
  short_sentence_pct: number;
  medium_sentence_pct: number;
  long_sentence_pct: number;
  dialogue_ratio_pct: number;
  colloquial_per_kchars: number;
  rhetoric_per_kchars: number;
}

export interface StyleProfile {
  version: string;
  source_type: "builtin_preset" | "reference_excerpt" | "user_custom";
  language: {
    colloquial_level: string;
    sentence_length_ratio: string;
    rhetoric_density: string;
    paragraph_rhythm: string;
    metrics: LanguageMetrics;
  };
  narrative: {
    pov_mode: string;
    info_release: string;
    scene_to_summary_ratio: string;
    transition_style: string;
  };
  dialogue: {
    dialogue_rhythm: string;
    subtext_technique: string;
    interaction_texture: string;
  };
  emotion: {
    action_and_detail: string;
    inner_monologue_ratio: string;
    whitespace_and_restraint: string;
  };
  pacing: {
    opening_setup: string;
    conflict_progression: string;
    turning_point: string;
    closing_hook: string;
  };
  genre_traits: {
    genre_name: string;
    core_appeal: string;
    characteristic_techniques: string;
    genre_taboos: string[];
  };
  anti_ai_rules: string[];
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
  style_profile?: StyleProfile | null;
  created_at: string;
  updated_at: string;
}

export interface StyleTemplateCreateInput {
  name: string;
  pov?: string;
  tense_feel?: string;
  tone?: string;
  sentence_pref?: string;
  dialogue_ratio?: string;
  desc_focus?: string;
  pacing?: string;
  example_paras?: string[];
  forbidden_exprs?: string[];
  style_profile?: StyleProfile | null;
}

export type StyleTemplateUpdateInput = Partial<StyleTemplateCreateInput>;

export interface StyleProfileAnalyzeInput {
  reference_text: string;
  genre: string;
  template_name?: string;
  save_as_template?: boolean;
  target_template_id?: number | null;
  use_llm?: boolean;
}

export interface StyleProfileAnalyzeResult {
  style_profile: StyleProfile;
  derived_template_fields: Record<string, string>;
  saved_template_id: number | null;
  analysis_notes: string[];
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
