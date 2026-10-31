/** TanStack Query hooks for M3 Writing Workbench. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "@/lib/http";
import { novelKeys } from "@/features/novels/api";
import { outlineKeys } from "@/features/outline/api";
import type {
  AiSmellScanResult,
  ChapterWorkspace,
  ContextPreview,
  SceneItem,
  SelectionCritiqueResult,
} from "./types";

export const editorKeys = {
  workspace: (uid: string, chId: number) =>
    ["novels", uid, "chapters", chId, "workspace"] as const,
  context: (uid: string, chId: number, sceneId: number | null, disabled: string) =>
    ["novels", uid, "chapters", chId, "context", sceneId, disabled] as const,
};

export function useChapterWorkspace(novelUid: string, chapterId: number | null) {
  return useQuery({
    queryKey: editorKeys.workspace(novelUid, chapterId ?? 0),
    queryFn: () =>
      apiRequest<ChapterWorkspace>(
        `/api/v1/novels/${novelUid}/chapters/${chapterId}/workspace`
      ),
    enabled: Boolean(novelUid && chapterId),
  });
}

export function useSaveChapterContent(novelUid: string, chapterId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: {
      content: string;
      source?: "ai" | "manual";
      create_new_version?: boolean;
    }) =>
      apiRequest<ChapterWorkspace>(
        `/api/v1/novels/${novelUid}/chapters/${chapterId}/content`,
        {
          method: "PUT",
          body: JSON.stringify(input),
        }
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: editorKeys.workspace(novelUid, chapterId) });
      qc.invalidateQueries({ queryKey: outlineKeys.tree(novelUid) });
      qc.invalidateQueries({ queryKey: novelKeys.detail(novelUid) });
    },
  });
}

export function useRestoreChapterVersion(novelUid: string, chapterId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (versionNum: number) =>
      apiRequest<ChapterWorkspace>(
        `/api/v1/novels/${novelUid}/chapters/${chapterId}/versions/${versionNum}/restore`,
        { method: "POST" }
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: editorKeys.workspace(novelUid, chapterId) });
      qc.invalidateQueries({ queryKey: outlineKeys.tree(novelUid) });
    },
  });
}

export function useCreateScene(novelUid: string, chapterId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: {
      beat: string;
      pov_character?: number | null;
      location_id?: number | null;
      character_ids?: number[];
      story_time?: string;
      target_words?: number;
    }) =>
      apiRequest<SceneItem>(
        `/api/v1/novels/${novelUid}/chapters/${chapterId}/scenes`,
        {
          method: "POST",
          body: JSON.stringify(input),
        }
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: editorKeys.workspace(novelUid, chapterId) });
      qc.invalidateQueries({ queryKey: outlineKeys.tree(novelUid) });
    },
  });
}

export function useUpdateScene(novelUid: string, chapterId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      sceneId,
      input,
    }: {
      sceneId: number;
      input: Partial<Omit<SceneItem, "id" | "chapter_id" | "created_at" | "updated_at">>;
    }) =>
      apiRequest<SceneItem>(`/api/v1/novels/${novelUid}/scenes/${sceneId}`, {
        method: "PUT",
        body: JSON.stringify(input),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: editorKeys.workspace(novelUid, chapterId) });
    },
  });
}

export function useDeleteScene(novelUid: string, chapterId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (sceneId: number) =>
      apiRequest<void>(`/api/v1/novels/${novelUid}/scenes/${sceneId}`, {
        method: "DELETE",
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: editorKeys.workspace(novelUid, chapterId) });
    },
  });
}

export function useGenerateScenes(novelUid: string, chapterId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: { scene_count?: number; instruction?: string }) =>
      apiRequest<SceneItem[]>(
        `/api/v1/novels/${novelUid}/chapters/${chapterId}/scenes/generate`,
        {
          method: "POST",
          body: JSON.stringify(input),
        }
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: editorKeys.workspace(novelUid, chapterId) });
      qc.invalidateQueries({ queryKey: outlineKeys.tree(novelUid) });
    },
  });
}

export function useContextPreview(
  novelUid: string,
  chapterId: number | null,
  sceneId: number | null,
  disabledKeys: string[]
) {
  const disabledStr = disabledKeys.slice().sort().join(",");
  return useQuery({
    queryKey: editorKeys.context(novelUid, chapterId ?? 0, sceneId, disabledStr),
    queryFn: () => {
      const params = new URLSearchParams();
      if (sceneId !== null) params.set("scene_id", String(sceneId));
      if (disabledStr) params.set("disabled_keys", disabledStr);
      const qs = params.toString() ? `?${params.toString()}` : "";
      return apiRequest<ContextPreview>(
        `/api/v1/novels/${novelUid}/chapters/${chapterId}/context-preview${qs}`
      );
    },
    enabled: Boolean(novelUid && chapterId),
  });
}

export function useAiSmellScan(novelUid: string) {
  return useMutation({
    mutationFn: (text: string) =>
      apiRequest<AiSmellScanResult>(`/api/v1/novels/${novelUid}/ai-smell-scan`, {
        method: "POST",
        body: JSON.stringify({ text }),
      }),
  });
}

export function useCritiqueSelection(novelUid: string, chapterId: number) {
  return useMutation({
    mutationFn: (selectedText: string) =>
      apiRequest<SelectionCritiqueResult>(
        `/api/v1/novels/${novelUid}/chapters/${chapterId}/critique-selection`,
        {
          method: "POST",
          body: JSON.stringify({ selected_text: selectedText }),
        }
      ),
  });
}

