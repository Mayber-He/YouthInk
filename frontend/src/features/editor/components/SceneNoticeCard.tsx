import React from "react";

export interface SceneNoticeView {
  tone: "info" | "warn";
  text: string;
  details: string[];
}

interface SceneNoticeCardProps {
  notice: SceneNoticeView;
}

/**
 * D：把重复检测/一致性提示挂在对应场景旁边。
 * 这里只展示原因，不提供“自动改写”入口；作者要改就点本场的“续写此景”或
 * 在正文里手动改。
 */
export const SceneNoticeCard: React.FC<SceneNoticeCardProps> = ({ notice }) => (
  <div
    className={`mt-2 rounded-lg border p-2 text-[11px] leading-relaxed ${
      notice.tone === "warn"
        ? "border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-900/50 dark:bg-amber-950/30 dark:text-amber-200"
        : "border-sky-200 bg-sky-50 text-sky-800 dark:border-sky-900/50 dark:bg-sky-950/30 dark:text-sky-200"
    }`}
  >
    <p className="font-medium">{notice.text}</p>
    {notice.details.length > 0 && (
      <ul className="mt-1 list-disc space-y-0.5 pl-4">
        {notice.details.map((detail, index) => (
          <li key={`${index}-${detail}`}>{detail}</li>
        ))}
      </ul>
    )}
  </div>
);
