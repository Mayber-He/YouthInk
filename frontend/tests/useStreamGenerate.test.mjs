import { build } from 'esbuild';
import assert from 'node:assert/strict';
import test from 'node:test';
import path from 'node:path';

// Exercise the real hook's async lifecycle without a browser or an upstream model.
async function harness() {
  const result = await build({
    stdin: {
      contents: `export { useStreamGenerate } from './src/features/editor/hooks/useStreamGenerate';
        export { setConsumer } from '@/lib/sse';`,
      resolveDir: path.resolve('.'),
    },
    bundle: true, write: false, format: 'cjs', platform: 'node',
    plugins: [{ name: 'isolated-hook-dependencies', setup(builder) {
      builder.onResolve({ filter: /^(react|@\/lib\/sse)$/ }, args => ({ path: args.path, namespace: 'test' }));
      builder.onLoad({ filter: /.*/, namespace: 'test' }, args => ({ contents: args.path === 'react'
        ? `export const useCallback = fn => fn;
           export const useEffect = () => {};
           export const useRef = value => ({current:value});
           export const useState = value => [value, () => {}];`
        : `let consumer; export const setConsumer = fn => { consumer = fn; };
           export const consumeSseStream = (...args) => consumer(...args);`
      }));
    } }],
  });
  const module = { exports: {} };
  new Function('module', 'exports', result.outputFiles[0].text)(module, module.exports);
  return module.exports;
}

const params = { chapter_id: 1, scene_id: null, mode: 'chapter', existing_content: '', disabled_context_keys: [], custom_context: '', instruction: '' };

for (const outcome of ['error', 'cancel', 'missing-done']) {
  test(`restore original text after ${outcome}, never save the partial draft`, async () => {
    const { useStreamGenerate, setConsumer } = await harness();
    const hook = useStreamGenerate('test');
    let editor = '完整原稿';
    let saves = 0;
    setConsumer(async (_url, _body, _signal, handlers) => {
      handlers.onDelta('半截');
      if (outcome === 'error') handlers.onError({ message: '模型失败' });
      if (outcome === 'cancel') hook.stopStream();
    });
    await hook.startWriteStream(params, delta => { editor = delta; }, () => { saves++; }, undefined,
      () => { editor = '完整原稿'; });
    assert.equal(editor, '完整原稿');
    assert.equal(saves, 0);
  });
}

test('completed draft saves once and does not restore original', async () => {
  const { useStreamGenerate, setConsumer } = await harness();
  const hook = useStreamGenerate('test');
  let saved = '';
  let restored = false;
  setConsumer(async (_url, _body, _signal, handlers) => {
    handlers.onDelta('完整新稿');
    handlers.onDone({ input_tokens: 1, output_tokens: 1, elapsed_ms: 1 });
  });
  await hook.startWriteStream(params, () => {}, text => { saved = text; }, undefined,
    () => { restored = true; });
  assert.equal(saved, '完整新稿');
  assert.equal(restored, false);
});
