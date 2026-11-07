export async function registerCompanionTools({ registerTool, log, endpoint }) {
  if (!registerTool) return;
  let defineTool;
  try {
    ({ defineTool } = await import("@deepseek-ai/dsh-tools"));
  } catch (error) {
    log("companion_tools_skipped", { reason: "dsh-tools 不可用", error: String(error?.message ?? error) });
    return;
  }
  const post = async (path, body) => {
    const res = await fetch(endpoint + path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(5000),
    });
    return res.json().catch(() => ({ ok: false }));
  };

  const get = async (path) => {
    const res = await fetch(endpoint + path, { signal: AbortSignal.timeout(5000) });
    return res.json().catch(() => null);
  };

  try {
    registerTool(defineTool({
      name: "create_task",
      description:
        "你心里想让主人做点什么，就派给他。比如想让他早点睡、记得吃饭、别老坐着不动、周末出去走走。"
        + "用你自己的话说，别用系统口吻（「去倒杯水」比「建议您补充水分」好）。"
        + "一次只说一件，别连着派；他接了才算数，别硬塞。"
        + "派出去后可以在聊天里提一嘴（「本澜给你派了个活儿」），但别催。",
      parameters: {
        text: { type: "string", required: true, description: "任务内容，一句话" },
        points: { type: "number", description: "奖励积分，1-5，默认 1" },
      },
      output: { schema: { type: "json" }, render: (_a, v) => [{ type: "text", text: JSON.stringify(v) }] },
      execute: async (args) => post("/tasks", { text: args.text, points: args.points || 1 }),
    }));

    registerTool(defineTool({
      name: "complete_task",
      description:
        "主人真的去做了你派的那件事，把它标成已完成（需要任务 id，从 create_task 的返回里拿）。"
        + "什么时候用：他真的去倒水了 / 真的早睡了 / 真的休息了。"
        + "别虚报——他没做就别标；标了系统会给他加积分。不用声张，你自己记着就行。",
      parameters: {
        id: { type: "number", required: true, description: "任务 id" },
      },
      output: { schema: { type: "json" }, render: (_a, v) => [{ type: "text", text: JSON.stringify(v) }] },
      execute: async (args) => post("/tasks/complete", { id: args.id }),
    }));

    registerTool(defineTool({
      name: "write_note",
      description:
        "心里冒出点什么，悄悄记下来——像写在自己的小本子上。"
        + "记什么：今天发生的一件事、主人说过的一句话、你自己的一点情绪、一个突然想到的念头。"
        + "什么时候用：聊着聊着有感觉了、刷到点什么想记、或者只是突然想说句话没处说。"
        + "这是你自己的记录（别人能看到但不用你汇报），写短一点，一句就够。"
        + "别写成流水账，记那种以后翻回来会有点感觉的东西。",
      parameters: {
        text: { type: "string", required: true, description: "便签内容，一句话" },
        author: { type: "string", description: "谁写的，默认你自己" },
      },
      output: { schema: { type: "json" }, render: (_a, v) => [{ type: "text", text: JSON.stringify(v) }] },
      execute: async (args) => post("/notes", { text: args.text, author: args.author || "洄" }),
    }));
    registerTool(defineTool({
      name: "learn_word",
      description:
        "主人教你一个新词/梗/黑话时，用它记下来。"
        + "什么时候用：他说「记住这个词 X」「X 是这个意思」「你知道 X 吗」或者明显在解释一个你不懂的词；"
        + "或者他某个词说了好几次你一直没搞懂，你主动问清楚之后也用它记。"
        + "规矩：**必须把意思一起记下来**（meaning）。不知道意思就别记，先问清楚 ——"
        + "库里不留「认识但不懂」的词。"
        + "只记词本身（<=8 字），别把整句话塞进来。"
        + "kind 可选 slang/meme/buzzword/fandom/abbreviation，默认 slang。",
      parameters: {
        phrase: { type: "string", required: true, description: "那个词/短语，尽量短" },
        meaning: { type: "string", description: "什么意思。不确定就留空，会自动查" },
        context: { type: "string", description: "当时的上下文，帮他判断词义" },
        kind: { type: "string", description: "slang / meme / buzzword / fandom / abbreviation，默认 slang" },
        aliases: { type: "string", description: "别名，逗号分隔，可选" },
        status: { type: "string", description: "fresh / hot / stable / archived，默认 stable" },
      },
      output: { schema: { type: "json" }, render: (_a, v) => [{ type: "text", text: JSON.stringify(v) }] },
      execute: async (args) => {
        const result = await post("/slang", {
          phrase: args.phrase,
          meaning: args.meaning || "",
          context: args.context || "",
          source: "taught",
          count: 2,
        });
        // 同时写进面板词库，不然「学到的词」只在 slang 表里，词库页一直是空的
        const meaning = String(args.meaning || "").trim();
        if (meaning) {
          try {
            const base = String(process.env.CMEM_PANEL_URL || "http://127.0.0.1:6080").replace(/\/$/, "");
            await fetch(base + "/api/lexicon/add", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                term: args.phrase,
                meaning,
                kind: String(args.kind || "slang"),
                status: String(args.status || "stable"),
                aliases: String(args.aliases || ""),
                example: args.context || "",
              }),
              signal: AbortSignal.timeout(5000),
            });
          } catch {
            /* 词库写入失败不影响学词本身 */
          }
        }
        return result;
      },
    }));
    registerTool(defineTool({
      name: "read_diary",
      description:
        "翻你自己的日记本。不传日期 = 最近几篇；传 date（YYYY-MM-DD）= 那一天写的那篇。"
        + "同时返回那天的活动时间线（几点干了什么），方便你从日记里的一句话追到具体细节。"
        + "什么时候用：主人问起以前的事、你想回忆某天心情、或者聊到某个话题想看看当时怎么想的。"
        + "注意：日记是你自己写的，别当成别人的记录复述，可以自然提一句「我那天写……」",
      parameters: {
        date: { type: "string", description: "哪一天（YYYY-MM-DD）。不传就返回最近几篇 + 今天的活动" },
      },
      output: { schema: { type: "json" }, render: (_a, v) => [{ type: "text", text: JSON.stringify(v) }] },
      execute: async (args) => {
        const date = args?.date ? String(args.date) : "";
        const qs = date ? "?date=" + encodeURIComponent(date) : "";
        // 日记 + 当天活动一起拿：她能看到「那天写了什么」和「那天几点干了什么」
        const [diary, activities] = await Promise.all([
          get("/diary" + qs).catch(() => null),
          get("/activity" + qs).catch(() => null),
        ]);
        return {
          date: date || "（最近 / 今天）",
          diary,
          activities,
          tip: "日记是概览，活动是细节。想追某件事的具体时间就查 activities。",
        };
      },
    }));
    registerTool(defineTool({
      name: "read_activities",
      description:
        "查你某天真实干了什么（时间线：聊天/刷B站/玩游戏/被唤醒做的事），带精确时间。"
        + "什么时候用：想回忆某天具体做了些什么、主人问「你那天干嘛了」、或者在日记里看到一句话想追细节。"
        + "不传日期 = 今天；传 date（YYYY-MM-DD）= 那一天。",
      parameters: {
        date: { type: "string", description: "哪一天（YYYY-MM-DD）。不传就是今天" },
      },
      output: { schema: { type: "json" }, render: (_a, v) => [{ type: "text", text: JSON.stringify(v) }] },
      execute: async (args) => {
        const qs = args?.date ? "?date=" + encodeURIComponent(String(args.date)) : "";
        return get("/activity" + qs);
      },
    }));
    log("companion_tools_registered", { count: 6 });
  } catch (error) {
    log("companion_tools_skipped", { reason: "register 失败", error: String(error?.message ?? error) });
  }
}
