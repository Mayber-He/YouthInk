import { build } from 'esbuild';
import assert from 'node:assert/strict';
import test from 'node:test';
import { createRequire } from 'node:module';
import path from 'node:path';

async function load() {
  const result = await build({
    stdin: {
      contents: `export { SceneReviewBar } from './src/features/editor/components/SceneReviewBar';
        export { SceneNoticeCard } from './src/features/editor/components/SceneNoticeCard';
        export { appendSceneText } from './src/features/editor/sceneFlow';
        export { renderToStaticMarkup } from 'react-dom/server';`,
      resolveDir: path.resolve('.'),
    },
    bundle: true, write: false, format: 'cjs', platform: 'node',
  });
  const module = { exports: {} };
  new Function('module', 'exports', 'require', result.outputFiles[0].text)(
    module, module.exports, createRequire(import.meta.url)
  );
  return module.exports;
}

const props = {
  sceneLabel: '场景 2/4',
  text: '本场正文',
  reasons: ['重复检测命中：有 1 句台词与前文整句重复'],
  instruction: '',
  isStreaming: false,
  onChangeInstruction() {},
  onAccept() {},
  onRewrite() {},
  onDiscard() {},
};

test('per-scene review shows accept / rewrite / discard and detection reasons', async () => {
  const { SceneReviewBar, renderToStaticMarkup } = await load();
  const html = renderToStaticMarkup(SceneReviewBar({ ...props }));
  assert.match(html, /场景 2\/4 已写完，请确认/);
  assert.match(html, />接受</);
  assert.match(html, />带指令重写本场</);
  assert.match(html, />丢弃</);
  assert.ok(html.includes(props.reasons[0]));
  // 没有指令时重写按钮不可点，避免空指令重写。
  assert.match(html, /<button[^>]*\sdisabled=""/);
});

test('rewrite button becomes available once an instruction is entered', async () => {
  const { SceneReviewBar, renderToStaticMarkup } = await load();
  const html = renderToStaticMarkup(
    SceneReviewBar({ ...props, instruction: '少写心理，多写对话' })
  );
  assert.doesNotMatch(html, /<button[^>]*\sdisabled=""/);
});

test('scene notice shows detection reasons without any rewrite action', async () => {
  const { SceneNoticeCard, renderToStaticMarkup } = await load();
  const html = renderToStaticMarkup(SceneNoticeCard({
    notice: {
      tone: 'warn',
      text: '该场景有重复/一致性问题，已保留原文，请作者判断是否修改。',
      details: ['重复检测命中：有 1 句台词与前文整句重复'],
    },
  }));
  assert.match(html, /已保留原文/);
  assert.match(html, /有 1 句台词与前文整句重复/);
  assert.doesNotMatch(html, /<button/);
});

test('appendSceneText joins accepted scenes with a blank line and trims edges', async () => {
  const { appendSceneText } = await load();
  assert.equal(appendSceneText('', ' 第一场 '), '第一场');
  assert.equal(appendSceneText('第一场\n', '\n第二场  '), '第一场\n\n第二场');
  assert.equal(appendSceneText('第一场', '   '), '第一场');
});
