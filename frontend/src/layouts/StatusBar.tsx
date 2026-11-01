import React from "react";
import { Cpu, Database, Moon, ShieldCheck, Sun } from "lucide-react";
import {
  useEmbeddingStatus,
  useLlmProfiles,
  useTaskAssignments,
  useTrustMode,
} from "@/features/app-settings/api";
import { useUiStore } from "@/stores/uiStore";
import type { NovelDetail, WorkbenchSection } from "@/types/api";

interface StatusBarProps {
  novel: NovelDetail;
  activeSection: WorkbenchSection;
}

export const StatusBar: React.FC<StatusBarProps> = ({ novel, activeSection }) => {
  const { data: profiles = [] } = useLlmProfiles();
  const { data: assignments } = useTaskAssignments();
  const { data: embStatus } = useEmbeddingStatus();
  const { data: trustMode } = useTrustMode();
  const { darkMode, toggleDarkMode, openSettingsModal } = useUiStore();

  const defaultProfile =
    profiles.find((p) => p.is_default) ?? profiles[0] ?? null;
  const taskCategory =
    activeSection === "writing"
      ? "writing"
      : activeSection === "foreshadowing" || activeSection === "pending_queue"
      ? "extract"
      : "planning";
  const assignedProfileId = assignments?.[taskCategory];
  const currentProfile = assignedProfileId
    ? profiles.find((profile) => profile.id === assignedProfileId) ?? null
    : defaultProfile;
  const taskCategoryLabel = {
    writing: "正文",
    planning: "规划",
    extract: "抽取",
  }[taskCategory];

  return (
    <footer className="flex h-8 shrink-0 items-center justify-between border-t border-slate-200 bg-slate-100/90 px-4 text-[11px] text-slate-600 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-400">
      <div className="flex items-center gap-4">
        <span>
          全书字数:{" "}
          <strong className="text-slate-800 dark:text-slate-200">
            {novel.current_words.toLocaleString()}
          </strong>{" "}
          / {novel.target_words.toLocaleString()}
        </span>
        <span>
          章节进度:{" "}
          <strong className="text-slate-800 dark:text-slate-200">
            {novel.finalized_chapters}
          </strong>
          /{novel.total_chapters} 定稿
        </span>
      </div>

      <div className="flex items-center gap-4">
        <button
          type="button"
          onClick={() => openSettingsModal("profiles")}
          className="inline-flex items-center gap-1 hover:text-indigo-600 cursor-pointer"
        >
          <Cpu className="h-3.5 w-3.5" />
          <span>
            当前{taskCategoryLabel}模型:{" "}
            {currentProfile
              ? `${currentProfile.name} (${currentProfile.model})`
              : profiles.length === 0
              ? "未配置（点击设置）"
              : "任务模型档案不存在"}
          </span>
        </button>

        <button
          type="button"
          onClick={() => openSettingsModal("embedding")}
          className="inline-flex items-center gap-1 hover:text-indigo-600 cursor-pointer"
        >
          <Database className="h-3.5 w-3.5" />
          <span>
            Embedding: {embStatus?.ready ? "bge-m3 就绪" : "待准备"}
          </span>
        </button>

        <button
          type="button"
          onClick={() => openSettingsModal("trust")}
          className="inline-flex items-center gap-1 hover:text-indigo-600 cursor-pointer"
        >
          <ShieldCheck className="h-3.5 w-3.5 text-emerald-600" />
          <span>信任模式: {trustMode?.enabled ? "开启" : "关闭"}</span>
        </button>

        <button
          type="button"
          onClick={toggleDarkMode}
          className="inline-flex items-center gap-1 hover:text-indigo-600 cursor-pointer"
          title="切换浅色/深色主题"
        >
          {darkMode ? <Sun className="h-3.5 w-3.5" /> : <Moon className="h-3.5 w-3.5" />}
          <span>{darkMode ? "浅色" : "深色"}</span>
        </button>
      </div>
    </footer>
  );
};
