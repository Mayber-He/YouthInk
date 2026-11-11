/** TanStack Query hooks for Global Settings (LLM profiles, Prompts, Styles, Embedding). */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "@/lib/http";
import type {
  EmbeddingModelStatus,
  LlmConnectionTestInput,
  LlmConnectionTestResult,
  LlmProfile,
  LlmProfileCreateInput,
  LlmProfileUpdateInput,
  PromptTemplateItem,
  StyleProfileAnalyzeInput,
  StyleProfileAnalyzeResult,
  StyleTemplate,
  StyleTemplateCreateInput,
  StyleTemplateUpdateInput,
  TaskModelAssignments,
  TrustModeSettings,
} from "@/types/api";

export const settingsKeys = {
  profiles: ["settings", "llm-profiles"] as const,
  assignments: ["settings", "task-assignments"] as const,
  prompts: ["settings", "prompt-templates"] as const,
  styles: ["settings", "style-templates"] as const,
  trustMode: ["settings", "trust-mode"] as const,
  embedding: ["settings", "embedding"] as const,
};

export function useLlmProfiles() {
  return useQuery({
    queryKey: settingsKeys.profiles,
    queryFn: () => apiRequest<LlmProfile[]>("/api/v1/settings/llm-profiles"),
  });
}

export function useCreateLlmProfile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: LlmProfileCreateInput) =>
      apiRequest<LlmProfile>("/api/v1/settings/llm-profiles", {
        method: "POST",
        body: JSON.stringify(input),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: settingsKeys.profiles });
    },
  });
}

export function useUpdateLlmProfile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, input }: { id: number; input: LlmProfileUpdateInput }) =>
      apiRequest<LlmProfile>(`/api/v1/settings/llm-profiles/${id}`, {
        method: "PUT",
        body: JSON.stringify(input),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: settingsKeys.profiles });
    },
  });
}

export function useDeleteLlmProfile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) =>
      apiRequest<void>(`/api/v1/settings/llm-profiles/${id}`, {
        method: "DELETE",
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: settingsKeys.profiles });
      qc.invalidateQueries({ queryKey: settingsKeys.assignments });
    },
  });
}

export function useTestLlmConnection() {
  return useMutation({
    mutationFn: (input: LlmConnectionTestInput) =>
      apiRequest<LlmConnectionTestResult>("/api/v1/settings/llm-profiles/test", {
        method: "POST",
        body: JSON.stringify(input),
      }),
  });
}

export function useTaskAssignments() {
  return useQuery({
    queryKey: settingsKeys.assignments,
    queryFn: () =>
      apiRequest<TaskModelAssignments>("/api/v1/settings/task-assignments"),
  });
}

export function useUpdateTaskAssignments() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: TaskModelAssignments) =>
      apiRequest<TaskModelAssignments>("/api/v1/settings/task-assignments", {
        method: "PUT",
        body: JSON.stringify(input),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: settingsKeys.assignments });
    },
  });
}

export function usePromptTemplates() {
  return useQuery({
    queryKey: settingsKeys.prompts,
    queryFn: () =>
      apiRequest<PromptTemplateItem[]>("/api/v1/settings/prompt-templates"),
  });
}

export function useSavePromptTemplate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ taskType, content }: { taskType: string; content: string }) =>
      apiRequest<PromptTemplateItem>(
        `/api/v1/settings/prompt-templates/${taskType}`,
        {
          method: "PUT",
          body: JSON.stringify({ content, version: "custom-1.0" }),
        }
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: settingsKeys.prompts });
    },
  });
}

export function useResetPromptTemplate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (taskType: string) =>
      apiRequest<PromptTemplateItem>(
        `/api/v1/settings/prompt-templates/${taskType}`,
        { method: "DELETE" }
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: settingsKeys.prompts });
    },
  });
}

export function useStyleTemplates() {
  return useQuery({
    queryKey: settingsKeys.styles,
    queryFn: () =>
      apiRequest<StyleTemplate[]>("/api/v1/settings/style-templates"),
  });
}

export function useCreateStyleTemplate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: StyleTemplateCreateInput) =>
      apiRequest<StyleTemplate>("/api/v1/settings/style-templates", {
        method: "POST",
        body: JSON.stringify(input),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: settingsKeys.styles });
    },
  });
}

export function useUpdateStyleTemplate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, input }: { id: number; input: StyleTemplateUpdateInput }) =>
      apiRequest<StyleTemplate>(`/api/v1/settings/style-templates/${id}`, {
        method: "PUT",
        body: JSON.stringify(input),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: settingsKeys.styles });
    },
  });
}

export function useAnalyzeStyleExcerpt() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: StyleProfileAnalyzeInput) =>
      apiRequest<StyleProfileAnalyzeResult>(
        "/api/v1/settings/style-templates/analyze",
        {
          method: "POST",
          body: JSON.stringify(input),
        }
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: settingsKeys.styles });
    },
  });
}

export function useTrustMode() {
  return useQuery({
    queryKey: settingsKeys.trustMode,
    queryFn: () =>
      apiRequest<TrustModeSettings>("/api/v1/settings/trust-mode"),
  });
}

export function useUpdateTrustMode() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: TrustModeSettings) =>
      apiRequest<TrustModeSettings>("/api/v1/settings/trust-mode", {
        method: "PUT",
        body: JSON.stringify(input),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: settingsKeys.trustMode });
    },
  });
}

export function useEmbeddingStatus() {
  return useQuery({
    queryKey: settingsKeys.embedding,
    queryFn: () =>
      apiRequest<EmbeddingModelStatus>("/api/v1/settings/embedding"),
    refetchInterval: (query) =>
      query.state.data?.status === "downloading" ? 1000 : false,
  });
}

export function useTriggerEmbeddingDownload() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (source: "modelscope" | "hf_mirror" | "huggingface") =>
      apiRequest<EmbeddingModelStatus>(
        `/api/v1/settings/embedding/download?source=${source}`,
        { method: "POST" }
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: settingsKeys.embedding });
    },
  });
}
