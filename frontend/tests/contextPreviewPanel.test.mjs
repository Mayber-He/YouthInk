import { build } from 'esbuild';
import assert from 'node:assert/strict';
import test from 'node:test';
import { createRequire } from 'node:module';
import path from 'node:path';

test('unresolved story_time reminder is visible even when context block is disabled', async () => {
  const result = await build({
    stdin: {
      contents: `export { ContextPreviewPanel } from './src/features/editor/components/ContextPreviewPanel';
        export { renderToStaticMarkup } from 'react-dom/server';`,
      resolveDir: path.resolve('.'),
    },
    bundle: true, write: false, format: 'cjs', platform: 'node',
  });
  const module = { exports: {} };
  new Function('module', 'exports', 'require', result.outputFiles[0].text)(module, module.exports, createRequire(import.meta.url));
  const { ContextPreviewPanel, renderToStaticMarkup } = module.exports;
  const warning = '时间锚点无法确定：请补充 story_time';
  const html = renderToStaticMarkup(ContextPreviewPanel({
    preview: { total_tokens: 0, budget_tokens: 24000, blocks: [], warnings: [warning] },
    isLoading: false, disabledKeys: ['summaries_and_prev'], customContext: '',
    onToggleKey() {}, onChangeCustomContext() {},
  }));
  assert.match(html, /role="alert"/);
  assert.ok(html.includes(warning));
});
