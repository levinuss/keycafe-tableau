const object = (value) => value !== null && typeof value === "object" && !Array.isArray(value);
const id = (value) => typeof value === "string" || typeof value === "number";

export const validConfig = (data) => ["ready", "demoMode", "keycafeConfigured"].every((field) => typeof data[field] === "boolean");
export const validGroups = (data) => Array.isArray(data.groups) && data.groups.every((group) => object(group) && id(group.id) && typeof group.name === "string");
export const validKeys = (data) => Array.isArray(data.keys) && data.keys.every((key) =>
  object(key) && id(key.id) && typeof key.name === "string" &&
  ["at-home", "checked-out", "unknown"].includes(key.status) && typeof key.statusLabel === "string",
) && object(data.summary) && ["total", "at-home", "checked-out", "unknown"].every((field) => Number.isInteger(data.summary[field]) && data.summary[field] >= 0);

export async function requestJson(url, validate) {
  let response;
  try {
    response = await fetch(url, { headers: { Accept: "application/json" }, cache: "no-store" });
  } catch {
    throw new Error("Der Server ist nicht erreichbar. Bitte die Verbindung prüfen.");
  }
  if (response.redirected || [401, 403].includes(response.status)) {
    throw new Error("Der Zugriff wurde unterbrochen. Bitte die Seite neu laden und gegebenenfalls erneut anmelden.");
  }
  let payload;
  try {
    if (!response.headers.get("content-type")?.includes("application/json")) throw new Error();
    payload = await response.json();
  } catch {
    throw new Error("Der Server hat keine gültige API-Antwort geliefert. Bitte die Seite neu laden oder den Proxy prüfen.");
  }
  if (!response.ok) throw new Error(typeof payload?.error === "string" ? payload.error : `Die Anfrage ist fehlgeschlagen (HTTP ${response.status}).`);
  if (!object(payload) || !validate(payload)) throw new Error("Die API-Antwort ist unvollständig oder ungültig.");
  return payload;
}
