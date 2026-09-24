import assert from "node:assert/strict";
import { afterEach, mock, test } from "node:test";
import { requestJson, validConfig, validGroups, validKeys } from "./api.js";

afterEach(() => mock.restoreAll());
const respond = (body, options = {}) => mock.method(globalThis, "fetch", async () => new Response(body, options));
const json = (data, status = 200) => respond(JSON.stringify(data), { status, headers: { "content-type": "application/json" } });

test("accepts a valid empty group list", async () => {
  json({ groups: [] });
  assert.deepEqual(await requestJson("/api/groups/", validGroups), { groups: [] });
});
test("rejects a proxy HTML login page with HTTP 200", async () => {
  respond("<html>Login</html>", { headers: { "content-type": "text/html" } });
  await assert.rejects(requestJson("/api/groups/", validGroups), /keine gültige API-Antwort/);
});
test("rejects invalid JSON", async () => {
  respond("{", { headers: { "content-type": "application/json" } });
  await assert.rejects(requestJson("/api/groups/", validGroups), /keine gültige API-Antwort/);
});
test("rejects redirects even when the destination returns JSON", async () => {
  mock.method(globalThis, "fetch", async () => ({ redirected: true }));
  await assert.rejects(requestJson("/api/groups/", validGroups), /erneut anmelden/);
});
test("rejects unauthenticated and forbidden responses", async () => {
  for (const status of [401, 403]) {
    json({}, status);
    await assert.rejects(requestJson("/api/groups/", validGroups), /erneut anmelden/);
    mock.restoreAll();
  }
});
test("rejects missing and malformed group data", async () => {
  for (const payload of [null, [], {}, { groups: [{}] }]) {
    json(payload);
    await assert.rejects(requestJson("/api/groups/", validGroups), /unvollständig oder ungültig/);
    mock.restoreAll();
  }
});
test("retains a server error message", async () => {
  json({ error: "Keycafe ist derzeit nicht erreichbar." }, 502);
  await assert.rejects(requestJson("/api/keys/", validKeys), /Keycafe ist derzeit/);
});
test("reports network failures", async () => {
  mock.method(globalThis, "fetch", async () => { throw new TypeError("offline"); });
  await assert.rejects(requestJson("/api/config/", validConfig), /Server ist nicht erreichbar/);
});
test("validates configuration and key response shapes", () => {
  assert.equal(validConfig({ ready: true, demoMode: true, keycafeConfigured: false }), true);
  assert.equal(validConfig({ ready: "true" }), false);
  assert.equal(validKeys({ keys: [], summary: { total: 0, "at-home": 0, "checked-out": 0, unknown: 0 } }), true);
  assert.equal(validKeys({ keys: [], summary: {} }), false);
  assert.equal(validKeys({ keys: [{}], summary: {} }), false);
});
