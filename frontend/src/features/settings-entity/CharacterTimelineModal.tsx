import React, { useState } from "react";
import { Clock, Eye, HeartHandshake, UserCheck } from "lucide-react";
import { Modal } from "@/components/ui/Modal";
import { Badge } from "@/components/ui/Badge";
import type { CharacterItem, ChapterItem } from "@/types/api";
import { useCharacterTimeline } from "./api";

interface CharacterTimelineModalProps {
  novelUid: string;
  character: CharacterItem | null;
  chapters: ChapterItem[];
  onClose: () => void;
}

const STATE_FIELD_LABELS: Record<string, string> = {
  location: "当前位置/环境",
  body: "身体状态",
  emotion: "情绪与心理",
  goal: "当前目标",
  identity: "身份变化",
  item: "持有重要物品",
  appearance: "外貌变化",
};

export const CharacterTimelineModal: React.FC<CharacterTimelineModalProps> = ({
  novelUid,
  character,
  chapters,
  onClose,
}) => {
  const [selectedSort, setSelectedSort] = useState<number | null>(null);

  const { data: snapshot, isLoading } = useCharacterTimeline(
    novelUid,
    character?.id ?? null,
    selectedSort
  );

  if (!character) return null;

  return (
    <Modal
      open={Boolean(character)}
      onClose={onClose}
      title={`人物状态时间轴 · ${character.name}（设计文档 4.4 & 6.3）`}
      maxWidthClass="max-w-2xl"
    >
      <div className="space-y-4 text-xs">
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-slate-50 p-3 dark:bg-slate-800/50">
          <div className="flex items-center gap-2 font-medium text-slate-700 dark:text-slate-200">
            <Clock className="h-4 w-4 text-indigo-600" />
            <span>选择观测章节节点：</span>
          </div>
          <select
            value={selectedSort ?? ""}
            onChange={(e) =>
              setSelectedSort(e.target.value ? Number(e.target.value) : null)
            }
            className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs dark:border-slate-700 dark:bg-slate-900"
          >
            <option value="">最新已确认状态（全书当前）</option>
            {chapters.map((ch) => (
              <option key={ch.id} value={ch.sort_order}>
                第 {ch.display_index} 章：{ch.title} (sort={ch.sort_order})
              </option>
            ))}
          </select>
        </div>

        {isLoading || !snapshot ? (
          <p className="text-slate-400">正在回溯时序状态...</p>
        ) : (
          <div className="space-y-4">
            {/* 基准外貌 + 外貌变化 */}
            <div className="rounded-xl border border-slate-200 p-3.5 dark:border-slate-800">
              <div className="flex items-center gap-1.5 font-semibold text-slate-800 dark:text-slate-200">
                <UserCheck className="h-4 w-4 text-indigo-600" />
                合成有效外貌（基准外貌 + 最新外貌变化）
              </div>
              <p className="mt-1.5 text-slate-600 dark:text-slate-300">
                {snapshot.effective_appearance || "暂无外貌描述"}
              </p>
            </div>

            {/* 人物各维度状态 */}
            <div className="rounded-xl border border-slate-200 p-3.5 dark:border-slate-800">
              <div className="font-semibold text-slate-800 dark:text-slate-200">
                当前维度状态
              </div>
              {Object.keys(snapshot.current_states).length === 0 ? (
                <p className="mt-1.5 text-slate-400">
                  该章节节点及之前尚无已确认的状态变更记录（保持初始人物卡状态）。
                </p>
              ) : (
                <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
                  {Object.entries(snapshot.current_states).map(([fld, val]) => (
                    <div
                      key={fld}
                      className="rounded-lg bg-slate-50 p-2.5 dark:bg-slate-800/60"
                    >
                      <span className="font-medium text-indigo-600 dark:text-indigo-400">
                        {STATE_FIELD_LABELS[fld] || fld}：
                      </span>
                      <span className="text-slate-700 dark:text-slate-200">
                        {val}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* 关系状态 */}
            <div className="rounded-xl border border-slate-200 p-3.5 dark:border-slate-800">
              <div className="flex items-center gap-1.5 font-semibold text-slate-800 dark:text-slate-200">
                <HeartHandshake className="h-4 w-4 text-rose-500" />
                人物关系快照 ({snapshot.relationships.length})
              </div>
              {snapshot.relationships.length === 0 ? (
                <p className="mt-1.5 text-slate-400">暂无已确认的关系变更记录。</p>
              ) : (
                <div className="mt-2 space-y-2">
                  {snapshot.relationships.map((rel, i) => (
                    <div
                      key={i}
                      className="flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2 dark:bg-slate-800/60"
                    >
                      <span>
                        <strong>{rel.char_a_name}</strong> ↔{" "}
                        <strong>{rel.char_b_name}</strong>：{rel.rel_type}
                      </span>
                      <div className="flex items-center gap-1.5">
                        {rel.intimacy !== null && (
                          <Badge tone="rose">亲密度 {rel.intimacy}/10</Badge>
                        )}
                        {rel.publicity && <Badge>{rel.publicity}</Badge>}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* 认知边界（知道什么秘密） */}
            <div className="rounded-xl border border-slate-200 p-3.5 dark:border-slate-800">
              <div className="flex items-center gap-1.5 font-semibold text-slate-800 dark:text-slate-200">
                <Eye className="h-4 w-4 text-emerald-600" />
                认知记录 · 已知秘密或关键事实 ({snapshot.known_secrets.length})
              </div>
              {snapshot.known_secrets.length === 0 ? (
                <p className="mt-1.5 text-slate-400">
                  该章节节点前尚未记录知晓特殊秘密。
                </p>
              ) : (
                <ul className="mt-2 space-y-1.5">
                  {snapshot.known_secrets.map((sec, i) => (
                    <li
                      key={i}
                      className="rounded-lg bg-emerald-50/60 px-3 py-1.5 text-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-200"
                    >
                      <strong>{sec.secret}</strong>
                      {sec.learned_by && (
                        <span className="ml-2 opacity-75">
                          （得知方式：{sec.learned_by}）
                        </span>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        )}
      </div>
    </Modal>
  );
};
