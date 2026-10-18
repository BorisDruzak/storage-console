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

## Exact-head CI follow-up

- Candidate `0e3120d874c3d449a6f1d99e49be2db48f576328`, run
  [39155273220](https://github.com/BorisDruzak/storage-console/actions/runs/39155273220):
  native Audit/security cases passed, but the existing end-to-end USN test failed
  on its first final Activity assertion. Retained diagnostics showed that data
  and lost-ACK replay were accepted while the latest received heartbeat still
  reported `USN_BOOTSTRAP`. Data receipt does not prove readiness receipt.
- The fixture now waits on the existing bounded condition mechanism for actual
  API continuity/freshness admission before its unchanged four consecutive
  assertions. No heartbeat interval, source-quality rule or product assertion
  was relaxed; the failed SHA/run are retained rather than rerun unchanged.
- Full isolated first-candidate Linux/PostgreSQL gate: Ruff, mypy138, OpenAPI,
  1242 backend/deployment PASS and98 platform SKIP. This is source validation,
  not live installed acceptance. New exact head/main CI remains required.
## Inventory refresh efficiency, separate change

- Synthetic PostgreSQL RED: observing 20 unchanged, explicitly single-link files
  again took 340 SQL statements. Their dated history remained unchanged.
- GREEN: the conservative sole-path refresh takes 100 SQL statements for the
  same input, preserving history rows and advancing freshness timestamps.
- Differential tests compare optimized state with the unchanged general
  reconciler for stable metadata, metadata/path/count changes, older observations,
  partial rename, delayed/equal-time follow-up events and deletion/reuse.
- Independent review found an Important partial-rename counterexample. Its actual
  PostgreSQL RED was preserved, then fixed by requiring absence of other active
  paths inside the existing lookup. No additional database round trip is needed.
- 37 real PostgreSQL cost/history tests pass; independent revised review approves
  with no remaining Critical/Important findings. Full candidate CI, publication
  and installed acceptance remain pending. No retention cleanup is included.

## Source publication closure

The following later receipts close the source gates listed above. Earlier
failed/incomplete candidates and their evidence remain retained.

| Change | Reviewed head / exact CI | Merged main / exact CI |
| --- | --- | --- |
| [PR50](https://github.com/BorisDruzak/storage-console/pull/50), Audit/status and proof freshness | `4f7ead5e1e2c409a08206a2edb86ea753efaef76`, [39156434573](https://github.com/BorisDruzak/storage-console/actions/runs/39156434573) | `c811cd743bef8e075319ee22880b83b80cf8ffa0`, [39157218938](https://github.com/BorisDruzak/storage-console/actions/runs/39157218938) |
| [PR51](https://github.com/BorisDruzak/storage-console/pull/51), conservative inventory refresh | `a725a1365eed1ded4ca25294d91197bbc19298d3`, [39156501551](https://github.com/BorisDruzak/storage-console/actions/runs/39156501551) | `b56143b7c80ea32a830ee7dd3c83d31b90bac242`, [39158135550](https://github.com/BorisDruzak/storage-console/actions/runs/39158135550) |

All four runs completed the six configured required jobs successfully, with an
explicit exact-checkout step in each job. Sonar remained skipped/unverified;
this record does not convert that external limitation into a passing gate.

The final isolated Python 3.13/PostgreSQL candidate passed Ruff, mypy (138 source
files), OpenAPI and 1254 backend/deployment tests, with 98 platform skips. Its tree equals the
deployed merge tree; native Windows checks also passed in exact-head/main CI.
The corrected native USN proof test separately passed on Windows. Independent
source and operational reviews approved after their findings were addressed.

## Installed recovery acceptance — 2026-10-18 UTC

**PASS for the existing approved scope**, recorded at 20:01 UTC. Installed
API/worker/Web and the separate Audit runtime are bound to
`b56143b7c80ea32a830ee7dd3c83d31b90bac242`. This is recovery acceptance, not a new
department rollout, fleet-readiness claim or universal actor determination.

- A fresh canonical backup was hash-verified outside the VM and fully restored
  in an isolated bounded fixture before deployment. The stopped Audit state also
  has a consistent protected backup and a separately verified off-host copy.
- Central services switched to the accepted release. The initial final health
  check rejected an existing resource discrepancy: the PostgreSQL cgroup allowed
  unlimited swap despite Docker already declaring the intended no-swap budget.
  Reapplying that same declared budget corrected the cgroup. The budget
  reapplication preserved container/process, mounts, configuration and restart count. The
  subsequent canonical HTTPS/resource healthcheck passed; deployment was not
  blindly reapplied and no database restore/downgrade occurred.
- Only the two privately identified ordinary files with empty SACLs received
  the existing approved Success audit entries. Pinned handles and before/after
  descriptors confirmed unchanged owner/group/DACL and content metadata. Parent
  coverage and audit policy were unchanged; no GPO write or business CRUD test.
- The first SACL preparation attempt timed out before any preparation or
  mutation receipt. Exact process/creation/command checks and both lifecycle
  mutexes fenced reconciliation of only its owned process tree. The original
  claim remains retained. A separate reviewed attempt with bounded single-line
  transport and phase markers completed preparation and application. The old
  attempt was not replayed or relabelled as successful.
- A complete native policy/SACL proof admitted a separate protected Audit
  generation and bookmark. The same SCM registration now uses the new version
  and state. Credentials, source/host identities and scope were preserved.
  Original state/config/backup hashes, checkpoint and latched configuration GAP
  were rechecked unchanged after startup. The uncovered historical interval
  remains explicit; no automatic GAP reset or USN rebaseline was performed.
- Repeated live API/native snapshots confirmed HEALTHY Audit, COMPLETE Activity,
  advancing collected-through and refreshed complete scope proofs. The new Audit
  PID remained stable. Independent USN code, registration and PID were preserved;
  its cursor advanced with continuous-baseline status and empty queues/quarantine.
- Both exact previously accepted DELETE witnesses still return CORRELATED_HIGH
  with unchanged original payload hashes and native account/session/client
  evidence, including 4663/4660/4624 chains. Only derived directory projections
  may refresh. No correlation recheck was submitted. Fresh coverage alone is not
  new proof of a business mutation's author; ambiguous and non-DELETE attribution
  remains governed by the existing conservative rules.
- Strict HTTPS authenticated browser checks passed for fresh source status,
  Activity and the event detail, with no page errors or mobile overflow. The
  directory projection was CURRENT. Screenshots and exact security evidence
  remain protected outside Git.
- The approved data device/bind and existing container budgets were verified,
  with resource headroom and no observed OOM. Ordinary inventory was current;
  queues were empty in the acceptance snapshots. The SQL-work reduction remains
  a synthetic differential measurement, not a measured fleet speedup or a promise
  of flat database allocation. Physical allocation is not logical history size.

No retention change, queue/history deletion, policy weakening, new monitoring
period or working-file content read was part of recovery. The completed 72-hour
automation remains PAUSED. Stop infrastructure work after this acceptance;
publication of this documentation does not change installed code.
