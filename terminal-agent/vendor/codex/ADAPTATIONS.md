# Codex intake sources

These files are exact copies from OpenAI Codex at commit `d99213289f9abe6daeefa50cde67634d9ea6eeed`, retrieved on 2026-09-21. `source.json` records each original path, permanent source URL, and SHA-256. The original `LICENSE` and `NOTICE` are retained without changes.

The runtime adaptation is `jev_agent/prompts/intake.md`. It reuses the upstream planning sequence (environment facts → user intent → implementation and acceptance), the distinction between discoverable facts and preferences, the question schema, compact final-plan guidance, and complete-replacement semantics for plan revisions.

Changes made for this project: Russian-friendly short labels; one or two interview rounds as a target; a small coherent deliverable; explicit source/context limitations; no execution during intake; a JSON object instead of `<proposed_plan>` tags; structured deliverables and acceptance; credentials excluded from questions; and a separate host-controlled transition into Jev execution. The host's validation and UI implementation are Python/Textual, not a copied Rust binary or upstream app-server implementation.

The vendored Rust file and app-server schemas are reference contracts. The generated wire schemas are experimental upstream and are not claimed to be the schema of our own intake response. Our validator adds explicit limits and checks appropriate to the terminal UI.
