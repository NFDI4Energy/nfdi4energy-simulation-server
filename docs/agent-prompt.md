# Agenten-Prompt: Roadmap umsetzen

Dieses Dokument hat drei Teile:

- **Teil 1** verweist auf die dauerhaften Regeln in `CLAUDE.md`.
- **Teil 2** ist der kurze Startprompt, den du pro Phase in eine neue Session gibst.
- **Teil 3** ist der vorgeschlagene Schnitt der Phasen in Review-Einheiten.

Platzhalter in `<SPITZEN_KLAMMERN>` im Startprompt pro Session ersetzen.

---

## Teil 1: Regeln

Die Regeln stehen in [`CLAUDE.md`](../CLAUDE.md) im Repo-Root. Claude Code lädt sie in jeder Session automatisch. Änderungen an den Regeln (z. B. Antworten der Maintainer) nur dort eintragen.

---

## Teil 2: Startprompt pro Phase

Pro Phase (bzw. pro Einheit aus Teil 3) eine **neue** Session starten, im SimaaS-Ordner, mit dem DaceDSX-Klon als zusätzlichem Ordner. Erst im Plan-Modus planen lassen, Plan prüfen, dann umsetzen.

```text
Setze Phase <N> der ROADMAP.md um (Einheiten laut Teil 3 in docs/agent-prompt.md: <z. B. 1a, 1b, 1c>).
Halte dich an die Regeln in CLAUDE.md.

Stand der Vorgänger: <z. B. „Phase 0 ist gemergt“ / „roadmap/phase-1a-repo-hygiene ist noch im Review, darauf aufsetzen“>.
Antworten der Maintainer seit der letzten Phase: <keine / Text>.

Bevor du Code änderst:
1. Lies die Schritte der Phase, die zugehörigen Abschnitte in TODO.md und im Patch-Inventar und den betroffenen Code.
2. Lege einen Plan vor: Einheiten mit Branch-Namen und Basis, Schritte mit geplanten Commits,
   geschätzte Größe je Einheit, geplante Tests und Akzeptanztest, Schritte, die du nicht selbst
   erledigen kannst, und Annahmen.
Warte auf meine Freigabe des Plans, dann setze ihn Schritt für Schritt um.
```

---

## Teil 3: Vorgeschlagener Schnitt in Review-Einheiten

| Einheit | Repo | Schritte | Inhalt | Hinweis |
|---|---|---|---|---|
| 0a | SimaaS | 2, 4 | `nohup.out` löschen; Mosaik per Konfiguration abschaltbar, standardmäßig aus | trägt auch die Häkchen für 0b |
| 0b | DaceDSX | 3 | PR 0: pandapower lehnt Pickle und JSON mit `_module` ab | sofort einreichbar |
| 1a | SimaaS | 7, 8 | Laufzeitdaten und `svelte-dist` aus Git | fast nur Löschungen |
| 1b | SimaaS | 9, 10, 11 | Dockerfile, gepinnte Abhängigkeiten, Backend-Tests, CI | Grundlage für alle weiteren Tests |
| 1c | SimaaS | 12 | Login aktiv, `AUTH_DISABLED` in Produktion verboten, `https_only` | OIDC-Registrierung macht der Mensch |
| 2a–2h | DaceDSX | 13–15, 18–23 | ein Branch pro PR: 5, 2, 1, 6, 9, 4, 3, 7, 8 | Reihenfolge und Abhängigkeiten laut Roadmap |
| 2i | DaceDSX | 16, 17 | Release-Workflow, CHANGELOG, Wrapper-READMEs | kein Tag setzen |
| 2t | SimaaS | 13–24 | Häkchen, `docs/changes/phase-2.md`, PR-Beschreibungen, Zeitsync-Test (24) | Tracking-Branch für Phase 2 |
| 3a | SimaaS | 25, 26 | `dacedsx-bridge` mit Tests | gegen lokal gebaute Images aus den 2er-Branches testen |
| 3b | SimaaS | 27, 28 | feste Image-Versionen, Renovate, Contract-Test in CI | |
| 3c | SimaaS | 29 | `simservice/` löschen, `k8s/` nach `deploy/` | erst wenn die zugehörigen PRs gemergt sind |
| 4a | SimaaS | 30, 31, 32 | Worker-Fehlerbehandlung, hängende Tasks, Abbrechen/Löschen | |
| 4b | SimaaS | 33, 34 | Dateirechte, Szenario-Validierung | |
| 4c | SimaaS | 35, 36 | Alembic, EventStore-Umbau | größte Einheit in Phase 4, ggf. weiter teilen |
| 5a | SimaaS | 37 | Besitzprüfung für alle Endpunkte | Tests für fremde Tasks |
| 5b | SimaaS | 38, 39, 40 | Mounts pro Task, NodePorts zu, Auth für Dienste, NetworkPolicies | |
| 5c | SimaaS | 41 | Mosaik isolieren | eher Design + Prototyp, ggf. eigener Folge-Branch |
| 6a | SimaaS | 42, 43, 44 | Helm/Kustomize, Registry-Images, Secrets | Helm muss erst installiert werden, sonst Kustomize |
| 6b | SimaaS | 45, 46 | RWX-Speicher, Backups, Kafka KRaft | |
| 6c | SimaaS | 47, 48, 49 | Ingress/TLS, Health-Endpunkte, Monitoring | Domain macht der Mensch |
| 7a | SimaaS | 50–53 | Aufbewahrung konfigurierbar, Vorlagen Impressum/Datenschutz/AGB, Quellcode-Link | Texte rechtlich prüfen lassen |
| 8a | SimaaS | 54, 55 | Landingpage, Mosaik-GUI-URL | |
| 8b | SimaaS | 56, 57 | Live-Stats und Graph optional | |
| 8c | SimaaS | 58 | generische Live-Stats | nach 3a |
| 9a | SimaaS | 59 | Lasttest-Skripte | |
| 9b | SimaaS | 60, 61 | Requests/Limits, `ResourceQuota` | Messwerte aus echter Umgebung nachtragen |
| 9c | SimaaS | 62 | Credits: erst Konzept-Dokument zum Review, Umsetzung in Folge-Branch | |
| 10a | SimaaS | 63 | Analysebericht zu den übrigen DaceDSX-Branches | nur Bericht |
| 10b | DaceDSX | 64, 65 | OMNeT++ rebasen, headless, Image | |
| 10c | DaceDSX + SimaaS | 66, 67 | Kopplung mit Energiedomäne, Freischaltung im SimaaS | |

**Parallel arbeiten:** Phase 1 (SimaaS) und Phase 2 (DaceDSX) können gleichzeitig in zwei Sessions laufen. Beide schreiben aber in das SimaaS-Repo (Häkchen, Doku). Deshalb jede Session in einem **eigenen Git-Worktree** starten, nie zwei Sessions im selben Ordner auf verschiedenen Branches.
