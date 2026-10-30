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
    secret: string;
    learned_by: string | null;
    chapter_title: string | null;
  }>;
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
