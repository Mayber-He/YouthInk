/** TypeScript types for Volumes, Arcs, Chapters, and Outline Tree (M2). */

export type ChapterStatus = "pending" | "outline" | "draft" | "final";

export interface ChapterItem {
  id: number;
  arc_id: number;
  sort_order: number;
  display_index: number;
  title: string;
  synopsis: string;
  status: ChapterStatus;
  word_count: number;
  story_time: string;
  locked: boolean;
  created_at: string;
  updated_at: string;
}

export interface ArcTreeNode {
  id: number;
  volume_id: number;
  sort_order: number;
  title: string;
  goal: string;
  core_conflict: string;
  start_chapter: number | null;
  end_chapter: number | null;
  chapters: ChapterItem[];
  created_at: string;
  updated_at: string;
}

export interface VolumeTreeNode {
  id: number;
  novel_id: number;
  sort_order: number;
  title: string;
  synopsis: string;
  goal: string;
  arcs: ArcTreeNode[];
  created_at: string;
  updated_at: string;
}

export interface OutlineTree {
  volumes: VolumeTreeNode[];
  total_chapters: number;
}
