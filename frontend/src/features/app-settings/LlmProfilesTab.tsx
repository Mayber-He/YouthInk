import React, { useState } from "react";
import { CheckCircle2, Loader2, Play, Plus, Star, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import {
  useCreateLlmProfile,
  useDeleteLlmProfile,
  useLlmProfiles,
  useTestLlmConnection,
  useUpdateLlmProfile,
} from "./api";
import type { LlmConnectionTestResult } from "@/types/api";

export const LlmProfilesTab: React.FC = () => {
  const { data: profiles = [], isLoading } = useLlmProfiles();
  const createMut = useCreateLlmProfile();
  const updateMut = useUpdateLlmProfile();
  const deleteMut = useDeleteLlmProfile();
  const testMut = useTestLlmConnection();

  const [name, setName] = useState("");
  const [baseUrl, setBaseUrl] = useState("https://api.deepseek.com/v1");
  const [model, setModel] = useState("deepseek-chat");
  const [apiKey, setApiKey] = useState("");
  const [isDefault, setIsDefault] = useState(true);
  const [formError, setFormError] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<LlmConnectionTestResult | null>(null);
  const [testError, setTestError] = useState<string | null>(null);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    if (!name.trim() || !baseUrl.trim() || !model.trim() || !apiKey.trim()) {
      setFormError("请完整填写档案名称、API 地址、模型标识与 API Key");
      return;
    }
    try {
      await createMut.mutateAsync({
        name: name.trim(),
        base_url: baseUrl.trim(),
        model: model.trim(),
        api_key: apiKey.trim(),
        is_default: isDefault,
      });
      setName("");
      setApiKey("");
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "添加失败");
    }
  };

  const handleTestDraft = async () => {
    setTestResult(null);
    setTestError(null);
    try {
      const res = await testMut.mutateAsync({
        base_url: baseUrl.trim(),
        model: model.trim(),
        api_key: apiKey.trim(),
      });
      setTestResult(res);
    } catch (err) {
      setTestError(err instanceof Error ? err.message : "连接测试失败");
    }
  };

  const handleTestSaved = async (profileId: number) => {
    setTestResult(null);
    setTestError(null);
    try {
      const res = await testMut.mutateAsync({ profile_id: profileId });
      setTestResult(res);
    } catch (err) {
      setTestError(err instanceof Error ? err.message : "连接测试失败");
    }
  };

  return (
    <div className="space-y-6">
      <div className="rounded-xl border border-slate-200 bg-slate-50/70 p-4 dark:border-slate-800 dark:bg-slate-800/40">
        <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-100">
          新增 OpenAI 兼容模型档案
        </h3>
        <p className="mt-0.5 text-xs text-slate-500">
          API Key 将通过本机 Fernet 密钥加密后存入 global.db，绝不明文落盘。
        </p>

        <form onSubmit={handleCreate} className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div>
            <label className="block text-xs font-medium text-slate-700 dark:text-slate-300">
              档案名称
            </label>
            <input
              type="text"
              placeholder="如：DeepSeek V3 主力写作"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-900"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-700 dark:text-slate-300">
              模型名称 (Model ID)
            </label>
            <input
              type="text"
              placeholder="如：deepseek-chat / gpt-4o"
              value={model}
              onChange={(e) => setModel(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-900"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-700 dark:text-slate-300">
              Base URL
            </label>
            <input
              type="text"
              placeholder="https://api.deepseek.com/v1"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-900"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-700 dark:text-slate-300">
              API Key
            </label>
            <input
              type="password"
              placeholder="sk-..."
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-900"
            />
          </div>
          <div className="sm:col-span-2 flex flex-wrap items-center justify-between gap-2 pt-1">
            <label className="inline-flex items-center gap-2 text-xs text-slate-600 dark:text-slate-300">
              <input
                type="checkbox"
                checked={isDefault}
                onChange={(e) => setIsDefault(e.target.checked)}
                className="rounded border-slate-300"
              />
              设为默认模型档案
            </label>
            <div className="flex items-center gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={testMut.isPending || !apiKey.trim()}
                onClick={handleTestDraft}
              >
                {testMut.isPending ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Play className="h-3.5 w-3.5" />
                )}
                测试当前填写的连接
              </Button>
              <Button type="submit" size="sm" disabled={createMut.isPending}>
                <Plus className="h-3.5 w-3.5" />
                保存档案
              </Button>
            </div>
          </div>
        </form>
        {formError && <p className="mt-2 text-xs text-rose-600">{formError}</p>}
      </div>

      {(testResult || testError) && (
        <div
          className={`rounded-xl border p-3.5 text-xs ${
            testResult
              ? "border-emerald-200 bg-emerald-50/70 text-emerald-900 dark:border-emerald-900/50 dark:bg-emerald-950/40 dark:text-emerald-200"
              : "border-rose-200 bg-rose-50/70 text-rose-800 dark:border-rose-900/50 dark:bg-rose-950/40 dark:text-rose-200"
          }`}
        >
          {testResult ? (
            <div className="space-y-1">
              <div className="flex items-center justify-between font-semibold">
                <span className="inline-flex items-center gap-1.5">
                  <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                  LLM 连通成功（{testResult.model}）
                </span>
                <span>
                  耗时 {testResult.elapsed_ms} ms · Token: {testResult.input_tokens} in /{" "}
                  {testResult.output_tokens} out
                </span>
              </div>
              <p className="italic opacity-90">「{testResult.reply}」</p>
            </div>
          ) : (
            <p className="font-medium">连接测试失败：{testError}</p>
          )}
        </div>
      )}

      <div className="space-y-2.5">
        <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-500">
          已保存的模型档案 ({profiles.length})
        </h4>
        {isLoading ? (
          <p className="text-xs text-slate-400">加载中...</p>
        ) : profiles.length === 0 ? (
          <p className="text-xs text-slate-500">尚未添加任何模型档案。</p>
        ) : (
          profiles.map((p) => (
            <div
              key={p.id}
              className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white px-4 py-3 dark:border-slate-800 dark:bg-slate-900"
            >
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-slate-900 dark:text-slate-100">
                    {p.name}
                  </span>
                  <Badge tone="indigo">{p.model}</Badge>
                  {p.is_default && <Badge tone="emerald">默认</Badge>}
                </div>
                <p className="mt-0.5 text-xs text-slate-500">
                  {p.base_url} · Key: <code className="font-mono">{p.api_key_masked}</code>
                </p>
              </div>
              <div className="flex items-center gap-1.5">
                {!p.is_default && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() =>
                      updateMut.mutate({ id: p.id, input: { is_default: true } })
                    }
                  >
                    <Star className="h-3.5 w-3.5" />
                    设为默认
                  </Button>
                )}
                <Button
                  variant="outline"
                  size="sm"
                  disabled={testMut.isPending}
                  onClick={() => handleTestSaved(p.id)}
                >
                  <Play className="h-3.5 w-3.5" />
                  测试连接
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => deleteMut.mutate(p.id)}
                  className="text-rose-600 hover:bg-rose-50"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};
