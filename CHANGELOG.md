# Changelog

All notable changes to codebone will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Official milestone releases are clean numbers (`1.0`, `1.1`, `1.2`, `1.3`, `1.4`, `1.5`, `1.6`, `1.7`).
Development preview snapshots leading up to each milestone use letter releases (`.a`, `.b`, `.c`).

---

## [Unreleased]

---

## [1.7] - 2026-10-09
*Official Milestone Full Release (Current)*

### 🎯 Ziel dieser Version
Echtes Hybrid-Scanning aus statischem Multi-Language AST-Scan und LLM-Synthese etablieren, UI-Überlagerungen in der macOS-Menüleiste beseitigen und die Integration für externe Coding-Agenten (Claude Code, Cursor, Codex) zentralisieren.

### Added
- **True Hybrid Scan Engine**: Kombiniert deterministisches statisches Multi-Language AST-Scanning (Python, TS/JS, Go, Rust, Ruby, PHP, Java, C/C++) mit lokaler und BYOK-LLM-Semantik für tiefgehendes Symbol-, Abhängigkeits- und Architektur-Indexing.
- **Aus 1.7c – Cancelable & Resumable Scanning**: Erweiterte Scan-Steuerung mit sofortigem `Cancel Scan` sowie `Pause Scanning`/`Resume Scanning` inklusive Live-ETA-Berechnung und Phasenanzeigen.
- **Aus 1.7c – Per-Project Auto-Scan Toggle**: Neuer `Auto-Scan on Save`-Schalter direkt in jedem Projektmenü (`ON` by default), um automatisches Re-Scanning bei Massenbearbeitungen temporär abzuschalten.
- **Aus 1.7b – Re-architected Project TL;DR**: Vollständig überarbeitete Projekt-Zusammenfassungen ohne Prompt-Echo für kleine lokale Modelle; automatische Anhänge für **💻 Tech Stack & Scale**, **🏛️ Key Domains** und **📊 Entities**.
- **Aus 1.7b – Interaktiver TL;DR Dialog**: Integrierter **Copy TLDR**-Button (1-Klick Markdown-Kopie ins Clipboard mit macOS-Mitteilung) und **Open Map**-Verknüpfung direkt in den Architektur-Graphen.
- **Aus 1.7a – 1-Klick Model-Synchronisation**: Automatische Erkennung bereits konfigurierter Cloud-BYOK-Schlüssel im Map Agent mit 1-Klick-Übernahme in die Coding Agents.
- **Aus 1.7a – Erweiterte Coding Presets**: Presets für Claude (Anthropic), OpenAI, OpenRouter und Local Server (Ollama) neben MiMo V2.6 Pro.
- **Aus 1.7a – Dediziertes Agent-Routing**: Klare Routing-Schalter für Claude Code, Cursor, Codex, Gemini/Antigravity und opencode.
- **Aus 1.7a – Kategoriertes API-Key Management**: Saubere Trennung in `Map Agent (Cloud BYOK)` und `Coding Agent Models`.

### Changed
- **Abgeflachte Menüstruktur**: Beseitigung von Cocoa-Submenu-Überlagerungen und hängenden Tooltips durch übersichtliche Hauptmenüs.
- **Terminologie-Vereinheitlichung**: Konsistente Umstellung aller Bezeichnungen von „Index / Indexing“ auf „Scan / Scanning / Scanned“.
- **Gespiegelte Agenten-Menüs**: Map Agent und Coding Agent teilen sich nun ein identisches, intuitives Layout mit Statuszeile.
- **Direktes Projektmenü**: Die drei zuletzt gescannten Projekte sind direkte Menüs in der Hauptleiste.

### Fixed
- **Aus 1.7b – Menüleisten-Startabsturz behoben**: Fehlende Menü-Instanziierungen und `time`-Import nach der Menüabflachung korrigiert; Absicherung durch automatisierte Regressionstests.
- **Aus 1.7a – Resilientes Routing**: Transiente Verbindungsfehler deaktivieren ausgewählte Agenten nicht mehr automatisch.
- **Verständliche Netzwerk-Meldungen**: Klare Fehlermeldungen im Auto-Updater bei unterbrochener Internetverbindung.

---

## [1.7c] - 2026-10-09
*Pre-Release*

### Added
- **Per-Project Auto-Scan Toggle**: Schalter `Auto-Scan on Save` direkt im Projektmenü (Standard: `ON`), um Scans bei Dateispeicherungen projektbezogen zu steuern.
- **Cancelable Scan Controls**: Pause-, Fortsetzen- und Abbruch-Steuerung für laufende Scanvorgänge mit Live-ETA in der Menüleiste.

### Changed
- **Terminologie-Standardisierung**: Umstellung aller Menüeinträge, Dialoge und Mitteilungen von „Index“ auf „Scan“.

---

## [1.7b] - 2026-10-09
*Pre-Release*

### Added
- **Architektur-Highlights im TL;DR**: Strukturierte Ausgabe von Tech Stack, Key Domains und Entities im TL;DR Dialog.
- **Copy TLDR & Map Shortcut**: Interaktive Buttons im TL;DR Dialog zum Kopieren in die Zwischenablage und Öffnen des Graphen.

### Fixed
- **Menüleisten-Startfehler**: Behebung von `AttributeError` und fehlendem `time`-Import, der den Start der Menüleisten-App verhinderte.
- **Menü-Registrierung**: Vollständige Wiederherstellung von `open_map_item`, `documentation_item`, `feedback_item`, `check_updates_item` und `uninstall_item`.

---

## [1.7a] - 2026-10-09
*Pre-Release*

### Added
- **Hybrid Architecture Preview**: Erste Integration von statischem Multi-Language AST-Scanning mit LLM-Synthese.
- **Resilientes Agenten-Routing**: Nicht-blockierende Warnungen bei Verbindungsabbrüchen ohne Zurücksetzen der Benutzerauswahl.
- **Codex Dual Injection**: Bereitstellung von `OPENAI_BASE_URL` und `OPENAI_API_BASE` für erweiterte CLI-Kompatibilität.
- **Systemanforderungen & Thermik**: Dokumentation von Richtlinien für passive Kühlung und batteriefreundliches Debouncing.

### Changed
- **Abflachung der macOS-Menüs**: Entfernung verschachtelter Submenüs zur Vermeidung von Cocoa-Darstellungsfehlern.

---

## [1.6] - 2026-10-08
*Official Milestone Release*

### 🎯 Ziel dieser Version
Vollautomatisierung der Release-Pipeline für GitHub Actions, Einführung des nativen In-App-Auto-Updaters mit robuster Versionsvergleichslogik und automatisierte Homebrew-Verteilung.

### Added
- **GitHub Actions Release Pipeline**: Automatisierter Workflow zur Erstellung signierter macOS DMGs und ZIP-Archive bei Push von Versions-Tags (`v*`).
- **Aus 1.6a – Nativer In-App Auto-Updater**: Robuste Versionsvergleichslogik in `src/updater.py` mit Unterstützung für Meilensteine und Buchstaben-Pre-Releases (`1.6a < 1.6b < 1.6`).
- **Aus 1.6a – Prüfsummen-Validierung**: Automatische Erstellung und Verifikation von SHA256-Prüfsummen für alle Release-Artefakte.
- **Aus 1.6b – Homebrew Formula Synchronisation**: Automatisches Update von Download-URL und Checksum in `Formula/codebone.rb`.

### Changed
- **Gating von Releases**: Trennung von normalen `main`-Pushes und Veröffentlichungen; Releases werden ausschließlich durch explizite Tags ausgelöst.
- **Standardisiertes Versionsschema**: Konsolidierung der Release-Hierarchie in saubere Hauptgenerationen mit transparenten Zwischenstufen.

### Fixed
- **Release-Races**: Beseitigung von Race-Conditions beim simultanen Bauen von DMGs und Aktualisieren des Repositories.

---

## [1.6b] - 2026-10-08
*Pre-Release*

### Added
- **Release CI Automation**: GitHub Actions Pipeline zum Erstellen signierter DMG-Dateien und Bereitstellen der Release-Assets.
- **Homebrew Formula Sync**: Automatische Aktualisierung von `Formula/codebone.rb` mit den generierten SHA256-Prüfsummen.

---

## [1.6a] - 2026-10-08
*Pre-Release*

### Added
- **Release Workflow Automation**: Gating der CI-Releases auf explizite Tags (`v*`) zur Vermeidung automatisierter Commits auf `main`.
- **Letter-Based Auto-Updater**: Native Versionsvergleichslogik in `src/updater.py` für Vorabversionen mit SHA256-Validierung.

---

## [1.5] - 2026-09-26
*Official Milestone Release*

### 🎯 Ziel dieser Version
Skalierbare Graph-Performance für große Repositories durch Star-Topologien, Einführung semantischer Ranked Search und automatisierte Architektur-Zusammenfassungen via MCP.

### Added
- **Aus 1.5c – Architectural Project TL;DR**: `codebone_tldr` MCP-Tool und `/codebone/tldr` HTTP-Endpoint für prägnante Architektur-Zusammenfassungen ganzer Repositories.
- **Aus 1.5b – Ranked Search**: `cb(query=...)` durchsucht Symbolnamen, Kommentare und Codezeilen mit Konfidenz-Scoring (`high` / `medium` / `low`).
- **Aus 1.5b – 2-Step Context Offer Protokoll**: Zweistufige Context-Bereitstellung; erste Anfrage liefert Trefferübersicht, `whisper=true` expandiert den vollständigen Token-Kontext.
- **Aus 1.5b – Smarte Filter & Frischeanzeige**: Domänen- und Asset-Filterung (`assets=true`) sowie Anzeige der Aktualität des Graphen (`Index freshness indicator`).
- **Aus 1.5a – Standalone File Linking**: Unverknüpfte Dokumentations- und Konfigurationsdateien werden an benachbarte Ordner gebunden, um isolierte Knoten zu vermeiden.

### Changed
- **Aus 1.5a – Stern-Topologie im Graphen**: Große Entitätsgruppen kollabieren zu Stern-Topologien um zentrale Hubs, wodurch das Kanten-Budget nicht mehr erschöpft wird.
- **Konsolidiertes MCP-Tooling**: `cb` fasst Importe und Querverweise zusammen; Entfernung redundanter Einzel-Tools.

### Fixed
- **Graph-Fragmentierung**: Behebung von Darstellungsabbrüchen und isolierten Clustern bei großen Codebasen.

---

## [1.5c] - 2026-09-26
*Pre-Release*

### Added
- **Architectural Project TLDR via MCP & API**: Bereitstellung von `codebone_tldr` und `/codebone/tldr` für ganzheitliche Architekturübersichten über indizierte Codebasen.

---

## [1.5b] - 2026-09-26
*Pre-Release*

### Added
- **Ranked Word and Meaning Search**: Präzise Suche über Symbole, Kommentare und Dateien mit Treffer-Scoring (`cb(query=...)`).
- **2-Step Offer Protokoll**: Leichtgewichtige Treffer-Angebote zur Schonung von Token-Budgets bei KI-Agenten (`whisper=true` für Volltext).
- **Smarte Filter**: Domänen-Boosting und Ausblendung von Asset-Dateien.

---

## [1.5a] - 2026-09-26
*Pre-Release*

### Changed
- **Graph Density Optimization**: Große Dateigruppen kollabieren zu Stern-Topologien um zentrale strukturelle Hubs.
- **Nachbarschafts-Verlinkung**: Automatische Verknüpfung isolierter Config- und Dokumentationsdateien mit Ordnernachbarn.

---

## [1.4] - 2026-09-25
*Official Milestone Release*

### 🎯 Ziel dieser Version
Unterstützung echter Multi-Folder Projekt-Workspaces und Vertiefung des System-Graphen durch dynamische Call-Chains und SQL/Route-Erkennung.

### Added
- **Aus 1.4b – Multi-Folder Project Workspaces**: Verwaltung mehrerer Projektordner in einem gemeinsamen Workspace mit sequenziellem Hintergrund-Scan und rollierenden Snapshots.
- **Aus 1.4a – Live Call Chains**: Visuelle Aufruf-Kanten von Frontend-Routen zu Backend-Handlern und Supabase/SQL-Tabellen (`Calls: /api/... -> ...`).
- **Aus 1.4a – Dynamische Map-Vertiefung**: Re-Evaluation von Importen, DDL-Tabellen und Dateifunktionen zur Abfragezeit (`source_facts`).
- **Aus 1.4b – Vereinheitlichtes Einstellungsfenster**: Zentrales Settings-Menü für Module, Modelle, API-Keys und Workspace-Pfade.

### Changed
- **Aus 1.4a – Bereinigte Scan-Bäume**: Automatisches Pruning von `node_modules`, `.git`, Virtualenvs und Build-Verzeichnissen (`dist`).
- **Graph-Layout-Stabilität**: Jittered-Grid Initialisierung verhindert leere Viewports beim Öffnen des Graphen.

### Fixed
- **Aus 1.4b – MCP Scan-Adoption**: Pfad-Auflösung unter `scan_path` stabilisiert und Routen-Tiefen beibehalten.
- **Fehlertoleranz bei Server-Antworten**: Verbindungstests tolerieren abgeschnittene Fehler-Bodys robuster.

---

## [1.4b] - 2026-09-25
*Pre-Release*

### Added
- **Multi-Folder Workspaces**: Unterstützung mehrerer Projektordner mit rollierenden Snapshots.
- **Unified Settings**: Zusammenfassung von Modulen, Modellen und API-Keys in einem Einstellungsmenü.

### Fixed
- **Scan Adoption**: Korrektur von Routentiefen und stabilere Fehlerbehandlung beim Verbindungsaufbau.

---

## [1.4a] - 2026-09-25
*Pre-Release*

### Added
- **Dynamic Map Deepening**: Dynamisches Nachladen von Import-Kanten und Tabellenverweisen zur Query-Zeit.
- **Live Call Chains**: Visualisierung von Call-Kanten von Endpunkten zu Handlern im Graphen.

---

## [1.3] - 2026-09-24
*Official Milestone Release*

### 🎯 Ziel dieser Version
Bereitstellung einer flexiblen Modell-Bibliothek mit Keychain-Sicherheit, Multi-Agenten-Routing und fortgeschrittener Graph-Analyse mittels Louvain-Community-Erkennung.

### Added
- **Aus 1.3a – Modul-Modell-Bibliothek**: Unterstützung für beliebige Anthropic- und OpenAI-kompatible Endpunkte (inkl. MiMo V2.6 Pro) mit Speicherung von Schlüsseln im macOS Keychain.
- **Aus 1.3b – Import Graph Edges**: Statische Querverbindungen für Python- und TypeScript/JavaScript-Importe im Systemgraphen.
- **Aus 1.3b – Louvain Community Clustering**: Modularity-basierte Community-Erkennung (`networkx`) über dem Co-Occurrence-Graphen mit Labeln nach strukturellen Hubs.
- **Aus 1.3c – Lokale Translation Bridge**: Übersetzung zwischen Anthropic- und OpenAI-Nachrichtenformaten zur nahtlosen CLI-Anbindung.
- **Aus 1.3c – OpenRouter Integration**: Native Unterstützung für OpenRouter in allen Modul- und Routing-Bereichen.
- **Aus 1.3c – Leichtgewichtige Delta-Updates**: Bereitstellung von Update-ZIPs ohne Basis-Modell für minimale Downloadgrößen.
- **Aus 1.3a – In-App Uninstaller**: Sauberes Entfernen von App, Modellen, Caches, Preferences und MCP-Einträgen direkt aus den Einstellungen.

### Changed
- **Modul-Schnellschalter**: Dedizierte Schalterreihe in der Menüleiste für Coding-Agenten.
- **Gehärtete lokale Schnittstelle**: DNS-Rebinding-Schutz und strikte CORS-Guards auf allen lokalen Endpunkten.

### Fixed
- **Aus 1.3c – Routing-Stabilisierung**: Behebung von Fehlern beim Umschalten von Claude Code und opencode.
- **Wiederanlauf-Erkennung**: Das erneute Starten einer laufenden Instanz bringt die Menüleiste in den Vordergrund, statt lautlos zu beenden.

---

## [1.3c] - 2026-09-24
*Pre-Release*

### Added
- **Translation Bridge & OpenRouter**: Anthropic ↔ OpenAI Nachrichtenübersetzung und native OpenRouter-Unterstützung.
- **Lightweight Delta Updates**: Delta-Update-Pakete ohne Basis-Modell-Dateien für minimale Downloadgrößen.

### Fixed
- **Routing-Stabilisierung**: Zuverlässiges Umschalten von Coding-Agenten auf externe APIs.

---

## [1.3b] - 2026-09-24
*Pre-Release*

### Added
- **Import Graph Edges**: Cross-File Importkanten für Python und JS/TS im Systemgraphen.
- **Graph Community Clustering**: Louvain-Clustering zur Erkennung zusammenhängender Architektur-Domänen.

---

## [1.3a] - 2026-09-24
*Pre-Release*

### Added
- **Modules Model Library**: Pluggable Modelle mit Routing-Schaltern und sicherer macOS Keychain-Speicherung.
- **In-App Uninstaller**: Vollständige Deinstallations-Routine für Anwendung und Benutzerdaten.
- **Zuverlässiges Indexing**: Kooperative Hintergrund-Scans mit dateibasierten Locks.

---

## [1.2] - 2026-09-23
*Official Milestone Release*

### 🎯 Ziel dieser Version
Vollständige Überarbeitung der Live-Graph-Benutzeroberfläche auf modernes Dark-Glassmorphism, Zero-Config MCP-Verteilung über npm und tiefere macOS-Systemintegration.

### Added
- **Aus 1.2a – Live Graph UI Redesign**: Modernes Slate-and-Iris Dark-Glassmorphism Interface mit Kategorie-Filter-Pills, Hover-Tooltips und interaktiver Detailansicht.
- **Aus 1.2b – Zero-Config MCP Package**: Veröffentlichung von `codebone-mcp` auf npm für sofortige Bridge-Nutzung via `npx -y codebone-mcp`.
- **Aus 1.2b – Multi-Client MCP Auto-Registration**: Automatische Konfiguration für Gemini / Antigravity IDE, Claude Desktop und Cursor.
- **Aus 1.2b – Nativer Mach-O Launcher**: Eigenständiges Launcher-Binary zur garantierten Menüleisten-Sichtbarkeit und Gatekeeper-Kompatibilität.
- **Aus 1.2b – Direktes `cb` MCP-Tool**: Schlankes Lookup-Tool zur Integration in Agenten-Systemprompts.
- **Aus 1.2a – Nativer macOS Auto-Updater**: Vollautomatischer Download, Signaturprüfung und atomarer Bundle-Tausch mit Neustart.
- **Aus 1.2a – Zuletzt geöffnete Projekte**: Schneller Projektwechsel direkt im Hauptmenü.

### Changed
- **Apple SF Symbols**: Verwendung nativer AppKit-Symbole in der gesamten Menüleiste.
- **Full Disk Access Automation**: Automatisierte TCC-Berechtigungsprüfung mit direkter Systemeinstellungs-Verlinkung.

### Fixed
- **Aus 1.2a – Signatur- und Bundle-Struktur**: Behebung von Symlink-Problemen in signierten DMGs und NSOpenPanel Runloop-Korrekturen.

---

## [1.2b] - 2026-09-23
*Pre-Release*

### Added
- **Zero-Config MCP Package**: `codebone-mcp` auf npm für blitzschnellen Start ohne Klonen.
- **Multi-Client MCP Registrierung**: Automatische Konfiguration für Antigravity, Claude und Cursor.
- **Nativer Mach-O Launcher**: Standalone-Launcher für macOS AppKit Menüleisten-Icon.
- **Kompaktes `cb` Tool**: Schneller Kontext-Zugriff für LLM-Agenten.

---

## [1.2a] - 2026-09-23
*Pre-Release*

### Added
- **Live Graph UI Redesign**: Neues Dark-Glassmorphism Design mit interaktivem Inspector Drawer.
- **Nativer macOS Auto-Updater**: Hintergrundprüfung und atomic Bundle-Swap.
- **SF Symbols & Full Disk Access**: Native Symbole und automatisierter FDA-Preflight.
- **Recent Projects History**: 1-Klick Projektverlauf im Hauptmenü.

---

## [1.1] - 2026-09-22
*Official Milestone Release*

### 🎯 Ziel dieser Version
Reduzierung des RAM-Footprints auf Apple Silicon durch Standardisierung auf Qwen 0.5B und Bereitstellung eines rein nativen macOS AppKit Menüleisten-Erlebnisses.

### Added
- **Aus 1.1a – Qwen 0.5B Modell-Standardisierung**: Sub-Sekunden-Inferenz mit Apple Silicon Metal-Beschleunigung und nur ca. 390 MB RAM-Bedarf.
- **Aus 1.1a – Native Cocoa Menüleiste**: 100% native AppKit Benutzeroberfläche mit Status, Einstellungen und Live-ETA-Berechnung.
- **Aus 1.1b – Tailscale-Style Popover Header**: Master-Kippschalter, Status-LED, Modellwähler und native Symbole im Popover.
- **Aus 1.1a – Projekt-Baseline Übersicht**: Schätzung der Initial-Ladezeit und Fortschrittsanzeige für große Codebasen.

### Changed
- **Verbesserte Dashboard-Bedienung**: Prominenter „Scan Project Now“-Button im Dashboard-Header.

### Fixed
- **Aus 1.1b – Live Graph Resilienz**: Behebung unendlicher Lade-Spinner im Knowledge-Graph-Dashboard.

---

## [1.1b] - 2026-09-22
*Pre-Release*

### Added
- **Tailscale-Style Popover Header**: Master-Schalter und Status-LED im Header.
- **Live Graph Resilienz**: Prominenter Scan-Button und Fehlerbehebung bei Lade-Animationen.

---

## [1.1a] - 2026-09-22
*Pre-Release*

### Added
- **Qwen 0.5B Standardisierung**: Lokales Leichtgewicht-Modell auf Apple Silicon Metal.
- **Native Cocoa Menüleiste**: AppKit Menüleisten-Interface mit Live-Statistiken.

---

## [1.0] - 2026-09-22
*Official Milestone Release*

### 🎯 Ziel dieser Version
Markteinführung von codebone als 24/7 lokaler macOS-Hintergrundassistent mit Metal-GPU-Inferenz und nativer MCP-Schnittstelle für KI-Coding-Tools.

### Added
- **24/7 Hintergrund-Engine**: Menüleisten-Assistent zur kontinuierlichen Dateiüberwachung mit batteriefreundlichem Debouncing (0.5s Netzteil, 15s Akku).
- **Apple Silicon Metal GPU Inferenz**: Lokale Modell-Ausführung via `llama-cpp-python` mit Metal-Hardwarebeschleunigung.
- **Semantischer System-Graph**: Echtzeit-Kartierung von Geschäftsdomänen, Querverbindungen und Modulabhängigkeiten.
- **Model Context Protocol (MCP)**: Nativer Server für Claude Desktop, Cursor, Gemini und Codex.
- **Aus 1.0b – Deep Scan Modus**: Hintergrund-Tiefenanalyse mit optionalem 7B-Modell und Live-Menüleisten-Dashboard.
- **Sicherheits-Sandbox**: Quellcode-Kapselung in isolierten XML-Containern mit Anti-Prompt-Injection Direktiven.

### Changed
- **Marken-Harmonisierung**: Vereinheitlichung aller Bundles, LaunchAgent-Plists, CLI-Befehle und MCP-Namen unter „CodeBone“.

### Fixed
- **Aus 1.0b – Day-One Stabilitäts-Patch**: Concurrency mit WAL+RLock, Level-of-Detail Filterung, Move-Erkennung und strikte `.gitignore`-Einhaltung.

---

## [1.0b] - 2026-09-22
*Pre-Release*

### Added
- **Deep Scan Modus**: Optionale Hintergrund-Tiefenanalyse mit 7B-Modell.
- **Brand Standardization**: Vereinheitlichung aller Strings und Plists auf CodeBone.

### Fixed
- **Day-One Patch**: WAL+RLock Concurrency, Level-of-Detail Filterung und `.gitignore`-Respekt.

---

## [1.0a] - 2026-09-22
*Pre-Release*

### Added
- **24/7 Background Engine**: Dateiüberwachung auf Dateispeicherung mit akkuschonendem Debouncing.
- **Metal GPU Inferenz**: Lokale Inferenz mit Apple Silicon Hardwarebeschleunigung.
- **Semantischer System-Graph**: Automatische Zuordnung von Geschäftsdomänen.
- **Model Context Protocol (MCP)**: Native Schnittstelle für Claude Desktop, Cursor, Gemini und Codex.
- **Security Sandboxing**: Isolierte XML-Container für analysierten Quellcode.
