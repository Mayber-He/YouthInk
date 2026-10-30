import React from "react";
import { RotateCcw } from "lucide-react";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import type { ChapterVersionItem } from "../types";

interface VersionHistoryModalProps {
  open: boolean;
  onClose: () => void;
  versions: ChapterVersionItem[];
  onRestore: (versionNum: number) => void;
  isRestoring: boolean;
}

export const VersionHistoryModal: React.FC<VersionHistoryModalProps> = ({
  open,
  onClose,
  versions,
  onRestore,
  isRestoring,
}) => {
  return (
    <Modal
      open={open}
      onClose={onClose}
      title="章节正文历史版本"
      maxWidthClass="max-w-2xl"
    >
      <div className="space-y-3 text-xs">
        {versions.length === 0 ? (
          <p className="py-6 text-center text-slate-400">暂无历史版本记录。</p>
        ) : (
          versions.map((v) => (
            <div
              key={v.id}
              className="space-y-2 rounded-xl border border-slate-200 p-3.5 dark:border-slate-800"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="font-mono font-bold text-slate-900 dark:text-slate-100">
                    v{v.version}
                  </span>
                  <Badge tone={v.source === "ai" ? "indigo" : "emerald"}>
                    {v.source === "ai" ? "AI 生成" : "手动保存"}
                  </Badge>
                  <span className="text-slate-400">
                    {v.word_count} 字 · {new Date(v.created_at).toLocaleString()}
                  </span>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={isRestoring}
                  onClick={() => {
                    onRestore(v.version);
                    onClose();
                  }}
                >
                  <RotateCcw className="h-3.5 w-3.5" />
                  恢复此版本
                </Button>
              </div>
              <p className="line-clamp-3 rounded bg-slate-50 p-2 text-slate-600 dark:bg-slate-950 dark:text-slate-400">
                {v.content || "（空内容）"}
              </p>
            </div>
          ))
        )}
      </div>
    </Modal>
  );
};
