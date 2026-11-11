/** TypeScript types for Worldview, Characters, Locations, and Main Plot (M2). */

export type WorldviewCategory =
  | "era"
  | "city"
  | "school"
  | "rules"
  | "culture"
  | "term";

export type CharacterRole =
  | "female_lead"
  | "male_lead"
  | "major"
  | "minor"
  | "extra";

export type CharacterMemoryType = "daily" | "schedule" | "secret";

export type ScheduleStatus = "pending" | "completed" | "cancelled" | "expired";

export interface CharacterMemoryItem {
  id: number;
  content: string;
  secret: string;
  memory_type: CharacterMemoryType;
  time_scope: string;
  schedule_status: ScheduleStatus;
  effective_schedule_status: ScheduleStatus;
  related_record_id: number | null;
  knower_ids: number[];
  knower_names: string[];
  learned_by: string;
  chapter_id: number | null;
  chapter_title: string;
  chapter_display_index: number | null;
  chapter_sort_order: number | null;
  story_time: string;
  source_quote: string;
  origin: string;
  confirm_status: string;
  is_disabled: boolean;
  is_stale: boolean;
  is_effective: boolean;
  resolved_chapter_id: number | null;
  resolved_chapter_title: string;
  resolved_chapter_display_index: number | null;
  resolved_story_time: string;
  resolved_quote: string;
  resolution_record_id: number | null;
  created_at: string;
}

export interface CharacterMemoryCreateInput {
  content: string;
  memory_type: CharacterMemoryType;
  time_scope?: string;
  schedule_status?: ScheduleStatus;
  related_record_id?: number | null;
  knower_ids: number[];
  learned_by?: string;
  chapter_id?: number | null;
  source_quote?: string;
}

export interface CharacterMemoryUpdateInput {
  content?: string;
  memory_type?: CharacterMemoryType;
  time_scope?: string;
  schedule_status?: ScheduleStatus;
  related_record_id?: number | null;
  knower_ids?: number[];
  learned_by?: string;
  chapter_id?: number | null;
  clear_chapter?: boolean;
  source_quote?: string;
  is_disabled?: boolean;
  resolved_chapter_id?: number | null;
}

export interface WorldviewEntry {
  id: number;
  category: WorldviewCategory;
  content: string;
  locked: boolean;
  created_at: string;
  updated_at: string;
}

export interface CharacterItem {
  id: number;
  name: string;
  aliases: string[];
  role: CharacterRole;
  gender: string;
  initial_age: string;
  appearance: string;
  personality: string;
  speech_style: string;
  background: string;
  arc_design: string;
  locked: boolean;
  created_at: string;
  updated_at: string;
}

export interface CharacterTimelineSnapshot {
  character_id: number;
  up_to_chapter_sort: number | null;
  effective_appearance: string;
  current_states: Record<string, string>;
  relationships: Array<{
    char_a_id: number;
    char_a_name: string;
    char_b_id: number;
    char_b_name: string;
    rel_type: string;
    intimacy: number | null;
    publicity: string | null;
    change_reason: string | null;
  }>;
  known_secrets: Array<{
    id?: number;
    secret: string;
    content?: string;
    memory_type?: CharacterMemoryType;
    time_scope?: string;
    schedule_status?: ScheduleStatus;
    effective_schedule_status?: ScheduleStatus;
    knower_ids?: number[];
    knower_names?: string[];
    learned_by: string | null;
    chapter_id?: number | null;
    chapter_title: string | null;
    chapter_display_index?: number | null;
    story_time?: string | null;
    source_quote?: string | null;
    origin?: string;
    is_disabled?: boolean;
    resolved_chapter_id?: number | null;
    resolved_chapter_title?: string | null;
    resolved_chapter_display_index?: number | null;
  }>;
  character_memories?: CharacterMemoryItem[];
}

export interface LocationItem {
  id: number;
  name: string;
  aliases: string[];
  type: string;
  description: string;
  sensory_details: string;
  related_chars: number[];
  locked: boolean;
  created_at: string;
  updated_at: string;
}

export interface TurningPointItem {
  desc: string;
  chapter_sort: number | null;
}

export interface MainPlot {
  id: number;
  novel_id: number;
  core_conflict: string;
  romance_arc: string;
  growth_arc: string;
  key_turning_pts: TurningPointItem[];
  locked: boolean;
  updated_at: string;
}

export type ConstraintTargetType =
  | "character"
  | "location"
  | "worldview"
  | "chapter"
  | "novel";

export type ConstraintSeverity = "hard" | "soft";

export type ConstraintStatus = "active" | "resolved" | "violated";

export interface ConstraintItem {
  id: number;
  target_type: ConstraintTargetType;
  target_id: number | null;
  content: string;
  severity: ConstraintSeverity;
  status: ConstraintStatus;
  valid_from_chapter_id: number | null;
  valid_until_chapter_id: number | null;
  source_quote: string;
  locked: boolean;
  target_name: string;
  created_at: string;
  updated_at: string;
}

export interface ConstraintCreateInput {
  target_type: ConstraintTargetType;
  target_id?: number | null;
  content: string;
  severity?: ConstraintSeverity;
  valid_from_chapter_id?: number | null;
  valid_until_chapter_id?: number | null;
  source_quote?: string;
  locked?: boolean;
}
