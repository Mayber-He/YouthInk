import React, { useState } from "react";
import { RotateCcw, Save } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import {
  usePromptTemplates,
  useResetPromptTemplate,
  useSavePromptTemplate,
} from "./api";

export const PromptTemplatesTab: React.FC = () => {
  const { data: templates = [], isLoading } = usePromptTemplates();
  const saveMut = useSavePromptTemplate();
  const resetMut = useResetPromptTemplate();

  const [selectedTask, setSelectedTask] = useState<string>("system_role");
  const [draftContent, setDraftContent] = useState<string | null>(null);

  const current = templates.find((t) => t.task_type === selectedTask) ?? templates[0];
  const editorValue = draftContent !== null ? draftContent : current?.content ?? "";

  const handleSelect = (taskType: string) => {
    setSelectedTask(taskType);
    setDraftContent(null);
  };

  if (isLoading) {
    return <p className="text-xs text-slate-400">正在加载内置与自定义 Prompt 模板...</p>;
  }

  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
      <div className="space-y-1.5 border-r border-slate-200 pr-3 dark:border-slate-800">
        {templates.map((t) => (
          <button
            key={t.task_type}
            type="button"
            onClick={() => handleSelect(t.task_type)}
            className={`w-full rounded-lg px-3 py-2 text-left text-xs transition-colors cursor-pointer ${
              current?.task_type === t.task_type
                ? "bg-indigo-50 text-indigo-700 font-semibold dark:bg-indigo-950/60 dark:text-indigo-300"
                : "text-slate-600 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800"
            }`}
          >
            <div className="flex items-center justify-between">
              <span>{t.description}</span>
              {t.is_overridden && <Badge tone="amber">已定制</Badge>}
            </div>
            <div className="mt-0.5 font-mono text-[10px] opacity-70">{t.task_type}</div>
          </button>
        ))}
      </div>

      {current && (
        <div className="md:col-span-2 flex flex-col space-y-3">
          <div className="flex items-center justify-between">
            <div>
              <h4 className="text-sm font-semibold">{current.description}</h4>
              <p className="text-xs text-slate-500">
                支持 <code className="font-mono">{"{{变量名}}"}</code> 占位符渲染 · 版本{" "}
                {current.version}
              </p>
            </div>
            <div className="flex items-center gap-2">
              {current.is_overridden && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    resetMut.mutate(current.task_type);
                    setDraftContent(null);
                  }}
                >
                  <RotateCcw className="h-3.5 w-3.5" />
                  恢复默认
                </Button>
              )}
              <Button
                size="sm"
                disabled={saveMut.isPending}
                onClick={() =>
                  saveMut.mutate({
                    taskType: current.task_type,
                    content: editorValue,
                  })
                }
              >
                <Save className="h-3.5 w-3.5" />
                保存修改
              </Button>
            </div>
          </div>

          <textarea
            rows={12}
            value={editorValue}
            onChange={(e) => setDraftContent(e.target.value)}
            className="w-full rounded-xl border border-slate-300 bg-slate-50 p-3 font-mono text-xs leading-relaxed text-slate-800 focus:border-indigo-500 focus:outline-none dark:border-slate-700 dark:bg-slate-950 dark:text-slate-200"
          />
        </div>
      )}
    </div>
  );
};
