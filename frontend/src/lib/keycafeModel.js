export function emptySummary() {
  return {
    total: 0,
    "at-home": 0,
    "checked-out": 0,
    unknown: 0,
  };
}

export function holderLabel(key) {
  if (key.currentUser?.name) {
    return key.currentUser.email
      ? `${key.currentUser.name} (${key.currentUser.email})`
      : key.currentUser.name;
  }

  if (key.status === "unknown") return "Nicht bestätigt";
  return key.status === "checked-out" ? "Person unbekannt" : "Nicht ausgegeben";
}

export function filterKeys(keys, query = "", status = "all") {
  const search = query.trim().toLowerCase();
  return keys.filter((key) =>
    (status === "all" || key.status === status) && keySearchText(key).includes(search),
  );
}

export function currentLocationLabel(key) {
  if (key.status === "at-home" && key.currentLocation?.name) {
    return key.currentLocation.name;
  }

  return key.status === "checked-out" ? "Ausgegeben" : "Nicht bestätigt";
}

export function locationName(location) {
  return location?.name || "Nicht verfügbar";
}

export function keySearchText(key) {
  return [
    key.name,
    key.statusLabel,
    currentLocationLabel(key),
    holderLabel(key),
    key.serialNumber,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

export function removalTimeLabel(value) {
  if (!value) return "Nicht verfügbar";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Nicht verfügbar";
  return new Intl.DateTimeFormat("de-DE", {
    dateStyle: "medium", timeStyle: "short", timeZone: "Europe/Berlin",
  }).format(date);
}
