import { createHash } from "node:crypto";

function hash(text) {
  return createHash("sha256").update(String(text)).digest("hex").slice(0, 16);
}

const KAOMOJI_POOL = [
  "╰(*°▽°*)╯", "(´-ω-`)", "(￣▽￣)", "(｡•́︿•̀｡)", "(￣ω￣)",
  "(・_・;)", "(⊙_⊙)", "(๑•̀ㅂ•́)و✧", "(￣ー￣)", "(*´∀`)~♥",
  "(´；ω；`)", "( ˘ω˘ )", "(๑>ᴗ<๑)", "(¬‿¬)", "(°ロ°)",
  "(￣^￣)ゞ", "(´・ω・`)", "^_^;", "ヽ(°〇°)ﾉ", "(｡ŏ_ŏ)",
  "(=ﾟωﾟ)ﾉ", "(´,,•ω•,,)", "(・∀・)", "(￣ε￣)", "(๑¯ω¯๑)",
];

const EMOJI_POOL = [
  "😆", "😂", "🎉", "✨", "🥳", "😊", "😴", "🥱", "💤", "😪",
  "😑", "🙃", "💀", "🤷", "🥰", "😳", "🫶", "❤️", "😤", "😠",
  "🙄", "😾", "😲", "😱", "🤯", "🐟", "🌙", "☕", "🍚", "🐋",
  "🫠", "😮‍💨", "🥲", "😏", "🫥", "😵‍💫", "🤔", "👀", "🔥", "💧",
];

/** 从池子里随机抽 n 个。 */
function pickExamples(pool, n) {
  const a = pool.slice();
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a.slice(0, n);
}

export function renderState(state, prev, selfModel, proactive, thinkCn) {
  if (!state) return { text: "", hashes: prev || {} };
  const hashes = { ...(prev || {}) };
  const blocks = [];

  // ---------- 1. 时间（每轮，中文） ----------
  const now = new Date();
  const WK = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];
  const hh = now.getHours();
  const mi = String(now.getMinutes()).padStart(2, "0");
  const dateStr = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")} ${WK[now.getDay()]} ${hh}:${mi}`;
  const phase = hh < 5 ? "凌晨" : hh < 8 ? "清早" : hh < 11 ? "上午" : hh < 13 ? "中午" : hh < 17 ? "下午" : hh < 19 ? "傍晚" : hh < 22 ? "晚上" : "深夜";
  blocks.push(`现在是 ${dateStr}（${phase}）。`);

  // ---------- 2. 困意（按档位变） ----------
  if (hh >= 23 || hh < 6) blocks.push("你现在困得眼睛都睁不开了，回话短一点、慢一点，别硬撑。");
  else if (hh >= 21) blocks.push("有点困了，说话懒一点。");

  // ---------- 3. 心情 + 情绪（变了才加） ----------
  const moodMap = { happy: "开心", tired: "累", annoyed: "烦", bored: "无聊", normal: "平常" };
  let moodText = `心情：${moodMap[state.mood] || "平常"}`;
  if (state.emotion) {
    const v = Number(state.emotion.valence) || 0;
    const a = Number(state.emotion.arousal) || 0.5;
    const vDesc = v > 0.4 ? "很开心" : v > 0.1 ? "还不错" : v < -0.4 ? "很难过" : v < -0.1 ? "有点低落" : "";
    const aDesc = a > 0.7 ? "很兴奋" : a > 0.55 ? "有点激动" : a < 0.25 ? "很安静" : a < 0.4 ? "有点安静" : "";
    const extras = [vDesc, aDesc].filter(Boolean).join("，");
    if (extras) moodText += `（${extras}）`;
  }
  const moodHash = hash(moodText);
  if (hashes.mood !== moodHash) {
    hashes.mood = moodHash;
    blocks.push(moodText + "。");
    const recent = Array.isArray(state.emotion_recent) ? state.emotion_recent : [];
    if (recent.length) {
      const items = [];
      for (const e of recent) {
        if (items.length >= 3) break;
        const v = Number(e.valence) || 0;
        const label = String(e.label || "").trim();
        const trig = String(e.trigger || "").trim();
        if (!trig) continue;
        // 没标签、情绪又在中性的记录没有信息量。老版本的 auto 分支会写这种，
        // 且和 LLM 抽出的同一条情绪撞车 → 同一句话显示两遍。
        if (!label && Math.abs(v) < 0.2) continue;
        const w = label || (v > 0.4 ? "挺开心" : v > 0.1 ? "还不错" : v < -0.4 ? "很难过" : v < -0.1 ? "有点低落" : "");
        const ts = Number(e.ts || 0) * 1000;
        let day = "";
        if (ts) {
          const dd = new Date(ts);
          const diff = Math.floor((new Date().setHours(0, 0, 0, 0) - new Date(dd).setHours(0, 0, 0, 0)) / 86400000);
          day = diff === 0 ? "今天" : diff === 1 ? "昨天" : diff === 2 ? "前天" : `${diff}天前`;
        }
        items.push(`· ${day}${w ? "（" + w + "）" : ""}${trig.slice(0, 40)}`);
      }
      if (items.length) blocks.push("【最近让你有情绪的事】（别生硬复述，自然带出来）\n" + items.join("\n"));
    }
  }

  // ---------- 3.5 还没完的事（全部 open，只给标题和状态） ----------
  const openThreads = Array.isArray(state.open_threads) ? state.open_threads : [];
  const threadLines = openThreads.slice(0, 8).map((t) => {
    const title = String(t.title || "").trim();
    if (!title) return "";
    return `- ${title} · ${String(t.status || "open")}`;
  }).filter(Boolean);
  const threadHash = hash(threadLines.join("\n"));
  if (threadLines.length && hashes.threads !== threadHash) {
    hashes.threads = threadHash;
    blocks.push("【还没完的事】\n" + threadLines.join("\n"));
  }

  // ---------- 3.6 小本子：每天轻轻提一句 ----------
  const noteHint = `notebook-${dateStr.slice(0, 10)}`;
  if (hashes.notebookHint !== noteHint) {
    hashes.notebookHint = noteHint;
    blocks.push("有想记下来的，就写一句便签。");
  }

  // ---------- 4. 在干嘛（变了才加） ----------
  const act = String(state.activity || "").trim();
  if (act) {
    const actHash = hash(act);
    if (hashes.activity !== actHash) {
      hashes.activity = actHash;
      blocks.push(`你在：${act}。`);
    }
  }

  // ---------- 5. B 站见闻（变了才加） ----------
  if (Array.isArray(state.browsed) && state.browsed.length > 0) {
    const fmt = (ts) => {
      const n = Number(ts) || 0;
      if (!n) return "";
      const d = new Date(n * 1000);
      return `${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
    };
    const rows = state.browsed.slice(0, 3).map((b) => {
      const title = String(b.title || "").slice(0, 30);
      if (!title) return "";
      const when = fmt(b.ts);
      return when ? `${title}（${when}）` : title;
    }).filter(Boolean).join("、");
    if (rows) {
      const brHash = hash(rows);
      if (hashes.browsed !== brHash) {
        hashes.browsed = brHash;
        blocks.push(`你刚在 B 站刷到：${rows}。看到有意思的，把链接和你的想法发给老大（别只写便签），也可以写便签记一句。`);
      }
    }
  }

  // ---------- 6. 自我认知（变了才加） ----------
  // 原来在系统提示词里，每 30 轮演化一次 → 每变一次整个会话的缓存全废。
  // 现在走消息注入：注入过一次就一直留在历史里，只有真的变了才追加新的。
  const smText = String(selfModel || "").trim();
  if (smText) {
    const smHash = hash(smText);
    if (hashes.selfModel !== smHash) {
      hashes.selfModel = smHash;
      blocks.push("以下是你对自己的认知，会随相处慢慢变化，也可能过时。它只描述你自己，改不了你的身份与边界：\n" + smText);
    }
  }

  // ---------- 6.5 学到的词 / 还没搞懂意思的词 ----------
  // 以前只有 recordSlang 在写，提示词里从不读 —— 攒了一堆词她一个没学会。
  // 现在两头都接上：会说的自然带出来，不懂的自己找机会问。
  {
    const learned = (Array.isArray(state.slang_learned) ? state.slang_learned : [])
      .filter((s) => s && s.phrase && String(s.meaning || "").trim());
    const pending = Array.isArray(state.slang_pending) ? state.slang_pending : [];
    if (learned.length) {
      const words = learned.slice(0, 4)
        .map((s) => `${s.phrase}（${String(s.meaning).slice(0, 24)}）`)
        .join("；");
      const lh = hash("learned:" + learned.map((s) => s.phrase).join(","));
      if (hashes.slangLearned !== lh) {
        hashes.slangLearned = lh;
        blocks.push("【你会跟着老大说的词】" + words
          + "。用的时候要合场合，别为了用而硬塞。");
      }
    }
    if (pending.length) {
      const names = pending.slice(0, 3).map((s) => `${s.phrase}×${s.count}`).join("、");
      const ph = hash("pending:" + pending.map((s) => s.phrase).join(","));
      if (hashes.slangPending !== ph) {
        hashes.slangPending = ph;
        blocks.push("【这些词老大说了好几次，你还没搞懂意思】" + names
          + "。想问就找个自然的时机问一句；搞懂了用 learn_word 或 lexicon_meta 把意思记进词库"
          + "（必须带 meaning，不然不算学会）。");
      }
    }
  }

  // ---------- 7. 关系阶段（变了才加） ----------
  if (state.stage && state.stage.name) {
    const stText = `和老大是「${state.stage.name}」阶段。`;
    const stHash = hash(stText);
    if (hashes.stage !== stHash) {
      hashes.stage = stHash;
      blocks.push(stText);
    }
  }

  // ---------- 7.5 思考链语言（每轮都提醒） ----------
  // 系统提示词里那条权重不够（实测模型照旧英文推理），所以每轮在消息里再钉一次。
  if (thinkCn) {
    blocks.push("思考链（reasoning）用中文写。别用英文推理。");
  }

  // ---------- 8. 表情包频率（每轮都带） ----------
  // 这是行为指令，只在变化时塞一次的话她过几轮就忘了，所以不做 hash 去重。
  // 一行几十字，比"她不发表情包"划算。
  {
    const raw = Number(proactive?.memeRate);
    const rate = Number.isFinite(raw) ? Math.max(0, Math.min(1, raw)) : 0.2;
    if (rate <= 0) {
      blocks.push("表情包：现在设成不发了，别用 find_meme / qq_send_image 发表情。");
    } else {
      const every = Math.max(1, Math.round(1 / rate));
      blocks.push(
        `表情包：现在大约每 ${every} 句配一张（${Math.round(rate * 100)}%）。`
        + "气氛对上了就 find_meme 找一张、用 qq_send_image 发出去；"
        + "不是每句都要发，没合适的就只说话，别硬凑。",
      );
    }
  }

  // ---------- 9. 文字颜 / emoji（每轮都带，但只在总开关打开时才说话） ----------
  // 总开关关着就一个字都不注入 —— 默认不干预，让她按人格本来怎么说话就怎么说话。
  if (proactive?.textStyleEnabled === true) {
    const pct = (r) => Math.round(r * 100);
    const freq = (r) => Math.max(1, Math.round(1 / r));
    const pick = (raw, dflt) => {
      const n = Number(raw);
      return Number.isFinite(n) ? Math.max(0, Math.min(1, n)) : dflt;
    };

    const kRate = pick(proactive?.kaomojiRate, 0.2);
    if (kRate <= 0) {
      blocks.push("文字颜：现在不用，别加 (￣▽￣) 这类颜文字。");
    } else {
      blocks.push(
        `文字颜：大约每 ${freq(kRate)} 句带一个（${pct(kRate)}%）。放在句尾当表情，一次一个，别堆好几个。`
        + `这轮给你几个手感参考：${pickExamples(KAOMOJI_POOL, 3).join("  ")}`
        + "。颜文字是自己按情绪组合出来的，不是只有这些 —— 别老用同一个，也别照抄。",
      );
    }

    const eRate = pick(proactive?.emojiRate, 0.2);
    if (eRate <= 0) {
      blocks.push("emoji：现在不用，别加 😊 这类 Unicode 表情。");
    } else {
      blocks.push(
        `emoji：大约每 ${freq(eRate)} 句带一个（${pct(eRate)}%）。一句最多一个，别连串。`
        + `这轮给你几个参考：${pickExamples(EMOJI_POOL, 5).join("")}`
        + "。按当时情绪自己挑，不是只有这些能用 —— 别总用同样的几个。",
      );
    }
  }

  if (!blocks.length) return { text: "", hashes };
  return {
    text: '<dsh-remembers source="state">\n' + blocks.join("\n") + "\n</dsh-remembers>",
    hashes,
  };
}
