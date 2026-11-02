/** B：逐场景写作流程的纯函数，便于在不启动界面的情况下做单元测试。 */

/** 把已接受的场景正文与新场景正文合并，场景之间固定空一行。 */
export function appendSceneText(base: string, next: string): string {
  const head = base.trim();
  const body = next.trim();
  if (!head) return body;
  if (!body) return head;
  return `${head}\n\n${body}`;
}
