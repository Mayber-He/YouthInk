import React, { useState } from "react";
import {
  Archive,
  ArrowLeft,
  BookMarked,
  CheckSquare,
  Compass,
  FileEdit,
  GitBranch,
  Globe,
  ListTree,
  MapPin,
  Maximize2,
  Minimize2,
  PanelRightClose,
  PanelRightOpen,
  Settings,
  Users,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { useNovelDetail } from "@/features/novels/api";
import { ProjectInitiationView } from "@/features/novels/ProjectInitiationView";
import { NovelBackupsModal } from "@/features/novels/NovelBackupsModal";
import { WorldviewSection } from "@/features/settings-entity/WorldviewSection";
import { CharactersSection } from "@/features/settings-entity/CharactersSection";
import { LocationsSection } from "@/features/settings-entity/LocationsSection";
import { MainPlotSection } from "@/features/settings-entity/MainPlotSection";
import { OutlineSection } from "@/features/outline/OutlineSection";
import { WritingWorkbench } from "@/features/editor/WritingWorkbench";
import { ForeshadowingSection } from "@/features/memory/ForeshadowingSection";
import { PendingQueueSection } from "@/features/memory/PendingQueueSection";
import { useOutlineTree } from "@/features/outline/api";
import { useUiStore } from "@/stores/uiStore";
import type { WorkbenchSection } from "@/types/api";
import { OutlineSidebarTree } from "./OutlineSidebarTree";
import { StatusBar } from "./StatusBar";

const NAV_ITEMS: Array<{
  id: WorkbenchSection;
  label: string;
  icon: React.FC<{ className?: string }>;
  milestone: string;
}> = [
  { id: "initiation", label: "立项设定", icon: BookMarked, milestone: "M1" },
  { id: "worldview", label: "世界观", icon: Globe, milestone: "M2" },
  { id: "characters", label: "人物卡", icon: Users, milestone: "M2" },
  { id: "locations", label: "地点场景", icon: MapPin, milestone: "M2" },
  { id: "main_plot", label: "主线剧情", icon: Compass, milestone: "M2" },
  { id: "outline", label: "目录 (卷/弧/章)", icon: ListTree, milestone: "M2" },
  { id: "writing", label: "正文写作", icon: FileEdit, milestone: "M3" },
  { id: "foreshadowing", label: "伏笔台账", icon: GitBranch, milestone: "M4" },
  { id: "pending_queue", label: "待确认队列", icon: CheckSquare, milestone: "M4" },
];

export const WorkbenchLayout: React.FC = () => {
  const {
    currentNovelUid,
    activeSection,
    selectedChapterId,
    rightPanelOpen,
    focusMode,
    closeNovel,
    setActiveSection,
    setSelectedChapterId,
    toggleRightPanel,
    toggleFocusMode,
    openSettingsModal,
  } = useUiStore();

  const { data: novel, isLoading } = useNovelDetail(currentNovelUid);
  const { data: outline } = useOutlineTree(currentNovelUid);
  const [backupOpen, setBackupOpen] = useState(false);

  if (isLoading || !novel) {
    return (
      <div className="flex h-screen items-center justify-center bg-slate-50 text-sm text-slate-500 dark:bg-slate-950">
        正在加载作品工作台...
      </div>
    );
  }

  const renderMainSection = () => {
    switch (activeSection) {
      case "initiation":
        return <ProjectInitiationView novel={novel} />;
      case "worldview":
        return <WorldviewSection novelUid={novel.novel_uid} />;
      case "characters":
        return <CharactersSection novelUid={novel.novel_uid} />;
      case "locations":
        return <LocationsSection novelUid={novel.novel_uid} />;
      case "main_plot":
        return <MainPlotSection novelUid={novel.novel_uid} />;
      case "outline":
        return <OutlineSection novelUid={novel.novel_uid} />;
      case "writing":
        return <WritingWorkbench novelUid={novel.novel_uid} />;
      case "foreshadowing":
        return <ForeshadowingSection novelUid={novel.novel_uid} />;
      case "pending_queue":
        return <PendingQueueSection novelUid={novel.novel_uid} />;
      default:
        return <ProjectInitiationView novel={novel} />;
    }
  };

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-slate-50 dark:bg-slate-950">
      <header className="flex h-13 shrink-0 items-center justify-between border-b border-slate-200 bg-white px-4 dark:border-slate-800 dark:bg-slate-900">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" onClick={closeNovel}>
            <ArrowLeft className="h-4 w-4" />
            返回作品列表
          </Button>
          <div className="h-4 w-px bg-slate-200 dark:bg-slate-800" />
          <span className="text-sm font-bold text-slate-900 dark:text-slate-100">
            《{novel.title}》
          </span>
          <Badge tone="indigo">{novel.genre || "校园"}</Badge>
          <Badge>{novel.pov || "第三人称限知"}</Badge>
        </div>

        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" onClick={() => setBackupOpen(true)}>
            <Archive className="h-4 w-4" />
            快照备份
          </Button>
          <Button variant="ghost" size="sm" onClick={toggleFocusMode}>
            {focusMode ? (
              <>
                <Minimize2 className="h-4 w-4" />
                退出专注
              </>
            ) : (
              <>
                <Maximize2 className="h-4 w-4" />
                专注模式
              </>
            )}
          </Button>
          <Button variant="ghost" size="sm" onClick={toggleRightPanel}>
            {rightPanelOpen ? (
              <PanelRightClose className="h-4 w-4" />
            ) : (
              <PanelRightOpen className="h-4 w-4" />
            )}
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => openSettingsModal("profiles")}
          >
            <Settings className="h-4 w-4" />
            设置
          </Button>
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        {!focusMode && (
          <aside className="flex w-60 shrink-0 flex-col overflow-y-auto border-r border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
            <div className="p-3">
              <div className="mb-2 px-2 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                创作流程导航
              </div>
              <nav className="space-y-1">
                {NAV_ITEMS.map((item) => {
                  const Icon = item.icon;
                  const active = activeSection === item.id;
                  return (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => setActiveSection(item.id)}
                      className={`flex w-full items-center justify-between rounded-lg px-3 py-2 text-xs font-medium transition-colors cursor-pointer ${
                        active
                          ? "bg-indigo-50 text-indigo-700 dark:bg-indigo-950/70 dark:text-indigo-300"
                          : "text-slate-600 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800"
                      }`}
                    >
                      <span className="flex items-center gap-2">
                        <Icon className="h-4 w-4" />
                        {item.label}
                      </span>
                      {item.id === "pending_queue" &&
                      novel.pending_confirm_count > 0 ? (
                        <Badge tone="rose">{novel.pending_confirm_count}</Badge>
                      ) : (
                        <span className="text-[10px] text-slate-400">
                          {item.milestone}
                        </span>
                      )}
                    </button>
                  );
                })}
              </nav>
            </div>

            <OutlineSidebarTree
              outline={outline}
              selectedChapterId={selectedChapterId}
              onSelectChapter={(chId) => {
                setSelectedChapterId(chId);
                setActiveSection("outline");
              }}
            />
          </aside>
        )}

        <main className="flex-1 overflow-y-auto">{renderMainSection()}</main>

        {!focusMode && rightPanelOpen && activeSection !== "writing" && (
          <aside className="flex w-72 shrink-0 flex-col border-l border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
            <h3 className="text-xs font-semibold text-slate-800 dark:text-slate-200">
              上下文透明面板
            </h3>
            <p className="mt-1 text-xs text-slate-500">
              每次 AI 生成前，在此处展示即将注入模型的六层上下文与 Token 预算分布。
            </p>
            <div className="mt-4 space-y-2.5 text-xs">
              <div className="rounded-lg border border-slate-200 p-3 dark:border-slate-800">
                <div className="font-medium text-slate-700 dark:text-slate-300">
                  ① 系统角色 + ② 风格模板
                </div>
                <p className="mt-1 text-[11px] text-slate-500">
                  视角：{novel.pov || "第三人称限知"} · 基调：{novel.tone || "清新治愈"}
                </p>
              </div>
              <div className="rounded-lg border border-slate-200 p-3 dark:border-slate-800">
                <div className="font-medium text-slate-700 dark:text-slate-300">
                  ③ 作品核心设定
                </div>
                <p className="mt-1 line-clamp-3 text-[11px] text-slate-500">
                  感情结局：{novel.romance_ending || "HE"} / 成长结局：
                  {novel.growth_ending || "HE"}
                </p>
              </div>
              <div className="rounded-lg border border-slate-200 p-3 dark:border-slate-800">
                <div className="font-medium text-slate-700 dark:text-slate-300">
                  ④ 动态记忆与认知约束
                </div>
                <p className="mt-1 text-[11px] text-slate-500">
                  已规划章节：{outline?.total_chapters ?? 0} 章 · 待确认抽取项：
                  {novel.pending_confirm_count} 条
                </p>
              </div>
            </div>
          </aside>
        )}
      </div>

      <StatusBar novel={novel} />

      <NovelBackupsModal
        novelUid={backupOpen ? novel.novel_uid : null}
        novelTitle={novel.title}
        onClose={() => setBackupOpen(false)}
      />
    </div>
  );
};
