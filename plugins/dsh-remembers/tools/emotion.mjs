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
        + "valence 必填，-1 很负面、0 中性、1 很正面；"
        + "arousal 0 很平静、0.5 普通、1 很激动；reason 写一句由头。"
        + "不要用 intensity，也不要按 label 猜正负；valence 必须由你判断。",
      parameters: {
        label: { type: "string", required: true, description: "情绪词，一两个词" },
        valence: { type: "number", required: true, description: "必填 -1..1：负=难受，0=中性，正=舒服" },
        arousal: { type: "number", description: "0..1：0 很平静，0.5 普通，1 很激动；默认 0.5" },
        reason: { type: "string", description: "一句由头：因为什么" },
      },
      output: { schema: { type: "json" }, render: (_args, value) => [{ type: "text", text: JSON.stringify(value) }] },
      execute: async (args) => {
        const label = String(args.label || "").trim().slice(0, 20);
        if (!label) return { ok: false, error: "label is required" };
        const valence = Number(args.valence);
        if (!Number.isFinite(valence)) {
          return { ok: false, error: "valence is required (-1..1)" };
        }
        const clamp = (value, lo, hi, fallback) => {
          const n = Number(value);
          return Number.isFinite(n) ? Math.max(lo, Math.min(hi, n)) : fallback;
        };
        const v = clamp(valence, -1, 1, 0);
        const arousal = clamp(args.arousal, 0, 1, 0.5);
        const reason = String(args.reason || "").trim().slice(0, 200);
        try {
          await fetch(endpoint + "/state", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ valence: v, arousal }),
            signal: AbortSignal.timeout(5000),
          });
          await fetch(endpoint + "/emotion", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ label, valence: v, arousal, trigger: reason, source: "self" }),
            signal: AbortSignal.timeout(5000),
          });
          return { ok: true, label, valence: v, arousal };
        } catch (error) {
          return { ok: false, error: String(error?.message ?? error) };
        }
      },
    }));
  } catch (error) {
    log("emotion_tool_skipped", { reason: "register 失败", error: String(error?.message ?? error) });
  }
}
