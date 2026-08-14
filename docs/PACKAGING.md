# Installation and package publication

## Current supported paths

The release page exposes the verified wheel, sdist, no-Git source ZIP, complete release bundle,
portable checksums, SBOM, and release report as separate assets. The wheel is suitable for CLI,
SDK, API, and Web package smoke tests; the full repository or source ZIP is required for the
committed artifact catalog and golden rebuild workflows.

```bash
python -m pip install \
  https://github.com/limingrui679-design/civicdecision-os/releases/download/v0.8.1/civicdecision-0.8.1-py3-none-any.whl
civicdecision version
```

For the full Evidence Explorer, clone or extract the repository and run:

```bash
python -m pip install -e '.[api]'
civicdecision serve --root . --host 127.0.0.1 --port 8000
```

## PyPI status

The `civicdecision` distribution is not claimed as published on PyPI. Before publication, the
maintainer must configure a PyPI trusted publisher for the exact GitHub repository, workflow, and
release environment; verify the project name; and publish an immutable tagged candidate. Do not
store an API token in the repository or upload an untagged working-tree build under an existing
version.

The tag-triggered `Publish release assets` workflow intentionally publishes to GitHub Releases
only. Adding a PyPI step requires a separate reviewed change after trusted publishing is configured.
