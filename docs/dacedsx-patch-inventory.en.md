# DaceDSX patch inventory

As of 2026-11-04 · comparison of `simservice/` (this repo, `main` @ 226ae7a) against `cs7org/DaceDSX@main` (1d82385)

Goal: every local deviation under `simservice/` gets **one** destination.

- **Upstream:** contributed as a PR to DaceDSX.
- **Adapter:** belongs in the future `dacedsx-bridge` or in this repo's deployment configuration.
- **Drop:** upstream already has it (in a better form), or it is a hack or a duplicate copy.

After that, `simservice/` can be deleted from this repo.

## Method

Everything under `simservice/` arrived in a single import commit (`b3d29c2`). At that point the copies were identical:

- `CppBaseWrapper/` = `cppbase+sumowrapper/CppBaseWrapper/`
- `SumoWrapper/` = `cppbase+sumowrapper/SumoWrapper/`
- `src/` = `Worker/src/`

The folders `CppBaseWrapper/`, `SumoWrapper/`, `JavaBaseWrapper/`, `Worker/` and both `PythonBaseWrapper/` copies have **not been touched since**. They therefore serve as the baseline, i.e. the upstream state at import time. This allows a clean separation:

- **Local patches** = baseline → actively used copy (`cppbase+sumowrapper/`, `src/`, `PandaPowerWrapper/`, `ControllerWrapper/`)
- **Upstream progress** = baseline → `cs7org/DaceDSX@main`

What the build actually uses (`build-minikube.sh`):

| Image | Source |
|---|---|
| `simservice/simservice` | `simservice/` (Dockerfile, `src/`, `JavaBaseWrapper/`) |
| `simservice/pandapowerwrapper-wrapper` | `simservice/PandaPowerWrapper/` |
| `simservice/sumowrapper-wrapper` | `simservice/cppbase+sumowrapper/` |
| `simservice/controllerwrapper-wrapper` | `simservice/ControllerWrapper/` |

## Summary

| Component | Local patches | Upstream since import | Result |
|---|---|---|---|
| JavaBaseWrapper | **none** | thread safety, `scenarioMaxAge`, UTF-8 headers, tests | Drop (entirely) |
| PythonBaseWrapper (2 copies) | **none** | timeouts, strict consumer, sync-barrier fixes, tests | Drop (entirely) |
| AvroSchemas | new `ChargingSetpoint.avsc` | `bus.avsc` extended with `control` | 1 schema upstream, rest dropped |
| SimService | K8s executor, RabbitMQ, Redis, event emitter, resource publishing, `taskId` | ID validation, ProcessBuilder, start-failure detection, kill timeout, `scenarioMaxAge` | 2 upstream PRs, rest adapter/drop |
| CppBaseWrapper | env overrides in `Config.cpp`, `Makefile.docker` | 4 thread-safety/ordering fixes | 1 upstream PR |
| SumoWrapper | 6 files: real bug fixes, telemetry, events | – | 2–3 upstream PRs |
| PandaPowerWrapper | effectively a rewrite (time series, setpoints, events) | T&D coupling (different design) | coordination needed, 2 PRs |
| ControllerWrapper | new (DACH+ EI workshop 2026) | – | upstream as wrapper or example |

## Detailed inventory

### SimService (`simservice/src`, `pom.xml`, `config.properties`, `Dockerfile`)

| # | Local change | Destination | Reason / note |
|---|---|---|---|
| S1 | `KubernetesJobExecutor` (new, 454 lines) | **Upstream** (PR 3) | Generally useful. It must sit **next to** local execution instead of replacing it (today "Kubernetes mode: ENABLED" is hard-wired). Fix while upstreaming: `backoffLimit(2)` contradicts `failed > 0`; `imagePullPolicy: Never`; no resource limits/`securityContext`; the whole `/data` PVC is mounted; start command hard-coded per type (see S2). |
| S2 | `buildWrapperLaunchCommand()` with `sumowrapper`/`pandapowerwrapper`/otherwise `java -jar` | **Drop**, replaced by contract | Images define their own `ENTRYPOINT`; the executor only passes `<scenarioID> <instanceID>`. This also removes the need for the `java` shims in the Python Dockerfiles. |
| S3 | `ScenarioInstanceExecutor`: `ExecutorThread` replaced by K8s, `hasCorruptedParts()`/`getFailureMessage()` | **Upstream** (fold into PR 3) | Upstream now has `hasStartFailed()` + `describeTermination()`. The K8s failure diagnostics should map onto **that** interface (executor interface: `start/join/terminate/hasStartFailed/getExitVal`). |
| S4 | `publishScenarioResources()`: SimService reads `resourceDir/{taskId}` and publishes `ResourceFile`s | **Adapter** | Upstream lets the client (`SendScenarioObject`) publish the scenario **and** its resources. The bridge takes over exactly that client role, and SimService stays unchanged. **Open:** Kafka message size (default ~1 MB) vs. 512 MB upload limit; see [Open questions](#open-questions-for-the-maintainers). |
| S5 | `listenForRabbitMQRequests()` in `SimulationService` | **Adapter** | The bridge consumes `simulation_requests` and publishes the Avro `Scenario` on `orchestration.simulation`. This removes `amqp-client` and `org.json` parsing from DaceDSX. |
| S6 | Redis in `ScenarioManager` (`registerTaskId`, `updateRedisStatus`, static Jedis) | **Adapter** | The bridge derives status from the status/event topic and writes `task:{id}`. This also removes the non-thread-safe static Jedis client and `jedis` from the POM. |
| S7 | `taskId` threaded through `addScenarioRun`/`ScenarioInstanceExecutor`/K8s env (`TASK_ID`, `TASK_DIR`) | **Drop** | Replaced by the convention **`scenarioID = task_id`**. A UUID satisfies upstream's `SAFE_ID` (`[A-Za-z0-9._-]+`) and is a valid K8s name (lowercase; mind the 63-character limit for `scenarioID-instanceID`!). Also fixes the scenario-ID collision. |
| S8 | `SimulationEventEmitter` (Java): JSONL under `resultsDir/{taskId}/events` with a file lock **and** Kafka | **Upstream** (PR 4), Kafka only | Structured events belong in DaceDSX as a **versioned schema on a Kafka topic**. JSONL persistence (including the file lock and world-writable `chmod`) is done by the bridge. Wrappers no longer need write access to a shared volume. |
| S9 | Kafka commit failure no longer ends the main loop (`exitOnFailure` removed) | **Upstream** (PR 6, small) | Reasonable fix (a rebalance is not fatal), but clarify with the maintainers: retry/backoff rather than silently ignoring. |
| S10 | Hard-coded `MAX_AGE = 60 min`, message "maxSimTime" | **Drop** | Upstream has a configurable `scenarioMaxAge`. |
| S11 | `t.join()` without timeout on kill | **Drop** | Upstream: `KILL_JOIN_MS`. |
| S12 | Missing ID validation (`findInvalidID`) | **Drop** | Upstream has it (b058486). Important because IDs end up in paths and job names. |
| S13 | `SendScenarioObject` (older version) | **Drop** | Upstream has the URI fix, exit code on failure, writer close. |
| S14 | `pom.xml`: `kubernetes-client` (fabric8) | **Upstream** (with PR 3) | Keep optional (Maven profile or separate module), so local users don't need a K8s client. |
| S15 | `pom.xml`: `amqp-client`, `jedis` | **Drop** | Follows from S5/S6. |
| S16 | `config.properties` with cluster values (`broker.kafka.svc…`, `/data/...`, `kubernetesNamespace`, `rabbitmqHost`, `redisHost`) | **Adapter** (ConfigMap) | Upstream PR 2 makes everything overridable via env/mount; the values themselves belong in the deployment configuration here. |
| S17 | SimService `Dockerfile` (two stages with JavaBaseWrapper, non-root) | **Upstream** (PR 1) | Good foundation; remove `ENV RABBITMQ_HOST/REDIS_HOST`. |
| S18 | `Worker/` (identical copy of `src/`, `JavaBaseWrapper/`, own Dockerfile) | **Drop** | Unused, import only. |
| S19 | `nohup.out` (Minikube mount log with home path), `scenario.json`, `start-kube.sh`, `docker-compose.yml` | **Drop**/check | Delete `nohup.out` immediately. Keep the others only if still used, then move them to `deploy/`. |
| S20 | `simservice/k8s/*` | **Adapter** (stays here) | Deployment layer; in future it only references DaceDSX image tags. |

### JavaBaseWrapper

| # | Local change | Destination | Reason |
|---|---|---|---|
| J1 | none (import state) | **Drop** | Upstream is ahead: `ConcurrentHashMap` for counting, correct `ConsumerRecordComparator` (local: `a.key().hashCode()-a.key().hashCode()` is always 0, sender compared with `!=`), UTF-8 header decoding, `SCENARIO_MAX_AGE`, tests. |

### PythonBaseWrapper (`PandaPowerWrapper/PythonBaseWrapper`, `ControllerWrapper/PythonBaseWrapper`, identical)

| # | Local change | Destination | Reason |
|---|---|---|---|
| P1 | none (import state) | **Drop** | Upstream is ahead: schema-registry timeouts, `strict` consumer, delivery timeouts, `TimeSync` with `waitTimeout`/`progressHandler`, sync-barrier fixes (`break` instead of `return` with multiple topics, correct counting), tests. The local controller/pandapower timing issues (226ae7a) should be re-tested **against upstream's TimeSync first**. |

### AvroSchemas

| # | Local change | Destination | Reason |
|---|---|---|---|
| A1 | `ChargingSetpoint.avsc` (duplicated: `ControllerWrapper/` and `ControllerWrapper/AvroSchemas/`) | **Upstream** (with PR 8) | Into upstream `AvroSchemas/`, one copy. |
| A2 | `bus.avsc` without the `control` field | **Drop** | Use the upstream version; check whether the local pandapower variant copes with the additional required field. |

### CppBaseWrapper (`cppbase+sumowrapper/CppBaseWrapper`)

| # | Local change | Destination | Reason |
|---|---|---|---|
| C1 | `Config.cpp`: env overrides `KAFKA_BROKER`, `SCHEMA_REGISTRY`, `CHANNEL_*`, `RESULTS_DIR`, `RESOURCES_DIR` | **Upstream** (PR 2) | Upstream has **no** `getenv` anywhere. Essential for containers. Align the names across Java/C++/Python. |
| C2 | `readConfig()` returns `false` if the file is missing; no more `clear()` (overlay of several files) | **Upstream** (PR 2) | Small, clean improvement. |
| C3 | `Makefile.docker` | **Drop** | Upstream builds with `CMakeLists.txt`; the upstream Dockerfile (PR 1) uses that. |
| C4 | Vendored dependencies as nested git checkouts (`avro/`, `cppkafka/`, `libserdes/`, `pugixml/`) | **Drop** | Fetch at fixed versions/commits in the upstream Dockerfile. |
| C5 | – (missing locally) | – | Upstream fixes f11acc7, 01dec9f, 79c7199, e1fdada (locks in TimeSync/Consumer, MessageHandler ordering, exact sender match) come along automatically. |

### SumoWrapper (`cppbase+sumowrapper/SumoWrapper`)

| # | Local change | Destination | Reason |
|---|---|---|---|
| U1 | `main`: `argc < 3` instead of `< 2`, exit code `1` on errors, `try/catch` around the run | **Upstream** (PR 5) | Real bugs: wrong argument check; exit code 0 on failure prevents any executor from detecting the failure. |
| U2 | `ProvisionImpl.cpp`: `std:cout` typo (it is a label, not a namespace!), destination path via `getResourceDir()` | **Upstream** (PR 5) | Bug fix + uses C1. |
| U3 | `PrepareRun.cpp` + `default.sumocfg`: routes as `route-files` instead of `additional-files` (`{ROUTES}` placeholder), `summary` → `summary-output`, output block enabled | **Upstream** (PR 5) | Real SUMO bugs: routes/flows passed as additional files are not loaded correctly; `summary` is not a valid option. |
| U4 | `SumoSimulationControl.cpp`: start at `simStartMS` instead of 0, `stepLength > 0` check, branch for `responsibleForWholeMap` | **Upstream** (PR 5) | Bug fixes for scenarios with `simulationStart ≠ 0`. |
| U5 | `SumoSimulationControl.cpp`: vehicle telemetry (`monitorIntervalSteps`, `monitorMaxVehicles`), `stepDelayMs` | **Upstream** (PR 7) | As optional BB parameters, off by default. `stepDelayMs` is demo pacing; ask the maintainers whether they want it. |
| U6 | `SimulationEventEmitter.cpp/.h`, `EventFileLock.h`, `-ljansson` | **Upstream** (PR 4), without the file lock | As S8: Kafka topic only, no JSONL in the wrapper. |
| U7 | `CONFIG_PATH` env and fallback to a fixed `/data/config.properties` | **Upstream** (PR 2), only `CONFIG_PATH` | The fixed `/data` path is SimaaS-specific → drop. |
| U8 | `task_id` as 3rd argument / `TASK_ID` env | **Drop** | Follows from S7. |
| U9 | `create_directories` for output/log directory | **Upstream** (PR 5) | Small, sensible. |
| U10 | `erlangen_scenario/` | **Upstream** (PR 9) | As an example and **integration test** in upstream CI (contract test). |
| U11 | Committed artefacts: `bin/`, `obj/`, `logs/`, binary `SumoWrapper/SumoWrapper` (24 files under `bin|obj|logs`) | **Drop** | Build artefacts don't belong in git. |
| U12 | `simservice/SumoWrapper/`, `simservice/CppBaseWrapper/` (unused import copies) | **Drop** | |
| U13 | `cppbase+sumowrapper/Dockerfile` (multi-stage, SUMO 1.27, libserdes with C++17) | **Upstream** (PR 1) | With `ENTRYPOINT ["/app/SumoWrapper"]` it already fits the contract from S2. |

### PandaPowerWrapper

The local version is **not a patch but a separate wrapper**. It runs a standalone time-series calculation with `load_profile`/`sgen_profile` (CSV/JSON) from the resource directory, processes external setpoints and emits events. Upstream (`pandapowerWrapper/`) is built for **T&D coupling** instead: ghost buses, cuts, resources via Kafka. A line-by-line merge does not make sense.

| # | Local change | Destination | Reason |
|---|---|---|---|
| D1 | Profile-based time series (`load_profile`, `sgen_profile`, `step_length`, `n_steps`, `export_results`) | **Upstream** (PR 8) | As a **mode** of the upstream wrapper (e.g. BB parameter `mode=timeseries` vs. `td`) or as a separate BB type `pandapowerTimeseries`. **Maintainers' decision.** |
| D2 | External setpoints via `interaction.simulation.{sce}.charging.setpoints` (`apply_external_setpoints`) | **Upstream** (PR 8) | Phrase it generically ("load setpoints"), schema A1. |
| D3 | `simulation_event_emitter.py` (per wrapper) | **Upstream** (PR 4) in `PythonBaseWrapper` | Shared by all Python wrappers instead of copied per wrapper. |
| D4 | Paths via `RESOURCES_DIR`/`RESULTS_DIR`/`TASK_DIR`, config via env | **Upstream** (PR 2), without `TASK_DIR` | As C1. |
| D5 | `pp.from_pickle` and `pp.from_json` with `_module` (locally **and upstream**) | **Upstream** (PR 0, security) | Code execution via uploaded network files. Reject pickle; allow JSON only without `_module`/class hooks or via an allow-list. Important independently of SimaaS. |
| D6 | `Dockerfile` with `java` shim (`/usr/local/bin/java` → Python) | **Drop** (shim) / **Upstream** (Dockerfile, PR 1) | The shim becomes unnecessary with S2. Pin dependencies (unpinned today). |
| D7 | `config.properties` with cluster values | **Adapter** (ConfigMap) | The upstream version still contains personal paths → clean up in PR 2. |
| D8 | `examples/long_profile_scenario/` | **Upstream** (with PR 8) | |
| D9 | `requirements.txt` (only 3 packages; the Dockerfile installs different ones) | **Drop** / Upstream (PR 1) | One pinned dependency list upstream. |

### ControllerWrapper

| # | Local change | Destination | Reason |
|---|---|---|---|
| R1 | `controllerWrapper.py` (EV charging control: `uncontrolled`/`safe_mode`/`heuristic`, reads SUMO edge topics, writes setpoints) | **Upstream** (PR 8) | It is a DaceDSX building block; otherwise DaceDSX code stays in SimaaS. Suggestion: `ControllerWrapper/` upstream or `examples/ev-charging/`. Workshop specifics (`station_mapping.json`) then belong in the example scenario. |
| R2 | `Dockerfile` with `java` shim | as D6 | |

## PR list for DaceDSX

Ordered by dependencies. PR 0 and PR 5 are independent and can be submitted **right away**.

| PR | Title | Content (inventory no.) | Depends on | Acceptance criterion |
|---|---|---|---|---|
| **0** | `pandapowerWrapper: refuse pickle and code-loading JSON networks` | D5 | – | Test: `.p` files and JSON with `_module` are rejected; plain pandapower JSON networks still load. |
| **1** | `Add Dockerfiles and publish images from CI` | S17, U13, D6, D9, C3, C4 | – | CI builds and pushes `ghcr.io/cs7org/dacedsx-{simservice,sumo,pandapower,…}:{version}` and `main-<sha>`; every wrapper image has an `ENTRYPOINT` taking `<scenarioID> <instanceID>`; dependencies pinned; non-root. |
| **2** | `Configuration via environment variables and CONFIG_PATH` | C1, C2, U7, D4, S16 (part), D7 (cleanup) | – | Uniform env names (`KAFKA_BROKER`, `SCHEMA_REGISTRY`, `CHANNEL_*`, `RESOURCES_DIR`, `RESULTS_DIR`, `CONFIG_PATH`) in Java/C++/Python; repo `config.properties` without personal paths, with local defaults. |
| **3** | `Pluggable instance executor with optional Kubernetes Jobs` | S1, S3, S14, S2 (contract) | 1, 2 | `executor=local` (default, current behaviour) \| `kubernetes`; the interface covers `hasStartFailed`/`getExitVal`/`terminate`; K8s: configurable image prefix/tag/pull policy, resource limits, `securityContext`, mount only required subdirectories, consistent `backoffLimit`; fabric8 optional. |
| **4** | `Structured lifecycle events topic` | S8, U6, D3 | 2 | Avro or JSON schema (versioned) in the repo; topic e.g. `orchestration.simulation.{scenarioID}.events`; emitter in the Java/C++/Python base, **Kafka only**; status topic stays compatible. |
| **5** | `SumoWrapper: fix routes, summary output, start time and exit codes` | U1, U2, U3, U4, U9 | – | Erlangen scenario (PR 9) runs with `simulationStart ≠ 0`; routes are loaded; the wrapper exits non-zero on failure. |
| **6** | `SimService: survive offset-commit failures during rebalance` | S9 | – | Clarify with the maintainers (retry/backoff); running scenarios are not terminated. |
| **7** | `SumoWrapper: optional vehicle telemetry` | U5 | 4 | Parameters documented, off by default, no runtime cost unless enabled. |
| **8** | `pandapower time-series mode, load setpoints and EV controller` | D1, D2, D8, A1, R1 | 2, 4; design agreement | Open an issue first: mode vs. separate BB type. Example scenario with SUMO + controller + pandapower. |
| **9** | `Integration test: minimal co-simulation in CI` | U10, `examples/long_profile_scenario` | 1, 5 | CI starts Kafka + registry, submits a scenario, checks the exit status and status/event topic. This is the **contract test** for SimaaS. |

Open an **issue** for discussion before PR 3 and PR 8, since both involve architectural decisions.

## What goes into the `dacedsx-bridge` (this repo)

- Consume RabbitMQ `simulation_requests` (S5); acknowledge only after a successful Kafka publish.
- Set `scenarioID := task_id` (S7), publish the scenario + `ResourceFile`s to Kafka, i.e. take over the role of `SendScenarioObject` (S4).
- Subscribe to the scenario's status/event topic → Redis `task:{id}` and `results/{task_id}/events/structured_events.jsonl` (S6, S8).
- Deployment configuration: ConfigMaps instead of baked-in `config.properties` (S16, D7), `simservice/k8s/` → image tags (S20).

## What gets deleted once the images are available

```
simservice/Worker/
simservice/JavaBaseWrapper/
simservice/CppBaseWrapper/
simservice/SumoWrapper/
simservice/cppbase+sumowrapper/      (after PR 1, 5, 7)
simservice/PandaPowerWrapper/        (after PR 0, 1, 8)
simservice/ControllerWrapper/        (after PR 8)
simservice/src/, pom.xml, Dockerfile, config.properties   (after PR 1–4)
simservice/nohup.out                 (immediately)
```

`simservice/k8s/` moves to `deploy/` (or a Helm chart).

## Open questions for the maintainers

1. **Large resources:** uploads up to 512 MB don't fit into Kafka messages (default `max.message.bytes` ≈ 1 MB). Should the bridge use `ResourceFile.fileReference` (shared volume / object storage)? Is this supported by all wrappers?
2. **pandapower:** time-series mode in the existing wrapper or a separate BB type (PR 8)?
3. **Release process:** SemVer tags on `main`, images on `ghcr.io/cs7org`? Who maintains the CI secrets?
4. **Event schema:** Avro (like everything else) or JSON Schema? SimaaS needs at least `category`, `eventCode`, `message`, `progress`, `simulationTime`, `fatal`.
5. **Executor default:** does `local` stay the default, with `kubernetes` as opt-in?

## Independently (upstream, urgent)

- The branch `Simulation-Server` in `cs7org/DaceDSX` contains an enrolment certificate (PDF). Have the branch deleted; if needed, ask GitHub Support to purge caches.
- Upstream `SimService/config.properties` contains a personal Windows path (cleaned up in PR 2).
