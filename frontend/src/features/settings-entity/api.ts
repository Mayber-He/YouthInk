/** TanStack Query hooks for Worldview, Characters (+ timeline), Locations, and Main Plot. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "@/lib/http";
import type {
  CharacterItem,
  CharacterRole,
  CharacterTimelineSnapshot,
  ConstraintCreateInput,
  ConstraintItem,
  LocationItem,
  MainPlot,
  TurningPointItem,
  WorldviewCategory,
  WorldviewEntry,
} from "@/types/api";

export const entityKeys = {
  worldview: (uid: string) => ["novels", uid, "worldview"] as const,
  characters: (uid: string) => ["novels", uid, "characters"] as const,
  charTimeline: (uid: string, charId: number, sortOrder: number | null) =>
    ["novels", uid, "characters", charId, "timeline", sortOrder] as const,
  locations: (uid: string) => ["novels", uid, "locations"] as const,
  mainPlot: (uid: string) => ["novels", uid, "main-plot"] as const,
};

// --- Worldview ---

export function useWorldview(novelUid: string) {
  return useQuery({
    queryKey: entityKeys.worldview(novelUid),
    queryFn: () =>
      apiRequest<WorldviewEntry[]>(`/api/v1/novels/${novelUid}/worldview`),
  });
}

export function useCreateWorldview(novelUid: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: { category: WorldviewCategory; content: string; locked?: boolean }) =>
      apiRequest<WorldviewEntry>(`/api/v1/novels/${novelUid}/worldview`, {
        method: "POST",
        body: JSON.stringify(input),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: entityKeys.worldview(novelUid) }),
  });
}

export function useUpdateWorldview(novelUid: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      input,
    }: {
      id: number;
      input: Partial<{ category: WorldviewCategory; content: string; locked: boolean }>;
    }) =>
      apiRequest<WorldviewEntry>(`/api/v1/novels/${novelUid}/worldview/${id}`, {
        method: "PUT",
        body: JSON.stringify(input),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: entityKeys.worldview(novelUid) }),
  });
}

export function useDeleteWorldview(novelUid: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) =>
      apiRequest<void>(`/api/v1/novels/${novelUid}/worldview/${id}`, {
        method: "DELETE",
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: entityKeys.worldview(novelUid) }),
  });
}

export function useGenerateWorldview(novelUid: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: { instruction?: string; count?: number }) =>
      apiRequest<WorldviewEntry[]>(`/api/v1/novels/${novelUid}/worldview/generate`, {
        method: "POST",
        body: JSON.stringify(input),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: entityKeys.worldview(novelUid) }),
  });
}

export function useRewriteWorldview(novelUid: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, instruction }: { id: number; instruction: string }) =>
      apiRequest<WorldviewEntry>(
        `/api/v1/novels/${novelUid}/worldview/${id}/rewrite`,
        {
          method: "POST",
          body: JSON.stringify({ instruction }),
        }
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: entityKeys.worldview(novelUid) }),
  });
}

// --- Characters ---

export function useCharacters(novelUid: string) {
  return useQuery({
    queryKey: entityKeys.characters(novelUid),
    queryFn: () =>
      apiRequest<CharacterItem[]>(`/api/v1/novels/${novelUid}/characters`),
  });
}

export function useCreateCharacter(novelUid: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (
      input: Partial<Omit<CharacterItem, "id" | "created_at" | "updated_at">> & {
        name: string;
        role: CharacterRole;
      }
    ) =>
      apiRequest<CharacterItem>(`/api/v1/novels/${novelUid}/characters`, {
        method: "POST",
        body: JSON.stringify(input),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: entityKeys.characters(novelUid) }),
  });
}

export function useUpdateCharacter(novelUid: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      input,
    }: {
      id: number;
      input: Partial<Omit<CharacterItem, "id" | "created_at" | "updated_at">>;
    }) =>
      apiRequest<CharacterItem>(`/api/v1/novels/${novelUid}/characters/${id}`, {
        method: "PUT",
        body: JSON.stringify(input),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: entityKeys.characters(novelUid) }),
  });
}

export function useDeleteCharacter(novelUid: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) =>
      apiRequest<void>(`/api/v1/novels/${novelUid}/characters/${id}`, {
        method: "DELETE",
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: entityKeys.characters(novelUid) }),
  });
}

export function useGenerateCharacters(novelUid: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: { instruction?: string; count?: number }) =>
      apiRequest<CharacterItem[]>(`/api/v1/novels/${novelUid}/characters/generate`, {
        method: "POST",
        body: JSON.stringify(input),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: entityKeys.characters(novelUid) }),
  });
}

export function useRewriteCharacter(novelUid: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, instruction }: { id: number; instruction: string }) =>
      apiRequest<CharacterItem>(
        `/api/v1/novels/${novelUid}/characters/${id}/rewrite`,
        {
          method: "POST",
          body: JSON.stringify({ instruction }),
        }
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: entityKeys.characters(novelUid) }),
  });
}

export function useCharacterTimeline(
  novelUid: string,
  charId: number | null,
  upToChapterSort: number | null
) {
  return useQuery({
    queryKey: entityKeys.charTimeline(novelUid, charId ?? 0, upToChapterSort),
    queryFn: () => {
      const qs =
        upToChapterSort !== null ? `?up_to_chapter_sort=${upToChapterSort}` : "";
      return apiRequest<CharacterTimelineSnapshot>(
        `/api/v1/novels/${novelUid}/characters/${charId}/timeline${qs}`
      );
    },
    enabled: charId !== null,
  });
}

// --- Locations ---

export function useLocations(novelUid: string) {
  return useQuery({
    queryKey: entityKeys.locations(novelUid),
    queryFn: () =>
      apiRequest<LocationItem[]>(`/api/v1/novels/${novelUid}/locations`),
  });
}

export function useCreateLocation(novelUid: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (
      input: Partial<Omit<LocationItem, "id" | "created_at" | "updated_at">> & {
        name: string;
      }
    ) =>
      apiRequest<LocationItem>(`/api/v1/novels/${novelUid}/locations`, {
        method: "POST",
        body: JSON.stringify(input),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: entityKeys.locations(novelUid) }),
  });
}

export function useUpdateLocation(novelUid: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      input,
    }: {
      id: number;
      input: Partial<Omit<LocationItem, "id" | "created_at" | "updated_at">>;
    }) =>
      apiRequest<LocationItem>(`/api/v1/novels/${novelUid}/locations/${id}`, {
        method: "PUT",
        body: JSON.stringify(input),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: entityKeys.locations(novelUid) }),
  });
}

export function useDeleteLocation(novelUid: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) =>
      apiRequest<void>(`/api/v1/novels/${novelUid}/locations/${id}`, {
        method: "DELETE",
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: entityKeys.locations(novelUid) }),
  });
}

export function useGenerateLocations(novelUid: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: { instruction?: string; count?: number }) =>
      apiRequest<LocationItem[]>(`/api/v1/novels/${novelUid}/locations/generate`, {
        method: "POST",
        body: JSON.stringify(input),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: entityKeys.locations(novelUid) }),
  });
}

export function useRewriteLocation(novelUid: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, instruction }: { id: number; instruction: string }) =>
      apiRequest<LocationItem>(
        `/api/v1/novels/${novelUid}/locations/${id}/rewrite`,
        {
          method: "POST",
          body: JSON.stringify({ instruction }),
        }
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: entityKeys.locations(novelUid) }),
  });
}

// --- Main Plot ---

export function useMainPlot(novelUid: string) {
  return useQuery({
    queryKey: entityKeys.mainPlot(novelUid),
    queryFn: () => apiRequest<MainPlot>(`/api/v1/novels/${novelUid}/main-plot`),
  });
}

export function useUpdateMainPlot(novelUid: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (
      input: Partial<{
        core_conflict: string;
        romance_arc: string;
        growth_arc: string;
        key_turning_pts: TurningPointItem[];
        locked: boolean;
      }>
    ) =>
      apiRequest<MainPlot>(`/api/v1/novels/${novelUid}/main-plot`, {
        method: "PUT",
        body: JSON.stringify(input),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: entityKeys.mainPlot(novelUid) }),
  });
}

export function useGenerateMainPlot(novelUid: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: { instruction?: string }) =>
      apiRequest<MainPlot>(`/api/v1/novels/${novelUid}/main-plot/generate`, {
        method: "POST",
        body: JSON.stringify(input),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: entityKeys.mainPlot(novelUid) }),
  });
}

// --- Constraints (Explicit Constraint System) ---

export const constraintKeys = {
  all: (uid: string) => ["novels", uid, "constraints"] as const,
  byTarget: (uid: string, targetType: string, targetId: number | null) =>
    ["novels", uid, "constraints", targetType, targetId] as const,
};

export function useConstraints(
  novelUid: string,
  targetType?: string,
  targetId?: number | null,
  status?: string,
) {
  const params = new URLSearchParams();
  if (targetType) params.set("target_type", targetType);
  if (targetId != null) params.set("target_id", String(targetId));
  if (status) params.set("status", status);
  const qs = params.toString();
  return useQuery({
    queryKey: [...constraintKeys.byTarget(novelUid, targetType ?? "all", targetId ?? null), status ?? "all"],
    queryFn: () =>
      apiRequest<ConstraintItem[]>(
        `/api/v1/novels/${novelUid}/constraints${qs ? `?${qs}` : ""}`,
      ),
  });
}

export function useCreateConstraint(novelUid: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: ConstraintCreateInput) =>
      apiRequest<ConstraintItem>(
        `/api/v1/novels/${novelUid}/constraints`,
        { method: "POST", body: JSON.stringify(input) },
      ),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: constraintKeys.all(novelUid) }),
  });
}

export function useUpdateConstraint(novelUid: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      input,
    }: {
      id: number;
      input: Partial<
        Pick<
          ConstraintItem,
          "content" | "severity" | "status" | "locked" | "source_quote"
        >
      >;
    }) =>
      apiRequest<ConstraintItem>(
        `/api/v1/novels/${novelUid}/constraints/${id}`,
        { method: "PUT", body: JSON.stringify(input) },
      ),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: constraintKeys.all(novelUid) }),
  });
}

export function useDeleteConstraint(novelUid: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) =>
      apiRequest<void>(`/api/v1/novels/${novelUid}/constraints/${id}`, {
        method: "DELETE",
      }),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: constraintKeys.all(novelUid) }),
  });
}
