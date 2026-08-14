# Adoption and discovery metrics

Stars are a lagging, platform-specific signal. Review the full path from discovery to independent
use and do not interpret a clone, download, or star as municipal adoption.

## Weekly funnel

| Stage | Observable signal | Limitation |
|---|---|---|
| Discovery | GitHub unique visitors and referrers | Traffic data are retained for a limited window and can update with delay. |
| Evaluation | Popular paths, README/documentation visits | A page view does not prove comprehension. |
| Trial | Unique clones and release-asset downloads | Automation and repeat downloads can inflate counts. |
| Reproduction | Completed external reproduction issue with commands and hashes | Reproduction is not domain validation. |
| Contribution | External issue, discussion, or accepted pull request | A contribution is not adoption. |
| Use | Permissioned user report naming version and task | Self-report is not independent impact evidence. |
| Institutional outcome | Public deployment/adoption/impact record | Requires separate authorization and evaluation. |

The repository script below collects only GitHub-owned signals available to an authenticated
repository owner:

```bash
GITHUB_TOKEN=... python scripts/collect_github_funnel.py \
  --repo limingrui679-design/civicdecision-os \
  --output github-funnel.json
```

Do not paste a token into chat, logs, committed files, or shell history. The scheduled workflow
stores each report as a private Actions artifact rather than committing traffic data to the public
repository.

## Decision rules

- If unique visitors remain zero, improve metadata and distribution before adding features.
- If visitors rise but walkthrough/release paths do not, simplify the first screen and links.
- If clones rise but reproductions do not, reduce installation and verification friction.
- If reproductions succeed but external contributions do not, add smaller scoped issues and
  maintainer response expectations.
- Increase impact language only when separately reviewed evidence supports it; never infer it from
  GitHub traffic.
