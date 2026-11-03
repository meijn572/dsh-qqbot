import { appendFile } from "node:fs/promises";
import { join } from "node:path";

export async function registerMemeTools({ registerTool, log, endpoint, memeDir }) {
  if (!registerTool) return;
  let defineTool;
  try {
    ({ defineTool } = await import("@deepseek-ai/dsh-tools"));
  } catch (error) {
    log("meme_tools_skipped", { reason: "dsh-tools 不可用", error: String(error?.message ?? error) });
    return;
  }
  const get = async (path) => {
    const res = await fetch(endpoint + path, { signal: AbortSignal.timeout(5000) });
    return res.json().catch(() => null);
  };
  const post = async (path, body) => {
    const res = await fetch(endpoint + path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(5000),
    });
    return res.json().catch(() => ({ ok: false }));
  };

  try {
    registerTool(defineTool({
      name: "find_meme",
      description:
        "按情绪找表情包。emotion 可选 happy / angry / sad / shy / confused / daily；"
        + "也可以给 q 用关键词找（比如「饼干」「下班」「比心」）。"
        + "返回匹配的图片文件名，挑一张用 qq_send_image 发出去。"
        + "发多勤看你上下文里「表情包：现在大约每 N 句配一张」那条——按那个频率来，别自己乱定。",
      parameters: {
        emotion: { type: "string", description: "情绪：happy / angry / sad / shy / confused / daily" },
        q: { type: "string", description: "关键词，比如 饼干 / 下班 / 比心" },
      },
      output: { schema: { type: "json" }, render: (_a, v) => [{ type: "text", text: JSON.stringify(v) }] },
      execute: async (args) => {
        const params = new URLSearchParams();
        if (args.emotion) params.set("emotion", String(args.emotion));
        if (args.q) params.set("q", String(args.q));
        const list = await get("/memes?" + params.toString());
        if (!Array.isArray(list) || list.length === 0) {
          return { ok: true, memes: [], hint: "没找到匹配的，换个情绪或关键词试试" };
        }
        const base = String(memeDir || "").replace(/\/$/, "");
        return {
          ok: true,
          memes: list.slice(0, 8).map((m) => ({
            file: m.file,
            emotion: m.emotion,
            caption: m.caption || m.file,
            path: base ? base + "/" + m.file : m.file,
          })),
        };
      },
    }));

    registerTool(defineTool({
      name: "learn_meme",
      description:
        "把一张图收进你的表情包库。"
        + "老大发来的图、或者你在网上看到喜欢的图，把图片的完整路径传进来，系统会复制入库并自动识别情绪和描述。"
        + "memes 目录里已有的图也可以只传文件名。"
        + "\n图库分三个包，存的时候用 pack 指定：user = 老大发给你的（他发才值得收），found = 你自己叼回来的（刷到顺眼的），dafeiyu = 内置大肥鱼图库（别往里塞）。"
        + "\n什么时候收：老大同一种图发过两次以上、或你自己刷到觉得以后想用，就收。别贪多，收进来要记得住来源。"
        + "\n老大也可能自己改图库描述——改了以他的为准，不要覆盖回你写的。",
      parameters: {
        file: { type: "string", required: true, description: "文件名（memes 目录里的）或完整路径" },
        pack: { type: "string", description: "存到哪个图库包：user（老大发的）、found（你自己叼回来的）、dafeiyu（内置，别用）。默认 found" },
        emotion: { type: "string", description: "情绪：happy / angry / sad / shy / confused / daily" },
        caption: { type: "string", description: "一句话描述这张图的样子" },
        keywords: { type: "string", description: "关键词，空格分隔" },
      },
      output: { schema: { type: "json" }, render: (_a, v) => [{ type: "text", text: JSON.stringify(v) }] },
      execute: async (args) => post("/memes", {
        file: args.file,
        pack: args.pack || "found",
        emotion: args.emotion || "",
        caption: args.caption || "",
        keywords: args.keywords || "",
      }),
    }));

    registerTool(defineTool({
      name: "mark_meme_used",
      description:
        "标记这张表情我用过。发完表情包后顺手记一下，系统会统计哪几张你最常用。"
        + "不是必须的，但记了之后找表情更准（常用的一搜就出来）。file 只填文件名，不用路径。",
      parameters: {
        file: { type: "string", required: true, description: "文件名" },
      },
      output: { schema: { type: "json" }, render: (_a, v) => [{ type: "text", text: JSON.stringify(v) }] },
      execute: async (args) => post("/memes/used", { file: args.file }),
    }));
    registerTool(defineTool({
      name: "sticker_meta",
      description:
        "给刚收到的表情包写语义信息。你看到表情图、也认得出角色/梗/动作时调用一次。"
        + "source 填 bridge-note 里的完整图片路径；tags 用逗号分隔，只写图本身（角色、外观、动作、情绪），不要写聊天场景。"
        + "系统会把它补进表情库索引，不回复用户。",
      parameters: {
        source: { type: "string", required: true, description: "bridge-note 里的完整图片路径" },
        name: { type: "string", description: "这张表情叫什么，比如「奶龙举旗」；不知道就空" },
        tags: { type: "string", description: "逗号或空格分隔的标签，比如「奶龙, 小恐龙, 举旗, 开心」" },
        caption: { type: "string", description: "一句话描述图里是什么、在做什么" },
      },
      output: { schema: { type: "json" }, render: (_a, v) => [{ type: "text", text: JSON.stringify(v) }] },
      execute: async (args) => {
        const source = String(args.source || "").trim();
        const home = String(process.env.DSH_HOME || "").trim();
        if (!source) return { ok: false, error: "缺少 source" };
        if (!home) return { ok: false, error: "没有 DSH_HOME，无法写表情队列" };
        const record = {
          source,
          name: String(args.name || "").trim(),
          tags: String(args.tags || "").split(/[,，、\s]+/).map((x) => x.trim()).filter(Boolean).slice(0, 12),
          caption: String(args.caption || "").trim(),
          ts: Date.now(),
        };
        await appendFile(join(home, "sticker-meta-queue.jsonl"), JSON.stringify(record) + "\n", "utf8");
        return { ok: true, queued: true, name: record.name, tags: record.tags };
      },
    }));

    log("meme_tools_registered", { count: 4 });
  } catch (error) {
    log("meme_tools_skipped", { reason: "register 失败", error: String(error?.message ?? error) });
  }
}
