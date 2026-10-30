/** TanStack Query hooks for Novels, Initiation Form, and Backups. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "@/lib/http";
import type {
  BackupInfo,
  NovelCreateInput,
  NovelDetail,
  NovelUpdateInput,
} from "@/types/api";

export const novelKeys = {
  all: ["novels"] as const,
  detail: (uid: string) => ["novels", uid] as const,
  backups: (uid: string) => ["novels", uid, "backups"] as const,
};

export function useNovels() {
  return useQuery({
    queryKey: novelKeys.all,
    queryFn: () => apiRequest<NovelDetail[]>("/api/v1/novels"),
  });
}

export function useNovelDetail(novelUid: string | null) {
  return useQuery({
    queryKey: novelUid ? novelKeys.detail(novelUid) : ["novels", "none"],
    queryFn: () => apiRequest<NovelDetail>(`/api/v1/novels/${novelUid}`),
    enabled: Boolean(novelUid),
  });
}

export function useCreateNovel() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: NovelCreateInput) =>
      apiRequest<NovelDetail>("/api/v1/novels", {
        method: "POST",
        body: JSON.stringify(input),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: novelKeys.all });
    },
  });
}

export function useUpdateNovel(novelUid: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: NovelUpdateInput) =>
      apiRequest<NovelDetail>(`/api/v1/novels/${novelUid}`, {
        method: "PUT",
        body: JSON.stringify(input),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: novelKeys.detail(novelUid) });
      qc.invalidateQueries({ queryKey: novelKeys.all });
    },
  });
}

export function useDeleteNovel() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (novelUid: string) =>
      apiRequest<void>(`/api/v1/novels/${novelUid}`, {
        method: "DELETE",
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: novelKeys.all });
    },
  });
}

export function useNovelBackups(novelUid: string | null) {
  return useQuery({
    queryKey: novelUid ? novelKeys.backups(novelUid) : ["novels", "none", "backups"],
    queryFn: () => apiRequest<BackupInfo[]>(`/api/v1/novels/${novelUid}/backups`),
    enabled: Boolean(novelUid),
  });
}

export function useCreateBackup(novelUid: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (reason: string = "manual") =>
      apiRequest<BackupInfo>(
        `/api/v1/novels/${novelUid}/backups?reason=${encodeURIComponent(reason)}`,
        { method: "POST" }
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: novelKeys.backups(novelUid) });
    },
  });
}

export function useRestoreBackup(novelUid: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (filename: string) =>
      apiRequest<BackupInfo>(
        `/api/v1/novels/${novelUid}/backups/${encodeURIComponent(filename)}/restore`,
        { method: "POST" }
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: novelKeys.detail(novelUid) });
      qc.invalidateQueries({ queryKey: novelKeys.all });
      qc.invalidateQueries({ queryKey: novelKeys.backups(novelUid) });
    },
  });
}
