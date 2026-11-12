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

export function renderState(state, prev, proactive, thinkCn) {
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
  // 状态块文本由服务端 render.py 给，拿不到才自己拼
  const rnd = state.render || {};
  blocks.push(rnd.time || `现在是 ${dateStr}（${phase}）。`);

  // ---------- 2. 困意（按档位变） ----------
  const sleepy = rnd.sleepy !== undefined
    ? String(rnd.sleepy || "")
    : (hh >= 23 || hh < 6 ? "你现在困得眼睛都睁不开了，回话短一点、慢一点，别硬撑。"
       : hh >= 21 ? "有点困了，说话懒一点。" : "");
  if (sleepy) blocks.push(sleepy);

  // ---------- 3.5 还没完的事（全部 open，只给标题和状态） ----------
  const openThreads = Array.isArray(state.open_threads) ? state.open_threads : [];
  const threadLines = openThreads.slice(0, 8).map((t) => {
    const title = String(t.title || "").trim();
    if (!title) return "";
    return `- ${title}`;
  }).filter(Boolean);
  const threadHash = hash(threadLines.join("\n"));
  if (threadLines.length && hashes.threads !== threadHash) {
    hashes.threads = threadHash;
    blocks.push(rnd.open_threads || ("【还没完的事】\n" + threadLines.join("\n")));
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

  // ---------- 7. 关系状态（变了才加） ----------
  const rel = state.relationship || {};
  if (rel.summary) {
    const stText = rnd.relationship || `最近我们的关系：${rel.summary}`;
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
