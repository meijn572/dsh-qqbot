/** pre-step hook：只转发，召回策略在服务端。 */
export async function loadRecall(client, payload) {
  const res = await client.hookPreStep(payload);
  return res?.recall || "";
}
