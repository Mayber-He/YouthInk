import React from "react";
import { Lock, Unlock } from "lucide-react";

interface LockToggleProps {
  locked: boolean;
  onToggle: (nextLocked: boolean) => void;
  disabled?: boolean;
}

export const LockToggle: React.FC<LockToggleProps> = ({
  locked,
  onToggle,
  disabled = false,
}) => {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={() => onToggle(!locked)}
      title={locked ? "已锁定（AI 重新生成全部时保留此项）" : "未锁定（点击锁定保护）"}
      className={`inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium transition-colors cursor-pointer ${
        locked
          ? "bg-amber-100 text-amber-800 hover:bg-amber-200 dark:bg-amber-950/60 dark:text-amber-300"
          : "bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-400"
      }`}
    >
      {locked ? <Lock className="h-3.5 w-3.5" /> : <Unlock className="h-3.5 w-3.5" />}
      <span>{locked ? "已锁定" : "未锁定"}</span>
    </button>
  );
};
