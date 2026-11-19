const object = (value) => value !== null && typeof value === "object" && !Array.isArray(value);
const id = (value) => typeof value === "string" || typeof value === "number";

export const validConfig = (data) =>
  ["ready", "demoMode", "keycafeConfigured"].every((field) => typeof data[field] === "boolean") &&
  typeof data.csrfToken === "string";
export const validGroups = (data) => Array.isArray(data.groups) && data.groups.every((group) => object(group) && id(group.id) && typeof group.name === "string");
export const validInventory = (data) => Array.isArray(data.keys) && data.keys.every((key) =>
  object(key) && id(key.id) && typeof key.name === "string" && typeof key.serialNumber === "string"
);
export const validKeys = (data) => Array.isArray(data.keys) && data.keys.every((key) =>
  object(key) && id(key.id) && typeof key.name === "string" &&
  ["at-home", "checked-out", "unknown"].includes(key.status) && typeof key.statusLabel === "string",
) && object(data.summary) && ["total", "at-home", "checked-out", "unknown"].every((field) => Number.isInteger(data.summary[field]) && data.summary[field] >= 0) &&
  (data.missingKeyIds === undefined || (Array.isArray(data.missingKeyIds) && data.missingKeyIds.every(id)));

function httpError(message, status) {
  const error = new Error(message);
  error.status = status;
  return error;
}

export async function requestJson(url, validate, options = {}) {
  const { headers, ...rest } = options;
  let response;
  try {
    response = await fetch(url, {
      cache: "no-store",
      ...rest,
      headers: { Accept: "application/json", ...headers },
    });
  } catch {
    throw new Error("Der Server ist nicht erreichbar. Bitte die Verbindung prüfen.");
  }
  if (response.redirected || [401, 403].includes(response.status)) {
    throw httpError("Der Zugriff wurde unterbrochen. Bitte die Seite neu laden und gegebenenfalls erneut anmelden.", response.status);
  }
  let payload;
  try {
    if (!response.headers.get("content-type")?.toLowerCase().includes("application/json")) throw new Error();
    payload = await response.json();
  } catch {
    throw new Error("Der Server hat keine gültige API-Antwort geliefert. Bitte die Seite neu laden oder den Proxy prüfen.");
  }
  if (!response.ok) {
    throw httpError(typeof payload?.error === "string" ? payload.error : `Die Anfrage ist fehlgeschlagen (HTTP ${response.status}).`, response.status);
  }
  if (!object(payload) || !validate(payload)) throw new Error("Die API-Antwort ist unvollständig oder ungültig.");
  return payload;
}
