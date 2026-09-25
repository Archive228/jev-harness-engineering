# Hermes source provenance

Upstream: [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent).
Fetched 2026-09-21; pinned commit:
`c1c84ea37f9cfee75a1bf8326b5597959c7ba499`.

- `clarify_tool.py` is an exact copy of upstream
  [`tools/clarify_tool.py`](https://github.com/NousResearch/hermes-agent/blob/c1c84ea37f9cfee75a1bf8326b5597959c7ba499/tools/clarify_tool.py).
  SHA-256: `3c55327461b28fa36905f12660122bd131fa84a09a44e481efb230edbf411ab3`.
- `LICENSE` is the exact upstream MIT license, Copyright (c) 2025 Nous Research.
  SHA-256: `821556e6336796450ab852d375117b48a4887e71d255794fd6318d99982a5ab6`.

These files document the source of the adaptation. The product does **not** import
or execute this upstream module; its registry integration belongs to Hermes.

The actual adapted runtime code is `jev_agent/choice_labels.py`:

- copied the structure of `mark_recommended` and `strip_recommended`;
- write only upstream's own English `(Recommended)` suffix, and also accept a
  Russian `(Рекомендуется)` suffix when reading an answer saved before the
  interface was translated;
- return a fresh display list, including for empty and single-choice inputs;
- avoid marking an empty first choice;
- retain undecorated answer values separately from display labels.

We did not port timeout-as-consent behavior, callback dispatch, gateway state,
model tool registration, or a second terminal UI framework. See
[`research/hermes-intake.md`](../../research/hermes-intake.md) for the traced lifecycle.
