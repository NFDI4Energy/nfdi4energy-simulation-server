# Phase 0: immediate privacy and security fixes

## Goal

Remove leaked local data, decide how Mosaik is exposed, and close the
code-execution hole in the pandapower wrapper, both upstream in DaceDSX and in
the wrapper copy that SimaaS builds today.

**Rebased on 2026-11-12** onto `main` @ 724c9bf, which meanwhile gained an
authenticated Mosaik editor gateway, per-task Mosaik pods, task-scoped wrapper
mounts, broker authentication and a Traefik ingress (roadmap steps 38, 39, 41,
47, 55 in part). The original "Mosaik off by default" change of step 4 was
dropped during the rebase on the maintainer's decision; see step 4 below.

## Branches and base

| Unit | Repo | Branch | Base | Steps |
|---|---|---|---|---|
| 0a | SimaaS | `roadmap/phase-0a-cleanup-mosaik-off` | `main` @ 724c9bf (rebased; originally 226ae7a) | 2, 4, docs |
| 0b | DaceDSX | `simaas/pr0-pandapower-safe-load` | `main` @ 1d82385 (= `origin/main`) | 3 (PR 0) |
| 0c | SimaaS | `roadmap/phase-0c-pandapower-guard` | 0a | 3 applied to the SimaaS wrapper copy |

0c is not a roadmap step of its own. It exists because `simservice/PandaPowerWrapper`
is the image the SimaaS deployment runs until Phase 3 switches to the registry
image, so the upstream fix alone would leave the deployment open.

## Steps

### 0a

| Step | Commit | What changed |
|---|---|---|
| – | `docs: add roadmap, TODO list and DaceDSX patch inventory` | The planning documents were untracked; without them the roadmap ticks could not be committed. |
| 2 | `chore(simservice): remove nohup.out with local paths` | `git rm simservice/nohup.out`. The file still exists in the import commit `b3d29c2`; it holds only a home-directory path, so no history rewrite is proposed. |
| 4 | `test(mosaik): cover the MOSAIK_ENABLED submission toggle` | **Decision (maintainer, 2026-11-12): Mosaik stays enabled by default.** `main` now puts the editor behind the web login (`/mosaik/` gateway) and runs each Mosaik simulation in its own Orbit pod, so the original reason for switching it off (editor without authentication, shared process) no longer holds. What is still missing for step 41 (resource limits, `securityContext`, network policy for the task pods) is tracked there. This commit only adds `test_mosaik_toggle.py` for the existing `MOSAIK_ENABLED` switch and removes `fastapi_app/tests/` from `.gitignore` (small overlap with step 10). |
| – | `docs: add phase 0 notes and DaceDSX PR 0 description` | This file, `docs/changes/dacedsx-pr0.md`, CHANGELOG, roadmap ticks. |

### 0b (DaceDSX)

| Step | Commit | What changed |
|---|---|---|
| 3 | `chore(data): convert example pandapower networks from pickle to JSON` | `_data/resources/ieee_13*.p` (4 files) converted with `pandapower.to_json` (pandapower 3.5.6, inside an isolated container), the two `sce_co_sim_copy*.json` scenarios now reference the `.json` files, pickles removed with `git rm`. |
| 3 | `fix(pandapower): refuse pickle and code-loading JSON networks` | New `pandapowerWrapper/network_loader.py`: `.p` refused unless `PANDAPOWER_ALLOW_PICKLE=true`; pandapower JSON decoded only when every `_module`/`_class` tag, including tags nested in DataFrame strings, is in `ALLOWED_JSON_CLASSES` (`pandapowerNet`, `DataFrame`, `Series`); dict format and Excel unchanged. `pandapowerApi.init` uses the loader. `pandapowerWrapper/tests/test_network_loader.py`, `pandapowerWrapper/requirements-local.txt` (pinned) and a `pandapower` CI job added. |

### 0c

| Step | Commit | What changed |
|---|---|---|
| 3 | `fix(pandapower): refuse pickle and code-loading JSON networks in SimaaS image` | Verbatim copy of `network_loader.py` into `simservice/PandaPowerWrapper/`, `pandapowerApi.init` routed through it, `Dockerfile` copies the module, four tests under `simservice/PandaPowerWrapper/tests/`. |

## Assumptions

- **Contradiction noted:** PR 0's acceptance criterion in the patch inventory says
  "JSON with `_module` is rejected" while also requiring that "plain pandapower
  JSON networks keep loading". `pandapower.to_json` output itself carries
  `_module` tags, so both cannot hold. The loader follows the D5 wording
  ("allowlist") instead: known pandapower/pandas classes are allowed, everything
  else is refused. The inventory row for PR 0 should be reworded accordingly.
- Pickle stays available as an explicit opt-in (`PANDAPOWER_ALLOW_PICKLE=true`)
  for operators who run DaceDSX on their own hardware with their own files. SimaaS
  never sets it. The name describes the trust decision rather than a "SimaaS mode",
  so nothing SimaaS-specific lands upstream.
- The allowlist was derived empirically from `pandapower.to_json` output for the
  repository networks, `case9`, `case14`, CIGRE MV and MV Oberrhein with pandapower
  3.5.6; all produce only `pandapowerNet` and `DataFrame`. `Series` is allowed in
  addition. Networks with controllers or other pandapower objects will be refused
  with a message naming the class; extend `ALLOWED_JSON_CLASSES` deliberately.
- The DaceDSX CI job pins `pandapower==3.5.6`, `openpyxl==3.1.5`, `xlsxwriter==3.3.1`
  (the versions used locally). `xlsxwriter` is needed only to write the Excel test
  fixture.
- Maintainer questions 1–5 from `CLAUDE.md` do not affect Phase 0; the default
  assumptions there are unchanged.
- Uncommitted changes on `main` (`fastapi_app/static/svelte-dist/*`, `requirements.txt`)
  were left untouched and are not part of any branch here.

## Acceptance test

**0a** (needs the scratch venv or any environment with `fastapi`, `httpx`, `pytest`,
`itsdangerous`, `SQLAlchemy`, `redis`, `pika`, `authlib`, `python-multipart`):

```bash
python -m pytest fastapi_app/tests -q
```

Expected: `4 passed`. `test ! -e simservice/nohup.out` succeeds.

**0b** (DaceDSX checkout, no local pandapower needed):

```bash
docker run --rm -v "$PWD":/w -w /w python:3.12-slim sh -c \
  "pip install -q -r requirements-test.txt -r pandapowerWrapper/requirements-local.txt && pytest pandapowerWrapper/tests -q"
```

Expected: `12 passed, 4 subtests passed`. The default `pytest` (PythonBaseWrapper
suites) still passes.

**0c** (SimaaS checkout):

```bash
docker run --rm -v "$PWD/simservice/PandaPowerWrapper":/w -w /w python:3.12-slim sh -c \
  "pip install -q pytest pandapower==3.5.6 openpyxl==3.1.5 && pytest tests -q"
```

Expected: `4 passed`.


## Manual steps for humans

1. **Step 3:** open PR 0 in `cs7org/DaceDSX` from `simaas/pr0-pandapower-safe-load`
   with the text in `docs/changes/dacedsx-pr0.md`. Mention the acceptance-criterion
   contradiction above and the pickle opt-in so the maintainers can object.
2. **Step 5:** maintainer meeting. Suggested agenda:
   - Present the roadmap and the PR list (PR 0–9) with dependencies.
   - Question 1: large resources, `ResourceFile.fileReference` on a shared volume?
   - Question 2: pandapower time-series mode as a parameter or a new BB type?
   - Question 3: release process, SemVer tags, `ghcr.io/cs7org/dacedsx-*`, who owns CI secrets?
   - Question 4: lifecycle event schema, Avro or JSON Schema?
   - Question 5: executor default stays `local`, `kubernetes` opt-in?
   - Open issues for PR 3 (executor) and PR 8 (pandapower time series) after the meeting.
   - Step 6: agree on deleting the fully merged branches listed in the roadmap.
   Record the answers in `CLAUDE.md` under "Antworten der Maintainer".
3. **Step 6:** delete the merged branches once agreed (cs7org admin).
4. Step 1 was already done before this phase started.

## Open questions

- Whether the maintainers want the pickle opt-in at all, or prefer a hard refusal.
  Removing it is a five-line change in `network_loader.py`.

## Review notes

Read in this order:

1. `simservice/nohup.out` deletion (trivial).
2. `fastapi_app/tests/test_mosaik_toggle.py` (tests only, no behaviour change).
3. For 0b, start with `network_loader.py` (103 lines), then the tests, then the
   two-line change in `pandapowerApi.init`.

Things to look at: the allowlist in `ALLOWED_JSON_CLASSES` is deliberately small;
`find_disallowed_classes` parses any string that looks like JSON, which is what
makes the nested-DataFrame test meaningful.
