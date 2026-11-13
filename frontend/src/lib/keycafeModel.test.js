import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  currentLocationLabel,
  filterKeys,
  holderLabel,
  keySearchText,
} from "./keycafeModel.js";

describe("keycafeModel", () => {
  const keys = [
    { name: "Main entrance", status: "at-home", currentLocation: { name: "Lobby" } },
    { name: "Pool car", status: "checked-out", currentUser: { name: "Ada", email: "ada@example.com" } },
    { name: "Archive", status: "unknown" },
  ];

  it("combines status and case-insensitive search filters", () => {
    assert.deepEqual(filterKeys(keys, " ADA ", "checked-out"), [keys[1]]);
    assert.deepEqual(filterKeys(keys, "Ada", "at-home"), []);
    assert.deepEqual(filterKeys(keys, "lobby"), [keys[0]]);
  });

  it("returns all keys when filters are cleared", () => {
    assert.deepEqual(filterKeys(keys), keys);
    assert.deepEqual(filterKeys(keys, "", "unknown"), [keys[2]]);
    assert.deepEqual(filterKeys([], "anything"), []);
  });

  it("does not claim an unknown key is not handed out", () => {
    assert.equal(holderLabel(keys[2]), "Nicht bestätigt");
  });

  it("labels a checked-out holder with name and email", () => {
    assert.equal(
      holderLabel({
        status: "checked-out",
        currentUser: { name: "Ada Lovelace", email: "ada@example.com" },
      }),
      "Ada Lovelace (ada@example.com)",
    );
  });

  it("labels checked-out current location clearly", () => {
    assert.equal(currentLocationLabel({ status: "checked-out" }), "Ausgegeben");
  });

  it("falls back when a location is missing", () => {
    assert.equal(currentLocationLabel({ status: "unknown" }), "Nicht bestätigt");
  });

  it("shows the SmartBox name only for a confirmed at-home key", () => {
    const currentLocation = { name: "SmartBox am Empfang" };
    assert.equal(currentLocationLabel({ status: "at-home", currentLocation }), currentLocation.name);
    assert.equal(currentLocationLabel({ status: "unknown", currentLocation }), "Nicht bestätigt");
    assert.equal(currentLocationLabel({ status: "checked-out", currentLocation }), "Ausgegeben");
  });

  it("searches German labels and names with umlauts", () => {
    const key = { name: "Büroschlüssel", status: "unknown", statusLabel: "Ungeklärt" };
    assert.deepEqual(filterKeys([key], "BÜRO"), [key]);
    assert.deepEqual(filterKeys([key], "ungeklärt", "unknown"), [key]);
  });

  it("builds searchable text from visible key fields", () => {
    const text = keySearchText({
      name: "Office",
      status: "at-home",
      statusLabel: "At home",
      currentLocation: { name: "Lobby" },
      currentUser: null,
      serialNumber: "ABC123",
    });

    assert.match(text, /office/);
    assert.match(text, /lobby/);
    assert.match(text, /abc123/);
  });
});

it("formats removal times in Berlin time and handles missing history", async () => {
  const { removalTimeLabel } = await import("./keycafeModel.js");
  assert.equal(removalTimeLabel("2026-11-13T08:30:00Z"), "13.11.2026, 09:30");
  assert.equal(removalTimeLabel(null), "Nicht verfügbar");
  assert.equal(removalTimeLabel("invalid"), "Nicht verfügbar");
});
