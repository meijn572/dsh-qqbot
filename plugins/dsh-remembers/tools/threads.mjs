/** 还没完的事：按标题查 open/closed L3。 */
export async function registerThreadTools({ registerTool, log, endpoint }) {
  if (!registerTool) return;
  let defineTool;
  try {
    ({ defineTool } = await import("@deepseek-ai/dsh-tools"));
  } catch (error) {
    log("thread_tool_skipped", { reason: "dsh-tools 不可用", error: String(error?.message ?? error) });
    return;
  }
  registerTool(defineTool({
    name: "get_open_thread",
    description:
      "按标题查一条事件线程的详情。优先查还没完的事（open），也可以查已经结束的（closed）。"
      + "query 用标题或别名，不要用数据库 id。"
      + "返回摘要和状态；标题重复时会返回多个候选。",
    parameters: {
      query: { type: "string", required: true, description: "事件标题或别名，例如「牙疼看牙」" },
    },
    output: { schema: { type: "json" }, render: (_a, v) => [{ type: "text", text: JSON.stringify(v) }] },
    execute: async (args) => {
      const q = String(args.query || "").trim();
      if (!q) return { ok: false, error: "query is required" };
      try {
        const url = endpoint + "/threads/get?q=" + encodeURIComponent(q);
        const resp = await fetch(url, { signal: AbortSignal.timeout(5000) });
        const data = await resp.json();
        return data;
      } catch (error) {
        return { ok: false, error: String(error?.message ?? error) };
      }
    },
  }));
  registerTool(defineTool({
    name: "list_open_threads",
    description: "列出全部还没完的事（最多 8 条）。需要看还有哪些事没结束时用。",
    parameters: {},
    output: { schema: { type: "json" }, render: (_a, v) => [{ type: "text", text: JSON.stringify(v) }] },
    execute: async () => {
      try {
        const resp = await fetch(endpoint + "/threads/open", { signal: AbortSignal.timeout(5000) });
        return await resp.json();
      } catch (error) {
        return { ok: false, error: String(error?.message ?? error) };
      }
    },
  }));
}
