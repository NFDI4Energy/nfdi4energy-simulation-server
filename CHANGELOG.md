# Changelog
All notable changes to this project will be documented in this file.

The format is inspired from [Keep a Changelog](http://keepachangelog.com/en/1.0.0/)
and the versioning aim to respect [Semantic Versioning](http://semver.org/spec/v2.0.0.html).

Here is a template for new release sections

```
## [_._._] - 20XX-MM-DD

### Added
-
### Changed
-
### Removed
-
```

## [Unreleased]

### Added
- endpoints for mvs simulation (#1)
- index page (#1)
- mvs version number on index page (#6)
- disclaimer about data safety on index page (#9)
- input json is returned in case of EPA->MVS conversion or simulation error (#9)
- possibility to pin mvs version centrally in `.env` file (#12)
- backend test suite under `fastapi_app/tests/` (Mosaik toggle) (roadmap #4)
- planning documents: `ROADMAP.md`, `TODO.md`, DaceDSX patch inventory, agent prompt
- backend tests for settings, storage containment, scenario validation, submission
  and authentication; `requirements-dev.txt`, `pytest.ini` (roadmap #10)
- GitHub Actions CI: flake8, pytest, frontend tests, `svelte-check`, Vite build,
  web image build with smoke test (roadmap #11)
- `SIMAAS_ENV` setting; `AUTH_DISABLED=true` is refused unless it is `development` (roadmap #12)

### Changed
- Fixed async function (#5)
- Convert json from EPA to MVS format (#6)
- web image: `python:3.12-slim` base, pinned `fastapi_app/requirements.txt`, non-root user
  (UID 1000), dashboard built in a Node stage; build context is the repository root (roadmap #8, #9)
- session cookie is `SameSite=Lax`; `SESSION_HTTPS_ONLY` keeps controlling `Secure` (roadmap #12)
- `task_queue/requirements.txt` pinned (roadmap #9)
- pandapower wrapper image refuses pickle networks and pandapower JSON that references
  classes outside pandapower/pandas; same fix as upstream DaceDSX PR 0 (roadmap #3)

### Removed
- `simservice/nohup.out`, a stray Minikube mount log with a local home path (roadmap #2)
- runtime task data under `data/resources/` and `data/results/` and the built dashboard
  `fastapi_app/static/svelte-dist/` are no longer tracked (roadmap #7, #8)






