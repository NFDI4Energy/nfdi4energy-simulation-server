# Roadmap: SimaaS & DaceDSX

Stand: 2026-11-11 · Dieselben Punkte wie in [TODO.md](TODO.md), aber **in Bearbeitungsreihenfolge** statt nach Themen. PR-Nummern beziehen sich auf das [Patch-Inventar](docs/dacedsx-patch-inventory.md).

**Legende:** `[DaceDSX]` = Arbeit im Repo `cs7org/DaceDSX` · `[SimaaS]` = dieses Repo · ⏸ = wartet auf Review/Antwort der Maintainer · ⇉ = kann parallel zur vorherigen Phase laufen

## Wie die Reihenfolge zustande kommt

Es gibt zwei Stränge:

- **Upstream (Phase 2):** PRs an DaceDSX. Wie schnell es hier vorangeht, bestimmen die Reviews der Maintainer. Deshalb früh einreichen.
- **SimaaS (Phasen 1, 3 bis 10):** In diesem Repo. Die Wartezeit auf Upstream-Reviews kann man mit den Phasen 1 und 4 füllen, weil sie DaceDSX nicht brauchen.

Für den **öffentlichen Betrieb** müssen die Phasen 0 bis 7 abgeschlossen sein. Phase 8 bis 10 können danach folgen.

---

## Phase 0: Sofort (unabhängig, Datenschutz und Sicherheit)

1. [x] `[DaceDSX]` Branch `Simulation-Server` löschen lassen und GitHub-Support bitten, Commit `1d96071e16901d79235ce9948f54a1b4d0b37604` zu entfernen (beides macht ein Admin von cs7org). Die betroffene Person informieren.
2. [x] `[SimaaS]` `simservice/nohup.out` löschen. (Branch: `roadmap/phase-0a-cleanup-mosaik-off`)
3. [~] `[DaceDSX]` **PR 0** einreichen: pandapower lehnt Pickle und JSON mit `_module` ab. (Branch: `simaas/pr0-pandapower-safe-load` in DaceDSX, SimaaS-Kopie in `roadmap/phase-0c-pandapower-guard`; fehlt: PR öffnen, Text in `docs/changes/dacedsx-pr0.md`. Abweichung: JSON mit `_module` wird per Allowlist geprüft statt pauschal abgelehnt, Pickle per `PANDAPOWER_ALLOW_PICKLE=true` als Opt-in)
4. [x] `[SimaaS]` Entscheidung: Mosaik bleibt vorerst nicht öffentlich, bis Phase 5 erledigt ist (Nutzer-Code ohne Sandbox, `mosaik-gui` ohne Authentifizierung). (Branch: `roadmap/phase-0a-cleanup-mosaik-off`; Entscheidung am 2026-11-12 revidiert: Mosaik bleibt aktiv, weil `main` inzwischen Editor-Login und Task-Pods hat; Rest von 41 offen)
5. [ ] `[DaceDSX]` Termin mit den Maintainern: Plan vorstellen, die 5 offenen Fragen aus dem Patch-Inventar klären (große Ressourcen, pandapower-Modus, Release-Prozess, Event-Schema, Executor-Default). Issues für PR 3 und PR 8 eröffnen. Davon hängt fast alles in Phase 2 und 3 ab. ⚠ menschlicher Schritt, Agenda in `docs/changes/phase-0.md`
6. [ ] `[DaceDSX]` Vollständig gemergte Branches löschen: `FAIRer_DaceDS`, `PyPSA_Wrapper`, `minor_bugfix_after_license_change`, `opendss-fresh-test`, `readme-update`, `sumo_pandapower_co_sim`, `update-branch-1` (im selben Termin absprechen). ⚠ menschlicher Schritt

## Phase 1: Grundlage im SimaaS ⇉ parallel zu Phase 2

Tests und CI zuerst, damit die späteren Umbauten abgesichert sind.

7. [x] Laufzeitdaten aus Git entfernen (`data/resources`, `data/results`) und in `.gitignore` aufnehmen. (Branch: `roadmap/phase-1a-repo-hygiene`)
8. [x] `fastapi_app/static/svelte-dist/` nicht mehr committen, im Docker-Build erzeugen. (Branch: `roadmap/phase-1a-repo-hygiene` für das Entfernen, `roadmap/phase-1b-docker-build` für den Build im Image)
9. [x] Web-Dockerfile: Python 3.8 (EOL) ersetzen, `requirements.txt` pinnen, non-root-User. (Branch: `roadmap/phase-1b-docker-build`)
10. [x] Backend-Tests anlegen (`fastapi_app/tests/` aus `.gitignore` nehmen). (Branch: `roadmap/phase-1c-backend-tests-ci`)
11. [x] CI: Lint, Tests, Frontend-Build, Image-Build. (Branch: `roadmap/phase-1c-backend-tests-ci`; erster CI-Lauf erst nach dem Push)
12. [~] Login wieder aktivieren: `AUTH_DISABLED=false`, in Produktion hart verbieten, Session-Cookie `https_only`, OIDC-Client bei NFDI AAI für die spätere Domain beantragen (dauert ggf.). (Branch: `roadmap/phase-1d-auth-hardening`; fehlt: OIDC-Client-Registrierung, Angaben in `docs/changes/phase-1.md`)

## Phase 2: Upstream-PRs an DaceDSX ⏸

Reihenfolge nach Abhängigkeiten. Wo nichts steht, ist der PR unabhängig.

13. [ ] **PR 5:** SUMO-Bugfixes (Route-Files, `summary-output`, Startzeit ≠ 0, Exit-Codes).
14. [ ] **PR 2:** Konfiguration über Env-Variablen und `CONFIG_PATH`; entfernt dabei den persönlichen Windows-Pfad aus `config.properties`.
15. [ ] **PR 1:** Dockerfiles und CI-Publishing nach `ghcr.io/cs7org/dacedsx-*`.
16. [ ] Release-Prozess festlegen (SemVer-Tags, Changelog) und **erstes Release** taggen, damit es feste Image-Versionen gibt (nach 15).
17. [ ] Wrapper-Anleitungen in die READMEs der Wrapper-Ordner verschieben, Root-README auf Überblick und Container-Nutzung kürzen (passt zu 15).
18. [ ] **PR 6:** SimService übersteht Offset-Commit-Fehler beim Rebalance.
19. [ ] **PR 9:** Integrationstest (Mini-Co-Simulation) in der Upstream-CI (nach 13 und 15).
20. [ ] **PR 4:** Strukturierte Lifecycle-Events auf einem Kafka-Topic (nach 14, Schema-Frage aus 5 geklärt).
21. [ ] **PR 3:** Executor-Plugin `local | kubernetes` mit Limits, `securityContext`, Mounts nur pro Task (nach 14, 15 und dem Issue aus 5).
22. [ ] **PR 7:** Optionale Fahrzeug-Telemetrie im SumoWrapper (nach 20).
23. [ ] **PR 8:** pandapower-Zeitreihe, Last-Setpoints, Controller (nach 14, 20 und dem Issue aus 5). Damit ist die SUMO-pandapower-Co-Sim in `main`.
24. [ ] Controller-/pandapower-Zeitsync (226ae7a) gegen den neuen `TimeSync` upstream nachtesten (mit 23).

## Phase 3: SimaaS auf DaceDSX-Images umstellen

Beginnt, sobald 15 und 20 gemergt sind. Die Bridge kann schon früher gegen die lokalen Images entwickelt werden, wenn das Event-Schema feststeht.

25. [ ] `dacedsx-bridge` bauen: RabbitMQ → Kafka, `scenarioID = task_id` (behebt die scenarioID-Kollision), Ressourcen publizieren, Status/Events → Redis + JSONL, erst nach erfolgreichem Publish acken.
26. [ ] Übertragung großer Ressourcen so umsetzen, wie in 5 vereinbart (z. B. `ResourceFile.fileReference` statt Kafka-Nachricht).
27. [ ] Manifeste auf feste DaceDSX-Image-Versionen umstellen; Renovate/Dependabot einrichten.
28. [ ] Contract-Test in der SimaaS-CI gegen das DaceDSX-Image.
29. [ ] `simservice/` schrittweise löschen (Reihenfolge laut Patch-Inventar, jeweils nach dem zugehörigen PR); `simservice/k8s/` nach `deploy/`. Damit sind auch die Build-Artefakte und vendorten C++-Repos weg.

## Phase 4: Backend-Robustheit ⇉ parallel zu Phase 2 und 3

Hängt nicht an DaceDSX und füllt Wartezeiten auf Reviews.

30. [ ] Mosaik-Worker: Exceptions abfangen, nack ohne Requeue bzw. Dead-Letter-Queue, Timeout mit Abbruch.
31. [ ] Hängende Tasks erkennen (Heartbeat/Timeout → `ERROR`).
32. [ ] Laufende Tasks abbrechen und löschen: Backend-Endpunkt und Button im Frontend.
33. [ ] `chmod 0o777` in `fastapi_app/tasks/storage.py` durch passende Gruppe/UID ersetzen.
34. [ ] Szenario-Validierung: Allowlist für Wrapper- und Ressourcentypen; Pydantic-`root_validator` migrieren.
35. [ ] Datenbank-Migrationen mit Alembic.
36. [ ] EventStore von SQLite auf Postgres-Tabelle oder Redis Streams umstellen, SSE per Push statt Polling.

## Phase 5: Sicherheit & Isolation

37. [ ] Autorisierung: alle Task- und Ergebnis-Endpunkte prüfen den Besitz.
38. [~] Pods mounten nur `resources/<id>` (read-only) und `results/<id>`; Zertifikate als K8s-Secret (setzt 21 voraus). (auf `main` @ 343afcc/9210711 ohne Roadmap-Branch umgesetzt: `subPath`-Mounts, `web-tls`-Secret; fehlt: Review, Tests hier im Repo, Abgleich mit PR 3)
39. [~] NodePorts schließen, nur Ingress öffentlich; Kafka, RabbitMQ und Redis mit Authentifizierung. (auf `main` @ d6e8a71/9210711 umgesetzt: SASL/TLS, Passwörter aus Secrets, Traefik-Ingress; fehlt: Review und Tests)
40. [ ] NetworkPolicies: Wrapper-Pods erreichen nur Kafka und Schema Registry.
41. [~] Mosaik: Nutzer-Code isolieren (eigener Pod pro Lauf mit Limits), `mosaik-gui` hinter Login und pro Nutzer. Erst danach Mosaik öffentlich anbieten (siehe 4). (auf `main` @ fc6c24a/8641b6f umgesetzt: Editor-Gateway hinter Login, Orbit-Pod pro Lauf; fehlt: Limits/`securityContext`/NetworkPolicy für die Task-Pods, Review, Tests)

## Phase 6: Deployment auf öffentlichen Servern

42. [ ] Helm-Chart oder Kustomize statt einzelner YAML-Dateien.
43. [ ] Alle Images aus einer Registry mit festen Versionen (kein `latest`, kein `imagePullPolicy: Never`).
44. [ ] Secrets-Management (Sealed Secrets / External Secrets) statt `.env`.
45. [ ] Speicher: RWX-Volume statt hostPath; Backups für Postgres und Ergebnisse.
46. [ ] Kafka verschlanken (KRaft, ohne Connect/ksqlDB/REST-Proxy).
47. [~] Ingress mit TLS (cert-manager) auf der öffentlichen Domain; OIDC-Redirect auf diese Domain umstellen (siehe 12). (auf `main` @ 9210711: Traefik-Ingress mit eigenem Zertifikat, `SIM_SERVER_HOST/URL`, Redirect-URI aus `SIM_SERVER_URL`; fehlt: öffentliche Domain, cert-manager)
48. [ ] Health-/Readiness-Endpunkte für Web, Worker und Bridge.
49. [ ] Monitoring, zentrale Logs, Alerting bei hängenden Tasks.

## Phase 7: Recht & Organisation ⇉ parallel ab Phase 4, Pflicht vor dem Go-live

50. [ ] Aufbewahrungsfrist für Ergebnisse festlegen (z. B. 30 Tage) und Job-TTL mit Log-Sicherung abstimmen; wird in der Datenschutzerklärung gebraucht.
51. [ ] Impressum und Datenschutzerklärung (OIDC-Daten, Uploads, Aufbewahrung).
52. [ ] Nutzungsbedingungen (erlaubte Nutzung, Kontingente, keine Garantie).
53. [ ] AGPL §13: Link auf den Quellcode der laufenden Version im Frontend.

> **Meilenstein: öffentlicher Betrieb** (vorerst mit festen Limits pro Nutzer statt Credits)

## Phase 8: Frontend

54. [ ] Start-/Landingpage für DaceDSX: Kurzbeschreibung, Wrapper, Beispielszenarien, Doku-Link.
55. [~] Mosaik-GUI-URL konfigurierbar statt `http://localhost:8002`. (auf `main` @ fc6c24a: `MOSAIK_GUI_URL` und `/mosaik/`-Gateway; fehlt: Review)
56. [ ] Live-Stats optional machen.
57. [ ] Graph-Ansicht optional bzw. nur für kleine Netze.
58. [ ] Live-Stats verallgemeinern: generische Metriken über das Event-Schema aus PR 4, domänenspezifische Ansichten als Plugins (nach 20 und 25).

## Phase 9: Last, Ressourcen & Fairness

Braucht das Deployment aus Phase 6, damit die Messwerte aussagekräftig sind.

59. [ ] Mit größeren Simulationen testen: lange Läufe, viele Schritte, große Netze/Uploads, viele parallele Nutzer; Lasttest-Skript ins Repo.
60. [ ] Ressourcenbedarf je Wrapper messen → Requests/Limits festlegen.
61. [ ] K8s `ResourceQuota`/`LimitRange` im Wrapper-Namespace.
62. [ ] Simulationszeit/Credits konzipieren und umsetzen: max. gleichzeitige Läufe, max. Laufzeit, Speicherkontingent, Verbrauch messen, Warteschlange mit Priorität.

## Phase 10: Neue Simulatoren (OMNeT++)

Erst wenn die Basis stabil ist, weil jeder neue Wrapper über denselben Weg (Image, Executor, Events) eingebunden wird.

63. [ ] `[DaceDSX]` Übrige Branches mit eigenen Commits entscheiden (mergen/archivieren): `codipy_dev`, `update-markdown`, `codipy-push`, `pv_and_battery`, `feature/opendss-setup-instructions` (Inhalt in die OpenDSS-README), `revert-11-feature/opendss-setup-instructions`.
64. [ ] `[DaceDSX]` `Omnet++Wrapper` auf `main` rebasen.
65. [ ] `[DaceDSX]` OMNeT++ headless mit `Cmdenv` (`-u Cmdenv`) starten; Container-Image wie bei den anderen Wrappern.
66. [ ] `[DaceDSX]` OMNeT++ mit der Energiedomäne koppeln: Avro-Schema für Mess- und Steuernachrichten, Beispielszenario Controller ↔ OMNeT++ ↔ pandapower.
67. [ ] `[SimaaS]` OMNeT++ im Frontend und in der Szenario-Validierung freischalten.
