# Verification evidence

`milestone-0.json` is produced by:

```bash
python scripts/verify_repository.py --report verification/milestone-0.json
```

The verifier uses a temporary directory, regenerates all three public JSON Schemas, validates
every committed protocol document, verifies each source artifact against its manifest, checks
portable SHA256SUMS files, rebuilds the completed and infeasible reference workflows, and requires
byte-for-byte equality with the committed JSON and Markdown outputs.

The report establishes repository integrity for this bounded milestone. It does not establish
policy correctness, causal validity, production deployment, external review, real users, or
real-world impact.
