# TODO: SimaaS & DaceDSX

Stand: 2026-11-05 · ★ = aus deiner Liste, sonst Vorschlag aus dem Audit bzw. dem [Patch-Inventar](docs/dacedsx-patch-inventory.md)

**Legende:** 🔴 dringend / vor öffentlichem Betrieb · `[DaceDSX]` = Arbeit im Repo `cs7org/DaceDSX` · `[SimaaS]` = dieses Repo · PR-Nummern beziehen sich auf das Patch-Inventar

---

## 1. Sofort: Datenschutz & kritische Sicherheit

- [ ] 🔴 `[DaceDSX]` Branch `Simulation-Server` löschen. Er enthält eine Immatrikulationsbescheinigung (PDF). Ggf. GitHub-Support um Cache-Bereinigung bitten.
- [ ] 🔴 `[DaceDSX]` PR 0: `pp.from_pickle` / `pp.from_json` mit `_module` ablehnen (Code-Ausführung über hochgeladene Netze; lokal **und** upstream betroffen)
- [ ] 🔴 `[SimaaS]` `simservice/nohup.out` löschen (Minikube-Log mit Home-Pfad)
- [ ] 🔴 `[DaceDSX]` Persönlichen Windows-Pfad aus `SimService/config.properties` entfernen (in PR 2)

## 2. DaceDSX-Integration entkoppeln

- [ ] ★ `[DaceDSX]` DaceDSX als Container aus einer Registry einbinden statt Code-Kopie (PR 1: Dockerfiles + CI-Publishing nach `ghcr.io/cs7org/…`, Tags `vX.Y.Z` und `main-<sha>`)
- [ ] `[DaceDSX]` PR 2: Konfiguration per Env-Variablen/`CONFIG_PATH` in Java, C++ und Python
- [ ] `[DaceDSX]` PR 3: Executor-Plugin `local | kubernetes` (K8s-Executor aus diesem Repo, mit Limits, `securityContext`, konsistentem `backoffLimit`, ohne festes `/data`-Mount)
- [ ] `[DaceDSX]` PR 4: Strukturierte Lifecycle-Events als versioniertes Schema auf einem Kafka-Topic
- [ ] `[DaceDSX]` PR 6: SimService übersteht Offset-Commit-Fehler beim Rebalance
- [ ] `[DaceDSX]` PR 9: Integrationstest (Mini-Co-Simulation) in der Upstream-CI als Contract-Test
- [ ] `[SimaaS]` `dacedsx-bridge` bauen: RabbitMQ → Kafka-Scenario, `scenarioID = task_id`, Ressourcen publizieren, Status/Events → Redis + JSONL; erst nach erfolgreichem Publish acken
- [ ] `[SimaaS]` Mit Maintainern klären, wie große Ressourcen übertragen werden (Kafka ~1 MB vs. 512 MB Upload, `ResourceFile.fileReference`?)
- [ ] `[SimaaS]` Manifeste auf feste DaceDSX-Image-Versionen umstellen; Renovate/Dependabot für neue Releases
- [ ] `[SimaaS]` `simservice/` löschen (Reihenfolge siehe Patch-Inventar), `simservice/k8s/` nach `deploy/`

## 3. DaceDSX: Simulatoren & Co-Simulation

- [ ] ★ `[DaceDSX]` SUMO-pandapower-Co-Sim in `main` integrieren
  - Hinweis: Der Branch `sumo_pandapower_co_sim` ist bereits vollständig in `main` (0 Commits voraus). Die **lauffähige** Co-Sim liegt in diesem Repo (`cppbase+sumowrapper/`, `PandaPowerWrapper/`, `ControllerWrapper/`, `examples/ev-charging-workshop/`) und kommt über die folgenden PRs upstream:
  - [ ] PR 5: SUMO-Bugfixes (Route-Files, `summary-output`, Startzeit ≠ 0, Exit-Codes, `std:cout`)
  - [ ] PR 7: optionale Fahrzeug-Telemetrie im SumoWrapper
  - [ ] Issue: Zeitreihen-Modus in pandapower als Modus oder eigener BB-Typ?
  - [ ] PR 8: pandapower-Zeitreihe, Last-Setpoints, `ChargingSetpoint.avsc`, Controller-Wrapper als Wrapper oder Beispiel
  - [ ] Controller-/PandaPower-Zeitsync-Probleme (226ae7a) gegen upstreams neuen `TimeSync` nachtesten
- [ ] ★ `[DaceDSX]` OMNeT++-Integration verbessern / Lauf ohne GUI prüfen
  - Code liegt im Branch `Omnet++Wrapper` (`OppWrapper/`, 15 Commits voraus, 46 hinter `main`, Stand 2025-07) → zuerst auf `main` rebasen
  - Headless: OMNeT++ bringt die Kommandozeilen-Umgebung `Cmdenv` mit (`-u Cmdenv`). Prüfen, ob der Wrapper damit startet; dann Container-Image wie bei den anderen Wrappern
- [ ] ★ `[DaceDSX]` OMNeT++ für Kopplung mit der Energiedomäne erweitern (hängt am Punkt davor)
  - Avro-Schema für Mess- und Steuernachrichten (Kommunikationsverzögerung/-verlust zwischen Controller und pandapower) definieren
  - Beispielszenario: Controller ↔ OMNeT++ ↔ pandapower

## 4. DaceDSX: Repo-Pflege & Doku

- [ ] ★ `[DaceDSX]` Offene Branches aufräumen
  - [ ] Vollständig gemergt (0 voraus), löschen: `FAIRer_DaceDS`, `PyPSA_Wrapper`, `minor_bugfix_after_license_change`, `opendss-fresh-test`, `readme-update`, `sumo_pandapower_co_sim`, `update-branch-1`
  - [ ] Mit eigenen Commits, entscheiden (mergen/archivieren): `Omnet++Wrapper` (15), `codipy_dev` (15), `update-markdown` (6), `codipy-push` (2), `pv_and_battery` (2), `feature/opendss-setup-instructions` (1), `revert-11-feature/opendss-setup-instructions` (1)
  - [ ] `Simulation-Server`: siehe Abschnitt 1
- [ ] ★ `[DaceDSX]` Wrapper-spezifische Anleitungen in READMEs der Wrapper-Ordner verschieben
  - [ ] SUMO-Build (heute „What to do to compile the SumoWrapper“ im Root-README) → `SumoWrapper/README.md`
  - [ ] PyPSA-Szenario (heute „What to do to run a PyPSA-scenario“) → `PyPSAWrapper/README.md`
  - [ ] pandapower, OpenDSS (Inhalt aus `feature/opendss-setup-instructions` übernehmen), Carla, OMNeT++ ergänzen
  - [ ] Root-README: nur Überblick, Architektur, Links auf Wrapper-READMEs, Container-Nutzung
- [ ] `[DaceDSX]` Release-Prozess festlegen (SemVer-Tags, Changelog)

## 5. SimaaS: Frontend

- [ ] ★ Login wieder aktivieren
  - `AUTH_DISABLED` muss `false` sein (Default; wird in `.env` bzw. `build-minikube.sh` überschrieben), OIDC-Client bei NFDI AAI für die öffentliche Domain registrieren
  - Session-Cookie mit `https_only` (`fastapi_app/webapp.py`)
  - `AUTH_DISABLED` in Produktion hart verbieten (Startfehler, wenn gesetzt und nicht lokal)
- [ ] ★ Start-/Landingpage für DaceDSX anpassen (`frontend/src/lib/FrameworkChooser.svelte`): Kurzbeschreibung, verfügbare Wrapper, Beispielszenarien, Doku-Link
- [ ] ★ Live-Stats optional machen (Schalter pro Lauf oder in den Szenario-Einstellungen; ohne Live-Stats nur Status + Logs)
- [ ] ★ Graph-Ansicht optional / nur für kleine Netze (Schwellwert z. B. nach Bus-/Fahrzeuganzahl; SUMO kappt schon bei `monitorMaxVehicles = 200`)
- [ ] ★ Prüfen, ob Live-Stats verallgemeinert werden können
  - Heute fest verdrahtet in `RunMonitor.svelte` (1385 Z.; `energy` → „Network State“, sonst Fahrzeugprojektion)
  - Vorschlag: Wrapper melden generische Metriken (Name, Einheit, Wert, Simulationszeit) über das Event-Schema aus PR 4; Frontend zeigt generische Zeitreihen, domänenspezifische Ansichten nur als Plugins
- [ ] Mosaik-GUI-URL nicht hart auf `http://localhost:8002` (`frontend/src/lib/MosaikWorkspace.svelte:7`)
- [ ] Laufende Tasks abbrechen und löschen können (Backend-Endpunkt fehlt ebenfalls)
- [ ] `fastapi_app/static/svelte-dist/` nicht mehr committen, im Docker-Build erzeugen

## 6. SimaaS: Backend & Bugs

- [ ] scenarioID-Kollision: gleiche ID wird von SimService still ignoriert (`ScenarioManager.java:195`) → erledigt durch Bridge mit `scenarioID = task_id`
- [ ] Hängende Tasks erkennen (Timeout/Heartbeat → Status `ERROR`), sonst bleiben sie ewig `PENDING`/`RUNNING`
- [ ] Mosaik-Worker: Exception in `process_task` führt zu Endlos-Redelivery (Poison Message) → Fehler abfangen, nack ohne Requeue / Dead-Letter-Queue; Timeout mit Abbruch
- [ ] SimService-Zustand ist im Speicher und nicht thread-sicher, Ack vor Verarbeitung → mit Bridge-Umbau erledigt bzw. upstream adressieren
- [ ] `chmod 0o777` in `fastapi_app/tasks/storage.py:68-71` durch passende Gruppe/UID ersetzen
- [ ] Szenario-Validierung: Allowlist für Wrapper-Typen und Ressourcentypen; Pydantic v1 `root_validator` migrieren
- [ ] EventStore skalieren: eine SQLite-Datei hinter globalem Lock, SSE pollt jede Sekunde → Postgres-Tabelle oder Redis Streams, Push statt Polling
- [ ] Datenbank-Migrationen mit Alembic

## 7. SimaaS: Sicherheit & Isolation

- [ ] 🔴 Mosaik: Nutzer-Code läuft ohne Sandbox; `mosaik-gui` ist ein geteilter Editor ohne Authentifizierung → hinter Login, pro Nutzer isoliert, oder vorerst nicht öffentlich anbieten
- [ ] 🔴 Pods mounten das ganze `/data` (inkl. TLS-Key unter `/data/certs`) → pro Task nur `resources/<id>` (read-only) und `results/<id>`; Zertifikate als K8s-Secret
- [ ] 🔴 NodePorts schließen (RabbitMQ 30672/31672, Web 30501, SimService 30080); nur Ingress öffentlich; Kafka/RabbitMQ/Redis mit Auth
- [ ] Autorisierung: alle Task-/Ergebnis-Endpunkte prüfen Besitz (nicht nur Login)
- [ ] NetworkPolicies: Wrapper-Pods dürfen nur Kafka/Registry erreichen

## 8. SimaaS: Ressourcen, Fairness & Skalierung

- [ ] ★ Dedizierte Simulationszeit / Simulations-Credits konzipieren
  - Pro Nutzer: max. gleichzeitige Läufe, max. Laufzeit pro Lauf (über `scenarioMaxAge`), Speicherkontingent
  - Verbrauch messen (CPU-/Wandzeit-Stunden aus K8s-Jobs) und als Credits abrechnen; Warteschlange mit Priorität
  - K8s `ResourceQuota`/`LimitRange` im Wrapper-Namespace
- [ ] Aufbewahrung von Ergebnissen begrenzen (z. B. 30 Tage) und Nutzer vorher informieren; Job-TTL (600 s) mit Log-Sicherung abstimmen
- [ ] ★ SimaaS mit größeren Simulationen testen
  - [ ] Lange Läufe (> 60 min = `scenarioMaxAge`-Default) und viele Schritte (Limit 100k Schritte in `scenario.py`)
  - [ ] Große Netze/Uploads (Kafka-Nachrichtengröße, 512 MB Upload-Limit)
  - [ ] Viele parallele Läufe/Nutzer (EventStore, SSE, Redis, Kafka-Topics pro Szenario)
  - [ ] Ressourcenbedarf je Wrapper messen → Requests/Limits festlegen
  - [ ] Ergebnisse als Lasttest-Skript im Repo ablegen

## 9. Deployment & Betrieb (öffentliche Server)

- [ ] Ingress mit TLS (cert-manager), eine öffentliche Domain
- [ ] Images in einer Registry mit festen Versionen (keine `latest`, kein `imagePullPolicy: Never`)
- [ ] Helm-Chart oder Kustomize statt einzelner YAML-Dateien
- [ ] Speicher: RWX-Volume statt hostPath, Backups für Postgres und Ergebnisse
- [ ] Kafka verschlanken (KRaft, ohne Connect/ksqlDB/REST-Proxy), nicht PLAINTEXT nach außen
- [ ] Secrets-Management (Sealed Secrets / External Secrets) statt `.env`
- [ ] Health-/Readiness-Endpunkte für Web, Worker, Bridge
- [ ] Monitoring & Logging (Prometheus/Grafana, zentrale Logs), Alerting bei hängenden Tasks
- [ ] Web-Dockerfile: Base-Image Python 3.8 (EOL) ersetzen, `requirements.txt` pinnen

## 10. Tests, CI & Repo-Hygiene (SimaaS)

- [ ] Backend-Tests anlegen (`/fastapi_app/tests/` steht heute in `.gitignore`)
- [ ] CI: Lint, Tests, Frontend-Build, Image-Build; Contract-Test gegen DaceDSX-Image
- [ ] Laufzeitdaten aus Git entfernen (113 Dateien unter `data/resources`, `data/results`)
- [ ] Build-Artefakte aus Git entfernen (`bin/`, `obj/`, `logs/`, SUMO-Binary, vendorte C++-Repos), danach mit `simservice/` erledigt

## 11. Recht & Organisation

- [ ] Impressum und Datenschutzerklärung (OIDC-Daten, Uploads, Aufbewahrung)
- [ ] Nutzungsbedingungen (erlaubte Nutzung, Kontingente, keine Garantie)
- [ ] AGPL §13: Link auf den Quellcode der laufenden Version im Frontend
- [ ] Abstimmung mit den DaceDSX-Maintainern (cs7org) zu PR-Reihenfolge, Release-Prozess und offenen Fragen
