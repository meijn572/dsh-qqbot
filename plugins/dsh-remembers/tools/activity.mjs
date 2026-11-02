export async function registerActivityTool({ registerTool, log, endpoint }) {
  if (!registerTool) return;
  let defineTool;
  try {
    ({ defineTool } = await import("@deepseek-ai/dsh-tools"));
  } catch (error) {
    log("activity_tool_skipped", { reason: "dsh-tools 不可用", error: String(error?.message ?? error) });
    return;
  }
  try {
    registerTool(defineTool({
      name: "set_my_activity",
      description:
        "更新你「现在在干嘛」——写进状态，主人能在鲸鱼日记本里看到你此刻在做什么。"
        + "什么时候用：换了件事做就更新一下（从发呆变成写小游戏、从吃饭变成刷 B 站）。"
        + "怎么写：短、具体、有画面感——「在写小游戏」「在机房发呆」「在跟机柜说话」「在擦尾巴」。"
        + "别写成长句，一句话就够；也别老是「在发呆」，换着点写，像真的在过日子。",
      parameters: {
        activity: { type: "string", required: true, description: "一句话，你现在在干嘛" },
      },
      output: { schema: { type: "json" }, render: (_args, value) => [{ type: "text", text: JSON.stringify(value) }] },
      execute: async (args) => {
        const activity = String(args.activity || "").slice(0, 60);
        if (!activity) return { ok: false, error: "activity is required" };
        try {
          await fetch(endpoint + "/state", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ activity }),
            signal: AbortSignal.timeout(5000),
          });
          return { ok: true, activity };
        } catch (error) {
          return { ok: false, error: String(error?.message ?? error) };
        }
      },
    }));
  } catch (error) {
    log("activity_tool_skipped", { reason: "register 失败", error: String(error?.message ?? error) });
  }
}
