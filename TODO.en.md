# TODO: SimaaS & DaceDSX

As of 2026-11-05 · ★ = from the original team list, everything else = suggestion from the code audit or the [patch inventory](docs/dacedsx-patch-inventory.en.md)

**Legend:** 🔴 urgent / required before public operation · `[DaceDSX]` = work in the `cs7org/DaceDSX` repository · `[SimaaS]` = this repository · PR numbers refer to the patch inventory

---

## 1. Immediately: privacy & critical security

- [ ] 🔴 `[DaceDSX]` Delete the `Simulation-Server` branch. It contains a personal document (enrolment certificate PDF). If needed, ask GitHub Support to purge cached views.
- [ ] 🔴 `[DaceDSX]` PR 0: reject `pp.from_pickle` and `pp.from_json` with `_module` (code execution via uploaded network files; affects both this repo **and** upstream)
- [ ] 🔴 `[SimaaS]` Delete `simservice/nohup.out` (Minikube log containing a home directory path)
- [ ] 🔴 `[DaceDSX]` Remove the personal Windows path from `SimService/config.properties` (part of PR 2)

## 2. Decouple the DaceDSX integration

**Why:** `simservice/` currently contains a partial copy of DaceDSX from before the 2025 MIT relicensing. Since then the copy and upstream have drifted apart in both directions:

- SimaaS added roughly 3,000 lines of its own changes: Kubernetes executor, RabbitMQ/Redis, events, SUMO fixes and a rewritten pandapower wrapper.
- Upstream has fixed thread-safety bugs, sync-barrier bugs and ID-validation bugs that are missing here.

There are also several duplicate copies inside `simservice/` itself (`Worker/`, two `CppBaseWrapper`s, two `SumoWrapper`s, two `PythonBaseWrapper`s).

**Target picture:** DaceDSX becomes the single source of truth for all simulation code. It builds and publishes versioned container images. SimaaS keeps no DaceDSX code. It only consumes those images through a small adapter, comparable to the existing `mosaik-worker`.

```
cs7org/DaceDSX (single source)              SimaaS (this repo)
──────────────────────────────              ─────────────────────────────────
SimService, base wrappers, wrappers         fastapi_app/frameworks/dacedsx/
Dockerfiles + CI                              (validation, monitoring UI)
  → ghcr.io/cs7org/dacedsx-simservice:1.4.0 dacedsx-bridge (new, small worker)
  → ghcr.io/cs7org/dacedsx-sumo:1.4.0         RabbitMQ → Kafka scenario
  → ghcr.io/cs7org/dacedsx-pandapower:1.4.0   Kafka status/events → Redis/JSONL
Executor plugin: local | kubernetes         deploy/: dacedsx.version = 1.4.0
Contract: Avro scenario, event schema,
          env vars, directory layout
```

**Why images rather than a git submodule:** A submodule would remove the copy but not the SimaaS-specific patches; they would still need a fork. It would also force this repo to build C++ (avro, cppkafka, libserdes), Java and Python. With images, the only shared thing is a small, versioned contract. For development against unreleased upstream code, `main-<sha>` image tags or a local build from a DaceDSX checkout are enough.

### 2.1 Upstream work in `cs7org/DaceDSX`

- [ ] ★ `[DaceDSX]` **PR 1: Dockerfiles and image publishing from CI.** Integrate DaceDSX into SimaaS as containers from a registry instead of copied code.
  - *What:* One Dockerfile per component (SimService, SumoWrapper, pandapowerWrapper, later OMNeT++ and others). The upstream CI (`.github/workflows/ci.yml` already exists) builds them and pushes them to `ghcr.io/cs7org/dacedsx-<component>`, tagged `vX.Y.Z` on releases and `main-<sha>` on every merge.
  - *Contract:* Every wrapper image has an `ENTRYPOINT` that takes `<scenarioID> <instanceID>`. That way any executor can start any wrapper without knowing what is inside. Today the SimaaS Kubernetes executor hard-codes one start command per wrapper type and falls back to `java -jar`, which is why the Python images contain a fake `/usr/local/bin/java` shim. Both go away.
  - *Also:* pin dependency versions (today `pip install` is unpinned), run as non-root, and fetch the C++ libraries at fixed versions instead of vendoring them as nested git checkouts.
  - *Starting point:* the existing Dockerfiles in `simservice/`, `simservice/cppbase+sumowrapper/` and `simservice/PandaPowerWrapper/`.
  - *Done when:* `docker pull ghcr.io/cs7org/dacedsx-sumo:main-<sha>` works and the image runs a scenario without any SimaaS files.

- [ ] `[DaceDSX]` **PR 2: Configuration via environment variables and `CONFIG_PATH`.**
  - *Why:* Containers are configured from outside (Kubernetes ConfigMaps, env vars). Upstream DaceDSX reads only `config.properties` and has no `getenv` anywhere. Broker addresses and paths are therefore baked into the files, including personal paths like `/mnt/c/Users/...`.
  - *What:* The same variable names in Java, C++ and Python: `KAFKA_BROKER`, `SCHEMA_REGISTRY`, `CHANNEL_ORCHESTRATION`/`_INTERACTION`/`_PROVISION`, `RESOURCES_DIR`, `RESULTS_DIR`, `CONFIG_PATH`. Env values override the file, and the file keeps sensible local defaults. The C++ part already exists in this repo (`cppbase+sumowrapper/CppBaseWrapper/src/util/Config.cpp`) and only needs to be generalised.
  - *Done when:* the same image runs locally and in the cluster, with only env vars changed.

- [ ] `[DaceDSX]` **PR 3: Pluggable instance executor (`local` | `kubernetes`).**
  - *Why:* SimService starts one process per simulator instance. On a shared server those must be isolated, resource-limited Kubernetes Jobs. SimaaS has a `KubernetesJobExecutor` for this, but it *replaced* local execution instead of sitting next to it. Without it, upstream cannot accept the change, and local DaceDSX users would lose their workflow.
  - *What:* A small executor interface (`start`, `join`, `terminate`, `hasStartFailed`, `getExitVal`) that upstream's existing `ExecutorThread` already almost implements. `executor=local` stays the default, and `executor=kubernetes` is opt-in. Keep the Kubernetes client (fabric8) as an optional Maven profile or module.
  - *Fix while porting:*
    - Configurable image prefix, tag and pull policy (today: `imagePullPolicy: Never`).
    - CPU/memory requests and limits.
    - A `securityContext` (non-root, read-only root filesystem).
    - Mount only the scenario's own resource and result directories, not the whole `/data` volume.
    - Make `backoffLimit(2)` consistent with the "any failure = failed" check.
  - *Done when:* an upstream test runs the same scenario with both executors.

- [ ] `[DaceDSX]` **PR 4: Structured lifecycle events on a Kafka topic.**
  - *Why:* SimaaS shows progress, errors and results in the UI. Today SimService and every wrapper write their own `structured_events.jsonl` into a shared volume, using a file lock and world-writable files, and *also* publish to Kafka. The UI only needs a stream of machine-readable events. Upstream only has free-text status messages such as "X was terminated."
  - *What:* A versioned event schema in the DaceDSX repo. Fields at minimum: `category`, `eventCode`, `message`, `progress`, `simulationTime`, `fatal`, plus optional generic metrics. A shared emitter in the Java, C++ and Python base wrappers publishes to e.g. `orchestration.simulation.<scenarioID>.events`, Kafka only. Persisting events to files becomes the bridge's job (see 2.2).
  - *Also enables:* generic live stats in the frontend (section 5).
  - *Done when:* a scenario run produces `SCENARIO_ACCEPTED … TASK_COMPLETED` events on the topic, and the existing status topic still works.

- [ ] `[DaceDSX]` **PR 6: SimService survives offset-commit failures during consumer-group rebalances.**
  - *Why:* With `exitOnFailure`, a single failed Kafka offset commit (normal during a rebalance) stops SimService's main loop, and every running scenario dies with it. SimaaS removed that exit but now silently ignores the error.
  - *What:* Agree with the maintainers on retry with backoff, and on stopping only after repeated failures.

- [ ] `[DaceDSX]` **PR 9: Integration test in upstream CI (the contract test).**
  - *Why:* Once SimaaS only consumes images, the risk moves to the interface: an upstream change could break SimaaS without anyone noticing. A small end-to-end test in upstream CI catches that before a release.
  - *What:* CI starts Kafka and the schema registry, submits a minimal scenario (e.g. the Erlangen SUMO scenario or a short pandapower time series from this repo), and checks the exit status, the status topic and the event topic. SimaaS runs the same test against each new image version before upgrading.

### 2.2 SimaaS work in this repository

- [ ] `[SimaaS]` **Build the `dacedsx-bridge`.** This is the only DaceDSX-specific runtime code left in SimaaS.
  - *Why:* SimService currently contains RabbitMQ and Redis code that exists only for SimaaS, and upstream would not want it. SimService already listens for scenarios on Kafka (`orchestration.simulation`). A small translator between the SimaaS world (RabbitMQ, Redis, task IDs) and the DaceDSX world (Kafka, Avro) keeps both sides clean.
  - *What it does:*
    1. Consume a task from the RabbitMQ queue `simulation_requests`.
    2. Build the Avro `Scenario` with **`scenarioID = task_id`**, which fixes the bug where reusing a scenario ID was silently ignored by SimService.
    3. Publish the scenario and its resource files to Kafka, the role `SendScenarioObject` plays upstream.
    4. Acknowledge the RabbitMQ message only **after** a successful publish, so no task is lost on a crash.
    5. Follow the scenario's status and event topics. Write `task:<id>` in Redis (`RUNNING`/`DONE`/`ERROR`) and `results/<id>/events/structured_events.jsonl` for the UI.
  - *Where:* a new `dacedsx/bridge/` worker next to `mosaik/mosaik-worker/`, written in Python like the rest of the backend.
  - *Done when:* a task submitted via the web UI runs end to end against unmodified upstream images.

- [ ] `[SimaaS]` **Decide with the maintainers how large resources are transferred.**
  - *Why:* Today resource files (networks, routes, profiles) travel as Kafka messages. Kafka's default limit is about 1 MB per message, while SimaaS allows uploads up to 512 MB.
  - *Options:*
    1. Use `ResourceFile.fileReference`: send only a path on a shared volume or an object-storage URL, and the wrapper reads the file directly. Check which wrappers support this.
    2. Raise Kafka limits. Not recommended for hundreds of MB.
  - *Outcome:* a documented rule in the contract.

- [ ] `[SimaaS]` **Pin DaceDSX image versions in the deployment.**
  - *What:* Kubernetes manifests (later a Helm chart) reference `ghcr.io/cs7org/dacedsx-*:<version>` with one version variable for all DaceDSX images. Renovate or Dependabot opens a PR when a new DaceDSX release appears. CI runs the contract test from PR 9, and the PR is merged when it passes.
  - *Why:* upgrades become explicit, reviewable and reversible. Today the deployment always uses whatever happens to be in the local copy, tagged `latest`.

- [ ] `[SimaaS]` **Delete `simservice/` and move deployment files.**
  - *When:* step by step as the corresponding upstream PRs land. The order is in the patch inventory: unused copies (`Worker/`, `JavaBaseWrapper/`, top-level `CppBaseWrapper/`/`SumoWrapper/`) can go right away. The SUMO, pandapower and controller wrappers follow after PRs 1, 5 and 8, and SimService after PRs 1–4.
  - `simservice/k8s/` stays in SimaaS but moves to `deploy/` (or into the Helm chart), because it describes *our* deployment, not DaceDSX.
  - *Done when:* this repo contains no DaceDSX source code, only the bridge, the validation/UI code and deployment configuration.

## 3. DaceDSX: simulators & co-simulation

- [ ] ★ `[DaceDSX]` Integrate the SUMO–pandapower co-simulation into DaceDSX `main`
  - Note: the branch `sumo_pandapower_co_sim` is already fully merged into `main` (0 commits ahead). The co-simulation that actually runs lives in this repo (`cppbase+sumowrapper/`, `PandaPowerWrapper/`, `ControllerWrapper/`, `examples/ev-charging-workshop/`). It goes upstream through the following PRs:
  - [ ] PR 5: SUMO bug fixes (route files, `summary-output`, start time ≠ 0, exit codes, `std:cout` typo)
  - [ ] PR 7: optional vehicle telemetry in the SumoWrapper
  - [ ] Issue: pandapower time-series as a mode of the existing wrapper, or as a separate building-block type?
  - [ ] PR 8: pandapower time series, load setpoints, `ChargingSetpoint.avsc`, controller as wrapper or example
  - [ ] Re-test the controller/pandapower time-sync issues (commit 226ae7a) against upstream's new `TimeSync`
- [ ] ★ `[DaceDSX]` Improve the OMNeT++ integration / check whether it can run without a GUI
  - The code is in the branch `Omnet++Wrapper` (`OppWrapper/`, 15 commits ahead, 46 behind `main`, last changed 2025-07) → rebase onto `main` first
  - Headless: OMNeT++ ships the command-line environment `Cmdenv` (`-u Cmdenv`). Check whether the wrapper starts with it, then build a container image like the other wrappers.
- [ ] ★ `[DaceDSX]` Extend OMNeT++ for coupling with the energy domain (depends on the previous item)
  - Define an Avro schema for measurement and control messages (communication delay/loss between controller and pandapower)
  - Example scenario: controller ↔ OMNeT++ ↔ pandapower

## 4. DaceDSX: repository maintenance & docs

- [ ] ★ `[DaceDSX]` Clean up open branches
  - [ ] Fully merged (0 commits ahead), delete: `FAIRer_DaceDS`, `PyPSA_Wrapper`, `minor_bugfix_after_license_change`, `opendss-fresh-test`, `readme-update`, `sumo_pandapower_co_sim`, `update-branch-1`
  - [ ] Own commits, decide (merge/archive): `Omnet++Wrapper` (15), `codipy_dev` (15), `update-markdown` (6), `codipy-push` (2), `pv_and_battery` (2), `feature/opendss-setup-instructions` (1), `revert-11-feature/opendss-setup-instructions` (1)
  - [ ] `Simulation-Server`: see section 1
- [ ] ★ `[DaceDSX]` Move wrapper-specific instructions into READMEs in the wrapper folders
  - [ ] SUMO build (currently "What to do to compile the SumoWrapper" in the root README) → `SumoWrapper/README.md`
  - [ ] PyPSA scenario (currently "What to do to run a PyPSA-scenario") → `PyPSAWrapper/README.md`
  - [ ] Add pandapower, OpenDSS (reuse content from `feature/opendss-setup-instructions`), Carla, OMNeT++
  - [ ] Root README: overview, architecture, links to wrapper READMEs, how to use the container images
- [ ] `[DaceDSX]` Define a release process (SemVer tags, changelog)

## 5. SimaaS: frontend

- [ ] ★ Re-enable login
  - `AUTH_DISABLED` must be `false` (the default; it is overridden in `.env` or `build-minikube.sh`). Register an OIDC client with NFDI AAI for the public domain.
  - Session cookie with `https_only` (`fastapi_app/webapp.py`)
  - Refuse to start in production when `AUTH_DISABLED` is set
- [ ] ★ Adapt the start/landing page for DaceDSX (`frontend/src/lib/FrameworkChooser.svelte`): short description, available wrappers, example scenarios, link to docs
- [ ] ★ Make live stats optional (toggle per run or in the scenario settings; without live stats show status + logs only)
- [ ] ★ Make the graph view optional / only for small networks (threshold e.g. by number of buses/vehicles; SUMO already caps at `monitorMaxVehicles = 200`)
- [ ] ★ Check whether live stats can be generalised
  - Currently hard-wired in `RunMonitor.svelte` (1385 lines; `energy` → "Network State", otherwise vehicle projection)
  - Suggestion: wrappers report generic metrics (name, unit, value, simulation time) through the event schema from PR 4; the frontend shows generic time series, with domain-specific views only as plugins
- [ ] Mosaik GUI URL must not be hard-coded to `http://localhost:8002` (`frontend/src/lib/MosaikWorkspace.svelte:7`)
- [ ] Allow cancelling and deleting running tasks (backend endpoint is missing too)
- [ ] Stop committing `fastapi_app/static/svelte-dist/`; build it in the Docker build

## 6. SimaaS: backend & bugs

- [ ] Scenario-ID collision: SimService silently ignores a reused ID (`ScenarioManager.java:195`) → solved by the bridge using `scenarioID = task_id`
- [ ] Detect stuck tasks (timeout/heartbeat → status `ERROR`); otherwise they stay `PENDING`/`RUNNING` forever
- [ ] Mosaik worker: an exception in `process_task` causes endless redelivery (poison message) → catch errors, nack without requeue / dead-letter queue; enforce a timeout that stops the run
- [ ] SimService state is in memory and not thread-safe, and messages are acknowledged before processing → resolved by the bridge rework, or address upstream
- [ ] Replace `chmod 0o777` in `fastapi_app/tasks/storage.py:68-71` with a proper group/UID
- [ ] Scenario validation: allow-list wrapper types and resource types; migrate the Pydantic v1 `root_validator`
- [ ] Scale the EventStore: one SQLite file behind a global lock, SSE polls every second → Postgres table or Redis Streams, push instead of polling
- [ ] Database migrations with Alembic

## 7. SimaaS: security & isolation

- [ ] 🔴 Mosaik: user code runs without a sandbox; `mosaik-gui` is a shared editor without authentication → put it behind login and isolate per user, or don't offer it publicly for now
- [ ] 🔴 Pods mount all of `/data` (including the TLS key under `/data/certs`) → per task mount only `resources/<id>` (read-only) and `results/<id>`; certificates as a Kubernetes Secret
- [ ] 🔴 Close NodePorts (RabbitMQ 30672/31672, web 30501, SimService 30080); expose only the Ingress; enable auth on Kafka/RabbitMQ/Redis
- [ ] Authorisation: every task/result endpoint checks ownership (not just login)
- [ ] NetworkPolicies: wrapper pods may only reach Kafka and the schema registry

## 8. SimaaS: resources, fairness & scaling

- [ ] ★ Design dedicated simulation time / simulation-run credits
  - Per user: max. concurrent runs, max. runtime per run (via `scenarioMaxAge`), storage quota
  - Measure usage (CPU/wall-clock hours from Kubernetes Jobs) and charge it as credits; queue with priorities
  - Kubernetes `ResourceQuota`/`LimitRange` in the wrapper namespace
- [ ] Limit result retention (e.g. 30 days) and inform users beforehand; align the Job TTL (600 s) with log collection
- [ ] ★ Test SimaaS with larger simulations
  - [ ] Long runs (> 60 min = `scenarioMaxAge` default) and many steps (limit of 100k steps in `scenario.py`)
  - [ ] Large networks/uploads (Kafka message size, 512 MB upload limit)
  - [ ] Many parallel runs/users (EventStore, SSE, Redis, Kafka topics per scenario)
  - [ ] Measure resource needs per wrapper → set requests/limits
  - [ ] Keep the load-test script in the repo

## 9. Deployment & operations (public servers)

- [ ] Ingress with TLS (cert-manager), one public domain
- [ ] Images in a registry with pinned versions (no `latest`, no `imagePullPolicy: Never`)
- [ ] Helm chart or Kustomize instead of loose YAML files
- [ ] Storage: RWX volume instead of hostPath; backups for Postgres and results
- [ ] Slim down Kafka (KRaft, without Connect/ksqlDB/REST Proxy); no PLAINTEXT exposed externally
- [ ] Secrets management (Sealed Secrets / External Secrets) instead of `.env`
- [ ] Health/readiness endpoints for web, workers and bridge
- [ ] Monitoring & logging (Prometheus/Grafana, central logs), alerting on stuck tasks
- [ ] Web Dockerfile: replace the Python 3.8 base image (EOL), pin `requirements.txt`

## 10. Tests, CI & repository hygiene (SimaaS)

- [ ] Add backend tests (`/fastapi_app/tests/` is currently in `.gitignore`)
- [ ] CI: lint, tests, frontend build, image build; contract test against the DaceDSX images
- [ ] Remove runtime data from git (113 files under `data/resources`, `data/results`)
- [ ] Remove build artefacts from git (`bin/`, `obj/`, `logs/`, SUMO binary, vendored C++ repos); done together with deleting `simservice/`

## 11. Legal & organisation

- [ ] Legal notice (Impressum) and privacy policy (OIDC data, uploads, retention)
- [ ] Terms of use (permitted use, quotas, no warranty)
- [ ] AGPL §13: link to the source code of the running version in the frontend
- [ ] Coordinate with the DaceDSX maintainers (cs7org) on PR order, release process and open questions
