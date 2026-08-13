# Evidence explorer

The packaged browser interface is a dependency-free projection of the read-only API. It is not a
separate dashboard database and does not compute new recommendations in JavaScript.

## Views

- verified catalog headline metrics and catalog fingerprint;
- Tier G, S, D, or highest-available city coverage;
- searchable city index and coordinate-based world overview;
- typed city details, metrics, capability assessments, data gaps, source IDs, and provenance;
- six scenario-library audit indicators, including the separate reference/design-only counts;
- explicit zero city-binding and zero method-claim indicators;
- all 30 domain families with family-to-eight-design filtering;
- 240 scenario designs filterable by suite, family, decision type, implementation status,
  readiness, and normalized text search;
- design details containing baseline, alternatives, objectives, constraints, evidence gate, source
  roles, assumptions, limitations, prohibited claims, and transportability risks;
- family details containing all eight ordered decision types and shared claim boundaries;
- anti-duplication evidence for all 28,680 unordered design pairs;
- deep execution completion/negative-release ratios by application suite;
- filterable standard, deep, and reference scenario ledger;
- scenario drawer with recommendation status, claim boundary, limitations, artifact hashes, and
  validated native payload;
- source-manifest inventory;
- benchmark and Tier-D workload evidence; and
- an explicit supported/not-claimed interpretation contract.

The map uses catalog point coordinates. It does not draw or imply official administrative
boundaries. Scenario completion is not presented as intervention success.

## Accessibility and responsive behavior

The interface uses semantic headings, landmarks, tables, native controls, visible focus states,
skip navigation, labelled map controls, keyboard-operable drawers, focus return, focus trapping,
Escape-to-close, live loading regions, reduced-motion support, and a print stylesheet. The layout
was inspected at the default desktop viewport and a 390 × 844 mobile viewport. Mobile inspection
confirmed a dedicated navigation control, family selection, exact eight-design filtering, drawer
interaction, and zero horizontal scroll. Desktop inspection confirmed compound filters,
punctuation-normalized search, audit/detail drawers, and zero browser warnings or errors.

## Runtime boundary

All assets are packaged under `src/civicdecision/web/`. There are no external runtime assets and
the Content Security Policy permits scripts, styles, images, and API connections only from the
same origin, with `data:` permitted for images. The browser uses bounded collection pages and
never sends user or catalog data to a third party.

Local browser inspection confirms rendering and interaction for the current build. It is not a
public hosted-demo availability check and does not satisfy the external accessibility-audit,
cross-browser, performance-budget, or penetration-test release gates.
