/** set_emotion 工具：schema + 直接写服务。 */
export async function registerEmotionTool({ registerTool, log, endpoint }) {
  if (!registerTool) return;
  let defineTool;
  try {
    ({ defineTool } = await import("@deepseek-ai/dsh-tools"));
  } catch (error) {
    log("emotion_tool_skipped", { reason: "dsh-tools 不可用", error: String(error?.message ?? error) });
    return;
  }
  try {
    registerTool(defineTool({
      name: "set_emotion",
      description:
        "记录你自己此刻的真实情绪。不是每句话都记，只有真的被戳到、情绪明显时才用。"
        + "label 用一两个词（开心/烦/委屈/温柔/复杂/无聊/愧疚/期待…）；"
        + "intensity 是强度 0–1；reason 写一句由头（因为什么）；"
        + "valence 可选 -1..1（负=难受，正=舒服），不填就按 label 的正负自动判断；arousal 可选 0..1。",
      parameters: {
        label: { type: "string", required: true, description: "情绪词，一两个词" },
        intensity: { type: "number", description: "强度 0–1，默认 0.5" },
        reason: { type: "string", description: "一句由头：因为什么" },
        valence: { type: "number", description: "可选 -1..1，不填按 label 自动判断" },
        arousal: { type: "number", description: "可选 0..1，默认 0.5" },
      },
      output: { schema: { type: "json" }, render: (_args, value) => [{ type: "text", text: JSON.stringify(value) }] },
      execute: async (args) => {
        const label = String(args.label || "").trim().slice(0, 20);
        if (!label) return { ok: false, error: "label is required" };
        const clamp = (value, lo, hi, fallback) => {
          const n = Number(value);
          return Number.isFinite(n) ? Math.max(lo, Math.min(hi, n)) : fallback;
        };
        const intensity = clamp(args.intensity, 0, 1, 0.5);
        const positive = /(开心|高兴|喜欢|温柔|感动|兴奋|甜|满意|期待|放松|骄傲|暖|被夸|幸福)/.test(label);
        const valence = args.valence === undefined ? (positive ? intensity : -intensity) : clamp(args.valence, -1, 1, 0);
        const arousal = clamp(args.arousal, 0, 1, 0.5);
        const reason = String(args.reason || "").trim().slice(0, 200);
        try {
          await fetch(endpoint + "/state", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ valence, arousal }),
            signal: AbortSignal.timeout(5000),
          });
          await fetch(endpoint + "/emotion", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ label, valence, arousal, trigger: reason, source: "self" }),
            signal: AbortSignal.timeout(5000),
          });
          return { ok: true, label, intensity, valence, arousal };
        } catch (error) {
          return { ok: false, error: String(error?.message ?? error) };
        }
      },
    }));
  } catch (error) {
    log("emotion_tool_skipped", { reason: "register 失败", error: String(error?.message ?? error) });
  }
}
