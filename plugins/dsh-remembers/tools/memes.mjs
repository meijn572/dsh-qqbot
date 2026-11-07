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
        "给表情包写语义信息。你看到表情图、也认得出角色/梗/动作时调用一次。"
        + "ref 支持 source:<图片路径> / file:<库内相对路径> / query:<描述>。"
        + "label 是给记忆/展示用的短名（2-10字），比如「大笑奶龙」；不要从标签拼。"
        + "identity/action/expression/generic 是检索分面，用逗号分隔。"
        + "bridge-note 里带「库里已有」时先看旧 label/分面；默认保留旧分面只追加，"
        + "要完整改写时传 replace_facets=true。"
        + "系统会把它补进表情库索引，不回复用户。",
      parameters: {
        ref: { type: "string", description: "source:D:\\...\\xxx.jpg 或 file:happy/u_xxx.jpg 或 query:黄色小恐龙" },
        source: { type: "string", description: "兼容写法：直接给图片路径" },
        label: { type: "string", description: "短名，2-10字，比如「大笑奶龙」；不知道就空" },
        identity: { type: "string", description: "身份/角色/IP，逗号分隔，比如「奶龙,小恐龙」" },
        action: { type: "string", description: "动作，逗号分隔，比如「举旗,抱饭」" },
        expression: { type: "string", description: "表情/情绪，逗号分隔，比如「大笑,开心」" },
        generic: { type: "string", description: "泛词，逗号分隔，比如「搞笑,可爱」" },
        replace_facets: { type: "boolean", description: "默认 false=保留旧分面只追加；true=用这次分面完整替换" },
        caption: { type: "string", description: "一句话描述图里是什么、在做什么" },
      },
      output: { schema: { type: "json" }, render: (_a, v) => [{ type: "text", text: JSON.stringify(v) }] },
      execute: async (args) => {
        const rawRef = String(args.ref || "").trim();
        const rawSource = String(args.source || "").trim();
        const ref = rawRef || (rawSource ? (rawSource.includes(":") ? rawSource : `source:${rawSource}`) : "");
        const home = String(process.env.DSH_HOME || "").trim();
        if (!ref) return { ok: false, error: "缺少 ref（source:/file:/query:）" };
        if (ref.startsWith("last:")) return { ok: false, error: "last 还没接，先用 source/file/query" };
        if (!home) return { ok: false, error: "没有 DSH_HOME，无法写表情队列" };
        const split = (value) => String(value || "").split(/[,，、\s]+/).map((x) => x.trim()).filter(Boolean).slice(0, 12);
        const record = {
          ref,
          label: String(args.label || "").trim(),
          identity: split(args.identity),
          action: split(args.action),
          expression: split(args.expression),
          generic: split(args.generic),
          replace_facets: Boolean(args.replace_facets),
          caption: String(args.caption || "").trim(),
          ts: Date.now(),
        };
        await appendFile(join(home, "sticker-meta-queue.jsonl"), JSON.stringify(record) + "\n", "utf8");
        return { ok: true, queued: true, ref: record.ref, label: record.label };
      },
    }));

    registerTool(defineTool({
      name: "sticker_lookup",
      description:
        "查这张表情在不在表情库里、库里叫什么、有哪些分面。"
        + "ref 支持 source:<bridge-note 图片路径> / file:<库内相对路径> / query:<关键词>。"
        + "用户问「库里有这张吗」「这张叫什么」时先查这个，不要猜。",
      parameters: {
        ref: { type: "string", required: true, description: "source:D:\\...\\xxx.jpg / file:happy/u_xxx.jpg / query:黄色小恐龙" },
      },
      output: { schema: { type: "json" }, render: (_a, v) => [{ type: "text", text: JSON.stringify(v) }] },
      execute: async (args) => {
        const ref = String(args.ref || "").trim();
        if (!ref) return { ok: false, found: false, error: "缺少 ref" };
        const base = String(process.env.CMEM_PANEL_URL || "http://127.0.0.1:6080").replace(/\/$/, "");
        const res = await fetch(base + "/api/stickers/lookup?ref=" + encodeURIComponent(ref), {
          signal: AbortSignal.timeout(5000),
        });
        return res.json().catch(() => ({ ok: false, found: false, error: "查询失败" }));
      },
    }));

    registerTool(defineTool({
      name: "lexicon_lookup",
      description:
        "只查词库：这个梗/黑话/热词是什么意思、有哪些别名。"
        + "只返回 terms，不返回表情；要找相关表情用 lexicon_search。",
      parameters: {
        q: { type: "string", required: true, description: "要查的词，比如 奶龙 / yyds / 2G" },
        scope: { type: "string", description: "可选：global 或 group:<群号>" },
        kind: { type: "string", description: "可选：slang/meme/buzzword/fandom/abbreviation" },
        status: { type: "string", description: "可选：fresh/hot/stable/archived" },
      },
      output: { schema: { type: "json" }, render: (_a, v) => [{ type: "text", text: JSON.stringify(v) }] },
      execute: async (args) => {
        const q = String(args.q || "").trim();
        if (!q) return { ok: false, error: "缺少 q" };
        const base = String(process.env.CMEM_PANEL_URL || "http://127.0.0.1:6080").replace(/\/$/, "");
        const params = new URLSearchParams({ q });
        for (const key of ["scope", "kind", "status"]) {
          if (args[key]) params.set(key, String(args[key]));
        }
        const res = await fetch(base + "/api/lexicon/lookup?" + params.toString(), {
          signal: AbortSignal.timeout(5000),
        });
        return res.json().catch(() => ({ ok: false, error: "查询失败" }));
      },
    }));

    registerTool(defineTool({
      name: "lexicon_search",
      description:
        "查梗/黑话/热词是什么意思，同时找相关的表情。"
        + "用户问「XX 是什么意思」「这什么梗」「有没有 XX 表情」时用；返回 terms（词条+别名+解释）和 stickers（相关表情）。",
      parameters: {
        q: { type: "string", required: true, description: "要查的词，比如 奶龙 / yyds / 2G" },
      },
      output: { schema: { type: "json" }, render: (_a, v) => [{ type: "text", text: JSON.stringify(v) }] },
      execute: async (args) => {
        const q = String(args.q || "").trim();
        if (!q) return { ok: false, error: "缺少 q" };
        const base = String(process.env.CMEM_PANEL_URL || "http://127.0.0.1:6080").replace(/\/$/, "");
        const res = await fetch(base + "/api/lexicon/search?q=" + encodeURIComponent(q), {
          signal: AbortSignal.timeout(5000),
        });
        return res.json().catch(() => ({ ok: false, error: "查询失败" }));
      },
    }));

    log("meme_tools_registered", { count: 7 });
  } catch (error) {
    log("meme_tools_skipped", { reason: "register 失败", error: String(error?.message ?? error) });
  }
}
