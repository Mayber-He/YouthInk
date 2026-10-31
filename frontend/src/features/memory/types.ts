export type MemoryItemCategory =
  | "fact"
  | "char_state"
  | "cognitive"
  | "relationship"
  | "foreshadowing"
  | "constraint_check";

export type ForeshadowStatus = "planted" | "hinted" | "recovered" | "abandoned";
export type SummaryLevel = "chapter" | "arc" | "volume" | "novel";

export type ConsistencyCheckType =
  | "constraint"
  | "fact"
  | "character"
  | "common_sense"
  | "continuity";
export type ConsistencyVerdict = "violation" | "suspicious";

export interface ConsistencyIssue {
  check_type: ConsistencyCheckType;
  ref_id: number | null;
  ref_label: string;
  verdict: ConsistencyVerdict;
  evidence_quote: string;
  historical_evidence: string;
  description: string;
  suggestion: string;
  suggested_rewrite?: string;
}

export interface ConsistencyReviewResponse {
  id: number;
  chapter_id: number;
  version_id: number | null;
  summary: string;
  issue_count: number;
  violation_count: number;
  issues: ConsistencyIssue[];
  model: string;
  created_at: string;
  is_stale: boolean;
}

export interface ConsistencyReviewSummary {
  id: number;
  chapter_id: number;
  summary: string;
  issue_count: number;
  violation_count: number;
  created_at: string;
  is_stale: boolean;
}

export interface PendingQueueItem {
  item_type: MemoryItemCategory;
  id: number;
  chapter_id: number | null;
  chapter_title: string;
  chapter_display_index: number | null;
  summary_text: string;
  source_quote: string;
  status: string;
  raw_payload: Record<string, unknown>;
  created_at: string;
}

export interface ForeshadowItem {
  id: number;
  description: string;
  planted_chapter_id: number | null;
  planted_chapter_title: string;
  plan_recover_start: number | null;
  plan_recover_end: number | null;
  status: ForeshadowStatus;
  related_chapter_ids: number[];
  source_quote: string;
  confirm_status: string;
  created_at: string;
  updated_at: string;
}

export interface SummaryItem {
  id: number;
  level: SummaryLevel;
  ref_id: number;
  content: string;
  is_stale: boolean;
  updated_at: string;
}

export interface RagChunkHit {
  chunk_id: string;
  chapter_id: number;
  chapter_sort_order: number;
  scene_id: number | null;
  text: string;
  rrf_score: number;
  source: "vector" | "fts" | "hybrid";
}

export interface RagSearchResponse {
  query: string;
  embedding_model_mismatch: boolean;
  hits: RagChunkHit[];
}

export interface FinalizeChapterResponse {
  chapter_id: number;
  status: string;
  backup_filename: string;
  chunks_indexed: number;
  chapter_summary: string;
  auto_confirmed_count: number;
  pending_count: number;
}
