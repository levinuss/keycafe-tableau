<script>
  import { ArrowUpRight, CircleHelp, House } from "@lucide/svelte";
  import { locationName, removalTimeLabel } from "../lib/keycafeModel.js";

  export let key;

  $: isOut = key.status === "checked-out";
  $: isUnknown = key.status === "unknown";
  $: statusIcon = isOut ? ArrowUpRight : isUnknown ? CircleHelp : House;
</script>

<article class={`key-card status-${key.status}`}>
  <div class="key-card-top">
    <span class="key-status"><svelte:component this={statusIcon} size={17} strokeWidth={2} aria-hidden="true" />{key.statusLabel}</span>
  </div>
  <div class="key-identity">
    <h2>{key.name}</h2>
  </div>
  <div class="key-custody">
    <div>
      <span class="field-label">{isOut ? "Ausgegeben an" : isUnknown ? "Verbleib" : "In der SmartBox"}</span>
      <p class="custody-name">{isOut ? key.currentUser?.name || "Person unbekannt" : isUnknown ? "Nicht bestätigt" : locationName(key.currentLocation)}</p>
      {#if isOut && key.currentUser?.email}<p class="custody-email">{key.currentUser.email}</p>{/if}
    </div>
  </div>
  {#if isOut}
    <div class="key-removal">
      <span class="field-label">Entnommen am</span>
      <p class="custody-name" title="Europe/Berlin">{removalTimeLabel(key.removedAt)}</p>
    </div>
  {/if}
  <div class="key-card-footer">
    <span class="key-serial">Schlüsselanhänger: {key.serialNumber || "Nicht zugewiesen"}</span>
  </div>
  {#if key.detailError}<p class="detail-error">{key.detailError}</p>{/if}
</article>
