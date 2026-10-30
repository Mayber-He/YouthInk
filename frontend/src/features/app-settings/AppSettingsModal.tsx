import React, { useEffect, useState } from "react";
import { Modal } from "@/components/ui/Modal";
import { useUiStore } from "@/stores/uiStore";
import { LlmProfilesTab } from "./LlmProfilesTab";
import { TaskAndEmbeddingTab } from "./TaskAndEmbeddingTab";
import { PromptTemplatesTab } from "./PromptTemplatesTab";

export const AppSettingsModal: React.FC = () => {
  const { settingsModalOpen, settingsInitialTab, closeSettingsModal } = useUiStore();
  const [tab, setTab] = useState<"profiles" | "tasks" | "prompts">("profiles");

  useEffect(() => {
    if (settingsInitialTab === "prompts") {
      setTab("prompts");
    } else if (
      settingsInitialTab === "tasks" ||
      settingsInitialTab === "embedding" ||
      settingsInitialTab === "trust"
    ) {
      setTab("tasks");
    } else {
      setTab("profiles");
    }
  }, [settingsInitialTab, settingsModalOpen]);

  return (
    <Modal
      open={settingsModalOpen}
      onClose={closeSettingsModal}
      title="全局设置 · 模型档案、任务分配、Embedding 与 Prompt 模板"
      maxWidthClass="max-w-4xl"
    >
      <div className="mb-5 flex gap-2 border-b border-slate-200 pb-3 dark:border-slate-800">
        {(
          [
            { id: "profiles", label: "① 模型档案与连接测试" },
            { id: "tasks", label: "② 任务分配 / 信任模式 / Embedding" },
            { id: "prompts", label: "③ Prompt 模板管理" },
          ] as const
        ).map((item) => (
          <button
            key={item.id}
            type="button"
            onClick={() => setTab(item.id)}
            className={`rounded-lg px-3.5 py-1.5 text-xs font-medium transition-colors cursor-pointer ${
              tab === item.id
                ? "bg-indigo-600 text-white"
                : "bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-300"
            }`}
          >
            {item.label}
          </button>
        ))}
      </div>

      {tab === "profiles" && <LlmProfilesTab />}
      {tab === "tasks" && <TaskAndEmbeddingTab />}
      {tab === "prompts" && <PromptTemplatesTab />}
    </Modal>
  );
};
