/** turn-end hook：只转发，写不写 L0 由服务端决定。 */
export async function recordTurn(client, payload) {
  return client.hookTurnEnd(payload);
}
