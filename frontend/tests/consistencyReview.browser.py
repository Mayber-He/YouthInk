"""Run from frontend: python tests/consistencyReview.browser.py."""
import os
import subprocess

from playwright.sync_api import expect, sync_playwright


bundle = subprocess.check_output([
    "node", "--input-type=module", "-e", """
import { build } from 'esbuild';
const result = await build({
  stdin: { resolveDir: process.cwd(), loader: 'tsx', contents: `
    import React, { useState } from 'react';
    import { createRoot } from 'react-dom/client';
    import { ConsistencyReviewModal } from './src/features/memory/ConsistencyReviewModal';
    const issue = (rewrite) => ({ check_type: 'prose', verdict: 'suspicious',
      description: '建议', evidence_quote: '原文', suggested_rewrite: rewrite });
    const initial = { id: 1, summary: '报告', issue_count: 3,
      issues: [issue('修改一'), issue('修改二'), issue('')], is_stale: false };
    window.calls = [];
    function App() {
      const [review, setReview] = useState(initial);
      const [open, setOpen] = useState(true);
      window.changeReport = (changes) => setReview({ ...initial, ...changes });
      window.setOpen = setOpen;
      return <ConsistencyReviewModal open={open} onClose={() => setOpen(false)}
        review={review} running={false} error={null}
        onApplyRewrite={(indices) => {
          window.calls.push(indices);
          return new Promise((resolve, reject) => { window.resolveApply = resolve; window.rejectApply = reject; });
        }} />;
    }
    createRoot(document.getElementById('root')).render(<App />);
  ` }, bundle: true, write: false, format: 'iife', platform: 'browser',
});
process.stdout.write(result.outputFiles[0].text);
"""
], text=True, encoding="utf-8")

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE"))
    page = browser.new_page()
    page.set_content('<div id="root"></div>')
    page.add_script_tag(content=bundle)
    boxes = page.get_by_role("checkbox")
    expect(boxes).to_have_count(2)
    expect(page.get_by_role("button", name="采用所选（0）")).to_be_disabled()
    boxes.nth(0).check()
    expect(page.get_by_role("button", name="采用所选（1）")).to_be_enabled()
    page.get_by_role("button", name="全选", exact=True).click()
    expect(boxes.nth(1)).to_be_checked()
    page.get_by_role("button", name="取消全选", exact=True).click()
    expect(boxes.nth(0)).not_to_be_checked()
    page.get_by_role("button", name="全选", exact=True).click()
    page.get_by_role("button", name="采用所选（2）").click()
    assert page.evaluate("window.calls") == [[0, 1]]
    expect(boxes.nth(0)).to_be_disabled()
    page.evaluate("window.rejectApply(new Error('片段重叠'))")
    expect(page.get_by_role("alert")).to_have_text("片段重叠")
    expect(boxes.nth(0)).to_be_checked()
    page.get_by_role("button", name="采用所选（2）").click()
    page.evaluate("window.resolveApply(true)")
    expect(page.get_by_role("button", name="采用所选（0）")).to_be_disabled()
    page.get_by_role("button", name="采纳并保存、复核").nth(1).click()
    assert page.evaluate("window.calls.at(-1)") == [1]
    page.evaluate("window.resolveApply(true)")
    boxes.nth(0).check()
    page.evaluate("window.changeReport({ id: 2 })")
    expect(boxes.nth(0)).not_to_be_checked()
    boxes.nth(0).check()
    page.get_by_role("button", name="关闭", exact=True).click()
    page.evaluate("window.setOpen(true)")
    expect(boxes.nth(0)).not_to_be_checked()
    page.evaluate("window.changeReport({ is_stale: true })")
    expect(boxes).to_have_count(0)
    expect(page.get_by_role("button", name="采纳并保存、复核")).to_have_count(0)
    browser.close()
print("Consistency review browser interactions passed")
