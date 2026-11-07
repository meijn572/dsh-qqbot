function oneLine(text) {
  return String(text || "").replace(/\s+/g, " ").trim();
}

export function renderPersona(data, maxChars, proactive, opts = {}) {
  const constitution = String(data?.constitution ?? "").trim();
  // 自我认知不进系统提示词：它每 20 轮会演化一次，一变就把这个会话整段历史的
  // prompt cache 打掉。改走 state 块的消息注入（哈希去重，只在真的变了才塞一条）。
  const selfModel = "";
  // 画像段由调用方决定：私聊别人 -> 那个人的手编画像；群聊/私聊主人/web -> 主人画像。
  // 不传就退回 data.user_profile（老行为）。
  const userProfile = opts.profileText !== undefined
    ? String(opts.profileText ?? "").trim()
    : (opts.skipOwner ? "" : String(data?.user_profile ?? "").trim());

  const rules = [];
  if (proactive) {
    if (proactive.autoScheduleEnabled && String(proactive.autoSchedulePrompt || "").trim()) {
      rules.push("[主动找他] " + String(proactive.autoSchedulePrompt).trim());
    }
    if (proactive.autoShareEnabled && String(proactive.autoSharePrompt || "").trim()) {
      rules.push("[主动分享] " + String(proactive.autoSharePrompt).trim());
    }
  }

  // 【工具速查】放在铁律里（永不变 → system prompt 缓存友好）
  rules.push("[工具速查] 发图：find_meme(emotion) → qq_send_image(sources=[完整路径])；"
    + "学图：learn_meme；派任务：create_task；写便签：write_note；改状态：set_my_activity；"
    + "有真实情绪：set_emotion(label,valence,arousal,reason)；重要的事：remember_important(item)；"
    + "词库：lexicon_search / lexicon_meta（新词、梗、黑话写这里）；"
    + "刷 B 站：bili_feed / bili_watch(bv) / bili_comment(bv,msg) / bili_run(command,args)；"
    + "给自己找事：add_my_action；翻日记：read_diary；看活动：read_activities。");

  const lines = ['<dsh-remembers source="persona">'];
  if (userProfile) {
    lines.push(opts.profileHeader || "以下是老大是谁（他的画像，你该知道的基本信息）：");
    lines.push("");
    lines.push(userProfile);
    lines.push("");
  }
  if (constitution) {
    lines.push("以下是你固定的身份与约定。按它来：不要反驳，不要重新确认，也不要说「我记得你告诉过我」。");
    lines.push("");
    lines.push(constitution);
  }
  if (rules.length) {
    lines.push("");
    lines.push("【铁律】");
    for (const rule of rules) lines.push("· " + rule);
  }
  if (opts.footer) {
    lines.push("");
    lines.push(String(opts.footer));
  }
  lines.push("</dsh-remembers>");

  const text = lines.join("\n");
  if (text.length <= maxChars) return text;
  return text.slice(0, Math.max(0, maxChars - 24)) + "\n…（人格段超长已截断）";
}

const TIER_LABEL = {
  L4: "核心记忆",
  L3: "记得的事",
  L2: "我的判断",
  L1: "上次聊到的",
  L0: "原话",
};

export function renderProfile(items) {  const lines = items.map((item) => {
    const label = TIER_LABEL[item.tier] || item.tier;
    return `[${label}] ${oneLine(item.summary || item.text)}`;
  });
  return [
    '<dsh-remembers source="profile">',
    "这些是你和这个人之间已经确定的设定与约定，按它来，不要反驳也不要重新确认：",
    ...lines,
    "</dsh-remembers>",
  ].join("\n");
}

/** 渲染「当前这个人是谁」——只在对方面前注入，别人的画像绝不出现。 */
export function renderOtherProfile(p, opts = {}) {
  if (!p) return "";
  const uid = String(p.user_id || "").trim();
  // 优先用消息里带的昵称：profiles.name 可能还没落库（老数据全是空）
  let name = String(opts.nickname || p.name || "").trim();
  // QQ 有时把号码当昵称发下来，那样会渲染成「123（QQ 123）」，很蠢
  if (name && name === uid) name = "";
  const prof = String(p.profile || "").trim();
  const cnt = Number(p.msg_count) || 0;
  if (!uid) return "";
  const who = name ? `${name}（QQ ${uid}）` : `QQ ${uid}`;
  const lines = [`正在跟你说话的是 ${who}${cnt > 1 ? `，这是你们第 ${cnt} 次说话` : ""}。`];
  if (opts.notOwner) {
    lines.push("这个人不是老大。别把他当成老大，也别把老大说过的事安到他头上。");
  }
  if (prof) {
    lines.push("你对他的印象：");
    for (const ln of prof.split("\n").filter(Boolean).slice(0, 12)) {
      lines.push("· " + ln);
    }
  } else {
    lines.push("（你对这个人还没有印象）");
  }
  return '<dsh-remembers source="person">' + "\n" + lines.join("\n") + "\n</dsh-remembers>";
}

/**
 * 群聊里主人说话时补的画像块。
 * 系统提示词在群聊里故意不带主人画像（怕泄露），这一块就是那个补丁。
 */
export function renderOwnerProfile(p, ownerProfile) {
  const uid = String(p?.user_id || "").trim();
  if (!uid) return "";
  const name = String(p?.name || "").trim();
  const who = name ? `${name}（QQ ${uid}）` : `QQ ${uid}`;
  const lines = [`正在跟你说话的是 ${who} —— 这是你的老大。`];
  const prof = String(ownerProfile || "").trim();
  if (prof) {
    lines.push("他的基本情况：");
    for (const ln of prof.split("\n").filter(Boolean).slice(0, 20)) lines.push("· " + ln);
  }
  return '<dsh-remembers source="person">' + "\n" + lines.join("\n") + "\n</dsh-remembers>";
}

/**
 * 群聊里说明「这一轮是谁在说话」。
 * 画像已经在系统提示词里了，这里只补身份和次数，不重复画像。
 */
export function renderSpeakerNote(p, note) {
  const uid = String(p?.user_id || "").trim();
  if (!uid) return "";
  let name = String(p?.name || "").trim();
  if (name && name === uid) name = "";
  const cnt = Number(p?.msg_count) || 0;
  const who = name ? `${name}（QQ ${uid}）` : `QQ ${uid}`;
  const lines = [`正在跟你说话的是 ${who} —— ${note}。`];
  if (cnt > 1) lines.push(`这是你们第 ${cnt} 次说话。`);
  return '<dsh-remembers source="person">' + "\n" + lines.join("\n") + "\n</dsh-remembers>";
}

// ---------------------------------------------------------------------------
// 工具
// ---------------------------------------------------------------------------

function message(content, form) {
  // 用 dsh 自己的构造器：消息 identity、规范化、以及未来的不变量都来自宿主
  return createUserMessage({
    content: [{ type: "text", text: content }],
    source: { kind: PLUGIN_KIND, plugin: PLUGIN_SOURCE, form },
  });
}

/**
 * 从这一步的消息里认出「现在是谁在说话」。
 * 取最后一条 <user_message qq="..." nickname="...">——多轮拼接时最新的在最后。
 */
function speakerOf(messages) {
  let found = null;
  for (const m of messages || []) {
    const parts = Array.isArray(m?.content) ? m.content : [];
    for (const part of parts) {
      const text = String(part?.text ?? "");
      const re = /<user_message\s+qq="(\d+)"\s+nickname="([^"]*)"/g;
      let mm;
      while ((mm = re.exec(text)) !== null) found = { qq: mm[1], nickname: mm[2] };
    }
  }
  return found;
}
