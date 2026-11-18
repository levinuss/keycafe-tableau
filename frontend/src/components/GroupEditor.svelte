<script>
  import { requestJson, validInventory } from '../lib/api.js';
  export let groups = [];
  export let csrfToken = '';
  export let onSaved;
  export let onClose;
  let selected = '';
  let name = '';
  let ids = '';
  let inventory = [];
  let busy = false;
  let error = '';
  let query = '';
  let confirmDelete = false;
  $: visible = inventory.filter(key => `${key.name} ${key.id} ${key.serialNumber || ''}`.toLowerCase().includes(query.toLowerCase()));
  function edit(id) {
    selected = id;
    const group = groups.find(group => group.id === id);
    name = group?.name || '';
    ids = (group?.keyIds || []).join(', ');
    confirmDelete = false;
    error = '';
  }
  $: selectedIds = new Set(ids.split(/[\s,;]+/).filter(Boolean));
  function toggle(id, checked) {
    const values = new Set(selectedIds);
    if (checked) values.add(String(id)); else values.delete(String(id));
    ids = [...values].join(', ');
  }
  async function loadInventory() {
    busy = true; error = '';
    try { inventory = (await requestJson('/api/inventory/', validInventory)).keys; }
    catch (err) { error = err.message; }
    finally { busy = false; }
  }
  async function save(remove = false) {
    busy = true; error = '';
    try {
      await requestJson(selected ? `/api/groups/${selected}/` : '/api/groups/', data => remove ? data.deleted === true : !!data.group, {
        method: remove ? 'DELETE' : selected ? 'PUT' : 'POST',
        headers: { Accept: 'application/json', 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
        ...(remove ? {} : { body: JSON.stringify({ name, keyIds: [...selectedIds] }) }),
      });
      await onSaved();
    } catch (err) { error = err.message; }
    finally { busy = false; }
  }
</script>

<section class="group-editor" aria-labelledby="group-editor-title">
  <div class="d-flex justify-content-between align-items-center gap-3 mb-3">
    <h2 id="group-editor-title">Schlüsselgruppen verwalten</h2>
    <button type="button" class="btn btn-sm btn-outline-dark" disabled={busy} on:click={onClose}>Schließen</button>
  </div>
  <p>Gruppen werden lokal gespeichert. Die Auswahl ändert keine Berechtigungen in Keycafe.</p>
  <label for="edit-group" class="form-label">Gruppe</label>
  <select id="edit-group" class="form-select mb-3" value={selected} disabled={busy} on:change={event => edit(event.currentTarget.value)}>
    <option value="">Neue Gruppe</option>
    {#each groups as group}<option value={group.id}>{group.name}</option>{/each}
  </select>
  <form on:submit|preventDefault={() => save()}>
    <label for="group-name" class="form-label">Name</label>
    <input id="group-name" class="form-control mb-3" bind:value={name} required maxlength="120" disabled={busy} />
    <label for="group-key-ids" class="form-label">Keycafe-Schlüssel-IDs</label>
    <textarea id="group-key-ids" class="form-control" bind:value={ids} rows="3" disabled={busy} aria-describedby="ids-help"></textarea>
    <p id="ids-help" class="small mt-2">IDs durch Kommas oder Zeilenumbrüche trennen. Leere Gruppen sind möglich.</p>
    <button type="button" class="btn btn-sm btn-outline-dark mb-3" disabled={busy} on:click={loadInventory}>Schlüssel aus Keycafe laden</button>
    {#if inventory.length}
      <label for="inventory-search" class="form-label d-block">Schlüssel suchen</label>
      <input id="inventory-search" class="form-control mb-2" bind:value={query} type="search" />
      <div class="group-key-picker">
        {#each visible as key}
          <label class="d-flex gap-2 py-2"><input type="checkbox" checked={selectedIds.has(String(key.id))} disabled={busy} on:change={event => toggle(key.id, event.currentTarget.checked)} /><span>{key.name} · {key.id}{key.serialNumber ? ` · ${key.serialNumber}` : ''}</span></label>
        {/each}
      </div>
    {/if}
    {#if error}<p class="error-message" role="alert">{error}</p>{/if}
    <div class="d-flex flex-wrap gap-2 mt-3">
      <button class="btn btn-dark" disabled={busy}>{busy ? 'Wird verarbeitet…' : 'Speichern'}</button>
      {#if selected}
        {#if confirmDelete}
          <button type="button" class="btn btn-danger" disabled={busy} on:click={() => save(true)}>Gruppe endgültig löschen</button>
          <button type="button" class="btn btn-outline-dark" disabled={busy} on:click={() => confirmDelete = false}>Abbrechen</button>
        {:else}<button type="button" class="btn btn-outline-danger" disabled={busy} on:click={() => confirmDelete = true}>Gruppe löschen…</button>{/if}
      {/if}
    </div>
  </form>
</section>
