import assert from "node:assert/strict";
import test from "node:test";

async function requestPath(path = "/") {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);
  return worker.fetch(new Request(`http://localhost${path}`, { headers: { accept: "text/html" } }), {
    ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) },
  }, { waitUntil() {}, passThroughOnException() {} });
}

test("renders the CivicDecision public walkthrough", async () => {
  const response = await requestPath();
  assert.equal(response.status, 200);
  const html = await response.text();
  assert.match(html, /CivicDecision OS · Auditable urban intervention analysis/);
  assert.match(html, /Urban decisions/);
  assert.match(html, /Suffolk heat access/);
  assert.match(html, /76 \/ 96/);
  assert.match(html, /20 withheld/);
  assert.match(html, /Simulation ≠ observed impact/);
  assert.doesNotMatch(html, /codex-preview|Your site is taking shape|react-loading-skeleton/i);
});

test("exposes bounded build identity without upgrading public evidence", async () => {
  const response = await requestPath("/build-info.json");
  assert.equal(response.status, 200);
  assert.equal(response.headers.get("cache-control"), "no-store");
  assert.equal(response.headers.get("x-content-type-options"), "nosniff");
  const payload = await response.json();
  assert.equal(payload.project, "CivicDecision OS");
  assert.equal(payload.packageVersion, "0.8.1");
  assert.equal(payload.repository, "limingrui679-design/civicdecision-os");
  assert.match(payload.evidenceBoundary, /not evidence of production deployment/);
});
