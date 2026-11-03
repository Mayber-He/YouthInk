import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "@/lib/http";
import type {
  ChapterMemoryItem,
  ConsistencyReviewResponse,
  ConsistencyReviewSummary,
  DisableableMemoryCategory,
  FinalizeChapterResponse,
  ForeshadowItem,
  ForeshadowStatus,
  MemoryItemCategory,
  PendingQueueItem,
  RagSearchResponse,
  SummaryItem,
} from "./types";

export function fetchConsistencyReviews(
  novelUid: string,
  chapterId: number
): Promise<ConsistencyReviewSummary[]> {
  return apiRequest<ConsistencyReviewSummary[]>(
    `/api/v1/novels/${novelUid}/chapters/${chapterId}/consistency-reviews`
  );
}

export function fetchConsistencyReview(
  novelUid: string,
  reviewId: number
): Promise<ConsistencyReviewResponse> {
  return apiRequest<ConsistencyReviewResponse>(
    `/api/v1/novels/${novelUid}/consistency-reviews/${reviewId}`
  );
}

export function usePendingQueue(
  novelUid: string | null,
  itemType?: string,
  chapterId?: number | null,
  status = "pending"
) {
  return useQuery({
    queryKey: ["pending-queue", novelUid, itemType ?? "", chapterId ?? "", status],
    queryFn: () => {
      const params = new URLSearchParams();
      if (itemType) params.set("item_type", itemType);
      if (chapterId) params.set("chapter_id", String(chapterId));
      params.set("status", status);
      return apiRequest<PendingQueueItem[]>(
        `/api/v1/novels/${novelUid}/memory/pending-queue?${params.toString()}`
      );
    },
    enabled: Boolean(novelUid),
  });
}

export function useChapterMemoryItems(
  novelUid: string | null,
  chapterId: number | null
) {
  return useQuery({
    queryKey: ["chapter-memory", novelUid, chapterId],
    queryFn: () =>
      apiRequest<ChapterMemoryItem[]>(
        `/api/v1/novels/${novelUid}/memory/items?chapter_id=${chapterId}`
      ),
    enabled: Boolean(novelUid && chapterId),
  });
}

export function useSetMemoryItemDisabled(novelUid: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: {
      item_type: DisableableMemoryCategory;
      id: number;
      is_disabled: boolean;
    }) =>
      apiRequest<{ status: string; is_disabled: boolean }>(
        `/api/v1/novels/${novelUid}/memory/items/${payload.item_type}/${payload.id}`,
        {
          method: "PUT",
          body: JSON.stringify({ is_disabled: payload.is_disabled }),
        }
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["chapter-memory", novelUid] });
      qc.invalidateQueries({ queryKey: ["pending-queue", novelUid] });
      qc.invalidateQueries({ queryKey: ["context-preview", novelUid] });
    },
  });
}

export function useUpdatePendingItem(novelUid: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: {
      item_type: MemoryItemCategory;
      id: number;
      action: "confirm" | "discard" | "edit";
      updated_text?: string;
    }) =>
      apiRequest<{ status: string }>(
        `/api/v1/novels/${novelUid}/memory/pending-queue/${payload.item_type}/${payload.id}`,
        {
          method: "PUT",
          body: JSON.stringify({
            action: payload.action,
            updated_text: payload.updated_text,
          }),
        }
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["pending-queue", novelUid] });
      qc.invalidateQueries({ queryKey: ["novels", novelUid] });
      qc.invalidateQueries({ queryKey: ["foreshadowing", novelUid] });
      qc.invalidateQueries({ queryKey: ["context-preview", novelUid] });
    },
  });
}

export function useBatchPendingAction(novelUid: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: {
      action: "confirm" | "discard";
      items: Array<{ item_type: string; id: number }>;
    }) =>
      apiRequest<{ updated_count: number }>(
        `/api/v1/novels/${novelUid}/memory/pending-queue/batch`,
        {
          method: "POST",
          body: JSON.stringify(payload),
        }
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["pending-queue", novelUid] });
      qc.invalidateQueries({ queryKey: ["novels", novelUid] });
      qc.invalidateQueries({ queryKey: ["foreshadowing", novelUid] });
      qc.invalidateQueries({ queryKey: ["context-preview", novelUid] });
    },
  });
}

export function useFinalizeChapter(novelUid: string, chapterId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiRequest<FinalizeChapterResponse>(
        `/api/v1/novels/${novelUid}/chapters/${chapterId}/finalize`,
        { method: "POST" }
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["chapter-workspace", novelUid, chapterId] });
      qc.invalidateQueries({ queryKey: ["outline", novelUid] });
      qc.invalidateQueries({ queryKey: ["pending-queue", novelUid] });
      qc.invalidateQueries({ queryKey: ["chapter-memory", novelUid] });
      qc.invalidateQueries({ queryKey: ["summaries", novelUid] });
      qc.invalidateQueries({ queryKey: ["foreshadowing", novelUid] });
      qc.invalidateQueries({ queryKey: ["novels", novelUid] });
    },
  });
}

export function useForeshadowingList(novelUid: string | null, status?: string) {
  return useQuery({
    queryKey: ["foreshadowing", novelUid, status ?? ""],
    queryFn: () => {
      const q = status ? `?status=${encodeURIComponent(status)}` : "";
      return apiRequest<ForeshadowItem[]>(
        `/api/v1/novels/${novelUid}/memory/foreshadowing${q}`
      );
    },
    enabled: Boolean(novelUid),
  });
}

export function useCreateForeshadow(novelUid: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: {
      description: string;
      planted_chapter_id?: number | null;
      plan_recover_start?: number | null;
      plan_recover_end?: number | null;
      status?: ForeshadowStatus;
      source_quote?: string;
    }) =>
      apiRequest<ForeshadowItem>(
        `/api/v1/novels/${novelUid}/memory/foreshadowing`,
        {
          method: "POST",
          body: JSON.stringify(payload),
        }
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["foreshadowing", novelUid] });
    },
  });
}

export function useUpdateForeshadow(novelUid: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: {
      id: number;
      description?: string;
      plan_recover_start?: number | null;
      plan_recover_end?: number | null;
      status?: ForeshadowStatus;
      confirm_status?: "pending" | "confirmed" | "discarded";
    }) =>
      apiRequest<ForeshadowItem>(
        `/api/v1/novels/${novelUid}/memory/foreshadowing/${payload.id}`,
        {
          method: "PUT",
          body: JSON.stringify(payload),
        }
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["foreshadowing", novelUid] });
    },
  });
}

export function useDeleteForeshadow(novelUid: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (fid: number) =>
      apiRequest<{ status: string }>(
        `/api/v1/novels/${novelUid}/memory/foreshadowing/${fid}`,
        { method: "DELETE" }
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["foreshadowing", novelUid] });
    },
  });
}

export function useSummaries(novelUid: string | null, level?: string) {
  return useQuery({
    queryKey: ["summaries", novelUid, level ?? ""],
    queryFn: () => {
      const q = level ? `?level=${encodeURIComponent(level)}` : "";
      return apiRequest<SummaryItem[]>(
        `/api/v1/novels/${novelUid}/memory/summaries${q}`
      );
    },
    enabled: Boolean(novelUid),
  });
}

export function useRagSearch(novelUid: string) {
  return useMutation({
    mutationFn: (params: { q: string; max_chapter_sort?: number }) => {
      const sp = new URLSearchParams({ q: params.q });
      if (params.max_chapter_sort !== undefined) {
        sp.set("max_chapter_sort", String(params.max_chapter_sort));
      }
      return apiRequest<RagSearchResponse>(
        `/api/v1/novels/${novelUid}/memory/search?${sp.toString()}`
      );
    },
  });
}

export function useRebuildMemoryIndex(novelUid: string) {
  return useMutation({
    mutationFn: () =>
      apiRequest<{ chapters_reindexed: number; chunks_indexed: number }>(
        `/api/v1/novels/${novelUid}/memory/rebuild-index`,
        { method: "POST" }
      ),
  });
}

export function useRunConsistencyReview(novelUid: string, chapterId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiRequest<ConsistencyReviewResponse>(
        `/api/v1/novels/${novelUid}/chapters/${chapterId}/consistency-review`,
        { method: "POST" }
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["novels", novelUid, "outline"] });
      qc.invalidateQueries({ queryKey: ["novels", novelUid, "chapters"] });
    },
  });
}

export function useApplyReviewRevision(novelUid: string, chapterId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: { reviewId: number; issueIndex: number; expectedContent: string }) =>
      apiRequest<import("@/features/editor/types").ChapterWorkspace>(
        `/api/v1/novels/${novelUid}/consistency-reviews/${input.reviewId}/apply`,
        { method: "POST", body: JSON.stringify({ issue_index: input.issueIndex, expected_content: input.expectedContent }) }
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["novels", novelUid] });
      qc.invalidateQueries({ queryKey: ["consistency-reviews", novelUid, chapterId] });
      qc.invalidateQueries({ queryKey: ["context-preview", novelUid] });
    },
  });
}

export function useConsistencyReviews(novelUid: string | null, chapterId: number | null) {
  return useQuery({
    queryKey: ["consistency-reviews", novelUid, chapterId],
    enabled: !!novelUid && !!chapterId,
    queryFn: () => fetchConsistencyReviews(novelUid!, chapterId!),
  });
}
