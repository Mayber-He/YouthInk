import React from "react";
import { ArchiveRestore, HardDriveDownload, Plus } from "lucide-react";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import {
  useCreateBackup,
  useNovelBackups,
  useRestoreBackup,
} from "./api";

interface NovelBackupsModalProps {
  novelUid: string | null;
  novelTitle: string;
  onClose: () => void;
}

export const NovelBackupsModal: React.FC<NovelBackupsModalProps> = ({
  novelUid,
  novelTitle,
  onClose,
}) => {
  const { data: backups = [], isLoading } = useNovelBackups(novelUid);
  const createBakMut = useCreateBackup(novelUid ?? "");
  const restoreBakMut = useRestoreBackup(novelUid ?? "");

  if (!novelUid) return null;

  return (
    <Modal
      open={Boolean(novelUid)}
      onClose={onClose}
      title={`作品快照备份管理 · 《${novelTitle}》`}
      maxWidthClass="max-w-xl"
    >
      <div className="space-y-4">
        <div className="flex items-center justify-between rounded-xl bg-slate-50 p-3.5 dark:bg-slate-800/50">
          <div className="text-xs text-slate-600 dark:text-slate-300">
            每次章节定稿会自动创建快照，你也可以随时手动创建快照。
          </div>
          <Button
            size="sm"
            disabled={createBakMut.isPending}
            onClick={() => createBakMut.mutate("manual")}
          >
            <Plus className="h-3.5 w-3.5" />
            立即创建快照
          </Button>
        </div>

        <div className="space-y-2">
          {isLoading ? (
            <p className="text-xs text-slate-400">正在读取备份目录...</p>
          ) : backups.length === 0 ? (
            <p className="py-6 text-center text-xs text-slate-500">
              当前作品暂无快照备份记录。
            </p>
          ) : (
            backups.map((b) => (
              <div
                key={b.filename}
                className="flex items-center justify-between rounded-lg border border-slate-200 px-3.5 py-2.5 text-xs dark:border-slate-800"
              >
                <div className="flex items-center gap-2.5">
                  <HardDriveDownload className="h-4 w-4 text-indigo-500" />
                  <div>
                    <div className="font-mono font-medium text-slate-800 dark:text-slate-200">
                      {b.filename}
                    </div>
                    <div className="text-[11px] text-slate-400">
                      {(b.size_bytes / 1024).toFixed(1)} KB ·{" "}
                      {new Date(b.created_at).toLocaleString()}
                    </div>
                  </div>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={restoreBakMut.isPending}
                  onClick={() => restoreBakMut.mutate(b.filename)}
                >
                  <ArchiveRestore className="h-3.5 w-3.5" />
                  恢复此快照
                </Button>
              </div>
            ))
          )}
        </div>
      </div>
    </Modal>
  );
};
