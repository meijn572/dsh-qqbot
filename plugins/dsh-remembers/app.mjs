/**
 * dsh-remembers —— 给情感陪伴场景做的「人格 + 记忆」二合一插件。
 *
 * 做四件事（都很薄，重活在 companion-memory 服务里）：
 *   1. 人格设定走 systemPrompt 独立段（宪法区 + 自我认知区，每轮必带）
 *   2. 启动时注入 L4 关系约定（agent.inject）
 *   3. 每步检索并注入相关记忆（agent/pre-step 追加消息）
 *   4. 每轮把原话写进 L0（不抽摘要，保证「说过的话不丢」）
 *
 * 人格为什么要走 system prompt，而记忆不走：
 *   - 人格是「一直成立的前提」，每轮都该在，且权重最高的位置才稳得住。
 *   - 记忆是「想起什么算什么」，按需追加，空的时候就不该出现任何块。
 *   代价是 complete:true 的预设会把 system prompt 整段换成自己的，那时人格段
 *   会静默消失——所以 L4 走 agent.inject 的那条路仍然保留，人格段是加厚的，
 *   不是替换掉兜底的。
 *
 * 刻意不做的事：
 *   - 检索结果为空时不注入任何东西。空就是真的没印象，模型不该看到空块还以为有记忆。
 *   - 人格段为空时也完全不注册内容，等于没装——不打扰任何现有部署。
 */

import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join as pathJoin } from "node:path";

import { createAssistantMessage, createUserMessage } from "@deepseek-ai/dsh-llm";

import { MemoryClient } from "./client.mjs";
import { PLUGIN_VERSION, resolveConfig } from "./config.mjs";
import { loadRecall } from "./hooks/recall.mjs";
import { recordTurn } from "./hooks/turn_end.mjs";
import { renderState } from "./hooks/state.mjs";
import { renderOtherProfile, renderOwnerProfile, renderPersona, renderSpeakerNote } from "./hooks/persona.mjs";
import { registerEmotionTool as registerEmotionToolModule } from "./tools/emotion.mjs";
import { registerImportantTool as registerImportantToolModule } from "./tools/important.mjs";
import { registerMemeTools as registerMemeToolsModule } from "./tools/memes.mjs";
import { registerCompanionTools as registerCompanionToolsModule } from "./tools/companion.mjs";
import { registerActivityTool as registerActivityToolModule } from "./tools/activity.mjs";
import { registerPersonaTool as registerPersonaToolModule } from "./tools/persona.mjs";

export const name = "dsh-remembers";
export const inject = ["agents", "sessions"];

const PLUGIN_SOURCE = "dsh-remembers";
const PLUGIN_KIND = `plugin:${PLUGIN_SOURCE}`;

/** 人格段在 systemPrompt 注册表里的名字。带前缀，避免和别人的 persona 段撞名。 */
const PERSONA_SECTION = "remembers:persona";

export function apply(ctx, input = {}) {
  const config = resolveConfig(input);
  console.log("[dsh-remembers] config hooks=" + String(config.hooks));
  const logger = ctx.logger;
  const client = new MemoryClient(
    { ...config, logger: config.logRequests ? logger : null },
    config.logRequests ? logger : null,
  );

  const log = (stage, data) => logger?.debug?.(`[dsh-remembers] ${stage} ${JSON.stringify(data)}`);

/** 拉运行时状态（心情/亲密度/勿扰），服务不可用时返回 null，绝不阻塞对话。 */
async function fetchState() {
  try {
    const res = await fetch(config.endpoint + "/state", { signal: AbortSignal.timeout(3000) });
    if (!res.ok) return null;
    return await res.json();
  }
  catch {
    return null;
  }
}

/** 拉主动消息配置（主动性开关 + 提示词），失败返回 null。 */
async function fetchProactive() {
  try {
    const res = await fetch(config.endpoint + "/proactive", { signal: AbortSignal.timeout(3000) });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

/** 社交亲和度：每次互动 +1（fire-and-forget）。 */
async function bumpAffinity() {
  try {
    await fetch(config.endpoint + "/affinity", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: "owner", delta: 1 }),
      signal: AbortSignal.timeout(3000),
    });
  }
  catch {
    /* 忽略 */
  }
}

/** 学说话：把用户短消息记成口头禅候选（fire-and-forget）。 */
async function recordSlang(text) {
  const msg = String(text || "").trim();
  if (msg.length < 2 || msg.length > 12) return;
  try {
    await fetch(config.endpoint + "/slang", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ phrase: msg }),
      signal: AbortSignal.timeout(3000),
    });
  }
  catch {
    /* 忽略 */
  }
}

/** 记一条活动日志（fire-and-forget）。 */
async function logActivity(kind, detail) {
  try {
    await fetch(config.endpoint + "/activity", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kind, detail: String(detail || "").slice(0, 120) }),
      signal: AbortSignal.timeout(3000),
    });
  }
  catch {
    /* 日志失败不影响对话 */
  }
}

/** 人设演化：让服务端从这段对话生一句「我发现自己……」（fire-and-forget）。 */
async function requestEvolve(userText, assistantText) {
  try {
    await fetch(config.endpoint + "/evolve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_text: userText, assistant_text: assistantText }),
      signal: AbortSignal.timeout(30000),
    });
  }
  catch {
    /* 演化失败不影响对话 */
  }
}

/** 情绪传染：老大情绪影响她的 valence/arousal（fire-and-forget）。 */
async function bumpEmotion(dv, da) {
  try {
    await fetch(config.endpoint + "/state", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ bump_valence: dv, bump_arousal: da }),
      signal: AbortSignal.timeout(3000),
    });
  }
  catch {
    /* 忽略 */
  }
}

/** 记一次「真实对话」，给唤醒做冷却用。 */
async function bumpChat() {
  try {
    await fetch(config.endpoint + "/state", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ bump_chat: 1 }),
      signal: AbortSignal.timeout(3000),
    });
  }
  catch {
    /* 忽略 */
  }
}

/** 真实互动涨亲密度（fire-and-forget），默认 +0.2 一轮。 */
async function bumpIntimacy(delta = 1.0) {
  try {
    await fetch(config.endpoint + "/state", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ bump: delta }),
      signal: AbortSignal.timeout(3000),
    });
  }
  catch {
    /* 状态服务不可用不影响对话 */
  }
}

/**
 * 把状态渲染成提示词段。
 *
 * 设计原则（2026-10-25 重构）：
 *   - 只在「变了」的时候注入；静态内容走工具查库
 *   - 时间每轮都带（她需要时间感）
 *   - 心情/在干嘛/B站见闻/阶段：跟上次比，变了才加
 *   - 学会的词 / 日记便签 / 工具速查：不在这里
 *
 * @param state  /state 返回的对象
 * @param prev   上次注入时的哈希表
 * @returns {{ text: string, hashes: object }}
 */
/**
 * 颜文字 / emoji 示例池。
 * 为什么要随机抽：示例给固定几个的话，模型会锚死在上面 —— 线上实测给 3 个颜文字，
 * 她连着几句都在用其中那一个。每轮从大池子里随机抽几个，命中面就散开了。
 */
const soft = (key) => {
    try {
      const value = ctx[key];
      if (value !== undefined) return value;
    } catch {
      // 未 inject 的宿主会抛错，视为服务不存在，走下面的兜底
    }
    try {
      return typeof ctx.get === "function" ? ctx.get(key) : undefined;
    } catch {
      return undefined;
    }
  };
  const systemPrompt = soft("systemPrompt");
  const tools = soft("tools");
  /** 绑定过 this 的服务方法；服务不在或没有这个方法时返回 null。 */
  const methodOf = (service, name) => (
    service && typeof service[name] === "function" ? service[name].bind(service) : null
  );
  const registerSection = methodOf(systemPrompt, "section");
  const registerTool = methodOf(tools, "register");

  // -------------------------------------------------------------------------
  // 0. 人格设定：宪法区（只有设置页能写）+ 自我认知区（AI 能写）
  // -------------------------------------------------------------------------
  // 缓存一份纯文本。systemPrompt 的 section provider 是同步的，每轮现发一个
  // HTTP 请求会把提示词组装拖死。所以「异步刷新 + 同步读缓存」：
  //   刷新时机 = 启动 / 每 personaRefreshMs / agent 创建时（节流后）
  //   失败时保留上一份好的：宁可人格旧一点，也不能让这轮没有人格。
  const persona = {
    /** /persona 的原始数据。系统提示词按会话现拼，画像段由 buildPersonaText 决定。 */
    data: null,
    /** proactive 配置也缓存一份，渲染时要 */
    proactive: null,
    /** 主人手编画像（= persona.user_profile）。主人画像百分百在场。 */
    ownerManual: "",
    /**
     * user_id -> { name, manual, is_owner }
     * 只装「手编画像」。AI 自动累积的那份（profiles.profile）每抽到一条 L2 就变，
     * 放进系统提示词会把 prompt cache 一直打穿，所以它只走 person 消息块。
     */
    manualByUser: {},
    /** 自我认知原文。走 state 块注入，不在这里进系统提示词。 */
    selfModel: "",
    /** L4 关系/规矩：进 system prompt，不再走 recall。 */
    l4: [],
    at: 0,         // 最近一次成功刷新（ms）
    triedAt: 0,    // 最近一次尝试（含失败），用于节流
    error: null,
  };

  async function refreshPersona(force = false) {
    if (!config.personaEnabled || !client.enabled || !client.profiles) return "";
    const now = Date.now();
    if (!force && now - persona.triedAt < config.personaRefreshMs) return "";
    persona.triedAt = now;
    try {
      // 一次拉齐：人格 + 主动配置 + 所有人的手编画像。
      // profiles 是给系统提示词按会话挑人用的，所以整份缓存在内存里（同步可读）。
      const [data, proactive, allProfiles, l4Items] = await Promise.all([
        client.persona(), fetchProactive(), client.profiles(), client.profile(config.profileSubject || null),
      ]);
      if (!data) return persona.data ? renderPersona(persona.data, config.personaMaxChars, persona.proactive, { l4: persona.l4 }) : "";
      // 只渲染人格。state 走 pre-step 注入，不进 system prompt
      //（system prompt 是最顶层前缀，一变整段历史缓存全失效）
      persona.data = data;
      persona.proactive = proactive;
      persona.l4 = Array.isArray(l4Items) ? l4Items : [];
      persona.ownerManual = String(data?.user_profile ?? "").trim();
      persona.selfModel = String(data?.self_model ?? "").trim();

      // 手编画像整份缓存：只有 manual_profile 进系统提示词，profile（自动累积）不进
      const map = {};
      for (const p of (allProfiles || [])) {
        const uid = String(p?.user_id ?? "").trim();
        if (!uid) continue;
        map[uid] = {
          name: String(p?.name ?? "").trim(),
          manual: String(p?.manual_profile ?? "").trim(),
          is_owner: Boolean(p?.is_owner),
        };
      }
      persona.manualByUser = map;
      const next = "";
      log("persona_refreshed", {
        constitution: Boolean(String(data.constitution || "").trim()),
        selfModel: Boolean(String(data.self_model || "").trim()),
        profiles: Object.keys(map).length,
        manualProfiles: Object.values(map).filter((x) => x.manual).length,
      });
      persona.at = now;
      persona.error = null;
    } catch (error) {
      persona.error = String(error?.message ?? error);
      log("persona_error", { error: persona.error });
    }
    return "";
  }

  // 人格段是否真的接管了 L4 的「自我」条目。空人格段 = 不接管 = 老行为。
  
  // per-session 状态
  const states = new Map();

  function stateFor(session) {
    const id = String(session?.id ?? "unknown");
    let state = states.get(id);
    if (!state) {
      state = {
        id,
        injectedHashes: new Set(),   // 去重：同一块不重复注入
        outboundSeen: new Set(),     // 已补进上下文的桥接主动消息
        turns: 0,                    // 已结束的轮数（每 50 轮重注入画像）
        turnUser: "",
        turnAssistant: "",
        internalTurn: false,
        recentUser: [],           // 最近几条用户输入，给惊讶度门控做参照
        episodeTurns: [],         // 攒着等压成 episode 的轮次
        episodeStartedAt: 0,      // 这一段从什么时候开始（ms）
        writes: Promise.resolve(),
      };
      states.set(id, state);
    }
    return state;
  }

  const skipped = (session) => (
    config.skipSubagentSessions && session?.header?.origin === "subagent"
  );

  // -------------------------------------------------------------------------
  // 1. 启动注入 L4
  // -------------------------------------------------------------------------
  async function injectProfile(agent) {
    if (!agent || skipped(agent.session)) return false;
    // L4 关系记忆不再由 profile 块注入；这里只负责新会话强制刷新人格缓存。
    await refreshPersona(true);
    return false;
  }

  ctx.on("agent/created", async ({ agent, source }) => {
    if (source === undefined) return undefined;
    try {
      await injectProfile(agent);
    } catch (error) {
      log("profile_error", { error: String(error?.message ?? error) });
    }
    return undefined;
  });

  ctx.on("agent/session-start", async ({ agent }) => {
    try {
      await injectProfile(agent);
    } catch (error) {
      log("profile_error", { error: String(error?.message ?? error) });
    }
  });

  // -------------------------------------------------------------------------
  // 2. 每步召回
  // -------------------------------------------------------------------------
  ctx.on("agent/pre-step", async ({ agent, signal }, next) => {
    const decision = await next();
    if (decision.kind !== "enter" || signal?.aborted) return decision;
    if (skipped(agent?.session)) return decision;
    const extra = [];
    const beforeUser = [];
    const finish = () => {
      if (!beforeUser.length && !extra.length) return decision;
      const messages = [...decision.messages];
      if (beforeUser.length) {
        let at = messages.length;
        for (let i = messages.length - 1; i >= 0; i -= 1) {
          if (messages[i]?.role === "user") { at = i; break; }
        }
        messages.splice(at, 0, ...beforeUser);
      }
      if (extra.length) messages.push(...extra);
      return { kind: "enter", messages };
    };

    // 记住这一步是谁在说话。turn/end 写记忆时要带昵称，不然 profiles.name 永远是空。
    try {
      const spNow = speakerOf(decision.messages);
      if (spNow && spNow.qq) stateFor(agent.session).nickname = spNow.nickname;
    } catch { /* 忽略：拿不到昵称不影响对话 */ }

    // 桥接主动发出的消息（主动说话/报告/B 站分享）补成 assistant 消息，
    // 放在当前 user 消息之前，避免被误读成主人说的话。
    try {
      const scopeOf = scopeFromSession(agent.session.id);
      if (scopeOf.scope && scopeOf.scope !== "global") {
        const items = await client.outbound(scopeOf.scope, 5);
        const st = stateFor(agent.session);
        for (const item of [...(items || [])].reverse()) {
          const id = String(item?.id ?? "");
          if (!id || st.outboundSeen.has(id)) continue;
          const text = String(item?.text || "").replace(/^我：/, "").trim();
          if (!text) continue;
          st.outboundSeen.add(id);
          beforeUser.push(createAssistantMessage({
            content: [{ type: "text", text }],
            source: { kind: "host:bridge-outbound", plugin: PLUGIN_SOURCE, form: "outbound" },
          }));
        }
      }
    } catch (error) {
      log("outbound_error", { error: String(error?.message ?? error) });
    }

    // ---- 多人画像：只注入「当前这个说话的人」，别人的绝不出现 ----
    try {
      const scopeOf = scopeFromSession(agent.session.id);
      if (scopeOf.userId) {
        const p = await client.profileOf(scopeOf.userId);
        // 系统提示词里放的：群聊 / 私聊主人 / web 无 QQ -> 主人画像；
        // 私聊别人 -> 那个人手编的画像。
        // 所以这里只补「系统提示词里没有的那部分」，绝不重复整段画像。
        const owner = Boolean(p && p.is_owner);
        const inGroup = String(agent?.session?.id ?? "").includes("-group-");
        // 消息里带着真实昵称（<user_message qq nickname>），比 profiles.name 新
        const sp = speakerOf(decision.messages);
        const nick = sp && sp.qq === scopeOf.userId ? sp.nickname : "";
        let block = "";
        if (inGroup) {
          // 群里发言人一直在换，系统提示词固定写的是主人 —— 必须逐轮说明是谁在说话，
          // 否则她会把每个群友都当成老大。
          block = owner
            ? renderSpeakerNote(p, "这是你的老大")
            : renderOtherProfile(p, { nickname: nick, notOwner: true });
        } else if (!owner) {
          // 私聊别人：系统提示词里有主人画像打底，这里必须说清他不是老大
          block = renderOtherProfile(p, { nickname: nick, notOwner: true });
        }
        // 私聊主人：系统提示词已经带全了，跳过
        if (block) {
          // 群聊和私聊别人都不做内容去重：发言人天天在换，
          // 「现在是谁在说话」这条一旦省掉，她就会认错人。
          const st = stateFor(agent.session);
          log("person_injected", { session: st.id, userId: scopeOf.userId, nick, chars: block.length });
          extra.push(message(block, "person"));
        }
      }
    } catch (error) {
      log("person_error", { error: String(error?.message ?? error) });
    }

    try {
      const scopeOf = scopeFromSession(agent.session.id);
      // 没登记映射的会话（维护/面板/测试）不注入召回，避免把私人记忆带进 global
      if (scopeOf.scope === "global" && !String(agent.session.id).includes("onebot-")) return finish();
      if (config.hooks) {
        const recall = await loadRecall(client, {
          request_id: globalThis.crypto?.randomUUID?.() || String(Date.now()),
          session: agent.session.id,
          scope: scopeOf.scope,
          messages: decision.messages,
        });
        if (!recall) return finish();
        if (signal?.aborted) return finish();
        const st = stateFor(agent.session);
        const digest = hash(recall);
        if (st.injectedHashes.has(digest)) return finish();
        st.injectedHashes.add(digest);
        log("recall_injected", { session: st.id, chars: recall.length, path: "hook" });
        extra.push(message(recall, "recall"));
        return finish();
      }
    } catch (error) {
      // 记忆召回失败绝不能挡住这一步
      log("recall_error", { error: String(error?.message ?? error) });
      return finish();
    }
  }, { prepend: true });

  // -------------------------------------------------------------------------
  // 2.5 状态注入：走消息，不进 system prompt（保护前缀缓存）
  //     state 没变就不塞（哈希去重），避免历史无限增长。
  // -------------------------------------------------------------------------
  ctx.on("agent/pre-step", async ({ agent, signal }, next) => {
    const decision = await next();
    if (decision.kind !== "enter" || signal?.aborted) return decision;
    if (skipped(agent?.session)) return decision;
    try {
      const st = await fetchState();
      const st2 = stateFor(agent.session);
      const r = renderState(st, st2.stateHashes || {}, persona.selfModel || "", persona.proactive,
        Boolean(persona.data?.identity && (() => { try { return JSON.parse(persona.data.identity).think_cn; } catch { return false; } })()));
      st2.stateHashes = r.hashes;
      if (!r.text) return decision;      // 这轮什么都没变、连时间都没有 → 不塞
      log("state_injected", { session: st2.id, chars: r.text.length });
      return { kind: "enter", messages: [...decision.messages, message(r.text, "state")] };
    } catch (error) {
      log("state_error", { error: String(error?.message ?? error) });
      return decision;
    }
  }, { prepend: true });

  // -------------------------------------------------------------------------
  // 3. 捕获原话 → L0
  // -------------------------------------------------------------------------
  ctx.on("session/event", (session, event) => {
    console.log("[dsh-remembers-debug] session/event session=" + String(session?.id) + " type=" + String(event?.type ?? event?.kind));
    // QQ 会话的 turn 结束走 session/event 的 type="turn/end"，不是独立钩子。
    // 必须在 early return 之前处理：turn/end 事件没有 message。
    if (event?.type === "turn/end") {
      try {
        flushTurn(session);
      }
      catch (error) {
        console.log("[dsh-remembers-debug] flushTurn error: " + String(error?.message ?? error));
      }
      return;
    }
    // 2026-10-27：原来这里无条件把整条消息（含 reasoning 全文、工具参数）打进
    // journal —— 24 小时 500 多行、约 300KB，既撑爆日志也泄露隐私。
    // 要排查再开 logRequests（CMEM_LOG=1）。
    if (config.logRequests && (event?.type === "user/message" || event?.type === "assistant/message")) {
      try {
        console.log("[dsh-remembers-debug] msgdata=" + JSON.stringify(event.data).slice(0, 600));
      }
      catch { /* ignore */ }
    }
    if (!config.captureRaw || skipped(session)) return;
    const state = stateFor(session);
    const message = eventMessage(event);
    if (!message) return;
    if (isSynthetic(message)) return;   // 别的插件注入的块、time-context 都不要

    const text = extractText(message);
    if (!text) return;
    if (message.role === "assistant") {
      state.turnAssistant = clip(`${state.turnAssistant}\n${text}`.trim(), 800);
    } else {
      if (/(内部维护|内部记录|内部探索|系统提醒|没人说话|抽到：|只输出\s*JSON)/.test(text)) {
        state.internalTurn = true;
      }
      state.turnUser = clip(`${state.turnUser}\n${text}`.trim(), 800);
    }
  });

  function flushTurn(session) {
    console.log("[dsh-remembers-debug] turn/end session=" + String(session?.id) + " skipped=" + skipped(session));
    if (skipped(session)) return;
    const state = stateFor(session);
    const scopeOf = scopeFromSession(state.id);   // 谁说的 / 在哪个场景
    // 桥接没登记的会话 = 内部维护/测试/DSH 面板，不写记忆
    if (scopeOf.scope === "global" && !String(state.id).startsWith("onebot-")) {
      state.turnUser = "";
      state.turnAssistant = "";
      state.internalTurn = false;
      return;
    }
    state.turns = (state.turns || 0) + 1;
    const user = state.turnUser.trim();
    const assistant = state.turnAssistant.trim();
    if (state.internalTurn) {
      state.internalTurn = false;
      state.turnUser = "";
      state.turnAssistant = "";
      return;
    }
    const nickname = String(state.nickname || "").trim();
    // 剥掉系统唤醒片段，只留真实内容
    const keptUser = cleanNudge(user);
    state.turnUser = "";
    state.turnAssistant = "";
    console.log("[dsh-remembers-debug] flush cfg extract=" + config.extract + " captureRaw=" + config.captureRaw + " userLen=" + user.length + " asstLen=" + assistant.length);
    // 每 20 轮让她演化一次自我认知（早期学得快一点）
    if (state.turns % 20 === 0 && user && assistant) {
      void requestEvolve(user, assistant);
    }
    // 亲密度：只有「老大真的说话」才涨（唤醒剥完就没内容了，不会走到这）
    if (keptUser && assistant) {
      void bumpIntimacy(1.0);
      void bumpChat();
    }
    // 情感层：旧的 /emotion auto 只看当前状态值，标签很粗；改由抽取模型给 semantic emotion
    // if (keptUser) {
    //   void (async () => {
    //     try {
    //       await fetch(config.endpoint + "/emotion", {
    //         method: "POST",
    //         headers: { "Content-Type": "application/json" },
    //         body: JSON.stringify({ auto: true, trigger: keptUser.slice(0, 120) }),
    //         signal: AbortSignal.timeout(4000),
    //       });
    //     }
    //     catch { /* 忽略 */ }
    //   })();
    // }
    // 记一条聊天活动。
    // 门控用 keptUser（剥掉系统唤醒之后的剩余），不是 user：
    // 唤醒轮里 user 是「（系统提醒：……）」，那是系统说的，不是用户说的 ——
    // 之前把它记成 chat、学进口头禅、还触发情绪传染，全是假的。
    if (keptUser) {
      void logActivity("chat", keptUser.slice(0, 80));
      // 整句用户消息不是黑话；群黑话由桥接的表负责，这里只保留 learn_word 主动教学
      // void recordSlang(keptUser);
      void bumpAffinity();
      void scanSeen();
      // 情绪传染：他难过她就跟着沉，他开心她就跟着亮
      if (/(累|烦|难过|难受|不想|沮丧|焦虑|崩溃|哭)/.test(keptUser)) {
        void bumpEmotion(-0.15, -0.05);
      } else if (/(开心|高兴|好耶|爽|棒|喜欢|哈哈|不错)/.test(keptUser)) {
        void bumpEmotion(0.15, 0.05);
      }
    }

    // 这一轮之前的几条用户输入，作为惊讶度门控的参照
    const context = state.recentUser.slice(-6).join("\n");
    if (user) {
      state.recentUser.push(user);
      if (state.recentUser.length > 8) state.recentUser.shift();
    }

    if (!keptUser || keptUser.length < 2) {
      log("nudge_skipped", { session: state.id, rawLen: user.length });
      return;
    }
    const merged = [`主人：${keptUser}`, assistant && `我：${assistant}`]
      .filter(Boolean).join("\n");

    // ---- 门控 1：惊讶度决定这一轮值不值得进 L0 ----
    // 寒暄（"嗯"、"好的"）在服务端被硬否决，不占记忆。
    if (config.hooks && config.captureRaw && merged.length >= config.captureMinChars) {
      state.writes = state.writes
        .then(async () => {
          const res = await recordTurn(client, {
            request_id: globalThis.crypto?.randomUUID?.() || String(Date.now()),
            session: state.id,
            scope: scopeOf.scope,
            user: keptUser,
            assistant,
            context,
            user_id: scopeOf.userId,
            nickname,
          });
          if (res?.stored) {
            log("raw_saved", { session: state.id, id: res.id, surprisal: res.surprisal, path: "hook" });
          } else {
            log("surprisal_skipped", { session: state.id, reason: res?.reason, path: "hook" });
          }
        })
        .catch((error) => log("raw_error", { error: String(error?.message ?? error), path: "hook" }));
    }

    // ---- 门控 2：LLM 抽取 + 逐条判定，写结构记忆 ----
    // 两次 LLM 调用，几十秒级 —— fire-and-forget，绝不阻塞对话。
    if (config.extract && keptUser.length >= config.captureMinChars) {
      client.extract({
        userText: keptUser,
        assistantText: assistant,
        user_id: scopeOf.userId,
        scope: scopeOf.scope,
        nickname,
      })
        .then((res) => {
          if (res?.ok) {
            log("extracted", { session: state.id, facts: res.facts, applied: res.applied });
          } else {
            log("extract_degraded", { session: state.id, reason: res?.degraded, error: res?.error });
          }
        })
        .catch((error) => log("extract_error", { error: String(error?.message ?? error) }));
    }

    // ---- 门控 3：episode 缓冲 ----
    // 跟上面两个门控是独立的事：那两个决定「存不存原话 / 抽不抽事实」，
    // 这个决定「要不要把这一段压成一条前情」。上下文被 compaction 压扁之后，
    // 只有它留下的东西还能告诉未来的她「这段时间我们是怎么过来的」。
    trackEpisode(state, user, assistant);
  }


  // -------------------------------------------------------------------------
  // episode：攒够一段就压成 L3 事件
  // -------------------------------------------------------------------------
  // 为什么不用内核的 compaction 摘要：那份摘要是 DSH 自己算的，用完就扔，
  // 而且格式面向"接着聊"，不是"记住"。这里自己留一份，格式面向以后回想。
  // 触发条件二选一：攒够 episodeEveryTurns 轮，或者这一段聊了超过 episodeMaxMinutes。
  function trackEpisode(state, user, assistant) {
    if (!config.episodeEnabled || !client.enabled) return;
    if (!user) return;

    if (!state.episodeStartedAt) state.episodeStartedAt = Date.now();
    state.episodeTurns.push({ user: clip(user, 800), assistant: clip(assistant, 800) });
    if (state.episodeTurns.length > 400) state.episodeTurns.shift();   // 硬上限，防内存涨

    const minutes = (Date.now() - state.episodeStartedAt) / 60000;
    const enough = state.episodeTurns.length >= config.episodeEveryTurns;
    const overdue = minutes >= config.episodeMaxMinutes && state.episodeTurns.length >= 3;
    if (!enough && !overdue) return;

    flushEpisode(state);
  }

  function flushEpisode(state) {
    const turns = state.episodeTurns;
    const startedAt = state.episodeStartedAt || Date.now();
    state.episodeTurns = [];
    state.episodeStartedAt = 0;
    if (turns.length === 0) return;

    // 必须用本地时间。以前这里用 toISOString()，那是 UTC —— 服务器 UTC+8，
    // 下午 14:51 传过去变成 06:51，LLM 就把它写成「凌晨」。已经错过三条 episode。
    const fmt = (ms) => {
      const d = new Date(ms);
      const p = (n) => String(n).padStart(2, "0");
      return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
    };
    // fire-and-forget：压一段要几十秒，绝不能挂在 turn/end 上
    client.episode({ turns, window: `${fmt(startedAt)} ~ ${fmt(Date.now())}` })
      .then((res) => {
        if (res?.ok) {
          log("episode_saved", { session: state.id, id: res.id, turns: turns.length, chars: res.chars });
        } else {
          // 服务端没配 LLM 是最常见的原因，这不是错误，只是这条链路没开
          log("episode_degraded", { session: state.id, reason: res?.degraded || "unavailable" });
        }
      })
      .catch((error) => log("episode_error", { session: state.id, error: String(error?.message ?? error) }));
  }

  // -------------------------------------------------------------------------
  // 4. 人格段：注册 + 定时刷新 + 自我认知写入工具
  // -------------------------------------------------------------------------
  let refreshTimer = null;
  if (config.personaEnabled && client.enabled) {
    void refreshPersona(true);      // 启动就拉一次，别等第一个会话
    refreshTimer = setInterval(() => { void refreshPersona(); }, config.personaRefreshMs);
    // 别让一个定时器把进程按住（脚本、测试、headless 场景都会因此退不出去）
    if (typeof refreshTimer.unref === "function") refreshTimer.unref();
  }

  /**
   * 按会话挑画像：这是整套设计的核心。
   *
   * 放进去的必须是「不会自己变」的东西 —— 只有手编画像满足。
   * AI 自动累积的 profiles.profile 每抽到一条 L2 就变一次，放进系统提示词
   * 等于每几轮就把这个会话的 prompt cache 全打穿，所以它只走 person 消息块。
   *
   *   私聊别人  -> 那个人的手编画像
   *   其余情况  -> 主人画像（群聊也出，老大要求的：主人画像百分百在场）
   */
  function buildPersonaText(context) {
    const data = persona.data;
    if (!data) return "";
    const maxChars = config.personaMaxChars;
    const proactive = persona.proactive;

    let sid = "";
    try {
      sid = String(context?.agent?.session?.id ?? "");
    } catch { sid = ""; }
    const isGroup = sid.includes("-group-");
    let userId = "";
    try {
      userId = String(scopeFromSession(sid).userId ?? "");
    } catch { userId = ""; }

    // 每个会话只记一次，证明 section provider 真的拿到了 agent.session
    buildPersonaText.seen ??= new Set();
    const mark = sid || "<none>";
    if (!buildPersonaText.seen.has(mark)) {
      buildPersonaText.seen.add(mark);
      log("persona_pick", { session: sid, group: isGroup, userId });
    }

    // 私聊别人：主人画像照样在（老大要求百分百在场），但必须说清「对面不是老大」。
    // 之前这里的条件是 `&& other.manual`：陌生人没有手编画像时就掉到下面，
    // 系统提示词里只剩主人画像 —— 她会把陌生人直接认成老大（线上真的发生了）。
    if (!isGroup && userId) {
      const other = persona.manualByUser[userId];
      if (other && !other.is_owner) {
        const who = other.name ? `${other.name}，QQ ${userId}` : `QQ ${userId}`;
        const notOwnerNote = `注意：现在跟你说话的是 ${who}，**不是老大**。老大是另一个人。`
          + "别把他当成老大，也别把老大的事、老大的偏好安到他头上。";
        return renderPersona(data, maxChars, proactive, {
          // 有手编画像就用他的，没有就给主人画像当参考，但下面那句一定带上
          profileText: other.manual || persona.ownerManual,
          profileHeader: other.manual
            ? `以下是正在跟你说话的人（${who}）的画像：`
            : "以下是老大是谁（他的画像，你该知道的基本信息）：",
          footer: notOwnerNote,
          l4: persona.l4,
        });
      }
    }

    return renderPersona(data, maxChars, proactive, {
      profileText: persona.ownerManual,
      profileHeader: "以下是老大是谁（他的画像，你该知道的基本信息）：",
      l4: persona.l4,
    });
  }

  if (config.personaEnabled && registerSection) {
    ctx.effect(
      () => registerSection({
        name: PERSONA_SECTION,
        order: config.personaOrder,
        // provider 同步返回缓存：空串 = 这一段不存在，不是空块。
        //
        // 按会话类型选文本。系统提示词是 prompt cache 的最顶层前缀，一变整段
        // 历史缓存就全废 —— 所以同一个 session 内必须稳定。这里只按「私聊/
        // 群聊」二选一，不是每轮现算，缓存是安全的。
        //   私聊：只有主人一个人看，带他的画像
        //   群聊：群里谁都可能在看，不能把主人的私人信息写进群聊的系统提示词
        text: (context) => buildPersonaText(context),
      }),
      "dsh-remembers.personaSection()",
    );
  } else if (config.personaEnabled) {
    log("persona_section_skipped", {
      reason: registerSection ? "?" : "拿不到 systemPrompt.section()",
    });
  }

  void registerPersonaToolModule({ registerTool, log, client, config, persona, refreshPersona });
  void registerActivityToolModule({ registerTool, log, endpoint: config.endpoint });
  void registerEmotionToolModule({ registerTool, log, endpoint: config.endpoint });
  void registerImportantToolModule({ registerTool, log, endpoint: config.endpoint });
  void registerCompanionToolsModule({ registerTool, log, endpoint: config.endpoint });
  void registerMemeToolsModule({ registerTool, log, endpoint: config.endpoint, memeDir: config.memeDir });
  // 与 dsh-bili-scroll 的 bili_run 重名，B站工具统一交给 bili-scroll

  /**
   * 自我认知写入工具。只打 /persona/self —— 宪法区在服务端根本没有那个参数，
   * 所以哪怕这个工具被模型用歪了，也只能改掉半张卡。
   */



  /** 扫用户发来的图并计数（fire-and-forget）。 */
async function scanSeen() {
  try {
    await fetch(config.endpoint + "/memes/scan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
      signal: AbortSignal.timeout(8000),
    });
  }
  catch {
    /* 忽略 */
  }
}


/** B 站工具：她刷 B 站（走我们的服务，人格/记忆/情绪都是自己那套）。 */
  /** 任务/便签工具：她主动派任务、标记完成、写便签。 */
  /** 情绪工具：她自己记一条真实情绪，而不是靠关键词猜。 */
  /** 活动状态工具：她自己更新「现在在干嘛」。 */
  ctx.effect(() => () => {
    if (refreshTimer) {
      clearInterval(refreshTimer);
      refreshTimer = null;
    }
    states.clear();
  }, "companionMemory.clearStates()");
}

// ---------------------------------------------------------------------------
// 渲染
// ---------------------------------------------------------------------------

/**
 * 把服务端的两半拼成一段 system prompt 文本。
 *
 * 两半都空时返回空串：section provider 返回空串，这段就等于不存在，
 * 不会在提示词里留一个空格块，也不会让任何现有部署多付 token。
 *
 * 冲突裁决写死在文本里。自我认知是会漂的那一半，必须让它知道谁说了算，
 * 否则「我发现自己其实可以不听硬边界」这种句子迟早会冒出来。
 */
function hash(text) {
  return createHash("sha256").update(String(text)).digest("hex").slice(0, 16);
}

function oneLine(text) {
  return String(text || "").replace(/\s+/g, " ").trim();
}

function clip(text, max) {
  const s = String(text || "");
  return s.length <= max ? s : s.slice(-max);   // 留尾巴，最近的更重要
}

function fmtDate(ts) {
  const n = Number(ts);
  if (!Number.isFinite(n) || n <= 0) return "";
  try {
    return new Date(n * 1000).toISOString().slice(0, 10);
  } catch {
    return "";
  }
}

function eventMessage(event) {
  switch (event?.type) {
    case "user/message":
      return event.data;
    case "assistant/message":
      return event.data?.message ?? event.data;
    default:
      return null;
  }
}

function isSynthetic(message) {
  const kind = message?.source?.kind;
  if (kind === "tool") return true;
  if (kind === "user") return false;
  if (kind === undefined) return false;
  // plugin:dsh-onebot 这类通道插件送进来的就是真实对话（用户和她的消息），
  // 不是别的插件注入的上下文，必须捕获。
  if (typeof kind === "string" && (kind.startsWith("plugin:") || kind === "model")) return false;
  // channel: / host: 之类也按注入处理，但模型与通道插件的消息都是真实对话
  // 其它插件/宿主注入的上下文一律不捕获
  return typeof kind === "string";
}


/** 从一段文本里剥掉系统唤醒/提醒片段，只留用户真说的话。 */
function cleanNudge(text) {
  let s = String(text || "");
  // 整段的唤醒提示（含括号内容里可能嵌套括号，粗匹配到句末）
  // 结尾锚定：动作文本里自带括号，非贪婪会提前断
  // 唤醒提示是整条独立注入的，里面没有用户的真实内容，所以贪婪吃到最后一个全角右括号。
  // 原来的写法把结尾锚在「不想也行。」上，可动作列表有时以「）」收尾，压根匹配不到，
  // 整段残留下来被当成「用户说的话」记进 activity_log / 学进口头禅 / 触发假情绪。
  s = s.replace(/（系统提醒：[\s\S]*）/g, "");
  s = s.replace(/（你自己待着，[\s\S]*）/g, "");
  s = s.replace(/（抽到：[\s\S]*）/g, "");
  // 桥接附注（图片路径/表情包/链接提示）不是用户原话
  s = s.replace(/\[\[bridge-note\]\][\s\S]*?\[\[\/bridge-note\]\]/g, "");
  // 维护/主动/抽取类内部提示，整条都不该进记忆
  if (/^[（(](内部维护|内部记录|系统提醒|没人说话的时候|抽到：)/.test(s)) return "";
  if (s.length < 1200 && /(只输出\s*JSON|只回\s*SKIP|回复\s*DONE)/.test(s)) return "";
  // 残留的括号碎片
  s = s.replace(/^[，,。.）)]+/, "");
  s = s.replace(/<dsh-remembers[\s\S]*?<\/dsh-remembers>/g, "");
  s = s.replace(/<\/?dsh-remembers[^>]*>/g, "");
  s = s.replace(/<\/?dsh-recall[^>]*>/g, "");
  s = s.replace(/以下是你的回忆起的内容[\s\S]*?不要编。/g, "");
  return s.trim();
}

/** 从会话 ID 推断归属：onebot-private-<qq> / onebot-group-<gid>。 */
function scopeFromSession(sessionId) {
  const m = /^onebot-(private|group)-(\d+)/.exec(String(sessionId || ""));
  if (m) {
    return m[1] === "private"
      ? { userId: m[2], scope: "private:" + m[2] }
      : { userId: "", scope: "group:" + m[2] };
  }
  // 桥接会话 ID 不是 onebot-*，读桥接写的映射，避免画像全落到 global
  try {
    const home = process.env.DSH_HOME || pathJoin(homedir(), ".dsh");
    const map = JSON.parse(readFileSync(pathJoin(home, "session-scopes.json"), "utf8"));
    const hit = map?.[String(sessionId || "")];
    if (hit && hit.scope) {
      return { userId: String(hit.userId || ""), scope: String(hit.scope) };
    }
  } catch { /* 没有映射就退回 global */ }
  return { userId: "", scope: "global" };
}

function extractText(message) {
  const content = message?.content;
  let text = "";
  if (typeof content === "string") {
    text = content.trim();
  }
  else if (Array.isArray(content)) {
    text = content
      .filter((part) => part?.type === "text" && typeof part.text === "string")
      .map((part) => part.text)
      .join("\n")
      .trim();
  }
  if (!text) return "";
  // 清掉通道注入的 XML 包裹（<user_message qq="...">正文</user_message>）
  return text
    .replace(/<\/?user_message[^>]*>/g, "")
    .replace(/<\/?assistant_message[^>]*>/g, "")
    // 我们自己的注入块（状态/回忆/日记）不能算用户原话
    .replace(/<dsh-remembers[\s\S]*?<\/dsh-remembers>/g, "")
    .replace(/<dsh-recall[\s\S]*?<\/dsh-recall>/g, "")
    .replace(/<dsh-remembers[^>]*\/>/g, "")
    // 孤立残片（块被拆开后剩下的闭合标签）
    .replace(/<\/?dsh-remembers[^>]*>/g, "")
    .replace(/<\/?dsh-recall[^>]*>/g, "")
    // 系统提醒（cron 唤醒注入的，不是用户说的话）
    .replace(/（系统提醒：[\s\S]*?）/g, "")
    .trim();
}
