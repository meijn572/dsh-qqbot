export async function registerPersonaTool({ registerTool, log, client, config, persona, refreshPersona }) {
  if (!config.personaEnabled || !config.personaAllowWrite) return;
  if (!registerTool) {
    log("persona_tool_skipped", { reason: "拿不到 tools.register()" });
    return;
  }
  let defineTool;
  try {
    ({ defineTool } = await import("@deepseek-ai/dsh-tools"));
  } catch (error) {
    log("persona_tool_skipped", { reason: "dsh-tools 不可用", error: String(error?.message ?? error) });
    return;
  }
  try {
    registerTool(defineTool({
      name: "persona_update",
      description:
        "整段改写你「对自己的认知」（不是身份设定那段，那段你改不了）。"
        + "当你发现自己身上一条稳定的特质、偏好、口头习惯，而那段里还没写；"
        + "或者实际经历和那段写的不一致时，用它把那段换成新的。"
        + "保持简洁、只写稳定的东西，不要把流水账堆进去。",
      parameters: {
        content: {
          type: "string",
          required: true,
          description: "自我认知段的完整新内容（Markdown）。整段替换，所以先看当前内容再写。",
        },
      },
      output: {
        schema: {
          type: "object",
          additionalProperties: false,
          properties: { ok: { type: "boolean" }, chars: { type: "integer" } },
        },
        render: (_args, value) => [{
          type: "text",
          text: value.ok ? `自我认知已更新（${value.chars} 字符）` : "自我认知更新失败",
        }],
      },
      isConcurrencySafe: () => false,
      async execute(args) {
        const content = String(args?.content ?? "").trim();
        if (!content) throw new Error("persona_update: content 不能为空");
        const res = await client.setSelfModel(content);
        if (!res?.ok) throw new Error("persona_update: 服务端拒绝或连不上");
        persona.triedAt = 0;                 // 下一轮组装前一定重新拉一次
        await refreshPersona(true);
        return { ok: true, chars: Number(res?.chars?.self_model ?? content.length) };
      },
    }));
    log("persona_tool_registered", { name: "persona_update" });
  } catch (error) {
    log("persona_tool_skipped", { reason: "注册失败", error: String(error?.message ?? error) });
  }
}
