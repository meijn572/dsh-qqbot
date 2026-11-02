/** remember_important 工具：只写核心设定的重要的事。 */
export async function registerImportantTool({ registerTool, log, endpoint }) {
  if (!registerTool) return;
  let defineTool;
  try {
    ({ defineTool } = await import("@deepseek-ai/dsh-tools"));
  } catch (error) {
    log("important_tool_skipped", { reason: "dsh-tools 不可用", error: String(error?.message ?? error) });
    return;
  }
  try {
    registerTool(defineTool({
      name: "remember_important",
      description:
        "把真正重要、长期有效的事写进核心设定的「非常重要的事」。"
        + "只收真正不能忘的：约定、底线、身份、关系里最关键的事；日常小事、情绪、一次性的经历不要放。"
        + "最多 8 条，写一句具体的话，不要写标签。",
      parameters: {
        item: { type: "string", required: true, description: "一句重要的事，最多 100 字" },
        reason: { type: "string", description: "可选：为什么重要" },
      },
      output: { schema: { type: "json" }, render: (_args, value) => [{ type: "text", text: JSON.stringify(value) }] },
      execute: async (args) => {
        const item = String(args.item || "").trim().slice(0, 100);
        if (!item) return { ok: false, error: "item is required" };
        try {
          const response = await fetch(endpoint + "/persona/important", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ action: "add", item, reason: String(args.reason || "") }),
            signal: AbortSignal.timeout(5000),
          });
          return { ok: response.ok, status: response.status };
        } catch (error) {
          return { ok: false, error: String(error?.message ?? error) };
        }
      },
    }));
  } catch (error) {
    log("important_tool_skipped", { reason: "register 失败", error: String(error?.message ?? error) });
  }
}
