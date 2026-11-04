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
        "只更新你「最近的变化 / 我学到的 / 还没想清」三块自我认知，不碰核心设定。"
        + "只写第一人称的叙事和发现；不要写行为规则、用户事实、工具说明、消息格式。"
        + "整组替换，先看当前内容再写；没想清就留空数组。",
      parameters: {
        changes: {
          type: "array", items: { type: "string" },
          description: "最近你身上发生的变化，最多 4 条",
        },
        learned: {
          type: "array", items: { type: "string" },
          description: "你学到的、确认的东西，最多 4 条",
        },
        open_questions: {
          type: "array", items: { type: "string" },
          description: "还没想清的问题，最多 4 条",
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
        const clean = (value) => (Array.isArray(value) ? value : [])
          .map((item) => String(item ?? "").trim()).filter(Boolean).slice(0, 4);
        const sections = {
          changes: clean(args?.changes),
          learned: clean(args?.learned),
          open_questions: clean(args?.open_questions),
        };
        if (!sections.changes.length && !sections.learned.length && !sections.open_questions.length) {
          throw new Error("persona_update: 三块都为空");
        }
        const res = await client.setSelfModel({ sections });
        if (!res?.ok) throw new Error("persona_update: 服务端拒绝或连不上");
        persona.triedAt = 0;                 // 下一轮组装前一定重新拉一次
        await refreshPersona(true);
        return { ok: true, chars: Number(res?.chars?.self_model ?? 0) };
      },
    }));
    log("persona_tool_registered", { name: "persona_update" });
  } catch (error) {
    log("persona_tool_skipped", { reason: "注册失败", error: String(error?.message ?? error) });
  }
}
