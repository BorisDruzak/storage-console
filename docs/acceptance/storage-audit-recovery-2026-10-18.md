# Audit observability recovery ledger

This repair follows a completed bounded observation period. It does not amend
the original accepted witnesses, erase historical gaps, or restart that period.
Private runtime evidence and exact scope metadata remain outside Git.

## Scope

Repair blocked Audit diagnostics, stale readiness projections and protected
status publication. Diagnose repeated inventory delivery/storage pressure and
repair only confirmed causes. Keep the independent USN stream and all existing
dated path history and authorization behavior intact.

## Source gate, first change

- RED: blocked capture published only once; old/future scope proof was returned
  as fresh; a genuine native reader denying share-delete caused `STATE_INVALID`.
  Ten targeted cases failed before the first implementation.
- Additional RED: response validity outlived scope proof; an incomplete scan
  could retain positive proof. Both cases passed after their minimal fixes.
- GREEN: 34 targeted portable/native tests, Ruff and Linux-targeted mypy pass.
  Wider collector/readiness/delivery selection: 84 pass with the database-backed
  previous-release case excluded pending the separate PostgreSQL run.
- A wider Windows/PostgreSQL run over an SSH tunnel reached its 240-second
  harness limit without a product failure report. This is incomplete validation,
  not a passing regression. An isolated Linux/PostgreSQL run is required.
- Independent source review: no Critical/Important findings. Both minor notes
  addressed: document status-only WinError 5 handling and test failed validation
  after the initial replacement error.
- Native tests are included explicitly in Windows CI, including the held-reader
  case. Exact head/main CI and installed acceptance are still pending.

## Rulings

- Keep status publication live while capture remains blocked; never use later
  readiness as permission to clear GAP or reopen capture automatically.
- Derive response freshness from wall-clock proof time plus scan duration;
  retain received payloads and legacy receipt serialization unchanged.
- Windows replacement can return WinError 5 for share-delete contention. Only
  `audit-status.json` permits that ambiguous bounded retry, with strict
  destination/temporary validation. Other access denial fails immediately.
- No fixes to file contents, no correlation recheck, retention cleanup, journal
  mutation or automatic rebaseline belong to this source gate.

## Remaining gates

Full regression, exact-SHA CI, publication, protected rollout/rollback material,
live resource/queue and API/UI checks, and explicit installed acceptance remain
open. Source tests alone are not recovery acceptance.
