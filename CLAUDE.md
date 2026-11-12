# Arbeitsregeln für die Roadmap-Umsetzung

## Umgebung
- SimaaS-Repo: `/home/cori/Desktop/nfdi4energy-simulation-server` (hier liegen ROADMAP.md, TODO.md, docs/)
- DaceDSX-Repo: `/home/cori/Desktop/DaceDSX_new` (Klon von `cs7org/DaceDSX`, Basis `main`).
  Die ungetrackten Dateien `CppBaseWrapper/Makefile`, `SimService/out.txt`, `_data/scenarios/resource.json`
  und `build_all.sh` gehören nicht zur Arbeit: nicht committen, nicht löschen.
- Maßgeblich sind `ROADMAP.md` (Reihenfolge, Schritt-Nummern) und `docs/dacedsx-patch-inventory.md`
  (Inhalt und Akzeptanzkriterien der DaceDSX-PRs, Inventar-Nummern S1–S20, U1–U13, D1–D9 usw.).
  `TODO.md` liefert Hintergrund. Bei Widersprüchen gilt ROADMAP.md und du notierst den Widerspruch.
- Startprompt pro Phase und Schnitt in Review-Einheiten: `docs/agent-prompt.md`.
- Verfügbare Werkzeuge: python3/pytest, java/mvn, node/npm, docker, minikube, kubectl, cmake/g++. Helm ist global nicht installiert; `build-minikube.sh` lädt es seit `main` @ 724c9bf bei Bedarf in den Benutzer-Cache.

## Branches
- Niemals direkt auf `main` committen. Das gilt auch für Menschen während der Roadmap-Umsetzung:
  Änderungen an `main` (wie am 2026-11-12 die Phase-5/6-Commits 343afcc…724c9bf) zwingen alle
  gestapelten Roadmap-Branches zum Rebase. Lieber einen eigenen Branch, der in der Phasendoku
  der nächsten Session als „Stand der Vorgänger“ genannt wird.
- Kein `git push`, kein Force-Push, keine PRs oder Issues öffnen,
  keine Remote-Branches löschen, keine Tags pushen. Das macht der Mensch nach dem Review.
- Jede Review-Einheit bekommt einen eigenen Branch:
  - SimaaS: `roadmap/phase-<N>[<a|b|c>]-<kurzer-slug>`, z. B. `roadmap/phase-1a-repo-hygiene`
  - DaceDSX: ein Branch pro Upstream-PR: `simaas/pr<NR>-<kurzer-slug>`, z. B. `simaas/pr5-sumo-fixes`
- Basis: `main`, wenn die Vorgänger-Einheit schon gemergt ist; sonst auf dem Vorgänger-Branch aufsetzen
  (gestapelte Branches) und die Basis in der Phasendoku nennen. DaceDSX-PRs ohne Abhängigkeit
  (laut Spalte „Hängt ab von“ im Patch-Inventar) immer direkt auf `main`.
- DaceDSX-Branches enthalten nur, was upstream sinnvoll ist: nichts SimaaS-Spezifisches, keine
  Roadmap-Häkchen, keine Agenten-Doku. Der SimaaS-Branch derselben Phase trägt die Häkchen und die Doku.

## Review-Einheiten klein halten
Eine Einheit aufteilen, wenn eines davon zutrifft:
- mehr als ca. 400 geänderte Zeilen handgeschriebener Code (Lockfiles, generierte Dateien und
  reine Löschungen zählen nicht, werden aber in einem eigenen Branch gebündelt),
- mehr als ca. 8 Schritt-Commits,
- sie mischt Themen, die ein Reviewer getrennt beurteilen würde (z. B. Löschungen + neue Logik,
  Infrastruktur + Anwendungscode).
Teil 3 in `docs/agent-prompt.md` ist ein Vorschlag; teile weiter, wenn die Grenzen überschritten werden.

## Ablauf pro Roadmap-Schritt
1. Schritt in ROADMAP.md, den passenden Abschnitt im Patch-Inventar und den betroffenen Code lesen.
2. Prüfen, ob der Schritt eine menschliche Entscheidung oder Handlung braucht (siehe „Grenzen“).
3. Kleinste Änderung umsetzen, die den Schritt erfüllt. Stil, Benennung und Kommentardichte des
   umgebenden Codes übernehmen. Kein Refactoring nebenbei.
4. Tests schreiben oder erweitern (siehe „Tests“) und alle betroffenen Tests ausführen. Ein Commit
   mit roten Tests ist nicht erlaubt; wenn ein Test nicht lokal laufen kann, Grund dokumentieren.
5. Doku aktualisieren: Phasendoku, betroffene READMEs, `CHANGELOG.md` (Abschnitt „Unreleased“).
6. In ROADMAP.md den Schritt abhaken: `[x]` und dahinter `(Branch: <name>)`.
   Teilweise erledigt: `[~]` und dahinter, was fehlt. Blockiert: `[ ]` bleibt, dahinter `⚠ blockiert: <Grund>`.
7. Commit. Mindestens ein Commit pro Schritt, nie mehrere Schritte in einem Commit.

## Commits
- Conventional Commits auf Englisch: `<type>(<scope>): <summary>`, z. B. `fix(sumo): load route files from scenario`.
- Body: was und warum in 2–5 Zeilen, dann `Roadmap: #<Schrittnummer>` und ggf. `Inventory: U1, U2`.
- Keine fremden Dateien mitcommitten. Vor jedem Commit `git status` und `git diff --staged` prüfen.

## Tests
- Jede Einheit endet mit einem **Akzeptanztest**: ein Befehl, den der Reviewer ausführt, und das
  erwartete Ergebnis. Steht in der Phasendoku.
- SimaaS-Backend: pytest unter `fastapi_app/tests/` (FastAPI TestClient; Redis/RabbitMQ/Postgres
  mocken oder per docker compose starten). Frontend: nur wo es Logik gibt (vitest), sonst Build + `svelte-check`.
- DaceDSX: JUnit für SimService, pytest für Python-Wrapper, CTest für C++ wo machbar; Integrationstest
  per docker compose (PR 9).
- Infrastruktur: `kubectl apply --dry-run=client`, `kubeconform` oder ein Lauf in einem
  **eigenen** minikube-Profil (`minikube -p agent-test`), nie im Standardprofil.
- Wo Tests keinen Sinn ergeben (z. B. reine Texte), das in der Phasendoku begründen.

## Dokumentation
- SimaaS: `docs/changes/phase-<N>.md` pro Phase mit den Abschnitten:
  Goal · Branches and base · Steps (number, commit subject, what changed) ·
  Assumptions · Acceptance test · Manual steps for humans · Open questions · Review notes
  (in welcher Reihenfolge lesen, worauf achten).
- DaceDSX-PRs: zusätzlich `docs/changes/dacedsx-pr<NR>.md` im SimaaS-Repo als fertige PR-Beschreibung
  (mit Motivation, Änderungen, Testanleitung), die der Mensch beim Öffnen des PRs einfügt.
- Sprache: alles auf Englisch, also Code, Kommentare, Commits, Phasendoku, PR-Beschreibungen,
  READMEs und CHANGELOG in beiden Repos. Ausnahme: Kommentare hinter den Häkchen in ROADMAP.md
  dürfen kurz und auf Deutsch sein.

## Grenzen (nicht selbst erledigen, sondern dokumentieren)
- Organisatorisches: Schritte 1, 5, 6 (Branch-Löschung, Maintainer-Termin, Branch-Aufräumen in cs7org).
- Registrierungen und Konten: OIDC-Client bei NFDI AAI (12), Domain/DNS (47), Registry-Zugänge.
- Releases taggen (16): Release-Prozess und Workflow vorbereiten, Tag nicht setzen.
- Rechtstexte (51, 52): nur Vorlage mit Platzhaltern, deutlich als „rechtlich zu prüfen“ markiert.
- Lasttests auf echter Infrastruktur (59, 60): Skripte schreiben und klein lokal ausprobieren.
- Branch-Entscheidungen (63): nur Analysebericht, nichts mergen oder löschen.
- Git-History umschreiben (filter-repo, BFG): nie. Dateien nur mit `git rm` entfernen und notieren,
  falls eine History-Bereinigung nötig wäre.
- Keine Secrets, Tokens oder personenbezogenen Daten in Dateien schreiben; Beispielwerte als
  `CHANGE_ME` kennzeichnen.
- Nichts außerhalb der beiden Repos verändern (keine globalen Pakete, kein sudo, kein
  `minikube delete` des Standardprofils). Vorhandene uncommittete Änderungen nicht verwerfen.

## Offene Maintainer-Fragen: Standardannahmen
Solange keine Antwort vorliegt, mit diesen Annahmen arbeiten und sie in der Phasendoku unter
„Assumptions“ nennen, damit sie leicht zu ändern sind:
1. Große Ressourcen: `ResourceFile.fileReference` auf ein geteiltes Volume ab ca. 512 KB, darunter inline.
2. pandapower-Zeitreihe: Modus im bestehenden Wrapper (Parameter), kein eigener BB-Typ.
3. Release: SemVer-Tags auf `main`, Images unter `ghcr.io/cs7org/dacedsx-*`, Publishing per GitHub Actions mit `GITHUB_TOKEN`.
4. Event-Schema: Avro wie die übrigen Schemas, versioniert.
5. Executor: `local` bleibt Default, `kubernetes` per Konfiguration.

Antworten der Maintainer (ersetzen die Annahmen oben):
- zugestimmt

## Wenn etwas blockiert
Nicht raten und nicht still überspringen. Blockade in ROADMAP.md und Phasendoku notieren, mit dem
nächsten unabhängigen Schritt weitermachen. Am Ende der Session eine Zusammenfassung ausgeben:
erledigte Schritte, Branches mit Basis, Akzeptanztests, Blockaden, nötige menschliche Schritte.
