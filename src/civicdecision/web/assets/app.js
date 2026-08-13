(() => {
  "use strict";

  const API = "/api/v1";
  const state = {
    summary: null,
    tier: "all",
    cityOffset: 0,
    cityLimit: 9,
    cityQuery: "",
    cityPage: null,
    scenarioOffset: 0,
    scenarioLimit: 10,
    scenarioKind: "all",
    scenarioStatus: "",
    scenarioQuery: "",
    scenarioPage: null,
    designOffset: 0,
    designLimit: 12,
    designQuery: "",
    designSuite: "",
    designFamily: "",
    designType: "",
    designImplementation: "",
    designReadiness: "",
    designPage: null,
    familyQuery: "",
    familyPage: null,
    libraryEvidence: null,
    sourceOffset: 0,
    sourceLimit: 8,
    sourceQuery: "",
    sourcePage: null,
    lastFocus: null,
  };

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const formatNumber = new Intl.NumberFormat("en-US");

  function escapeHTML(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function display(value, fallback = "—") {
    if (value === null || value === undefined || value === "") return fallback;
    return escapeHTML(value);
  }

  function compactHash(value) {
    if (!value) return "—";
    const raw = String(value).replace(/^sha256:/, "");
    return `${raw.slice(0, 12)}…${raw.slice(-8)}`;
  }

  function titleCase(value) {
    return String(value ?? "")
      .replaceAll("_", " ")
      .replaceAll("-", " ")
      .replace(/\b\w/g, (letter) => letter.toUpperCase());
  }

  function formatDate(value) {
    if (!value) return "—";
    const date = new Date(value);
    if (Number.isNaN(date.valueOf())) return String(value);
    return new Intl.DateTimeFormat("en", {
      year: "numeric",
      month: "short",
      day: "2-digit",
      timeZone: "UTC",
    }).format(date);
  }

  function formatValue(value) {
    if (typeof value === "number") return formatNumber.format(value);
    if (typeof value === "boolean") return value ? "Yes" : "No";
    if (value === null || value === undefined) return "—";
    return String(value);
  }

  function debounce(callback, wait = 240) {
    let timer;
    return (...args) => {
      window.clearTimeout(timer);
      timer = window.setTimeout(() => callback(...args), wait);
    };
  }

  async function api(path, params = {}) {
    const url = new URL(`${API}${path}`, window.location.origin);
    for (const [key, value] of Object.entries(params)) {
      if (value !== "" && value !== null && value !== undefined) {
        url.searchParams.set(key, String(value));
      }
    }
    const response = await fetch(url, {
      headers: { Accept: "application/json" },
      credentials: "same-origin",
    });
    if (!response.ok) {
      let detail = `${response.status} ${response.statusText}`;
      try {
        const problem = await response.json();
        detail = problem.detail || problem.title || detail;
      } catch {
        // Preserve the HTTP status when a proxy returns a non-JSON error page.
      }
      throw new Error(detail);
    }
    return response.json();
  }

  function setText(selector, value) {
    const node = $(selector);
    if (node) node.textContent = String(value);
  }

  function showToast(message, duration = 3600) {
    const toast = $("[data-toast]");
    if (!toast) return;
    toast.textContent = message;
    toast.hidden = false;
    window.clearTimeout(showToast.timer);
    showToast.timer = window.setTimeout(() => {
      toast.hidden = true;
    }, duration);
  }

  function renderSummary(summary) {
    state.summary = summary;
    setText("[data-fingerprint]", compactHash(summary.catalog_fingerprint));
    const fingerprint = $("[data-fingerprint]");
    if (fingerprint) fingerprint.title = summary.catalog_fingerprint;
    setText("[data-latest-source]", formatDate(summary.generated_from_latest_source_at));
    setText("[data-city-total]", formatNumber.format(summary.exposed_city_records));
    setText("[data-tier-count='all']", `${formatNumber.format(summary.exposed_city_records)} distinct cities`);
    setText("[data-tier-count='G']", `${formatNumber.format(summary.tier_g_cities)} cities`);
    setText("[data-tier-count='S']", `${formatNumber.format(summary.tier_s_cities)} cities`);
    setText("[data-tier-count='D']", `${formatNumber.format(summary.tier_d_cities)} cities`);
    setText("[data-deep-completed-count]", formatNumber.format(summary.completed_deep_executions));
    setText("[data-deep-negative-count]", formatNumber.format(summary.negative_deep_executions));
    setText("[data-decision-packs]", formatNumber.format(summary.decision_packs));
    setText("[data-design-total]", formatNumber.format(summary.scenario_library_designs));
    setText("[data-family-total]", formatNumber.format(summary.scenario_library_families));
    setText("[data-design-reference]", formatNumber.format(summary.reference_implemented_designs));
    setText("[data-design-only]", formatNumber.format(summary.design_only_scenarios));
    setText("[data-design-similarity]", Number(summary.scenario_library_maximum_similarity).toFixed(6));
    setText("[data-design-audit]", summary.scenario_library_audit_passed ? "PASS" : "REVIEW");
    setText("[data-source-total]", formatNumber.format(summary.source_artifacts));
    setText("[data-footer-version]", `Version ${summary.software_version}`);

    for (const node of $$('[data-kpi]')) {
      const key = node.dataset.kpi;
      if (Object.hasOwn(summary, key)) node.textContent = formatNumber.format(summary[key]);
    }

    const totalDeep = summary.deep_scenario_executions;
    const complete = summary.completed_deep_executions;
    const rate = totalDeep ? (complete / totalDeep) * 100 : 0;
    setText("[data-completion-rate]", `${rate.toFixed(1)}%`);
    setText("[data-deep-completed]", `${rate.toFixed(0)}%`);
    const ring = $("[data-ring]");
    if (ring) ring.setAttribute("stroke-dashoffset", String(439.82 * (1 - rate / 100)));

    const supported = $("[data-supported-boundaries]");
    if (supported && Array.isArray(summary.claim_boundary)) {
      supported.innerHTML = summary.claim_boundary
        .map((item) => `<li>${escapeHTML(item)}</li>`)
        .join("");
    }
  }

  async function loadSystem() {
    try {
      const [health, summary] = await Promise.all([fetch("/healthz").then((r) => r.json()), api("/meta")]);
      renderSummary(summary);
      $("[data-status-dot]")?.classList.add("ready");
      setText("[data-system-status]", health.status === "ok" ? "Catalog verified" : "Catalog not ready");
    } catch (error) {
      $("[data-status-dot]")?.classList.add("error");
      setText("[data-system-status]", "Catalog unavailable");
      showToast(`Catalog could not be loaded: ${error.message}`, 7000);
      throw error;
    }
  }

  function cityParams({ all = false } = {}) {
    return {
      tier: state.tier === "all" ? "" : state.tier,
      q: state.cityQuery,
      limit: all ? 100 : state.cityLimit,
      offset: all ? 0 : state.cityOffset,
    };
  }

  function cityTierLabel(tier) {
    return { G: "Global discovery", S: "Standardized screening", D: "Deep evidence" }[tier] || tier;
  }

  function renderCityList(page) {
    state.cityPage = page;
    const list = $("[data-city-list]");
    if (!list) return;
    if (!page.items.length) {
      list.innerHTML = '<div class="empty-state">No city records match this evidence filter.</div>';
    } else {
      list.innerHTML = page.items
        .map(
          (city) => `
            <button class="city-row" type="button" data-city-id="${escapeHTML(city.city_id)}">
              <span class="city-tier tier-${escapeHTML(city.tier)}">${escapeHTML(city.tier)}</span>
              <span class="city-name"><strong>${escapeHTML(city.name)}</strong><small>${escapeHTML(city.city_id)} · ${escapeHTML(city.country_code)}</small></span>
              <span class="city-scenario-count">${formatNumber.format(city.scenario_count)} work item${city.scenario_count === 1 ? "" : "s"}</span>
            </button>`,
        )
        .join("");
    }
    const pagination = page.pagination;
    const first = pagination.total ? pagination.offset + 1 : 0;
    const last = pagination.offset + pagination.returned;
    setText("[data-city-page]", `${first}–${last} of ${formatNumber.format(pagination.total)}`);
    $("[data-city-prev]").disabled = pagination.offset === 0;
    $("[data-city-next]").disabled = pagination.next_offset === null;
  }

  async function loadCities() {
    const list = $("[data-city-list]");
    if (list) list.setAttribute("aria-busy", "true");
    try {
      const page = await api("/cities", cityParams());
      renderCityList(page);
    } catch (error) {
      if (list) list.innerHTML = `<div class="error-state">Unable to load city catalog.<br>${escapeHTML(error.message)}</div>`;
    } finally {
      if (list) list.removeAttribute("aria-busy");
    }
  }

  async function fetchAllCities() {
    const items = [];
    let offset = 0;
    while (true) {
      const page = await api("/cities", { ...cityParams({ all: true }), offset });
      items.push(...page.items);
      if (page.pagination.next_offset === null) break;
      offset = page.pagination.next_offset;
    }
    return items;
  }

  function project(longitude, latitude) {
    return {
      x: ((Number(longitude) + 180) / 360) * 1000,
      y: ((90 - Number(latitude)) / 180) * 500,
    };
  }

  function positionTooltip(event, city) {
    const tooltip = $("[data-map-tooltip]");
    if (!tooltip) return;
    void event;
    tooltip.innerHTML = `<strong>${escapeHTML(city.name)}</strong><span>Tier ${escapeHTML(city.tier)} · ${escapeHTML(city.country_code)} · ${formatNumber.format(city.scenario_count)} work items</span>`;
    tooltip.hidden = false;
  }

  function renderMap(cities) {
    const group = $("[data-map-points]");
    if (!group) return;
    group.replaceChildren();
    const namespace = "http://www.w3.org/2000/svg";
    for (const city of cities) {
      const { x, y } = project(city.longitude, city.latitude);
      const circle = document.createElementNS(namespace, "circle");
      circle.setAttribute("cx", String(x));
      circle.setAttribute("cy", String(y));
      circle.setAttribute("r", city.tier === "D" ? "5.4" : city.tier === "S" ? "4.4" : "3.1");
      circle.setAttribute("class", `map-point tier-${city.tier}`);
      circle.setAttribute("tabindex", "0");
      circle.setAttribute("role", "button");
      circle.setAttribute("aria-label", `${city.name}, tier ${city.tier}. Open city evidence.`);
      circle.addEventListener("pointerenter", (event) => positionTooltip(event, city));
      circle.addEventListener("pointermove", (event) => positionTooltip(event, city));
      circle.addEventListener("pointerleave", () => {
        $("[data-map-tooltip]").hidden = true;
      });
      circle.addEventListener("focus", () => {
        const map = $("[data-map]");
        const box = circle.getBoundingClientRect();
        positionTooltip({ clientX: box.left + box.width / 2, clientY: box.top, currentTarget: circle }, city);
      });
      circle.addEventListener("blur", () => {
        $("[data-map-tooltip]").hidden = true;
      });
      circle.addEventListener("click", () => openCity(city.city_id, circle));
      circle.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          openCity(city.city_id, circle);
        }
      });
      group.append(circle);
    }
  }

  async function loadMap() {
    const map = $("[data-map]");
    if (map) map.setAttribute("aria-busy", "true");
    try {
      renderMap(await fetchAllCities());
    } catch (error) {
      showToast(`Map evidence could not be loaded: ${error.message}`);
    } finally {
      if (map) map.removeAttribute("aria-busy");
    }
  }

  async function setTier(tier) {
    state.tier = tier;
    state.cityOffset = 0;
    for (const card of $$('[data-tier]')) {
      const active = card.dataset.tier === tier;
      card.classList.toggle("active", active);
      card.setAttribute("aria-pressed", String(active));
    }
    setText("[data-city-browser-title]", tier === "all" ? "Highest available tier" : cityTierLabel(tier));
    await Promise.all([loadCities(), loadMap()]);
  }

  function statusClass(status) {
    const normalized = String(status).toLowerCase();
    if (normalized.includes("insufficient") || normalized.includes("failed") || normalized.includes("withheld")) return "negative";
    if (normalized.includes("complete")) return "completed";
    if (normalized.includes("screen")) return "screened";
    return normalized.replaceAll("_", "-");
  }

  function evidenceBadges(values, max = 3) {
    const items = Array.isArray(values) ? values : [];
    const visible = items.slice(0, max).map((value) => `<span class="evidence-badge">${escapeHTML(titleCase(value))}</span>`);
    if (items.length > max) visible.push(`<span class="evidence-badge">+${items.length - max}</span>`);
    return visible.join("") || '<span class="evidence-badge">Declared artifacts</span>';
  }

  function renderScenarioList(page) {
    state.scenarioPage = page;
    const body = $("[data-scenario-body]");
    if (!body) return;
    if (!page.items.length) {
      body.innerHTML = '<tr><td colspan="6"><div class="table-loading">No scenario executions match these filters.</div></td></tr>';
    } else {
      body.innerHTML = page.items
        .map(
          (scenario) => `
            <tr>
              <td><span class="scenario-title"><strong>${escapeHTML(scenario.title)}</strong><small>${escapeHTML(scenario.execution_id)}</small></span></td>
              <td>${escapeHTML(scenario.city_name)}<br><span class="kind-badge">${escapeHTML(scenario.kind)}</span></td>
              <td>${escapeHTML(titleCase(scenario.suite))}</td>
              <td><span class="evidence-stack">${evidenceBadges(scenario.evidence_types)}</span></td>
              <td><span class="status-badge ${escapeHTML(statusClass(scenario.status))}">${escapeHTML(titleCase(scenario.status))}</span></td>
              <td><button class="row-open" type="button" data-scenario-id="${escapeHTML(scenario.execution_id)}" aria-label="Open ${escapeHTML(scenario.title)}">→</button></td>
            </tr>`,
        )
        .join("");
    }
    const pagination = page.pagination;
    const first = pagination.total ? pagination.offset + 1 : 0;
    const last = pagination.offset + pagination.returned;
    setText("[data-scenario-page]", `${first}–${last} of ${formatNumber.format(pagination.total)}`);
    $("[data-scenario-prev]").disabled = pagination.offset === 0;
    $("[data-scenario-next]").disabled = pagination.next_offset === null;
  }

  async function loadScenarios() {
    const body = $("[data-scenario-body]");
    if (body) body.setAttribute("aria-busy", "true");
    try {
      const page = await api("/scenarios", {
        kind: state.scenarioKind === "all" ? "" : state.scenarioKind,
        status: state.scenarioStatus,
        q: state.scenarioQuery,
        limit: state.scenarioLimit,
        offset: state.scenarioOffset,
      });
      renderScenarioList(page);
    } catch (error) {
      if (body) body.innerHTML = `<tr><td colspan="6"><div class="table-loading">Unable to load scenario index: ${escapeHTML(error.message)}</div></td></tr>`;
    } finally {
      if (body) body.removeAttribute("aria-busy");
    }
  }

  function renderSuites(suites) {
    const grid = $("[data-suite-grid]");
    if (!grid) return;
    grid.innerHTML = suites
      .map((suite) => {
        const total = Math.max(1, suite.execution_count);
        const complete = (suite.completed_count / total) * 100;
        const negative = (suite.negative_count / total) * 100;
        return `
          <article class="suite-card" title="${escapeHTML(suite.claim_boundary)}">
            <span>${escapeHTML(titleCase(suite.suite))}</span>
            <strong>${formatNumber.format(suite.execution_count)}</strong>
            <small>${formatNumber.format(suite.design_count)} library designs · ${formatNumber.format(suite.template_count)} templates · ${formatNumber.format(suite.cities)} cities</small>
            <svg class="suite-meter" viewBox="0 0 100 4" preserveAspectRatio="none" aria-label="${complete.toFixed(0)} percent completed, ${negative.toFixed(0)} percent negative">
              <rect class="complete" x="0" y="0" width="${complete}" height="4"></rect>
              <rect class="negative" x="${complete}" y="0" width="${negative}" height="4"></rect>
            </svg>
          </article>`;
      })
      .join("");
  }

  async function loadSuites() {
    try {
      renderSuites(await api("/suites"));
    } catch (error) {
      const grid = $("[data-suite-grid]");
      if (grid) grid.innerHTML = `<div class="error-state">Suite evidence unavailable: ${escapeHTML(error.message)}</div>`;
    }
  }

  function designParams() {
    return {
      suite: state.designSuite,
      family_id: state.designFamily,
      decision_type: state.designType,
      implementation_status: state.designImplementation,
      current_readiness: state.designReadiness,
      q: state.designQuery,
      limit: state.designLimit,
      offset: state.designOffset,
    };
  }

  function renderDesigns(page) {
    state.designPage = page;
    const list = $("[data-design-list]");
    if (!list) return;
    if (!page.items.length) {
      list.innerHTML = '<div class="empty-state">No scenario designs match this evidence filter.</div>';
    } else {
      list.innerHTML = page.items
        .map(
          (design) => `
            <article class="design-row">
              <span class="design-order">${String(design.design_order).padStart(3, "0")}</span>
              <div class="design-identity">
                <div class="design-badges"><span class="decision-type">${escapeHTML(titleCase(design.decision_type))}</span><span class="implementation-badge ${escapeHTML(design.implementation_status)}">${escapeHTML(titleCase(design.implementation_status))}</span></div>
                <strong>${escapeHTML(design.title)}</strong>
                <p>${escapeHTML(design.decision_question)}</p>
                <small>${escapeHTML(titleCase(design.suite))} · ${escapeHTML(design.family_id)}</small>
              </div>
              <div class="design-outcome"><span>Primary outcome</span><strong>${escapeHTML(design.primary_outcome)}</strong><small>${escapeHTML(titleCase(design.current_readiness))}</small></div>
              <button class="row-open light" type="button" data-design-id="${escapeHTML(design.design_id)}" aria-label="Open ${escapeHTML(design.title)}">→</button>
            </article>`,
        )
        .join("");
    }
    const pagination = page.pagination;
    const first = pagination.total ? pagination.offset + 1 : 0;
    const last = pagination.offset + pagination.returned;
    setText("[data-design-page]", `${first}–${last} of ${formatNumber.format(pagination.total)}`);
    setText(
      "[data-design-browser-title]",
      state.designFamily ? `Family: ${state.designFamily}` : "All scenario designs",
    );
    $("[data-design-prev]").disabled = pagination.offset === 0;
    $("[data-design-next]").disabled = pagination.next_offset === null;
  }

  async function loadDesigns() {
    const list = $("[data-design-list]");
    if (list) list.setAttribute("aria-busy", "true");
    try {
      renderDesigns(await api("/designs", designParams()));
    } catch (error) {
      if (list) list.innerHTML = `<div class="error-state">Unable to load the scenario design index.<br>${escapeHTML(error.message)}</div>`;
    } finally {
      if (list) list.removeAttribute("aria-busy");
    }
  }

  function renderFamilies(page) {
    state.familyPage = page;
    const list = $("[data-family-list]");
    if (!list) return;
    if (!page.items.length) {
      list.innerHTML = '<div class="empty-state">No design families match this search.</div>';
      return;
    }
    list.innerHTML = page.items
      .map(
        (family) => `
          <article class="family-row ${state.designFamily === family.family_id ? "active" : ""}">
            <button class="family-filter" type="button" data-family-filter="${escapeHTML(family.family_id)}" aria-pressed="${state.designFamily === family.family_id}">
              <span class="family-order">${String(family.family_order).padStart(2, "0")}</span>
              <span><strong>${escapeHTML(family.title)}</strong><small>${escapeHTML(titleCase(family.suite))} · ${family.design_count} designs</small></span>
            </button>
            <button class="family-open" type="button" data-family-view="${escapeHTML(family.family_id)}" aria-label="Open ${escapeHTML(family.title)} family detail">↗</button>
          </article>`,
      )
      .join("");
  }

  async function loadFamilies() {
    const list = $("[data-family-list]");
    if (list) list.setAttribute("aria-busy", "true");
    try {
      renderFamilies(await api("/design-families", { q: state.familyQuery, limit: 100 }));
    } catch (error) {
      if (list) list.innerHTML = `<div class="error-state">Unable to load design families.<br>${escapeHTML(error.message)}</div>`;
    } finally {
      if (list) list.removeAttribute("aria-busy");
    }
  }

  function renderLibraryEvidence(evidence) {
    state.libraryEvidence = evidence;
    setText("[data-design-total]", formatNumber.format(evidence.design_count));
    setText("[data-family-total]", formatNumber.format(evidence.family_count));
    setText("[data-design-reference]", formatNumber.format(evidence.reference_implemented_designs));
    setText("[data-design-only]", formatNumber.format(evidence.design_only_scenarios));
    setText("[data-design-similarity]", Number(evidence.maximum_pairwise_similarity).toFixed(6));
    setText("[data-design-audit]", evidence.audit_passed ? "PASS" : "REVIEW");
  }

  async function loadLibraryEvidence() {
    try {
      renderLibraryEvidence(await api("/evidence/scenario-library"));
    } catch (error) {
      showToast(`Scenario-library evidence could not be loaded: ${error.message}`);
    }
  }

  function renderSources(page) {
    state.sourcePage = page;
    const list = $("[data-source-list]");
    if (!list) return;
    if (!page.items.length) {
      list.innerHTML = '<div class="empty-state">No source artifacts match this search.</div>';
    } else {
      list.innerHTML = page.items
        .map(
          (source) => `
            <article class="source-row" title="${escapeHTML(source.content_hash)}">
              <span class="source-identity"><strong>${escapeHTML(source.name)}</strong><small>${escapeHTML(source.publisher)} · ${escapeHTML(source.source_id)}</small></span>
              <span class="source-scope"><strong>${escapeHTML(source.geographic_scope)}</strong><small>${escapeHTML(source.temporal_scope)} · ${escapeHTML(source.license)}</small></span>
              <span class="source-count">${formatNumber.format(source.record_count)}<br>units</span>
            </article>`,
        )
        .join("");
    }
    const pagination = page.pagination;
    const first = pagination.total ? pagination.offset + 1 : 0;
    const last = pagination.offset + pagination.returned;
    setText("[data-source-page]", `${first}–${last} of ${formatNumber.format(pagination.total)}`);
    $("[data-source-prev]").disabled = pagination.offset === 0;
    $("[data-source-next]").disabled = pagination.next_offset === null;
  }

  async function loadSources() {
    const list = $("[data-source-list]");
    if (list) list.setAttribute("aria-busy", "true");
    try {
      renderSources(
        await api("/sources", {
          q: state.sourceQuery,
          limit: state.sourceLimit,
          offset: state.sourceOffset,
        }),
      );
    } catch (error) {
      if (list) list.innerHTML = `<div class="error-state">Unable to load sources.<br>${escapeHTML(error.message)}</div>`;
    } finally {
      if (list) list.removeAttribute("aria-busy");
    }
  }

  function benchmarkMethodValue(benchmark, needles) {
    const entries = Object.entries(benchmark.method_counts || {});
    return entries
      .filter(([key]) => needles.some((needle) => key.toLowerCase().includes(needle)))
      .reduce((sum, [, value]) => sum + Number(value || 0), 0);
  }

  function renderBenchmark(benchmark, deep) {
    window.civicDecisionBenchmark = benchmark;
    window.civicDecisionDeepEvidence = deep;
    setText("[data-benchmark-runs]", formatNumber.format(benchmark.run_artifacts));
    setText("[data-replays]", formatNumber.format(benchmark.historical_replays));
    setText("[data-optimizations]", formatNumber.format(benchmark.optimization_tasks));
    const forecasts = deep?.forecast_runs ?? benchmarkMethodValue(benchmark, ["forecast"]);
    const simulations = deep?.total_simulation_iterations ?? benchmarkMethodValue(benchmark, ["simulation", "monte"]);
    setText("[data-forecasts]", formatNumber.format(forecasts));
    setText("[data-simulations]", formatNumber.format(simulations));
  }

  async function loadBenchmark() {
    try {
      const [benchmark, deep] = await Promise.all([api("/benchmarks"), api("/evidence/deep")]);
      renderBenchmark(benchmark, deep);
    } catch (error) {
      showToast(`Benchmark evidence could not be loaded: ${error.message}`);
    }
  }

  function detailGrid(items) {
    return `<dl class="detail-grid">${items
      .map(([label, value]) => `<div><dt>${escapeHTML(label)}</dt><dd>${escapeHTML(formatValue(value))}</dd></div>`)
      .join("")}</dl>`;
  }

  function listSection(title, items) {
    if (!Array.isArray(items) || !items.length) return "";
    return `<section class="drawer-section"><h3>${escapeHTML(title)}</h3><ul>${items.map((item) => `<li>${escapeHTML(item)}</li>`).join("")}</ul></section>`;
  }

  function openDrawer({ kicker, title, body, sourceElement }) {
    const drawer = $("[data-drawer]");
    const backdrop = $("[data-drawer-backdrop]");
    if (!drawer || !backdrop) return;
    state.lastFocus = sourceElement || document.activeElement;
    setText("[data-drawer-kicker]", kicker);
    setText("[data-drawer-title]", title);
    $("[data-drawer-body]").innerHTML = body;
    backdrop.hidden = false;
    drawer.setAttribute("aria-hidden", "false");
    document.body.classList.add("drawer-open");
    requestAnimationFrame(() => {
      backdrop.classList.add("open");
      drawer.classList.add("open");
      $("[data-drawer-close]").focus();
    });
  }

  function closeDrawer() {
    const drawer = $("[data-drawer]");
    const backdrop = $("[data-drawer-backdrop]");
    if (!drawer || !backdrop || !drawer.classList.contains("open")) return;
    drawer.classList.remove("open");
    backdrop.classList.remove("open");
    drawer.setAttribute("aria-hidden", "true");
    document.body.classList.remove("drawer-open");
    window.setTimeout(() => {
      backdrop.hidden = true;
      if (state.lastFocus && typeof state.lastFocus.focus === "function") state.lastFocus.focus();
    }, 260);
  }

  function drawerLoading(kicker, title, sourceElement) {
    openDrawer({
      kicker,
      title,
      body: '<div class="skeleton-list"><span></span><span></span><span></span><span></span></div>',
      sourceElement,
    });
  }

  function renderCityDetail(detail) {
    const city = detail.city;
    const limitations = [...new Set([...(city.limitations || []), ...(detail.limitations || [])])];
    const metrics = detail.metrics
      .map(
        (metric) => `
          <article class="metric-item">
            <header><strong>${escapeHTML(metric.id)}</strong><span>${escapeHTML(formatValue(metric.value))} ${escapeHTML(metric.unit)}</span></header>
            <p>${escapeHTML(metric.interpretation)}</p>
          </article>`,
      )
      .join("");
    const capabilities = detail.capabilities
      .map(
        (capability) => `
          <article class="capability-item">
            <header><strong>${escapeHTML(capability.id)}</strong><span>${escapeHTML(titleCase(capability.status))}</span></header>
            <p>${escapeHTML(capability.diagnostics.join(" "))}</p>
          </article>`,
      )
      .join("");
    return `
      <p class="drawer-summary">${escapeHTML(city.readiness)}. This view reports the highest available evidence tier for the selected city.</p>
      <div class="detail-status-row"><span class="kind-badge">Tier ${escapeHTML(city.tier)}</span><span class="status-badge ${escapeHTML(statusClass(city.quality_status || "cataloged"))}">${escapeHTML(titleCase(city.quality_status || "cataloged"))}</span></div>
      ${detailGrid([
        ["City ID", city.city_id],
        ["Country", city.country_code],
        ["Coordinates", `${city.latitude.toFixed(4)}, ${city.longitude.toFixed(4)}`],
        ["Timezone", city.timezone],
        ["Source artifacts", city.source_artifact_count],
        ["Scenario work", city.scenario_count],
        ["Completed / negative", `${city.completed_scenarios} / ${city.negative_scenarios}`],
        ["Catalog population", city.source_population],
      ])}
      ${metrics ? `<section class="drawer-section"><h3>Typed metrics</h3><div class="metric-list">${metrics}</div></section>` : ""}
      ${capabilities ? `<section class="drawer-section"><h3>Capability assessments</h3><div class="capability-list">${capabilities}</div></section>` : ""}
      ${listSection("Data gaps", detail.data_gaps)}
      ${listSection("Limitations", limitations)}
      <section class="drawer-section"><h3>Source artifact identifiers</h3><div class="json-view">${escapeHTML(detail.source_artifact_ids.join("\n"))}</div></section>
      <section class="drawer-section"><h3>Provenance projection</h3><div class="json-view">${escapeHTML(JSON.stringify(detail.provenance, null, 2))}</div></section>`;
  }

  async function openCity(cityId, sourceElement) {
    drawerLoading("City evidence", cityId, sourceElement);
    try {
      const detail = await api(`/cities/${encodeURIComponent(cityId)}`);
      setText("[data-drawer-title]", detail.city.name);
      $("[data-drawer-body]").innerHTML = renderCityDetail(detail);
    } catch (error) {
      $("[data-drawer-body]").innerHTML = `<div class="error-state">Unable to open city evidence.<br>${escapeHTML(error.message)}</div>`;
    }
  }

  function renderScenarioDetail(detail) {
    const scenario = detail.scenario;
    const hashRows = Object.entries(detail.artifact_hashes || {});
    const actions = scenario.kind === "standard-screen"
      ? `<a href="${API}/scenarios/${encodeURIComponent(scenario.execution_id)}">View scenario JSON</a>`
      : `<a href="${API}/decision-packs/${encodeURIComponent(scenario.execution_id)}">View DecisionPack JSON</a><a href="${API}/decision-packs/${encodeURIComponent(scenario.execution_id)}/brief?format=markdown">Open decision brief</a>`;
    return `
      <p class="drawer-summary">${escapeHTML(scenario.readiness)}. Recommendation status is derived from the validated artifact, not inferred by this interface.</p>
      <div class="detail-status-row"><span class="kind-badge">${escapeHTML(scenario.kind)}</span><span class="status-badge ${escapeHTML(statusClass(scenario.status))}">${escapeHTML(titleCase(scenario.status))}</span>${evidenceBadges(scenario.evidence_types, 8)}</div>
      ${detailGrid([
        ["Execution ID", scenario.execution_id],
        ["Scenario / template", `${scenario.scenario_id}${scenario.template_id ? ` / ${scenario.template_id}` : ""}`],
        ["City", `${scenario.city_name} (${scenario.city_id})`],
        ["Suite", titleCase(scenario.suite)],
        ["Recommendation issued", scenario.recommendation_issued],
        ["Selected option", scenario.selected_option_id],
        ["Observed requests", scenario.observed_request_count],
        ["Content hash", compactHash(scenario.content_hash)],
      ])}
      ${listSection("Claim boundary", detail.claim_boundary)}
      ${listSection("Limitations", scenario.limitations)}
      ${hashRows.length ? `<section class="drawer-section"><h3>Analytical artifact hashes</h3><div class="json-view">${escapeHTML(hashRows.map(([key, value]) => `${key}\n  ${value}`).join("\n"))}</div></section>` : ""}
      <section class="drawer-section"><h3>Validated payload</h3><div class="json-view">${escapeHTML(JSON.stringify(detail.payload, null, 2))}</div></section>
      <div class="drawer-actions">${actions}</div>`;
  }

  async function openScenario(executionId, sourceElement) {
    drawerLoading("Scenario execution", executionId, sourceElement);
    try {
      const detail = await api(`/scenarios/${encodeURIComponent(executionId)}`);
      setText("[data-drawer-title]", detail.scenario.title);
      $("[data-drawer-body]").innerHTML = renderScenarioDetail(detail);
    } catch (error) {
      $("[data-drawer-body]").innerHTML = `<div class="error-state">Unable to open scenario evidence.<br>${escapeHTML(error.message)}</div>`;
    }
  }

  function renderDesignDetail(detail) {
    const design = detail.design;
    const family = detail.family;
    const objectives = (design.objectives || [])
      .map(
        (objective) => `
          <article class="contract-item ${objective.primary ? "primary" : ""}">
            <header><strong>${escapeHTML(objective.metric)}</strong><span>${escapeHTML(titleCase(objective.evidence_type))}</span></header>
            <p>${escapeHTML(titleCase(objective.sense))} · ${escapeHTML(objective.unit)}${objective.primary ? " · primary" : ""}</p>
          </article>`,
      )
      .join("");
    const constraints = (design.constraints || [])
      .map(
        (constraint) => `
          <article class="contract-item ${constraint.binding ? "binding" : ""}">
            <header><strong>${escapeHTML(titleCase(constraint.kind))}</strong><span>${constraint.binding ? "Binding" : constraint.hard ? "Hard" : "Soft"}</span></header>
            <p>${escapeHTML(constraint.description)}</p>
          </article>`,
      )
      .join("");
    const gate = design.release_gate;
    const implementationNote = design.reference_implementation_note
      ? `<section class="drawer-section reference-note"><h3>Reference implementation scope</h3><p>${escapeHTML(design.reference_implementation_note)}</p></section>`
      : "";
    return `
      <p class="drawer-summary">${escapeHTML(design.intended_claim)}</p>
      <div class="detail-status-row"><span class="kind-badge">${escapeHTML(titleCase(design.decision_type))}</span><span class="status-badge ${escapeHTML(statusClass(design.implementation_status))}">${escapeHTML(titleCase(design.implementation_status))}</span><span class="status-badge">${escapeHTML(titleCase(design.current_readiness))}</span>${evidenceBadges(design.evidence_requirements, 8)}</div>
      ${detailGrid([
        ["Design order", design.design_order],
        ["Design ID", design.design_id],
        ["Family", `${family.title} (${family.family_id})`],
        ["Application suite", titleCase(design.suite)],
        ["Decision owner", design.decision_owner],
        ["Affected system", design.affected_system],
        ["Horizon / cadence", `${titleCase(design.horizon)} / ${design.decision_cadence}`],
        ["Spatial unit", titleCase(design.spatial_unit)],
        ["Reference template", design.existing_template_ref],
        ["City bindings", design.city_bindings.length],
        ["New method claimed", design.method_claimed],
        ["Similarity audit maximum", detail.audit_maximum_pairwise_similarity],
      ])}
      <section class="drawer-section"><h3>Decision question</h3><p>${escapeHTML(design.decision_question)}</p></section>
      <section class="drawer-section"><h3>Baseline</h3><p>${escapeHTML(design.baseline)}</p></section>
      ${listSection("Alternatives", design.alternatives)}
      <section class="drawer-section"><h3>Objectives</h3><div class="contract-list">${objectives}</div></section>
      <section class="drawer-section"><h3>Constraints</h3><div class="contract-list">${constraints}</div></section>
      <section class="drawer-section evidence-gate-detail"><h3>Evidence release gate</h3>${detailGrid([
        ["Gate type", titleCase(gate.gate_type)],
        ["Pass condition", gate.pass_condition],
        ["Failure status", titleCase(gate.failure_status)],
      ])}<p><strong>Required negative release:</strong> ${escapeHTML(gate.failure_release)}</p></section>
      ${listSection("Required source roles", design.required_source_roles.map(titleCase))}
      ${listSection("Analysis modes", design.analysis_modes.map(titleCase))}
      ${implementationNote}
      ${listSection("Assumptions", design.assumptions)}
      ${listSection("Limitations", design.limitations)}
      ${listSection("Prohibited claims", design.prohibited_claims)}
      ${listSection("Transportability risks", design.transportability_risks)}
      ${listSection("Library claim boundary", detail.library_claim_boundary)}
      <div class="drawer-actions"><a href="${API}/designs/${encodeURIComponent(design.design_id)}">View design JSON</a><a href="${API}/design-families/${encodeURIComponent(family.family_id)}">View family JSON</a></div>`;
  }

  async function openDesign(designId, sourceElement) {
    drawerLoading("Scenario design", designId, sourceElement);
    try {
      const detail = await api(`/designs/${encodeURIComponent(designId)}`);
      setText("[data-drawer-title]", detail.design.title);
      $("[data-drawer-body]").innerHTML = renderDesignDetail(detail);
    } catch (error) {
      $("[data-drawer-body]").innerHTML = `<div class="error-state">Unable to open scenario design.<br>${escapeHTML(error.message)}</div>`;
    }
  }

  function renderFamilyDetail(detail) {
    const family = detail.family;
    const designs = detail.designs
      .map(
        (design) => `
          <button class="family-design-link" type="button" data-design-id="${escapeHTML(design.design_id)}">
            <span>${String(design.design_order).padStart(3, "0")}</span>
            <strong>${escapeHTML(design.title)}</strong>
            <small>${escapeHTML(titleCase(design.decision_type))} · ${escapeHTML(titleCase(design.implementation_status))}</small>
          </button>`,
      )
      .join("");
    return `
      <p class="drawer-summary">${escapeHTML(family.description)}</p>
      ${detailGrid([
        ["Family order", family.family_order],
        ["Family ID", family.family_id],
        ["Application suite", titleCase(family.suite)],
        ["Affected system", family.affected_system],
        ["Decision owner", family.decision_owner],
        ["Design contracts", detail.designs.length],
      ])}
      <section class="drawer-section"><h3>Eight decision types</h3><div class="family-design-links">${designs}</div></section>
      ${listSection("Common source roles", family.common_source_roles.map(titleCase))}
      ${listSection("Family claim boundary", family.claim_boundary)}
      ${listSection("Library claim boundary", detail.library_claim_boundary)}
      <div class="drawer-actions"><a href="${API}/design-families/${encodeURIComponent(family.family_id)}">View family JSON</a></div>`;
  }

  async function openFamily(familyId, sourceElement) {
    drawerLoading("Scenario family", familyId, sourceElement);
    try {
      const detail = await api(`/design-families/${encodeURIComponent(familyId)}`);
      setText("[data-drawer-title]", detail.family.title);
      $("[data-drawer-body]").innerHTML = renderFamilyDetail(detail);
    } catch (error) {
      $("[data-drawer-body]").innerHTML = `<div class="error-state">Unable to open design family.<br>${escapeHTML(error.message)}</div>`;
    }
  }

  function openLibraryEvidence(sourceElement) {
    const evidence = state.libraryEvidence;
    if (!evidence) {
      showToast("Scenario-library evidence is still loading.");
      return;
    }
    openDrawer({
      kicker: "Anti-duplication evidence",
      title: "240-design audit",
      sourceElement,
      body: `
        <p class="drawer-summary">The audit establishes structural completeness and transparent lexical separation. It does not establish academic novelty, external domain correctness, deployment, adoption, or impact.</p>
        ${detailGrid([
          ["Audit status", evidence.audit_passed ? "PASS" : "REVIEW"],
          ["Designs / families", `${evidence.design_count} / ${evidence.family_count}`],
          ["Reference / design-only", `${evidence.reference_implemented_designs} / ${evidence.design_only_scenarios}`],
          ["City-bound executions counted", evidence.city_bound_executions_counted],
          ["Methods claimed", evidence.methods_claimed],
          ["Similarity threshold", evidence.high_similarity_threshold],
          ["Maximum similarity", evidence.maximum_pairwise_similarity],
          ["High-similarity pairs", evidence.high_similarity_pair_count],
          ["Signature collisions", evidence.exact_signature_collision_count],
          ["Duplicate titles", evidence.duplicate_title_count],
          ["Duplicate questions", evidence.duplicate_question_count],
          ["Artifact-set hash", compactHash(evidence.artifact_set_hash)],
        ])}
        ${listSection("Verified invariants", evidence.invariants)}
        ${listSection("Claim boundary", evidence.claim_boundary)}
        ${listSection("Audit limitations", evidence.limitations)}
        <div class="drawer-actions"><a href="${API}/evidence/scenario-library">View evidence JSON</a></div>`,
    });
  }

  function openBenchmark(sourceElement) {
    const benchmark = window.civicDecisionBenchmark;
    const deep = window.civicDecisionDeepEvidence;
    if (!benchmark) {
      showToast("Benchmark evidence is still loading.");
      return;
    }
    const methods = Object.entries(benchmark.method_counts || {}).map(([key, value]) => `${titleCase(key)}: ${formatNumber.format(value)}`);
    const statuses = Object.entries(benchmark.status_counts || {}).map(([key, value]) => `${titleCase(key)}: ${formatNumber.format(value)}`);
    openDrawer({
      kicker: "Analytical evidence",
      title: "Benchmark inventory",
      sourceElement,
      body: `
        <p class="drawer-summary">A typed projection of the committed analytical benchmark summary and the separate Tier-D execution evidence.</p>
        ${detailGrid([
          ["Summary ID", benchmark.summary_id],
          ["Artifact set hash", compactHash(benchmark.artifact_set_hash)],
          ["Run artifacts", benchmark.run_artifacts],
          ["Historical replays", benchmark.historical_replays],
          ["Replay training values", benchmark.replay_training_values],
          ["Replay holdout values", benchmark.replay_holdout_values],
          ["Optimization tasks", benchmark.optimization_tasks],
          ["Search space", benchmark.optimization_search_space],
          ["Evaluated plans", benchmark.optimization_evaluated_plans],
          ["Feasible plans", benchmark.optimization_feasible_plans],
          ["Engine qualifications", benchmark.engine_qualification_runs],
          ["Tier-D simulation iterations", deep?.total_simulation_iterations],
          ["Tier-D uncertainty values", deep?.total_uncertainty_option_draw_values],
          ["Underlying municipal requests", deep?.deduplicated_underlying_requests],
        ])}
        ${listSection("Method counts", methods)}
        ${listSection("Optimization statuses", statuses)}
        ${listSection("Benchmark limitations", benchmark.limitations)}
        ${deep ? listSection("Tier-D evidence limitations", deep.limitations) : ""}`,
    });
  }

  function setupNavigation() {
    const menu = $("[data-menu]");
    const nav = $("[data-nav]");
    menu?.addEventListener("click", () => {
      const open = !nav.classList.contains("open");
      nav.classList.toggle("open", open);
      menu.setAttribute("aria-expanded", String(open));
    });
    for (const link of $$("a", nav)) {
      link.addEventListener("click", () => {
        nav.classList.remove("open");
        menu?.setAttribute("aria-expanded", "false");
      });
    }
    $("[data-scroll-boundaries]")?.addEventListener("click", () => $("#methods")?.scrollIntoView());
  }

  function selectDesignFamily(familyId) {
    state.designFamily = familyId;
    state.designOffset = 0;
    const clear = $("[data-clear-family]");
    if (clear) clear.hidden = !familyId;
    if (state.familyPage) renderFamilies(state.familyPage);
    loadDesigns();
  }

  function setupInteractions() {
    for (const card of $$('[data-tier]')) card.addEventListener("click", () => setTier(card.dataset.tier));

    $("[data-city-search]")?.addEventListener(
      "input",
      debounce((event) => {
        state.cityQuery = event.target.value.trim();
        state.cityOffset = 0;
        Promise.all([loadCities(), loadMap()]);
      }),
    );
    $("[data-city-prev]")?.addEventListener("click", () => {
      state.cityOffset = Math.max(0, state.cityOffset - state.cityLimit);
      loadCities();
    });
    $("[data-city-next]")?.addEventListener("click", () => {
      if (state.cityPage?.pagination.next_offset !== null) {
        state.cityOffset = state.cityPage.pagination.next_offset;
        loadCities();
      }
    });
    $("[data-city-list]")?.addEventListener("click", (event) => {
      const button = event.target.closest("[data-city-id]");
      if (button) openCity(button.dataset.cityId, button);
    });

    for (const pill of $$('[data-kind]')) {
      pill.addEventListener("click", () => {
        state.scenarioKind = pill.dataset.kind;
        state.scenarioOffset = 0;
        for (const item of $$('[data-kind]')) {
          const active = item === pill;
          item.classList.toggle("active", active);
          item.setAttribute("aria-pressed", String(active));
        }
        loadScenarios();
      });
    }
    $("[data-scenario-status]")?.addEventListener("change", (event) => {
      state.scenarioStatus = event.target.value;
      state.scenarioOffset = 0;
      loadScenarios();
    });
    $("[data-scenario-search]")?.addEventListener(
      "input",
      debounce((event) => {
        state.scenarioQuery = event.target.value.trim();
        state.scenarioOffset = 0;
        loadScenarios();
      }),
    );
    $("[data-scenario-prev]")?.addEventListener("click", () => {
      state.scenarioOffset = Math.max(0, state.scenarioOffset - state.scenarioLimit);
      loadScenarios();
    });
    $("[data-scenario-next]")?.addEventListener("click", () => {
      if (state.scenarioPage?.pagination.next_offset !== null) {
        state.scenarioOffset = state.scenarioPage.pagination.next_offset;
        loadScenarios();
      }
    });
    $("[data-scenario-body]")?.addEventListener("click", (event) => {
      const button = event.target.closest("[data-scenario-id]");
      if (button) openScenario(button.dataset.scenarioId, button);
    });

    $("[data-design-search]")?.addEventListener(
      "input",
      debounce((event) => {
        state.designQuery = event.target.value.trim();
        state.designOffset = 0;
        loadDesigns();
      }),
    );
    const designSelects = [
      ["[data-design-suite]", "designSuite"],
      ["[data-design-type]", "designType"],
      ["[data-design-implementation]", "designImplementation"],
      ["[data-design-readiness]", "designReadiness"],
    ];
    for (const [selector, key] of designSelects) {
      $(selector)?.addEventListener("change", (event) => {
        state[key] = event.target.value;
        state.designOffset = 0;
        loadDesigns();
      });
    }
    $("[data-design-prev]")?.addEventListener("click", () => {
      state.designOffset = Math.max(0, state.designOffset - state.designLimit);
      loadDesigns();
    });
    $("[data-design-next]")?.addEventListener("click", () => {
      if (state.designPage?.pagination.next_offset !== null) {
        state.designOffset = state.designPage.pagination.next_offset;
        loadDesigns();
      }
    });
    $("[data-design-list]")?.addEventListener("click", (event) => {
      const button = event.target.closest("[data-design-id]");
      if (button) openDesign(button.dataset.designId, button);
    });
    $("[data-family-search]")?.addEventListener(
      "input",
      debounce((event) => {
        state.familyQuery = event.target.value.trim();
        loadFamilies();
      }),
    );
    $("[data-family-list]")?.addEventListener("click", (event) => {
      const view = event.target.closest("[data-family-view]");
      if (view) {
        openFamily(view.dataset.familyView, view);
        return;
      }
      const filter = event.target.closest("[data-family-filter]");
      if (filter) selectDesignFamily(filter.dataset.familyFilter);
    });
    $("[data-clear-family]")?.addEventListener("click", () => selectDesignFamily(""));
    $("[data-open-library-evidence]")?.addEventListener("click", (event) =>
      openLibraryEvidence(event.currentTarget),
    );

    $("[data-source-search]")?.addEventListener(
      "input",
      debounce((event) => {
        state.sourceQuery = event.target.value.trim();
        state.sourceOffset = 0;
        loadSources();
      }),
    );
    $("[data-source-prev]")?.addEventListener("click", () => {
      state.sourceOffset = Math.max(0, state.sourceOffset - state.sourceLimit);
      loadSources();
    });
    $("[data-source-next]")?.addEventListener("click", () => {
      if (state.sourcePage?.pagination.next_offset !== null) {
        state.sourceOffset = state.sourcePage.pagination.next_offset;
        loadSources();
      }
    });

    $("[data-open-benchmark]")?.addEventListener("click", (event) => openBenchmark(event.currentTarget));
    $("[data-drawer-body]")?.addEventListener("click", (event) => {
      const design = event.target.closest("[data-design-id]");
      if (design) openDesign(design.dataset.designId, design);
    });
    $("[data-drawer-close]")?.addEventListener("click", closeDrawer);
    $("[data-drawer-backdrop]")?.addEventListener("click", closeDrawer);
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") closeDrawer();
      if (event.key === "Tab" && $("[data-drawer]")?.classList.contains("open")) {
        const focusable = $$('a[href], button:not([disabled]), input, select, [tabindex]:not([tabindex="-1"])', $("[data-drawer]"));
        if (!focusable.length) return;
        const first = focusable[0];
        const last = focusable.at(-1);
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    });
  }

  function setupReveal() {
    if (!("IntersectionObserver" in window)) {
      for (const node of $$(".reveal")) node.classList.add("revealed");
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            entry.target.classList.add("revealed");
            observer.unobserve(entry.target);
          }
        }
      },
      { threshold: 0.12 },
    );
    for (const node of $$(".reveal")) observer.observe(node);
  }

  async function initialize() {
    setupNavigation();
    setupInteractions();
    setupReveal();
    try {
      await loadSystem();
      await Promise.all([
        loadCities(),
        loadMap(),
        loadDesigns(),
        loadFamilies(),
        loadLibraryEvidence(),
        loadScenarios(),
        loadSuites(),
        loadSources(),
        loadBenchmark(),
      ]);
    } catch {
      // The health state and toast already expose the catalog failure.
    }
  }

  initialize();
})();
