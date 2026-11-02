import { build } from 'esbuild';
import assert from 'node:assert/strict';
import test from 'node:test';
import { createRequire } from 'node:module';
import path from 'node:path';

async function load() {
  const result = await build({
    stdin: {
      contents: `export { ConstraintMemoryPanel } from './src/features/editor/components/ConstraintMemoryPanel';
        export { renderToStaticMarkup } from 'react-dom/server';
        export { setConstraints } from '@/features/settings-entity/api';`,
      resolveDir: path.resolve('.'),
    },
    bundle: true, write: false, format: 'cjs', platform: 'node',
    plugins: [{
      name: 'mock-constraint-api',
      setup(builder) {
        builder.onResolve({ filter: /^@\/features\/settings-entity\/api$/ }, args => ({
          path: args.path, namespace: 'mock',
        }));
        builder.onLoad({ filter: /.*/, namespace: 'mock' }, () => ({
          contents: `let constraints = [];
            export const setConstraints = value => { constraints = value; };
            export const useChapterActiveConstraints = () => ({ data: constraints, isLoading: false });
            export const useUpdateConstraint = () => ({ mutate() {}, isPending: false });`,
        }));
      },
    }],
  });
  const module = { exports: {} };
  new Function('module', 'exports', 'require', result.outputFiles[0].text)(
    module, module.exports, createRequire(import.meta.url)
  );
  return module.exports;
}

const preview = {
  total_tokens: 100,
  budget_tokens: 24000,
  blocks: [{
    key: 'foreshadowing_and_facts',
    label: '伏笔台账与已确认事实库',
    priority: 'optional',
    enabled: true,
    tokens: 30,
    content: '• [伏笔-planted] 匿名乐谱背面写着缩写\n• [已确认事实] 她九月一日报到',
  }],
};

test('lists chapter constraints with status and disable/restore actions', async () => {
  const { ConstraintMemoryPanel, renderToStaticMarkup, setConstraints } = await load();
  setConstraints([
    {
      id: 1, target_type: 'character', target_id: 3, content: '绝不能写她会游泳',
      severity: 'hard', status: 'active', valid_from_chapter_id: null,
      valid_until_chapter_id: null, source_quote: '', locked: false,
      target_name: '林夏', created_at: '', updated_at: '',
    },
    {
      id: 2, target_type: 'novel', target_id: null, content: '不得出现真实学校名',
      severity: 'soft', status: 'resolved', valid_from_chapter_id: null,
      valid_until_chapter_id: null, source_quote: '', locked: false,
      target_name: '', created_at: '', updated_at: '',
    },
  ]);
  const html = renderToStaticMarkup(ConstraintMemoryPanel({
    novelUid: 'uid', chapterId: 7, preview, isLoading: false,
    disabledKeys: [], onToggleKey() {},
  }));
  assert.match(html, /本章生效约束 \(2\)/);
  assert.match(html, /生效中/);
  assert.match(html, /已解除/);
  assert.match(html, /绝不能写她会游泳/);
  assert.ok(html.includes('停用'));
  assert.ok(html.includes('恢复'));
  assert.match(html, /伏笔-planted/);
  assert.match(html, /已确认事实/);
  assert.match(html, /会随本章提示词一起注入模型/);
});

test('disabled fact block is shown as not injected', async () => {
  const { ConstraintMemoryPanel, renderToStaticMarkup, setConstraints } = await load();
  setConstraints([]);
  const html = renderToStaticMarkup(ConstraintMemoryPanel({
    novelUid: 'uid', chapterId: 7, preview, isLoading: false,
    disabledKeys: ['foreshadowing_and_facts'], onToggleKey() {},
  }));
  assert.match(html, /已停用：本章不会注入该块/);
  assert.ok(html.includes('本章暂无生效中的约束'));
});
