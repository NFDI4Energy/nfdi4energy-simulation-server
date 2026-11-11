# DaceDSX-Patch-Inventar

Stand: 2026-11-04 · Vergleich `simservice/` (dieses Repo, `main` @ 226ae7a) gegen `cs7org/DaceDSX@main` (1d82385)

Ziel: Jede lokale Abweichung unter `simservice/` bekommt **ein** Ziel.

- **Upstream:** wird als PR in DaceDSX eingebracht.
- **Adapter:** gehört in die künftige `dacedsx-bridge` bzw. die Deploy-Konfiguration dieses Repos.
- **Weg:** Upstream hat es schon (besser), oder es ist ein Hack bzw. eine Kopie.

Danach kann `simservice/` hier gelöscht werden.

## Methode

Alles unter `simservice/` kam mit einem einzigen Import-Commit (`b3d29c2`). Damals waren die Kopien identisch:

- `CppBaseWrapper/` = `cppbase+sumowrapper/CppBaseWrapper/`
- `SumoWrapper/` = `cppbase+sumowrapper/SumoWrapper/`
- `src/` = `Worker/src/`

Die Ordner `CppBaseWrapper/`, `SumoWrapper/`, `JavaBaseWrapper/`, `Worker/` und beide `PythonBaseWrapper/`-Kopien wurden seitdem **nicht mehr angefasst**. Sie dienen daher als Baseline, also als der Upstream-Stand zum Importzeitpunkt. Das erlaubt eine saubere Trennung:

- **Lokale Patches** = Baseline → aktiv genutzte Kopie (`cppbase+sumowrapper/`, `src/`, `PandaPowerWrapper/`, `ControllerWrapper/`)
- **Upstream-Fortschritt** = Baseline → `cs7org/DaceDSX@main`

Was das Build tatsächlich nutzt (`build-minikube.sh`):

| Image | Quelle |
|---|---|
| `simservice/simservice` | `simservice/` (Dockerfile, `src/`, `JavaBaseWrapper/`) |
| `simservice/pandapowerwrapper-wrapper` | `simservice/PandaPowerWrapper/` |
| `simservice/sumowrapper-wrapper` | `simservice/cppbase+sumowrapper/` |
| `simservice/controllerwrapper-wrapper` | `simservice/ControllerWrapper/` |

## Kurzfassung

| Komponente | Lokale Patches | Upstream seit Import | Ergebnis |
|---|---|---|---|
| JavaBaseWrapper | **keine** | Thread-Sicherheit, `scenarioMaxAge`, UTF-8-Header, Tests | Weg (komplett) |
| PythonBaseWrapper (2 Kopien) | **keine** | Timeouts, strict consumer, Sync-Barriere-Fixes, Tests | Weg (komplett) |
| AvroSchemas | `ChargingSetpoint.avsc` neu | `bus.avsc` um `control` erweitert | 1 Schema upstream, Rest weg |
| SimService | K8s-Executor, RabbitMQ, Redis, Event-Emitter, Ressourcen-Publish, `taskId` | ID-Validierung, ProcessBuilder, Start-Fehler-Erkennung, Kill-Timeout, `scenarioMaxAge` | 2 Upstream-PRs, Rest Adapter/weg |
| CppBaseWrapper | Env-Overrides in `Config.cpp`, `Makefile.docker` | 4 Thread-Safety-/Ordering-Fixes | 1 Upstream-PR |
| SumoWrapper | 6 Dateien: echte Bugfixes, Telemetrie, Events | – | 2–3 Upstream-PRs |
| PandaPowerWrapper | praktisch Neuschreibung (Zeitreihe, Setpoints, Events) | T&D-Kopplung (anderes Design) | Abstimmung nötig, 2 PRs |
| ControllerWrapper | neu (Workshop DACH+ EI 2026) | – | Upstream als Wrapper oder Beispiel |

## Inventar im Detail

### SimService (`simservice/src`, `pom.xml`, `config.properties`, `Dockerfile`)

| # | Lokale Änderung | Ziel | Begründung / Hinweis |
|---|---|---|---|
| S1 | `KubernetesJobExecutor` (neu, 454 Z.) | **Upstream** (PR 3) | Allgemein nützlich. Muss aber **neben** der lokalen Ausführung stehen, statt sie zu ersetzen (heute: „Kubernetes mode: ENABLED“ fest verdrahtet). Beim Upstreamen beheben: `backoffLimit(2)` widerspricht `failed > 0`; `imagePullPolicy: Never`; keine Resource-Limits/`securityContext`; ganzes `/data`-PVC gemountet; Startbefehl pro Typ hartkodiert (siehe S2). |
| S2 | `buildWrapperLaunchCommand()` mit `sumowrapper`/`pandapowerwrapper`/sonst `java -jar` | **Weg**, ersetzt durch Vertrag | Images definieren ihren `ENTRYPOINT`, der Executor übergibt nur `<scenarioID> <instanceID>`. Dadurch entfallen auch die `java`-Shims in den Python-Dockerfiles. |
| S3 | `ScenarioInstanceExecutor`: `ExecutorThread` durch K8s ersetzt, `hasCorruptedParts()`/`getFailureMessage()` | **Upstream** (in PR 3 aufgehen lassen) | Upstream hat inzwischen `hasStartFailed()` + `describeTermination()`. Die K8s-Fehlerdiagnose sollte auf **diese** Schnittstelle abgebildet werden (Executor-Interface: `start/join/terminate/hasStartFailed/getExitVal`). |
| S4 | `publishScenarioResources()`: SimService liest `resourceDir/{taskId}` und publiziert `ResourceFile`s | **Adapter** | Upstream lässt den Client (`SendScenarioObject`) Szenario **und** Ressourcen publizieren. Die Bridge übernimmt genau diese Client-Rolle, SimService bleibt unverändert. **Offen:** Kafka-Nachrichtengröße (Default ~1 MB) vs. 512 MB Upload-Limit, siehe [Offene Fragen](#offene-fragen-an-die-maintainer). |
| S5 | `listenForRabbitMQRequests()` in `SimulationService` | **Adapter** | Die Bridge konsumiert `simulation_requests` und publiziert das Avro-`Scenario` auf `orchestration.simulation`. Damit entfallen `amqp-client` und `org.json`-Parsing in DaceDSX. |
| S6 | Redis in `ScenarioManager` (`registerTaskId`, `updateRedisStatus`, Jedis-Static) | **Adapter** | Die Bridge leitet Status aus dem Status-Topic/Event-Topic ab und schreibt `task:{id}`. Damit entfallen auch der nicht thread-sichere statische Jedis-Client und `jedis` im POM. |
| S7 | `taskId` durch `addScenarioRun`/`ScenarioInstanceExecutor`/K8s-Env (`TASK_ID`, `TASK_DIR`) | **Weg** | Ersetzt durch die Konvention **`scenarioID = task_id`**. Eine UUID erfüllt upstreams `SAFE_ID` (`[A-Za-z0-9._-]+`) und ist als K8s-Name gültig (kleingeschrieben, ≤ 63 Zeichen bei `scenarioID-instanceID` beachten!). Behebt nebenbei die scenarioID-Kollision. |
| S8 | `SimulationEventEmitter` (Java): JSONL unter `resultsDir/{taskId}/events` mit File-Lock **und** Kafka | **Upstream** (PR 4), aber nur Kafka | Strukturierte Events gehören als **versioniertes Schema auf ein Kafka-Topic** in DaceDSX. Die JSONL-Persistenz (inkl. File-Lock, `chmod`-world-writable) macht die Bridge. Kein Shared-Volume-Schreibzugriff mehr aus Wrappern nötig. |
| S9 | Kafka-Commit-Fehler beendet die Hauptschleife nicht mehr (`exitOnFailure` entfernt) | **Upstream** (PR 6, klein) | Nachvollziehbarer Fix (Rebalance ≠ fatal), aber upstream mit Maintainern klären: lieber Retry/Backoff statt stillem Ignorieren. |
| S10 | Fest `MAX_AGE = 60 min`, Meldung „maxSimTime“ | **Weg** | Upstream hat konfigurierbares `scenarioMaxAge`. |
| S11 | `t.join()` ohne Timeout beim Kill | **Weg** | Upstream: `KILL_JOIN_MS`. |
| S12 | Fehlende ID-Validierung (`findInvalidID`) | **Weg** | Upstream hat sie (b058486). Wichtig, weil IDs in Pfaden/Jobnamen landen. |
| S13 | `SendScenarioObject` (ältere Version) | **Weg** | Upstream hat URI-Fix, Exit-Code bei Fehlschlag, Writer-Close. |
| S14 | `pom.xml`: `kubernetes-client` (fabric8) | **Upstream** (mit PR 3) | Optional halten (Maven-Profil oder eigenes Modul), damit lokale Nutzer keinen K8s-Client brauchen. |
| S15 | `pom.xml`: `amqp-client`, `jedis` | **Weg** | Folgt aus S5/S6. |
| S16 | `config.properties` mit Cluster-Werten (`broker.kafka.svc…`, `/data/...`, `kubernetesNamespace`, `rabbitmqHost`, `redisHost`) | **Adapter** (ConfigMap) | Upstream-PR 2 sorgt dafür, dass alles per Env/Mount überschreibbar ist; die Werte selbst gehören in die Deploy-Konfiguration hier. |
| S17 | `Dockerfile` SimService (2-stufig mit JavaBaseWrapper, non-root) | **Upstream** (PR 1) | Gutes Fundament; `ENV RABBITMQ_HOST/REDIS_HOST` entfernen. |
| S18 | `Worker/` (identische Kopie von `src/`, `JavaBaseWrapper/`, eigenes Dockerfile) | **Weg** | Unbenutzt, nur Import. |
| S19 | `nohup.out` (Minikube-Mount-Log mit Home-Pfad), `scenario.json`, `start-kube.sh`, `docker-compose.yml` | **Weg**/prüfen | `nohup.out` sofort löschen. Die anderen nur behalten, falls noch genutzt; dann nach `deploy/`. |
| S20 | `simservice/k8s/*` | **Adapter** (bleibt hier) | Deploy-Ebene; künftig nur noch Image-Tags von DaceDSX referenzieren. |

### JavaBaseWrapper

| # | Lokale Änderung | Ziel | Begründung |
|---|---|---|---|
| J1 | keine (Stand Import) | **Weg** | Upstream ist voraus: `ConcurrentHashMap` für Zählung, korrekter `ConsumerRecordComparator` (lokal: `a.key().hashCode()-a.key().hashCode()` ist immer 0, Sender per `!=` verglichen), UTF-8-Header-Decoding, `SCENARIO_MAX_AGE`, Tests. |

### PythonBaseWrapper (`PandaPowerWrapper/PythonBaseWrapper`, `ControllerWrapper/PythonBaseWrapper`, identisch)

| # | Lokale Änderung | Ziel | Begründung |
|---|---|---|---|
| P1 | keine (Stand Import) | **Weg** | Upstream ist voraus: Schema-Registry-Timeouts, `strict`-Consumer, Delivery-Timeouts, `TimeSync` mit `waitTimeout`/`progressHandler`, Sync-Barriere-Fixes (`break` statt `return` bei mehreren Topics, korrekte Zählung), Tests. Die lokalen Controller/PandaPower-Zeitprobleme (226ae7a) sollten **zuerst gegen upstreams TimeSync** nachgetestet werden. |

### AvroSchemas

| # | Lokale Änderung | Ziel | Begründung |
|---|---|---|---|
| A1 | `ChargingSetpoint.avsc` (doppelt: `ControllerWrapper/` und `ControllerWrapper/AvroSchemas/`) | **Upstream** (mit PR 8) | Nach `AvroSchemas/` upstream, eine Kopie. |
| A2 | `bus.avsc` ohne Feld `control` | **Weg** | Upstream-Version nehmen; prüfen, ob die lokale PandaPower-Variante mit dem zusätzlichen Pflichtfeld klarkommt. |

### CppBaseWrapper (`cppbase+sumowrapper/CppBaseWrapper`)

| # | Lokale Änderung | Ziel | Begründung |
|---|---|---|---|
| C1 | `Config.cpp`: Env-Overrides `KAFKA_BROKER`, `SCHEMA_REGISTRY`, `CHANNEL_*`, `RESULTS_DIR`, `RESOURCES_DIR` | **Upstream** (PR 2) | Upstream hat **nirgends** `getenv`. Für Container essenziell. Namen über Java/C++/Python vereinheitlichen. |
| C2 | `readConfig()` gibt `false` zurück, wenn Datei fehlt; kein `clear()` mehr (Overlay mehrerer Dateien) | **Upstream** (PR 2) | Kleine, saubere Verbesserung. |
| C3 | `Makefile.docker` | **Weg** | Upstream baut per `CMakeLists.txt`; das Upstream-Dockerfile (PR 1) nutzt das. |
| C4 | Vendorte Abhängigkeiten als verschachtelte Git-Checkouts (`avro/`, `cppkafka/`, `libserdes/`, `pugixml/`) | **Weg** | Im Upstream-Dockerfile mit festen Versionen/Commits holen. |
| C5 | – (fehlt lokal) | – | Upstream-Fixes f11acc7, 01dec9f, 79c7199, e1fdada (Locks in TimeSync/Consumer, MessageHandler-Ordering, exakter Sender-Match) kommen automatisch mit. |

### SumoWrapper (`cppbase+sumowrapper/SumoWrapper`)

| # | Lokale Änderung | Ziel | Begründung |
|---|---|---|---|
| U1 | `main`: `argc < 3` statt `< 2`, Exit-Code `1` bei Fehlern, `try/catch` um den Lauf | **Upstream** (PR 5) | Echte Bugs: falsche Argumentprüfung; Exit-Code 0 bei Fehler verhindert Fehlererkennung durch jeden Executor. |
| U2 | `ProvisionImpl.cpp`: `std:cout`-Tippfehler (ist ein Label, kein Namespace!), Zielpfad über `getResourceDir()` | **Upstream** (PR 5) | Bugfix + nutzt C1. |
| U3 | `PrepareRun.cpp` + `default.sumocfg`: Routen als `route-files` statt `additional-files` (`{ROUTES}`-Platzhalter), `summary` → `summary-output`, Output-Block aktiviert | **Upstream** (PR 5) | Echte SUMO-Bugs: Routen/Flows als Additional werden nicht korrekt geladen; `summary` ist keine gültige Option. |
| U4 | `SumoSimulationControl.cpp`: Start bei `simStartMS` statt 0, `stepLength > 0`-Prüfung, Zweig für `responsibleForWholeMap` | **Upstream** (PR 5) | Bugfixes bei Szenarien mit `simulationStart ≠ 0`. |
| U5 | `SumoSimulationControl.cpp`: Fahrzeug-Telemetrie (`monitorIntervalSteps`, `monitorMaxVehicles`), `stepDelayMs` | **Upstream** (PR 7) | Als optionale BB-Parameter, Default aus. `stepDelayMs` ist Demo-Pacing; Maintainer fragen, ob gewollt. |
| U6 | `SimulationEventEmitter.cpp/.h`, `EventFileLock.h`, `-ljansson` | **Upstream** (PR 4), ohne File-Lock | Wie S8: nur Kafka-Topic, keine JSONL im Wrapper. |
| U7 | `CONFIG_PATH`-Env und Fallback auf fest `/data/config.properties` | **Upstream** (PR 2) nur `CONFIG_PATH` | Fester `/data`-Pfad ist SimaaS-spezifisch → weg. |
| U8 | `task_id` als 3. Argument / `TASK_ID`-Env | **Weg** | Folgt aus S7. |
| U9 | `create_directories` für Output/Log-Verzeichnis | **Upstream** (PR 5) | Klein, sinnvoll. |
| U10 | `erlangen_scenario/` | **Upstream** (PR 9) | Als Beispiel und **Integrationstest** in der Upstream-CI (Contract-Test). |
| U11 | Commitete Artefakte: `bin/`, `obj/`, `logs/`, Binary `SumoWrapper/SumoWrapper` (24 Dateien unter `bin|obj|logs`) | **Weg** | Build-Artefakte gehören nicht ins Git. |
| U12 | `simservice/SumoWrapper/`, `simservice/CppBaseWrapper/` (unbenutzte Import-Kopien) | **Weg** | |
| U13 | `cppbase+sumowrapper/Dockerfile` (mehrstufig, SUMO 1.27, libserdes mit C++17) | **Upstream** (PR 1) | Mit `ENTRYPOINT ["/app/SumoWrapper"]` passt er schon zum Vertrag aus S2. |

### PandaPowerWrapper

Die lokale Version ist **kein Patch, sondern ein eigener Wrapper**. Sie macht eine eigenständige Zeitreihenrechnung mit `load_profile`/`sgen_profile` (CSV/JSON) aus dem Ressourcenverzeichnis, verarbeitet externe Setpoints und emittiert Events. Upstream (`pandapowerWrapper/`) ist dagegen für die **T&D-Kopplung** gebaut: Ghost-Busse, Schnitte, Ressourcen per Kafka. Ein Merge Zeile für Zeile ist nicht sinnvoll.

| # | Lokale Änderung | Ziel | Begründung |
|---|---|---|---|
| D1 | Profilbasierte Zeitreihe (`load_profile`, `sgen_profile`, `step_length`, `n_steps`, `export_results`) | **Upstream** (PR 8) | Als **Modus** des Upstream-Wrappers (z. B. BB-Parameter `mode=timeseries` vs. `td`) oder als eigener BB-Typ `pandapowerTimeseries`. **Entscheidung der Maintainer.** |
| D2 | Externe Setpoints über `interaction.simulation.{sce}.charging.setpoints` (`apply_external_setpoints`) | **Upstream** (PR 8) | Generisch formulieren („Lastsollwerte“), Schema A1. |
| D3 | `simulation_event_emitter.py` (pro Wrapper) | **Upstream** (PR 4) in `PythonBaseWrapper` | Gemeinsam für alle Python-Wrapper, nicht pro Wrapper kopiert. |
| D4 | Pfade über `RESOURCES_DIR`/`RESULTS_DIR`/`TASK_DIR`, Config über Env | **Upstream** (PR 2), ohne `TASK_DIR` | Wie C1. |
| D5 | `pp.from_pickle` und `pp.from_json` mit `_module` (lokal **und upstream**) | **Upstream** (PR 0, Security) | Code-Ausführung über hochgeladene Netzdateien. Pickle ablehnen, JSON nur ohne `_module`/Klassen-Hooks bzw. über Allowlist. Unabhängig von SimaaS wichtig. |
| D6 | `Dockerfile` mit `java`-Shim (`/usr/local/bin/java` → Python) | **Weg** (Shim) / **Upstream** (Dockerfile, PR 1) | Shim wird durch S2 überflüssig. Abhängigkeiten pinnen (heute ungepinnt). |
| D7 | `config.properties` mit Cluster-Werten | **Adapter** (ConfigMap) | Upstream-Version enthält dafür noch persönliche Pfade → in PR 2 aufräumen. |
| D8 | `examples/long_profile_scenario/` | **Upstream** (mit PR 8) | |
| D9 | `requirements.txt` (nur 3 Pakete, Dockerfile installiert andere) | **Weg** / Upstream (PR 1) | Eine gepinnte Abhängigkeitsliste im Upstream. |

### ControllerWrapper

| # | Lokale Änderung | Ziel | Begründung |
|---|---|---|---|
| R1 | `controllerWrapper.py` (EV-Ladesteuerung: `uncontrolled`/`safe_mode`/`heuristic`, liest SUMO-Edge-Topics, schreibt Setpoints) | **Upstream** (PR 8) | Ist ein DaceDSX-Building-Block; sonst bleibt DaceDSX-Code in SimaaS. Vorschlag: `ControllerWrapper/` upstream oder `examples/ev-charging/`. Die Workshop-Spezifika (`station_mapping.json`) gehören dann ins Beispielszenario. |
| R2 | `Dockerfile` mit `java`-Shim | wie D6 | |

## PR-Liste für DaceDSX

Reihenfolge nach Abhängigkeiten. PR 0 und PR 5 sind unabhängig und können **sofort** eingereicht werden.

| PR | Titel | Inhalt (Inventar-Nr.) | Hängt ab von | Akzeptanzkriterium |
|---|---|---|---|---|
| **0** | `pandapowerWrapper: refuse pickle and code-loading JSON networks` | D5 | – | Test: `.p`-Datei und JSON mit `_module` werden abgelehnt; reine pandapower-JSON-Netze laden weiter. |
| **1** | `Add Dockerfiles and publish images from CI` | S17, U13, D6, D9, C3, C4 | – | CI baut und pusht `ghcr.io/cs7org/dacedsx-{simservice,sumo,pandapower,…}:{version}` sowie `main-<sha>`; jedes Wrapper-Image hat `ENTRYPOINT`, das `<scenarioID> <instanceID>` nimmt; Abhängigkeiten gepinnt; non-root. |
| **2** | `Configuration via environment variables and CONFIG_PATH` | C1, C2, U7, D4, S16 (Teil), D7 (Aufräumen) | – | Einheitliche Env-Namen (`KAFKA_BROKER`, `SCHEMA_REGISTRY`, `CHANNEL_*`, `RESOURCES_DIR`, `RESULTS_DIR`, `CONFIG_PATH`) in Java/C++/Python; Repo-`config.properties` ohne persönliche Pfade, mit lokalen Defaults. |
| **3** | `Pluggable instance executor with optional Kubernetes Jobs` | S1, S3, S14, S2 (Vertrag) | 1, 2 | `executor=local` (Default, heutiges Verhalten) \| `kubernetes`; Interface deckt `hasStartFailed`/`getExitVal`/`terminate` ab; K8s: konfigurierbares Image-Präfix/Tag/PullPolicy, Resource-Limits, `securityContext`, nur benötigte Unterverzeichnisse mounten, `backoffLimit` konsistent; fabric8 optional. |
| **4** | `Structured lifecycle events topic` | S8, U6, D3 | 2 | Avro- oder JSON-Schema (versioniert) im Repo; Topic z. B. `orchestration.simulation.{scenarioID}.events`; Emitter in Java/C++/Python-Base, **nur Kafka**; Status-Topic bleibt kompatibel. |
| **5** | `SumoWrapper: fix routes, summary output, start time and exit codes` | U1, U2, U3, U4, U9 | – | Erlangen-Szenario (PR 9) läuft mit `simulationStart ≠ 0`; Routen werden geladen; Wrapper beendet sich bei Fehler mit ≠ 0. |
| **6** | `SimService: survive offset-commit failures during rebalance` | S9 | – | Mit Maintainern klären (Retry/Backoff); laufende Szenarien werden nicht beendet. |
| **7** | `SumoWrapper: optional vehicle telemetry` | U5 | 4 | Parameter dokumentiert, Default aus, keine Laufzeitkosten ohne Aktivierung. |
| **8** | `pandapower time-series mode, load setpoints and EV controller` | D1, D2, D8, A1, R1 | 2, 4; Design-Absprache | Vorher Issue: Modus vs. eigener BB-Typ. Beispielszenario mit SUMO + Controller + pandapower. |
| **9** | `Integration test: minimal co-simulation in CI` | U10, `examples/long_profile_scenario` | 1, 5 | CI startet Kafka + Registry, sendet ein Szenario, prüft Exit-Status und Status-/Event-Topic. Das ist der **Contract-Test** für SimaaS. |

Vor PR 3 und PR 8 je ein **Issue** zur Abstimmung eröffnen, da beide Architekturentscheidungen enthalten.

## Was in die `dacedsx-bridge` geht (dieses Repo)

- RabbitMQ `simulation_requests` konsumieren (S5); erst nach erfolgreichem Kafka-Publish acken.
- `scenarioID := task_id` setzen (S7), Szenario + `ResourceFile`s auf Kafka publizieren, also die Rolle von `SendScenarioObject` übernehmen (S4).
- Status-/Event-Topic des Szenarios abonnieren → Redis `task:{id}` und `results/{task_id}/events/structured_events.jsonl` (S6, S8).
- Deploy-Konfiguration: ConfigMaps statt eingebauter `config.properties` (S16, D7), `simservice/k8s/` → Image-Tags (S20).

## Was gelöscht wird, sobald die Images verfügbar sind

```
simservice/Worker/
simservice/JavaBaseWrapper/
simservice/CppBaseWrapper/
simservice/SumoWrapper/
simservice/cppbase+sumowrapper/      (nach PR 1, 5, 7)
simservice/PandaPowerWrapper/        (nach PR 0, 1, 8)
simservice/ControllerWrapper/        (nach PR 8)
simservice/src/, pom.xml, Dockerfile, config.properties   (nach PR 1–4)
simservice/nohup.out                 (sofort)
```

`simservice/k8s/` wandert nach `deploy/` (oder Helm-Chart).

## Offene Fragen an die Maintainer

1. **Große Ressourcen:** Uploads bis 512 MB passen nicht in Kafka-Nachrichten (Default `max.message.bytes` ≈ 1 MB). Soll die Bridge `ResourceFile.fileReference` (Shared Volume / Object Storage) nutzen? Wird das von allen Wrappern unterstützt?
2. **pandapower:** Zeitreihen-Modus im bestehenden Wrapper oder eigener BB-Typ (PR 8)?
3. **Release-Prozess:** SemVer-Tags auf `main`, Images auf `ghcr.io/cs7org`? Wer pflegt die CI-Secrets?
4. **Event-Schema:** Avro (wie der Rest) oder JSON-Schema? SimaaS braucht mindestens `category`, `eventCode`, `message`, `progress`, `simulationTime`, `fatal`.
5. **Executor-Default:** Bleibt `local` Default, mit `kubernetes` als Opt-in?

## Unabhängig davon (upstream, dringend)

- Branch `Simulation-Server` in `cs7org/DaceDSX` enthält eine Immatrikulationsbescheinigung (PDF). Branch löschen lassen, ggf. GitHub-Support um Cache-Bereinigung bitten.
- `SimService/config.properties` upstream enthält einen persönlichen Windows-Pfad (wird mit PR 2 bereinigt).
