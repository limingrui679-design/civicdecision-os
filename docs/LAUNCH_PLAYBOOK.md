# Evidence-first launch playbook

The launch message should make one narrow job understandable: CivicDecision OS records why an
urban intervention analysis may release a bounded result—or refuse to recommend one. It should
not lead with repository size, test counts, or a request for stars.

## Canonical story

**Question:** When should an urban analytics system refuse to recommend an intervention?

**Demonstration:** The Suffolk heat-access reference pair uses the same bounded public-data
sample. One declared configuration produces 16 feasible combinations from 55 evaluated. A
deliberately infeasible configuration evaluates 10 combinations, finds none feasible, and retains
the failure reason and evidence gaps.

**Boundary:** This is reproducible software behavior over public-data fixtures, not a verified
facility plan, municipal recommendation, deployment, adoption, or impact result.

## Short announcement

> Urban analytics tools often make the successful result easy to show and the refusal path hard
> to inspect. CivicDecision OS treats both as first-class artifacts. Its public walkthrough shows
> the same bounded heat-access case completing under one declared configuration and withholding a
> recommendation under another—while keeping observed, estimated, simulated, optimized, and
> proposed evidence separate. Explore the walkthrough, then reproduce the DecisionPacks from the
> tagged release.

Links to include:

- Public walkthrough: <https://civicdecision-os.limingrui2.chatgpt.site>
- Repository: <https://github.com/limingrui679-design/civicdecision-os>
- Release: <https://github.com/limingrui679-design/civicdecision-os/releases/tag/v0.8.0>
- Reviewer protocol: <https://github.com/limingrui679-design/civicdecision-os/blob/main/docs/EXTERNAL_REVIEW.md>

## Technical-community version

> CivicDecision OS is an evidence-typed Python compiler and read-only explorer for urban
> intervention screening. The v0.8.0 snapshot keeps negative releases, hard-constraint failures,
> reversal tests, source hashes, and value-of-information inside reproducible DecisionPacks. The
> release provides a wheel, sdist, no-Git source ZIP, SBOM, checksums, and a full verifier. I am
> looking for scoped reproduction and urban-domain review—not endorsements or unqualified impact
> claims.

## Distribution sequence

1. Publish the release and public walkthrough before announcing it.
2. Ask two or three relevant practitioners to reproduce or review one named case privately; do
   not ask them to endorse the project.
3. Share the case in geospatial, civic-tech, urban-planning, open-data, PyData, and decision-support
   communities whose rules permit project demonstrations.
4. Submit only to curated lists whose inclusion criteria the repository already satisfies.
5. Answer technical criticism with artifacts, hashes, and scoped limitations.
6. Convert repeated questions into documentation or issues instead of increasing claim strength.

Do not claim that a community, reviewer, municipality, or user participated until a public or
permissioned record confirms it.

## Launch review checklist

- [ ] The link preview shows the correct project name and evidence-gate figures.
- [ ] The first screen identifies the user and job without requiring compiler terminology.
- [ ] The walkthrough and release links work without authentication.
- [ ] The wheel, sdist, source ZIP, checksums, and SBOM download directly.
- [ ] The golden completed and negative runs reproduce from the named tag.
- [ ] Every launch statement has a repository, release, or external-review source.
- [ ] No star, adoption, deployment, user-impact, or external-validation claim is implied.
