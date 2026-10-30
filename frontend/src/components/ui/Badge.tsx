import React from "react";

interface BadgeProps {
  tone?: "default" | "indigo" | "emerald" | "amber" | "rose";
  children: React.ReactNode;
}

export const Badge: React.FC<BadgeProps> = ({ tone = "default", children }) => {
  const styles: Record<NonNullable<BadgeProps["tone"]>, string> = {
    default: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300",
    indigo: "bg-indigo-50 text-indigo-700 dark:bg-indigo-950/60 dark:text-indigo-300",
    emerald: "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300",
    amber: "bg-amber-50 text-amber-700 dark:bg-amber-950/60 dark:text-amber-300",
    rose: "bg-rose-50 text-rose-700 dark:bg-rose-950/60 dark:text-rose-300",
  };

  return (
    <span
      className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs font-medium ${styles[tone]}`}
    >
      {children}
    </span>
  );
};
