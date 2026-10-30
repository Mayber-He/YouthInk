/** TanStack Query hooks for Outline (Volumes, Arcs, Chapters, Float Reorder, AI Generation). */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "@/lib/http";
import { novelKeys } from "@/features/novels/api";
import type {
  ArcTreeNode,
  ChapterItem,
  ChapterStatus,
  OutlineTree,
  VolumeTreeNode,
} from "@/types/api";

export const outlineKeys = {
  tree: (uid: string) => ["novels", uid, "outline"] as const,
};

export function useOutlineTree(novelUid: string | null) {
  return useQuery({
    queryKey: novelUid ? outlineKeys.tree(novelUid) : ["novels", "none", "outline"],
    queryFn: () => apiRequest<OutlineTree>(`/api/v1/novels/${novelUid}/outline`),
    enabled: Boolean(novelUid),
  });
}

export function useCreateVolume(novelUid: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: { title: string; synopsis?: string; goal?: string }) =>
      apiRequest<VolumeTreeNode>(`/api/v1/novels/${novelUid}/outline/volumes`, {
        method: "POST",
        body: JSON.stringify(input),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: outlineKeys.tree(novelUid) }),
  });
}

export function useDeleteVolume(novelUid: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (volId: number) =>
      apiRequest<void>(`/api/v1/novels/${novelUid}/outline/volumes/${volId}`, {
        method: "DELETE",
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: outlineKeys.tree(novelUid) });
      qc.invalidateQueries({ queryKey: novelKeys.detail(novelUid) });
    },
  });
}

export function useCreateArc(novelUid: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: {
      volume_id: number;
      title: string;
      goal?: string;
      core_conflict?: string;
    }) =>
      apiRequest<ArcTreeNode>(`/api/v1/novels/${novelUid}/outline/arcs`, {
        method: "POST",
        body: JSON.stringify(input),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: outlineKeys.tree(novelUid) }),
  });
}

export function useDeleteArc(novelUid: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (arcId: number) =>
      apiRequest<void>(`/api/v1/novels/${novelUid}/outline/arcs/${arcId}`, {
        method: "DELETE",
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: outlineKeys.tree(novelUid) });
      qc.invalidateQueries({ queryKey: novelKeys.detail(novelUid) });
    },
  });
}

export function useCreateChapter(novelUid: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: {
      arc_id: number;
      title: string;
      synopsis?: string;
      story_time?: string;
      after_chapter_id?: number;
      before_chapter_id?: number;
      locked?: boolean;
    }) =>
      apiRequest<ChapterItem>(`/api/v1/novels/${novelUid}/outline/chapters`, {
        method: "POST",
        body: JSON.stringify(input),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: outlineKeys.tree(novelUid) });
      qc.invalidateQueries({ queryKey: novelKeys.detail(novelUid) });
    },
  });
}

export function useUpdateChapter(novelUid: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      input,
    }: {
      id: number;
      input: Partial<{
        title: string;
        synopsis: string;
        status: ChapterStatus;
        story_time: string;
        locked: boolean;
      }>;
    }) =>
      apiRequest<ChapterItem>(
        `/api/v1/novels/${novelUid}/outline/chapters/${id}`,
        {
          method: "PUT",
          body: JSON.stringify(input),
        }
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: outlineKeys.tree(novelUid) });
      qc.invalidateQueries({ queryKey: novelKeys.detail(novelUid) });
    },
  });
}

export function useReorderChapter(novelUid: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: {
      target_id: number;
      prev_sort_order: number | null;
      next_sort_order: number | null;
    }) =>
      apiRequest<ChapterItem>(
        `/api/v1/novels/${novelUid}/outline/chapters/reorder`,
        {
          method: "POST",
          body: JSON.stringify(input),
        }
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: outlineKeys.tree(novelUid) }),
  });
}

export function useDeleteChapter(novelUid: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (chapterId: number) =>
      apiRequest<void>(
        `/api/v1/novels/${novelUid}/outline/chapters/${chapterId}`,
        { method: "DELETE" }
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: outlineKeys.tree(novelUid) });
      qc.invalidateQueries({ queryKey: novelKeys.detail(novelUid) });
    },
  });
}

export function useGenerateStructure(novelUid: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: {
      volume_count?: number;
      arcs_per_volume?: number;
      instruction?: string;
    }) =>
      apiRequest<OutlineTree>(
        `/api/v1/novels/${novelUid}/outline/generate-structure`,
        {
          method: "POST",
          body: JSON.stringify(input),
        }
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: outlineKeys.tree(novelUid) }),
  });
}

export function useGenerateArcChapters(novelUid: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      arcId,
      chapterCount = 5,
      instruction = "",
    }: {
      arcId: number;
      chapterCount?: number;
      instruction?: string;
    }) =>
      apiRequest<OutlineTree>(
        `/api/v1/novels/${novelUid}/outline/arcs/${arcId}/generate-chapters`,
        {
          method: "POST",
          body: JSON.stringify({
            chapter_count: chapterCount,
            instruction,
          }),
        }
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: outlineKeys.tree(novelUid) });
      qc.invalidateQueries({ queryKey: novelKeys.detail(novelUid) });
    },
  });
}
