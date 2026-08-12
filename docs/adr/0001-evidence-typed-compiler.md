# ADR 0001: Build an evidence-typed compiler, not a dashboard collection

- Status: accepted
- Date: 2026-08-12

## Context

Urban analytics repositories often accumulate notebooks, maps, and models without a stable path
from source evidence to a decision artifact. A visually strong dashboard can obscure whether an
output was observed, estimated, simulated, or merely proposed.

## Decision

The central product is a compiler from City Adapter plus Policy Scenario plus versioned sources
to a DecisionPack. Every output is assigned one of six evidence types and passes type-specific
validation. User interfaces consume the compiled pack instead of maintaining parallel claims.

## Consequences

The architecture supports multiple cities, engines, and interfaces without weakening lineage.
It also adds upfront protocol work and can reject convenient but unsupported outputs. This is an
intentional trade: a failed compile is preferable to a polished unsupported recommendation.
