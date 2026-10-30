import React, { useState } from "react";
import {
  Archive,
  BookOpen,
  Feather,
  FolderOpen,
  Plus,
  Settings,
  Sparkles,
  Trash2,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/common/EmptyState";
import { useLlmProfiles } from "@/features/app-settings/api";
import { useUiStore } from "@/stores/uiStore";
import { useDeleteNovel, useNovels } from "./api";
import { CreateNovelModal } from "./CreateNovelModal";
import { NovelBackupsModal } from "./NovelBackupsModal";

export const NovelListPage: React.FC = () => {
  const { data: novels = [], isLoading } = useNovels();
  const { data: profiles = [] } = useLlmProfiles();
  const deleteMut = useDeleteNovel();

  const openNovel = useUiStore((s) => s.openNovel);
  const openSettingsModal = useUiStore((s) => s.openSettingsModal);

  const [createOpen, setCreateOpen] = useState(false);
  const [backupTarget, setBackupTarget] = useState<{
    uid: string;
    title: string;
  } | null>(null);

  const needsSetupWizard = profiles.length === 0;

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950">
      {/* 顶部栏 */}
      <header className="border-b border-slate-200 bg-white/80 backdrop-blur-xs dark:border-slate-800 dark:bg-slate-900/80">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-600 text-white shadow-xs">
              <Feather className="h-5 w-5" />
            </div>
            <div>
              <h1 className="text-base font-bold tracking-tight text-slate-900 dark:text-slate-100">
                YouthInk 青春小说工作台
              </h1>
              <p className="text-xs text-slate-500">
                百万字长篇设定一致性 · 三层防幻觉记忆系统 · 本地双库架构
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2.5">
            <Button
              variant="outline"
              size="md"
              onClick={() => openSettingsModal("profiles")}
            >
              <Settings className="h-4 w-4" />
              全局设置
            </Button>
            <Button size="md" onClick={() => setCreateOpen(true)}>
              <Plus className="h-4 w-4" />
              新建作品立项
            </Button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl space-y-6 px-6 py-8">
        {/* 首次启动向导提示（设计文档 6.1） */}
        {needsSetupWizard && (
          <div className="flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-indigo-200 bg-indigo-50/80 p-5 dark:border-indigo-900/60 dark:bg-indigo-950/40">
            <div className="space-y-1">
              <div className="flex items-center gap-2 text-sm font-semibold text-indigo-950 dark:text-indigo-200">
                <Sparkles className="h-4 w-4 text-indigo-600" />
                首次启动向导：尚未配置大模型 API 档案
              </div>
              <p className="text-xs text-indigo-800/80 dark:text-indigo-300/80">
                建议先前往「全局设置」添加 OpenAI 兼容模型档案（如 DeepSeek / OpenAI /
                Claude 中转），点击「测试连接」验证连通并准备本地 Embedding 模型。
              </p>
            </div>
            <Button size="sm" onClick={() => openSettingsModal("profiles")}>
              立即配置 API 并测试连接
            </Button>
          </div>
        )}

        {/* 作品列表 */}
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300">
            全部作品 ({novels.length})
          </h2>
        </div>

        {isLoading ? (
          <p className="text-xs text-slate-400">正在扫描本机作品库...</p>
        ) : novels.length === 0 ? (
          <EmptyState
            title="还没有创建任何青春小说作品"
            description="每部作品拥有独立的 SQLite 数据库 (novel.db)、向量索引与自动备份目录。"
            action={
              <Button onClick={() => setCreateOpen(true)}>
                <Plus className="h-4 w-4" />
                创建第一部青春小说
              </Button>
            }
          />
        ) : (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
            {novels.map((novel) => (
              <div
                key={novel.novel_uid}
                className="group flex flex-col justify-between rounded-2xl border border-slate-200 bg-white p-5 shadow-2xs transition-all hover:border-indigo-300 hover:shadow-md dark:border-slate-800 dark:bg-slate-900"
              >
                <div>
                  <div className="flex items-start justify-between gap-2">
                    <h3 className="text-base font-bold text-slate-900 group-hover:text-indigo-600 dark:text-slate-100">
                      《{novel.title}》
                    </h3>
                    <Badge tone="indigo">{novel.genre || "校园"}</Badge>
                  </div>

                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {novel.tone && <Badge>{novel.tone}</Badge>}
                    {novel.pov && <Badge>{novel.pov}</Badge>}
                    {novel.romance_ending && (
                      <Badge tone="emerald">感情线: {novel.romance_ending}</Badge>
                    )}
                  </div>

                  <p className="mt-3 line-clamp-3 text-xs leading-relaxed text-slate-600 dark:text-slate-400">
                    {novel.synopsis || novel.protagonist_concept || "暂无故事梗概"}
                  </p>
                </div>

                <div className="mt-5 space-y-3 border-t border-slate-100 pt-3 dark:border-slate-800">
                  <div className="flex items-center justify-between text-[11px] text-slate-400">
                    <span>
                      字数: {novel.current_words.toLocaleString()} /{" "}
                      {(novel.target_words / 10000).toFixed(0)}万字
                    </span>
                    <span>
                      章节: {novel.finalized_chapters}/{novel.total_chapters} 定稿
                    </span>
                  </div>

                  <div className="flex items-center justify-between gap-2">
                    <Button
                      size="sm"
                      className="flex-1"
                      onClick={() => openNovel(novel.novel_uid)}
                    >
                      <FolderOpen className="h-3.5 w-3.5" />
                      打开工作台
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      title="快照备份与恢复"
                      onClick={() =>
                        setBackupTarget({
                          uid: novel.novel_uid,
                          title: novel.title,
                        })
                      }
                    >
                      <Archive className="h-3.5 w-3.5" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      title="删除作品"
                      className="text-rose-600 hover:bg-rose-50"
                      onClick={() => {
                        if (
                          window.confirm(
                            `确定要永久删除《${novel.title}》及其目录吗？此操作不可撤销。`
                          )
                        ) {
                          deleteMut.mutate(novel.novel_uid);
                        }
                      }}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* M1 架构特性状态卡片 */}
        <div className="grid grid-cols-1 gap-4 pt-4 sm:grid-cols-3">
          <div className="rounded-xl border border-slate-200/80 bg-white/70 p-4 dark:border-slate-800 dark:bg-slate-900/50">
            <div className="flex items-center gap-2 text-xs font-semibold text-slate-800 dark:text-slate-200">
              <BookOpen className="h-4 w-4 text-indigo-600" />
              生成 → 编辑 → 锁定
            </div>
            <p className="mt-1 text-xs text-slate-500">
              世界观、人物卡、地点、主线与细纲均可单独锁定，下游以锁定内容为硬约束。
            </p>
          </div>
          <div className="rounded-xl border border-slate-200/80 bg-white/70 p-4 dark:border-slate-800 dark:bg-slate-900/50">
            <div className="flex items-center gap-2 text-xs font-semibold text-slate-800 dark:text-slate-200">
              <Sparkles className="h-4 w-4 text-emerald-600" />
              定稿入库与信任模式
            </div>
            <p className="mt-1 text-xs text-slate-500">
              草稿反复修改不污染记忆，点击定稿才触发摘要、状态抽取与向量入库。
            </p>
          </div>
          <div className="rounded-xl border border-slate-200/80 bg-white/70 p-4 dark:border-slate-800 dark:bg-slate-900/50">
            <div className="flex items-center gap-2 text-xs font-semibold text-slate-800 dark:text-slate-200">
              <Archive className="h-4 w-4 text-amber-600" />
              本机数据隔离与备份
            </div>
            <p className="mt-1 text-xs text-slate-500">
              所有业务数据保存在本机独立 novel.db，支持一键快照备份与回滚。
            </p>
          </div>
        </div>
      </main>

      <CreateNovelModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreated={(novel) => openNovel(novel.novel_uid)}
      />

      <NovelBackupsModal
        novelUid={backupTarget?.uid ?? null}
        novelTitle={backupTarget?.title ?? ""}
        onClose={() => setBackupTarget(null)}
      />
    </div>
  );
};
