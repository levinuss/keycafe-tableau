<script>
  import { onMount } from "svelte";
  import { CircleHelp, KeyRound, LayoutGrid, List, RefreshCw, Search, X } from "@lucide/svelte";
  import GroupEditor from "./components/GroupEditor.svelte";
  import KeyCard from "./components/KeyCard.svelte";
  import { requestJson, validConfig, validGroups, validKeys } from "./lib/api.js";
  import { currentLocationLabel, emptySummary, filterKeys, holderLabel, removalTimeLabel } from "./lib/keycafeModel.js";

  const statuses = [
    { id: "all", label: "Alle", count: "total" },
    { id: "at-home", label: "Vor Ort", count: "at-home" },
    { id: "checked-out", label: "Ausgegeben", count: "checked-out" },
    { id: "unknown", label: "Ungeklärt", count: "unknown" },
  ];
  let autoRefreshMinutes = "0";
  let lastRefresh = Date.now();
  let groups = [];
  let editingGroups = false;
  let csrfToken = "";
  let missingKeyIds = [];
  let selectedGroup = "";
  let keys = [];
  let summary = emptySummary();
  let searchQuery = "";
  let statusFilter = "all";
  let view = "cards";
  let isBusy = true;
  let statusMessage = "Verbindung wird hergestellt...";
  let isError = false;
  let connectionLabel = "Verbindung wird hergestellt";
  let isConnected = false;
  let updatedAt = "";
  let keycafeConfigured = false;
  let demoMode = false;

  $: filteredKeys = filterKeys(keys, searchQuery, statusFilter);
  $: groupName = groups.find((group) => String(group.id) === selectedGroup)?.name || "Schlüsselübersicht";

  let keyRequest = 0;

  function maybeAutoRefresh() {
    if (
      autoRefreshMinutes !== "0" &&
      !isBusy &&
      !editingGroups &&
      !document.hidden &&
      Date.now() - lastRefresh >= Number(autoRefreshMinutes) * 60000
    ) {
      refresh();
    }
  }

  onMount(() => {
    boot();
    const timer = setInterval(maybeAutoRefresh, 15000);
    const onVisibilityChange = () => {
      if (!document.hidden) maybeAutoRefresh();
    };
    document.addEventListener("visibilitychange", onVisibilityChange);
    return () => {
      clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  });

  async function boot() {
    lastRefresh = Date.now();
    setBusy("Verbindung wird hergestellt...");
    try {
      const config = await requestJson("/api/config/", validConfig);
      csrfToken = config.csrfToken;
      keycafeConfigured = config.keycafeConfigured;
      demoMode = config.demoMode;
      if (config.ready) {
        await loadGroups();
      } else {
        connectionLabel = "Nicht eingerichtet";
        setStatus("Der Keycafe-Zugang ist nicht eingerichtet. Bitte KEYCAFE_EMAIL und KEYCAFE_TOKEN auf dem Server setzen.", true);
      }
    } catch (error) {
      connectionLabel = "Nicht verbunden";
      setStatus(error.message, true);
    } finally {
      isBusy = false;
    }
  }

  async function loadGroups(allowGroupReload = true) {
    if (!keycafeConfigured && !demoMode) return;
    lastRefresh = Date.now();
    setBusy("Schlüsselgruppen werden geladen...");
    try {
      const payload = await requestJson("/api/groups/", validGroups);
      groups = payload.groups;
      isConnected = true;
      connectionLabel = demoMode ? "Demomodus" : "Mit Keycafe verbunden";
      const current = groups.find(group => String(group.id) === selectedGroup);
      resetGroup(current?.id ?? groups[0]?.id ?? "");
      if (groups.length) {
        await loadKeys(allowGroupReload);
      } else {
        setStatus("Noch keine Gruppen eingerichtet. Bitte über „Gruppen verwalten“ eine Gruppe anlegen.");
      }
    } catch (error) {
      isConnected = false;
      connectionLabel = "Nicht verbunden";
      setStatus(error.message, true);
    } finally {
      isBusy = false;
    }
  }

  function resetGroup(id) {
    ++keyRequest;
    selectedGroup = String(id);
    searchQuery = "";
    statusFilter = "all";
    keys = [];
    missingKeyIds = [];
    summary = emptySummary();
    updatedAt = "";
  }

  async function selectGroup(id) {
    if (isBusy) return;
    resetGroup(id);
    await loadKeys();
  }

  async function loadKeys(allowGroupReload = true) {
    if (!selectedGroup) return;
    const request = ++keyRequest;
    lastRefresh = Date.now();
    setBusy("Schlüsselübersicht wird aktualisiert...");
    try {
      const params = new URLSearchParams({ group: selectedGroup });
      const payload = await requestJson(`/api/keys/?${params.toString()}`, validKeys);
      if (request !== keyRequest) return;
      missingKeyIds = payload.missingKeyIds || [];
      keys = payload.keys;
      summary = payload.summary;
      isConnected = true;
      connectionLabel = demoMode ? "Demomodus" : "Mit Keycafe verbunden";
      updatedAt = new Date().toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" });
      setStatus(demoMode ? "Demodaten" : "Schlüsselübersicht ist aktuell");
    } catch (error) {
      if (request !== keyRequest) return;
      if (error.status === 404 && allowGroupReload) {
        await loadGroups(false);
        return;
      }
      isConnected = false;
      connectionLabel = "Nicht verbunden";
      setStatus(error.message, true);
    } finally {
      if (request === keyRequest) isBusy = false;
    }
  }

  async function refresh() {
    if (groups.length) await loadKeys();
    else await boot();
  }

  function setBusy(message) {
    isBusy = true;
    setStatus(message);
  }

  function setStatus(message, error = false) {
    statusMessage = message;
    isError = error;
  }

  function clearFilters() {
    searchQuery = "";
    statusFilter = "all";
  }
</script>

<svelte:head><title>{groupName} / Keycafe Tableau</title></svelte:head>

<div class="app-shell">
  <header class="masthead">
    <a class="brand" href="/" aria-label="Keycafe Tableau Startseite"><span class="brand-mark"><KeyRound size={23} strokeWidth={1.8} /></span><span>keycafe<span class="brand-divider">/</span><span class="brand-product">tableau</span></span></a>
    <div class="masthead-meta"><span class="masthead-caption">Schlüsselverwaltung</span>{#if demoMode}<span class="demo-label">Demodaten</span>{/if}</div>
  </header>

  <aside class="sidebar">
    <div class="rail-heading"><span>Schlüsselgruppen</span><span class="mono">{String(groups.length).padStart(2, "0")}</span></div>
    <nav class="group-nav" aria-label="Schlüsselgruppen">
      {#each groups as group (group.id)}
        <button type="button" class:active={selectedGroup === String(group.id)} aria-current={selectedGroup === String(group.id) ? "true" : undefined} disabled={isBusy} on:click={() => selectGroup(group.id)}>
          <span>{group.name || `Gruppe ${group.id}`}</span>
        </button>
      {/each}
    </nav>
    <div class="mobile-group">
      <label for="group" class="visually-hidden">Schlüsselgruppe</label>
      <select id="group" class="form-select" value={selectedGroup} disabled={isBusy || !groups.length} on:change={(event) => selectGroup(event.currentTarget.value)}>
        {#each groups as group (group.id)}<option value={String(group.id)}>{group.name || `Gruppe ${group.id}`}</option>{/each}
        {#if !groups.length}<option>Keine Gruppen geladen</option>{/if}
      </select>
    </div>
    <div class="rail-footer">
      <div class="connection"><span class="connection-dot" class:connected={isConnected}></span>{connectionLabel}</div>
    </div>
  </aside>

  <main class="workspace" aria-busy={isBusy}>
    <header class="register-heading">
      <div><p class="eyebrow">Schlüsselübersicht</p><h1>{groupName}</h1></div>
      {#if !demoMode}<button type="button" class="btn btn-sm btn-outline-dark" disabled={isBusy} on:click={() => editingGroups = !editingGroups}>Gruppen verwalten</button>{/if}
    </header>

    {#if editingGroups}
      <GroupEditor {groups} {csrfToken} onClose={() => editingGroups = false} onSaved={async () => { editingGroups = false; missingKeyIds = []; await loadGroups(); }} />
    {/if}
    {#if missingKeyIds.length}<p class="error-message" role="alert">Konfigurierte Schlüssel nicht verfügbar: {missingKeyIds.join(', ')}. Bitte IDs und Keycafe-Zugriffsrechte prüfen.</p>{/if}

    <section class="status-filters" aria-label="Nach Schlüsselstatus filtern">
      {#each statuses as status}
        <button type="button" class={`status-filter status-${status.id}`} class:active={statusFilter === status.id} aria-pressed={statusFilter === status.id} on:click={() => statusFilter = status.id}>
          <span class="filter-label"><span class="status-dot"></span>{status.label}</span><strong>{summary[status.count]}</strong>
        </button>
      {/each}
    </section>

    <section class="register-toolbar" aria-label="Suche und Ansicht">
      <div class="search-field"><Search size={17} aria-hidden="true" /><label class="visually-hidden" for="search">Schlüssel suchen</label><input id="search" class="form-control" type="search" placeholder="Schlüssel oder Person suchen" bind:value={searchQuery} />{#if searchQuery}<button type="button" class="icon-button" title="Suche löschen" aria-label="Suche löschen" on:click={() => searchQuery = ""}><X size={16} /></button>{/if}</div>
      <div class="toolbar-actions">
        <label class="auto-refresh">Automatisch
          <select class="form-select form-select-sm" bind:value={autoRefreshMinutes} aria-label="Automatisch aktualisieren">
            <option value="0">Aus</option>
            <option value="2">Alle 2 Minuten</option>
            <option value="5">Alle 5 Minuten</option>
            <option value="10">Alle 10 Minuten</option>
          </select>
        </label>
        <div class="view-toggle" role="group" aria-label="Ansicht">
          <button type="button" class="icon-button" class:active={view === "cards"} title="Kachelansicht" aria-label="Kachelansicht" aria-pressed={view === "cards"} on:click={() => view = "cards"}><LayoutGrid size={17} /></button>
          <button type="button" class="icon-button" class:active={view === "table"} title="Listenansicht" aria-label="Listenansicht" aria-pressed={view === "table"} on:click={() => view = "table"}><List size={19} /></button>
        </div>
        <button type="button" class="icon-button refresh-button" title="Aktualisieren" aria-label="Aktualisieren" disabled={isBusy} on:click={refresh}><RefreshCw size={17} class={isBusy ? "spinning" : ""} /></button>
      </div>
    </section>

    <div class="result-meta"><span aria-live="polite" aria-atomic="true">{filteredKeys.length} von {keys.length} {keys.length === 1 ? "Schlüssel" : "Schlüsseln"}{#if statusFilter !== "all"}<span class="result-filter"> / {statuses.find((status) => status.id === statusFilter)?.label}</span>{/if}</span><span>{isBusy ? "Wird aktualisiert..." : updatedAt ? `Stand: ${updatedAt} Uhr` : "Noch nicht aktualisiert"}</span></div>

    {#if isError}<div class="error-message" role="alert"><CircleHelp size={18} /><span>{statusMessage}</span><button type="button" class="btn btn-sm btn-outline-dark" disabled={isBusy} on:click={refresh}>Erneut versuchen</button></div>{/if}

    {#if filteredKeys.length}
      {#if view === "cards"}
        <section class="key-grid" aria-label="Schlüssel">
          {#each filteredKeys as key (key.id)}<KeyCard {key} />{/each}
        </section>
      {:else}
        <section class="table-responsive table-shell" aria-label="Schlüssel">
          <table class="table align-middle mb-0">
            <thead><tr><th scope="col">Schlüssel</th><th scope="col">Status</th><th scope="col">Verbleib</th><th scope="col">Ausgegeben an</th><th scope="col">Entnommen am</th></tr></thead>
            <tbody>
              {#each filteredKeys as key (key.id)}
                <tr><th scope="row"><span class="table-key-name">{key.name}</span><span class="table-serial">{key.serialNumber || "Kein Schlüsselanhänger"}</span>{#if key.detailError}<span class="detail-error">{key.detailError}</span>{/if}</th><td><span class={`key-status status-${key.status}`}><span class="status-dot"></span>{key.statusLabel}</span></td><td>{currentLocationLabel(key)}</td><td>{holderLabel(key)}</td><td title={key.status === "checked-out" ? "Europe/Berlin" : undefined}>{key.status === "checked-out" ? removalTimeLabel(key.removedAt) : "–"}</td></tr>
              {/each}
            </tbody>
          </table>
        </section>
      {/if}
    {:else}
      <section class="empty-state">
        <KeyRound size={32} strokeWidth={1.3} />
        <h2>{isBusy ? "Schlüssel werden geladen..." : searchQuery || statusFilter !== "all" ? "Keine passenden Schlüssel" : "Keine Schlüssel vorhanden"}</h2>
        {#if searchQuery || statusFilter !== "all"}<button type="button" class="btn btn-outline-dark btn-sm" on:click={clearFilters}>Filter zurücksetzen</button>{/if}
      </section>
    {/if}
    <footer class="register-footer"><span role="status" aria-live="polite">{isError ? "Aktualisierung fehlgeschlagen" : statusMessage}</span></footer>
  </main>
</div>
