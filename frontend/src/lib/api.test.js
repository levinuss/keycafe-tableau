import assert from "node:assert/strict";
import { afterEach, mock, test } from "node:test";
import { requestJson, validConfig, validGroups, validInventory, validKeys } from "./api.js";

afterEach(() => mock.restoreAll());
const respond = (body, options = {}) => mock.method(globalThis, "fetch", async () => new Response(body, options));
const json = (data, status = 200) => respond(JSON.stringify(data), { status, headers: { "content-type": "application/json" } });

test("accepts a valid empty group list", async () => {
  json({ groups: [] });
  assert.deepEqual(await requestJson("/api/groups/", validGroups), { groups: [] });
});
test("merges custom headers with Accept and accepts uppercase Content-Type", async () => {
  let sentHeaders;
  mock.method(globalThis, "fetch", async (_url, init) => {
    sentHeaders = init.headers;
    return new Response(JSON.stringify({ groups: [] }), { status: 200, headers: { "Content-Type": "Application/JSON; charset=utf-8" } });
  });
  await requestJson("/api/groups/", validGroups, { method: "POST", headers: { "X-CSRFToken": "tok" } });
  assert.equal(sentHeaders.Accept, "application/json");
  assert.equal(sentHeaders["X-CSRFToken"], "tok");
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
    await assert.rejects(requestJson("/api/groups/", validGroups), (error) => error.status === status && /erneut anmelden/.test(error.message));
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
test("retains a server error message and HTTP status", async () => {
  json({ error: "Gruppe wurde nicht gefunden." }, 404);
  await assert.rejects(requestJson("/api/keys/", validKeys), (error) => error.status === 404 && /nicht gefunden/.test(error.message));
});
test("reports network failures", async () => {
  mock.method(globalThis, "fetch", async () => { throw new TypeError("offline"); });
  await assert.rejects(requestJson("/api/config/", validConfig), /Server ist nicht erreichbar/);
});
test("validates configuration, inventory, and key response shapes", () => {
  assert.equal(validConfig({ ready: true, demoMode: true, keycafeConfigured: false, csrfToken: "tok" }), true);
  assert.equal(validConfig({ ready: true, demoMode: true, keycafeConfigured: false }), false);
  assert.equal(validConfig({ ready: "true" }), false);
  assert.equal(validInventory({ keys: [{ id: 1, name: "K1", serialNumber: "" }] }), true);
  assert.equal(validInventory({ keys: [{ id: 1, name: "K1" }] }), false);
  assert.equal(validKeys({ keys: [], summary: { total: 0, "at-home": 0, "checked-out": 0, unknown: 0 } }), true);
  assert.equal(validKeys({ keys: [], summary: { total: 0, "at-home": 0, "checked-out": 0, unknown: 0 }, missingKeyIds: ["99"] }), true);
  assert.equal(validKeys({ keys: [], summary: { total: 0, "at-home": 0, "checked-out": 0, unknown: 0 }, missingKeyIds: [{}] }), false);
  assert.equal(validKeys({ keys: [], summary: {} }), false);
  assert.equal(validKeys({ keys: [{}], summary: {} }), false);
});
