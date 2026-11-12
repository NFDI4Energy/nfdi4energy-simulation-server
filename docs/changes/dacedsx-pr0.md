# PR 0: pandapowerWrapper: refuse pickle and code-loading JSON networks

Branch: `simaas/pr0-pandapower-safe-load` → `main`

## Motivation

The pandapower wrapper loads the `Network` resource of a scenario with
`pp.from_pickle` for `.p` files and `pp.from_json` for JSON files that carry a
`_module` key. Both can execute code from the file:

- unpickling runs arbitrary code by design;
- pandapower's JSON decoder imports the module named in each `_module` tag and
  instantiates the class named in `_class`, so a file with
  `{"_module": "os", "_class": "system", ...}` runs a command while loading.

Network files are published to the wrapper as scenario resources and may come
from other parties, so this is remote code execution in the wrapper process. The
problem exists on `main` today and is independent of any particular deployment.

## Changes

- New `pandapowerWrapper/network_loader.py` with `load_network(path, build_plain)`:
  - `.p` files are refused with a message that explains how to convert them
    (`pandapower.to_json(net, "network.json")`). Operators who trust their own
    files can set `PANDAPOWER_ALLOW_PICKLE=true`; the default is off.
  - pandapower JSON (`_module` at the top level) is decoded only if every
    `_module`/`_class` pair in the document, including pairs nested inside the
    JSON strings pandapower uses for DataFrames, is in `ALLOWED_JSON_CLASSES`
    (`pandapower.auxiliary.pandapowerNet`, `pandas.core.frame.DataFrame`,
    `pandas.core.series.Series`). Anything else raises `UnsafeNetworkError`
    naming the offending class. The set is a module constant and can be
    extended deliberately.
  - The simple dict format (`build_network`) and Excel files load as before.
- `pandapowerApi.init` routes through the loader; no other behaviour changed.
- The four example networks `_data/resources/ieee_13*.p` were converted to JSON
  with `pandapower.to_json` (pandapower 3.5.6; each round-trips and converges in
  `runpp`), the two `sce_co_sim_copy*.json` scenarios reference the JSON files,
  and the pickles were removed. Users with their own pickle networks convert
  them once with `pandapower.to_json`.
- Tests in `pandapowerWrapper/tests/test_network_loader.py`, a pinned
  `pandapowerWrapper/requirements-local.txt`, and a `pandapower` job in
  `.github/workflows/ci.yml` (same pattern as the `pypsa` job).

## Test instructions

```bash
pip install -r requirements-test.txt -r pandapowerWrapper/requirements-local.txt
pytest pandapowerWrapper/tests
```

Expected: 12 tests pass (pickle refused by default, pickle loads only with the
opt-in, JSON with a foreign module refused at the top level and nested in a
DataFrame string, pandapower JSON and the dict format load, Excel loads, the
shipped example networks load through `pandapowerAPI.init`).

## Notes for reviewers

- The allowlist was derived from `pandapower.to_json` output for the repository
  networks, `case9`, `case14`, CIGRE MV and MV Oberrhein. Networks that contain
  controllers or other pandapower objects will be refused with a clear message;
  if that is a use case for you, the right fix is to add those classes to
  `ALLOWED_JSON_CLASSES`, not to disable the check.
- The pickle opt-in is a deliberate compromise for self-hosted setups. If you
  prefer a hard refusal, removing `pickle_allowed` is a five-line change.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
