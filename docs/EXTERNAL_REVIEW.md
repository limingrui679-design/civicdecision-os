# Independent review and reproduction protocol

This protocol creates a public place for third parties to test CivicDecision OS without turning a
successful software run into a claim of urban-domain correctness or real-world impact.

**Current state:** no external reviewer is assigned and no independent reproduction is claimed.

## Review tracks

### Track A — clean-environment reproduction

The reviewer checks out an immutable release, records the operating system and Python version,
installs from the release wheel or sdist, and reproduces:

1. the completed Suffolk heat-access DecisionPack;
2. the deliberately infeasible companion DecisionPack;
3. the full repository verifier from a no-Git source archive;
4. the expected content hashes and portable checksum verification.

The report must distinguish *reproduced on the reviewer's environment* from *independently
validated method or policy conclusion*.

### Track B — urban-domain and source-semantics review

The reviewer examines whether:

- source records are described with the correct observational unit;
- reporting, selection, aggregation, spatial, temporal, and licensing limits are visible;
- facility, travel, demand, cost, capacity, equity, and effect assumptions are labeled correctly;
- evidence gates prevent unsupported recommendation and causal language;
- the value-of-information list identifies evidence that could materially change the result.

Domain review should identify the reviewer's field and scope. It is not a municipal endorsement.

### Track C — analytical and governance review

The reviewer checks method implementation, qualification boundaries, hard-constraint behavior,
infeasibility, reversal tests, packaging, security controls, and claim auditing. Findings should
cite files, commands, versions, and minimal reproductions.

## Minimum evidence for a public review record

- reviewer identity or declared pseudonymous status;
- conflicts of interest and relationship to the maintainer;
- immutable release tag and commit;
- environment and installation path;
- exact commands and exit codes;
- expected and observed hashes;
- findings separated into software, method, domain, and claim-language categories;
- unresolved limitations;
- an explicit statement of what the review does **not** establish.

Use the repository's **Independent reproduction** issue form. Maintainer replies must not rewrite
the reviewer's conclusion. Corrections should be linked as new commits or follow-up records.

## Suggested reviewer conclusion vocabulary

- **Reproduced:** the stated artifact or test result was obtained from the named release.
- **Not reproduced:** the stated result was not obtained; diagnostics are attached.
- **Method finding:** a scoped implementation or qualification observation.
- **Domain finding:** a scoped source-semantic or urban-context observation.
- **Not reviewed:** outside the reviewer's declared scope.

Do not use *validated*, *effective*, *deployed*, *adopted*, *impactful*, or *policy-ready* without
separate evidence that directly supports that exact term.
