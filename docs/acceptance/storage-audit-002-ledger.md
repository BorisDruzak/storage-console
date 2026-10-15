# STORAGE-AUDIT-002 — bounded single-root rollout ledger

Status: A/B/C source PASS; corrected runtime CI/installation PASS; data-disk
migration PASS; bounded ordinary new-root history/evidence acceptance PASS through
retained replay and fresh-generation ordinary CREATE/WRITE observations.
Mutation actors remain unconfirmed; native client fields may be absent.
Permanent Audit RUNNING; STOP.
Specification and plan: docs/superpowers/{specs,plans}/2026-10-14-storage-audit-002.md.
Production scope and identities remain in the approved private operator design.

- 2026-10-14: operator approved necessary implementation/rollout and emphasized
  bounded Storage Console memory and correct persistent history. Existing audit
  acceptance is not reopened; permanent single-root rollout is separate work.
- Baseline main d95040b19d87ecc0c2e83460bd2d2b75f9592d3f; reused attached managed
  worktree, new branch codex/storage-audit-002-a, clean before new files. Original
  workspace unchanged. Issue22 OPEN, open PR list empty at inspection.
- GitNexus list_repos does not contain Storage Console; verify dynamic source and
  tests directly, no manual group_sync/reindex.
- Private read-only directory and metadata preflight completed; no real values in
  fixtures/public docs. Root exceeds old 256-object readiness bound and is outside
  existing USN scope. Audit remains STOPPED; existing USN running/unmodified.
- Central resource observation: containers currently have no cgroup memory limits.
  Available memory is substantial; disk free is below canonical deployment minimum
  at observation time. No cleanup or runtime mutation yet; deployment headroom must
  be resolved before live rollout. No promise of unlimited disk or history retention.
- Local Python3.14 baseline could not collect tests (ldap3 absent); not a product
  regression. Isolated Python3.13 focus: 28 passed/4 Windows-native skips; upstream
  pyasn1 deprecation warnings retained. No native/full-regression claim yet.
- Ruling: operator explicitly requested execution of the approved written design;
  implementation plan uses inline execution without a redundant permission loop.
  Independent stage review remains mandatory. Cost if wrong: plan changes require
  correction before affected stage gates/deployment.

## Task 1 — bounded readiness, portable verification

- RED: old breadth-first walker consumed the full wide directory before checking
  its first descendant. A complete synthetic 52k walk exceeded the 4 MiB traced
  allocation budget. Both tests fail against committed baseline and pass with
  lazy depth-first enumeration, finite iterator depth/count/deadline and cleanup.
- RED→GREEN: background probe/status independence, startup/stop, scan-start-based
  expiry, exception redaction, exact total budget and late expiry during capture.
  Incomplete/expired proof does not make HEALTHY. Actual negative completed proof
  retains the existing configuration-change GAP behavior.
- RED→GREEN: configured lower budget must not silently use the old default 256.
  First test double omitted Native.sacl and accidentally passed; it was corrected
  to preserve real scope verification behavior, then reproduced the actual RED.
- RED→GREEN: new optional heartbeat diagnostics changed canonical old receipt
  shape without conditional omission. Actual PostgreSQL previous-release receipt
  replay reproduced 409; omission of absent new fields restores 202/duplicate=true
  while retaining previous nullable fields and immutable evidence unchanged.
- Current focus: 63 PASS. Full frozen Python3.13 source regression: 906 PASS /
  85 platform SKIP; 68 upstream warnings retained. Earlier full snapshot 902 PASS
  is recorded separately and is not substituted for the current result.
- Deployment tests 54 PASS; Web 133 PASS, API generation/check/lint/typecheck PASS.
  Focused strict mypy six source modules and Ruff PASS. Native/exact CI PENDING.
- Additional FILESERVER volume API diagnostic timed out; cause UNKNOWN and no
  automatic retry. A short read-only CIM query separately confirmed NTFS and the
  same canonical volume as existing scope; Audit STOPPED/PID0 and old USN same PID.
- Operator screenshot clarified RAM versus disks. Second virtual data disk is
  present, unmounted and has no detected filesystem signature; PostgreSQL remains
  on system filesystem. No disk initialization/mount/migration performed.

## Task 2 — explicit scope transition and independent A review

- RED→GREEN: streamed atomic updates, iterator/capacity failure rollback, duplicate
  identity refusal and unchanged queued bytes. A complete 52k ancestry is staged
  on disk and committed without a width-sized Python group.
- Independent review identified seven Important findings. A real scope commit
  reproduced its own SQLite writer/reader lock after cache spill; transaction-local
  collision/revision reads remove it. The real 52k regression passes under the
  4 MiB traced-allocation budget while preserving the old cursor.
- RED→GREEN: immutable transition backups survive interruption before publication;
  DONE receipts permit later rotation/disable; CLI retry repairs half-written
  config/activation without duplicate roots; default readiness also runs in the
  background with expiry; failed unpublished stages do not accumulate; retained
  producer handles close; changes after the frozen fence remain observable.
- Missing-baseline and old-scope-move counterexamples were checked against source
  and covered by GREEN guards. Extension requires initialized volume baselines;
  staged identities in the old backlog cause refusal. These two guards have no
  separately executed pre-fix RED claim. New-root earlier history stays unknown.
- Journal retention is rechecked immediately before commit, including resume;
  rollover refuses the transition. Published pending stages and historical
  receipts survive for recovery. Existing gaps and credentials remain unchanged.
- Current focused backend/deployment regression 145 PASS / 6 platform SKIP;
  complete strict mypy and Ruff PASS; OpenAPI and staged secret scan PASS.
  Earlier full snapshots 925/86 and 934/86 PASS/SKIP remain separate evidence;
  final frozen full regression 936 PASS / 86 platform SKIP, 68 upstream warnings.
- Owned native NTFS extension and readiness cases were added to Windows CI.
  Native, exact head/main CI and live deployment remain PENDING.
- A fresh existing-schema backup passed pg_restore --list and off-VM DPAPI
  decrypt/hash verification. Writers and history unchanged. Backup integrity
  evidence does not establish restoration acceptance.
- PR31 first exact-head CI 38562589712: Windows readiness assertion failed because
  its test double compared plain and extended path spellings. Changed that
  assertion to filesystem identity; owned local Windows/Python3.14 check PASS,
  Python3.13 readiness focus 64 PASS. Native CI rerun still required. Source
  long-path support remains intact; this is a fixture correction, not a SACL bypass.

## A source acceptance / B resource admission

- PR31 merged. Exact head 5910e666f0e422dbb8a33475ee5cc4aec6678a96 run38563646555
  and main 14c9d42546acaf0cca34f488cab15953f6ca47aa run38565123890: six required
  checks PASS; Sonar SKIPPED by external configuration, not Quality Gate PASS.
  Native Windows groups 14 + 104 + 81 + 97 + 1 PASS. Task2 closure regression
  46 PASS / 5 platform SKIP. No FILESERVER deployment acceptance inferred.
- Existing-schema backup restored in an isolated PostgreSQL16 container limited
  to 512 MiB, matching recorded counts/schema. First disposable attempt failed
  because public schema already existed; corrected owned-fixture cleaning only.
  Production was not restored or stopped; off-VM encrypted archive remains.
- B RED→GREEN: seven admission/pool cases; excess heavy request cannot write a
  receipt, heartbeat reserve remains available, replay accepts exactly once.
  Exception/cancel/disconnect/oversize release the admission slots. Ten pooled
  connections are the maximum per process, with finite three-second pool wait.
- Resource verification RED eight cases; GREEN backend/deployment focus69 PASS,
  Ruff and strict application/deployment mypy PASS. Actual cgroup/SQL proof is
  added to disposable production smoke. Enforced production rollout still pending.
- Additional bounded read-only SACL timing helper timed out; cause UNKNOWN and no
  throughput/readiness claim. Fresh short service read found Audit stopped and
  old USN running unchanged; exact helper process selection found no remaining
  child. Do not blindly repeat the same diagnostic or treat it as positive proof.

## B independent review and isolated runtime proof

- Full pre-review frozen backend regression 943 PASS / 86 platform SKIP. Fresh
  independent review reproduced two Important issues: Nginx buffered before
  admission, and cancellation released a permit while a sync handler still held
  its batch. The actual pinned-runtime reproduction left three blocked handlers
  under a two-slot bound; the original async cancellation stub did not cover it.
- RED→GREEN: no-buffer ingest plus HTTP/1.1 forwarding, and cancelled sync workers
  retain a strongly referenced bounded child/permit until completion. Incomplete
  uploads can still cancel. Body-limit errors/disconnects do not leak permits.
  Canonical deployment healthcheck now verifies resources, including a negative
  case. Repeat independent review found no remaining Critical/Important; focused
  independent rerun 61 PASS. Full post-review backend 944 PASS / 86 platform SKIP,
  68 upstream warnings; deployment/admission focus71 PASS, Ruff, mypy126 + strict
  deploy7, OpenAPI and staged Gitleaks PASS (zero findings). Exact-SHA CI pending.
- Actual owned disposable production Compose proof PASS: enforced cgroup memory
  and zero swap, SQL settings, real HTTPS paused Content-Length/chunked third
  uploads rejected before body completion and without receipts, strict TLS,
  real browser authentication/collector lifecycle and isolated backup/restore.
  Initial fixture build failed because host buildx was absent; direct runtime
  build and read-only buildx diagnostic identified it. The owned fixture used
  supported legacy builder fallback; no production Docker changes were made.
  Candidate fixture provenance is separate from upcoming exact-head/main CI.
- Operator disk screenshot does not allocate its unused data disk to PostgreSQL.
  Protected exact-disk migration/rollback plan and restored off-VM backup are
  prepared. Operator separately approved that exact additional-disk plan; disk
  writes and live rollout remain pending. Source acceptance does not imply live.

## B merged-main failure and test observation follow-up

- PR32 head 9ed7e3354e285761702cb1762b61dde66c6bff93 / run38577118541:
  six required checks PASS; Sonar SKIPPED. Merged main
  cf16928423c1c58026f1f454351871ab7ee11a17 / run38578636658 remains FAIL.
  First native attempt passed groups 14 + 104 + 81 + 97, then Activity returned
  UNAVAILABLE instead of COMPLETE. Its freshness cause is UNKNOWN; no threshold
  or continuity requirement is weakened. Five other required checks PASS.
- One controlled rerun again passed those groups, then the test's writable
  queue observer competed for SQLite BEGIN IMMEDIATE and failed STATE_UNAVAILABLE.
  This observed lock failure is distinct from the first attempt's quality failure.
  No repeated blind rerun or live rollout follows a failed merged-main gate.
- RED: a reserved SQLite writer blocked the existing writable observer. GREEN:
  use the established read-only observer pattern, retry only BUSY/LOCKED inside
  the existing bounded wait, propagate other errors, and preserve database bytes.
  Sanitized post-response diagnostics expose proof age and bounded delivery timing
  without identities, paths, tokens or cursor fingerprints. All COMPLETE,
  CONTINUOUS_SINCE_BASELINE and 15-second validity assertions remain intact.
- Test-only follow-up: focus26 PASS, frozen full regression947 PASS / 86 platform
  SKIP / 68 upstream warnings; Ruff, strict application mypy126 and deployment
  mypy7 PASS. Fresh independent review: no Critical/Important findings, independent
  focus6 PASS. Exact native head/main gates remain pending.
- The earlier read-only timing timeout was isolated to an oversized SSH stdin
  line; bounded framing completed a 2,000-object sample without read errors or
  service changes. This is timing evidence only, not full-tree SACL readiness.

- PR33 head b22d439529a061eaa2ed0293ab234cf56b24f8af / run38587379983:
  six required PASS, Sonar SKIPPED; native14 + 104 + 81 + 97 + 1 PASS.
  Merged main d172a8a726bbe1e4369be25db003e2f13b904139 / run38588737929:
  five required PASS, native FAIL at Activity quality; preceding groups all PASS.
  Read-only observation did not report the previous writer-lock failure. Quality
  RCA remains UNKNOWN because pytest shortened the diagnostic assertion repr.
- RED→GREEN: an actual failing subprocess pytest case proves complete sanitized
  JSON survives captured stdout. Emit that existing bounded snapshot on assertion
  failure; production and all acceptance operands remain unchanged. Focus23 PASS,
  independent focus7 PASS; no Critical/Important findings. New exact CI pending;
  no formatting, migration, SACL/policy or service changes inferred from tests.

## B source closure / C directory contracts

- PR34 exact head47f5e6ab70cfda9dca8adc6b5aef7d05f6eb436b / run38590951155
  and merged main6422cc139263033af1d66f2212033748ef0c4d19 / run38592281935:
  six required checks PASS, Sonar SKIPPED. Native groups14 + 104 + 81 + 97 + 1
  PASS on both. Historical failed runs and UNKNOWN quality RCA remain recorded;
  this exact successor establishes B source acceptance, not a causal claim.
- Additional owned local Windows/Python3.13.15 installed-wheel NTFS→HTTPS→real
  disposable PostgreSQL→Activity test1 PASS (83.21s); production mutations NONE.
  Temporary tunnel closed. Linux-target mypy126 + deploy7 and Ruff PASS; default
  Windows-target mypy sees pre-existing POSIX-only platform attributes, so it is
  not represented as a passing supported deployment-target check.
- Task3 closure focus23 PASS. Task4 started on exact B successor. Initial RED
  absent directory contracts → GREEN17 typed cases: finite pages/counts/TTL,
  explicit incomplete state, source/domain/SID boundaries, disabled users and
  complete PTR/forward/unique-computer witnesses. Directory objects grant no role.
  C persistence, collection, UI, independent review and exact CI remain pending.

## C candidate verification

- Additive revision0009 keeps native audit rows/digests immutable and indexes
  separate IP/directory observations. Paged collector delivery uses signed/sealed
  machine Kerberos, bounded child jobs, cache and encrypted independent queue.
  Current directory names do not alter historical actor/confidence or Web roles.
- Independent review found five Important defects: regex domain split, missing
  numeric enabled proof, missing terminal snapshot-byte reserve, collector-rotation
  index scan and directory capability exposed through ordinary collector listing.
  All received focused RED→GREEN regressions. Packaged PowerShell AST/installed
  wheel and owned deadline/stop tests8 PASS; PostgreSQL EXPLAIN verifies collector
  equality in latest indexes with zero obsolete-history rows filtered.
- Backend frozen candidate1003 PASS/88 platform SKIP; full successor verification
  after the last RBAC/native cases is pending. Source/read/migration22 PASS;
  Web135 PASS, focused desktop/mobile enriched audit browser1 PASS. Ruff and
  Linux-target mypy135 PASS; TypeScript/i18n/API generation/build PASS.
- Actual isolated production Compose acceptance PASS: strict TLS/auth/browser,
  ingest refusal, cgroup memory/swap/SQL budgets and backup/restore. Fresh current
  schema0008 backup and off-VM encrypted hash/decrypt verified; independent bounded
  PostgreSQL restore PASS with matching counts and no production writes.
- Exact disk baseline matches approved250GiB target; read-only migration guard
  PASS. Disk formatting, DB cutover and permanent department rollout not executed.
  Final independent C source verdict APPROVE: fresh34 PostgreSQL/source cases,
  prior41 native/backend and7 Web cases independently PASS. Exact head/main CI
  remains required before disk apply and production rollout.

## C exact source acceptance and approved data-disk migration

- PR35 exact head0a825a5c1546f24e04751c313266f24c11bc4bf2 / run38609971123 and
  merged main927e4c5107785765b5040f571dd6b9cf6f119014 / run38611708662:
  six required checks PASS; Sonar SKIPPED. Both native groups
  14 + 41(directory) + 104 + 81 + 97 + 1 PASS. Independent source review APPROVE.
  Final frozen backend1003 PASS / 91 platform SKIP / 74 upstream warnings;
  Web135 and desktop/mobile Playwright14 PASS. Ruff, supported Linux-target
  mypy135 plus strict deployment7, OpenAPI/API generation, TypeScript, i18n,
  production Compose and secret scan PASS. Historical B failures remain recorded.
- Installed main wheel SHA256
  3659d4202360b52e481d22ca7456c29280a68082d14e23545bb877a0536406b5;
  selected packaged module bytes match exact merged main. Central revision is
  927e4c5107785765b5040f571dd6b9cf6f119014; schema0009.
- Operator-approved additional250GiB disk migration PASS. Fresh identity/blank
  guards, independent protected-helper review and restored off-VM backup preceded
  the single formatting operation. UUID-mounted data filesystem; original system
  disk and stopped original state retained. Four writers were proven quiescent.
  Full old/new manifest:1565 files / 725702501 bytes, equal SHA/size/mode/owner/group.
  SHA256 fa1ef7f3c22754e114207a3cb6b809d5b5d58480990c40e7faf0e0f9e3ac5bfd.
- Canonical deployment/strict TLS/browser verification PASS. PostgreSQL actual
  data mount is on the approved new filesystem. Every historical table count
  remains at least its closed pre-stop baseline; native evidence and GAP records
  retained. Free data-disk bytes248919089152 (about231.8GiB). Enforced memory/swap
  ceilings: PostgreSQL2048/API768/worker512/Web128MiB; no OOM. Follow-up read at
  2026-10-14T19:00Z confirms data mount and healthy running containers, about
  13.7GiB VM memory available. Rollback must retain new writes/schema and cannot
  silently replace current history with the stopped old copy.
- Live department rollout is separate from this migration acceptance and remains
  in progress. No synthetic production CRUD, content capture or GPO write.

## Live bootstrap and readiness performance follow-up

- Independent protected SACL/lifecycle/enrollment helper reviews APPROVE. Fresh
  metadata scan51988 objects; read-only signed/sealed directory preflight208 users.
  Narrow selected-root11-principal Success Write/Append/Delete SACL and local
  FileSystem Success policy applied. DACL/Owner/Group, Failure and GPO unchanged;
  all six governing GPO audit definitions checked read-only. Full-tree proofs
  initially PASS29.696/29.901s against the unchanged30-second deadline.
- USN exact-main stopped-runtime extension PASS: prior queue bytes/digests,
  credentials and old cursor/journal preserved; protected backup and immutable
  transition receipt retained. Restarted with two roots; fresh readonly queue0,
  nodecount62342, continuity codeNULL. Independent Audit generation/state initialized;
  old state/GAP retained. Machine-only directory collection/delivery has no local
  collection/delivery error or backlog; no operator password was installed.
- Actual service readiness remains unaccepted: OBSERVE with
  AUDIT_READINESS_UNAVAILABLE. Audit explicitly STOPPED for correction; USN remains
  RUNNING. Profiling reproduces AUDIT_READINESS_INCOMPLETE at30.0009s after51229
  objects, with11.79s ancestry work. The same installed-main readonly probe can
  complete near29.9s; there is insufficient timing margin. No deadline, proof
  freshness or configured/HEALTHY requirement is weakened.
- RED8 to GREEN36 focused cases for reuse of typed Win32 binding and bounded256
  immutable SID-byte decoding. Every current parent/leaf attribute, ACL, ACE mask,
  SID validity and length still checked; failed conversion is not cached. Read-only
  in-memory candidate diagnostic complete51988 proof22.375s; no deployment/gate
  claim from that diagnostic. Fresh full regression, independent review and exact
  CI remain required before restarting Audit with the corrected package.
- Repeated isolated browser checks reached the existing5-login/10-minute account
  rate bound. Normal window expiry is awaited; no throttle/reset/policy bypass.
  A real strict-TLS Sources-detail check confirms the new directory component and
  honest NOT_CONFIGURED/STALE pre-start state. Final role/name/live checks pending.

- Performance correction source commit6891130e3d3c0976da0221547fcd69ef8c3a9dd6:
  frozen full backend1011 PASS / 91 platform SKIP / 74 upstream warnings (377.97s),
  focused64 PASS, Ruff, supported deployment-target mypy and OpenAPI PASS; public
  source Gitleaks zero findings. Independent source verdict APPROVE, with actual
  owned local Win32 SID/attribute fixtures. Exact new head/main CI pending.
  Local combined focus initially lacked TEST_DATABASE_URL for one stored-heartbeat
  replay test; that environment setup error is separate from the passing full
  disposable PostgreSQL regression and is not represented as a product failure.
- Normal login window expired; exact prior Audit API registration disabled PASS.
  One enabled scoped Audit registration remains; prior history and user roles
  retained. Audit service remains STOPPED pending the corrected installed package;
  USN remains RUNNING. No automatic baseline reset or history deletion.


## Readiness cadence correction

- PR36 exact head79457f5a7e16afd85909a56ed7b4491d7ca8ef4a / run38624122965
  and merged maindd90de4499a23f4f2652e26b83c58328d16ff67a / run38626465344:
  six required checks PASS; Sonar SKIPPED. Both Windows groups
  14 + 41 + 104 + 81 + 97 + 1 PASS. Corrected installed package remains pending;
  no source-only result is represented as department live acceptance.
- Deterministic RED3 reproduces an additional scheduling defect: sleeping30s
  after a22s scan lets the previous proof age reach74s before the next valid
  proof is published. GREEN schedules the next complete probe from its start;
  failure/nonfinite/backwards-clock paths retain30s backoff. Deadline30s and
  freshness60s remain unchanged. Current ancestry/policy/SACL are never cached.
- Focus69 PASS; fresh frozen full backend1016 PASS / 91 platform SKIP / 74 upstream
  warnings (375.34s). Ruff, mypy135 plus strict deploy7, OpenAPI and diff check PASS.
  Independent cadence review APPROVE, including30s boundary and clock failure
  fixtures. New exact head/main CI required before corrected package installation.
- Separate protected version/lifecycle installation helpers reviewed APPROVE.
  All four prior owner journals must be QUIESCENT; both SACL and lifecycle mutexes
  are acquired in one order. Child timeout cannot incorrectly publish QUIESCENT.
  Target is only a new Audit runtime; old USN code/PID and Audit state/generation
  are preserved. No new SACL/policy/GPO change or baseline reset.
- Current read-only Security bookmark verification PASS, positive remaining record
  margin; original20MiB channel setting untouched. VM follow-up: about13.6GiB
  memory available, no container OOM, PostgreSQL mount still on approved data disk.

## USN regression witness correction

- PR37 head7753d09c3ac3aef4a60edbbccbee26cf8261763d / run38629369287:
  five required checks PASS, windows-pilot FAIL; Sonar SKIPPED. Windows Audit109,
  directory41 and SCM/runtime81 PASS. USN96 PASS / 1 FAIL: completed-inventory
  GAP test observed delivered BOOTSTRAP while GAP was already durably queued.
- Controlled RED reproduces the failure by delaying the first transport ACK.
  GREEN checks the latest durable heartbeat through a closed read-only SQLite
  connection after completed inventory, retaining exact CONTINUITY_GAP and gap
  cursor assertions. ACK is released and threads joined in finally. Production
  USN behavior, delivery contract and continuity requirements are unchanged.
- Focused regression126 PASS; final focused5 PASS, Ruff and diff check PASS.
  Independent review APPROVE; negative mutations removing GAP or replacing its
  cursor are detected. Frozen full regression1016 PASS / 91 platform SKIP /
  74 upstream warnings (394.57s); global Ruff, supported Linux-target mypy137
  and public-source secret scan PASS. New exact head/main CI required.

## Finite native delivery witness

- PR37 final head649be2d5792043a5ea0a5c25e09f7184a1274cb1 / run38633163428:
  six required checks PASS, Sonar SKIPPED. Native groups14 + 41 + 109 + 81 + 97
  + 1 PASS. Merged main1798af144854a5acf7a2c0880c8a584b461d285e /
  run38634602404: five required checks PASS, Windows FAIL in the unchanged native
  USN-to-HTTPS integration at queue_drained. Groups14 + 41 + 109 + 81 + 97 PASS.
  Audit installation remains BLOCKED on exact main CI; no gate bypass.
- Exact delay cause UNKNOWN: successful native changes/lost-ACK replay preceded
  the failure, but pytest shortened the runtime/queue diagnostic. New failure
  output prints the full bounded sanitized runtime witness, never payloads.
- Controlled RED: globally-empty polling rejects acknowledged closed work when
  the active producer adds another heartbeat. GREEN closes one sequence watermark
  after accepted_changes and requires every earlier batch to disappear by ACK;
  all domains/states count, including leased/quarantined work. Retryable reads
  never mean success. Future batches do not change that finite requirement.
- This is a finite delivery witness, not global empty-queue or latency acceptance.
  The original40s deadline, strict four Activity freshness/continuity reads,
  lost-ACK/duplicate and scope/privacy checks remain unchanged. Production code
  and collector configuration are unchanged. Targeted65 PASS / 4 native SKIP;
  portable witness3 PASS, global Ruff and Linux-target mypy137 PASS. Independent
  review APPROVE:43 PASS / 4 SKIP, leased-batch witness and negative mutations
  reject pending-only/global-empty predicates. Public source secret scan zero
  findings. New exact head/main CI required before installing Audit.

## Controlled independence scheduling

- PR38 head0fe9aa616d53b879ab91400cda9637f56ce1b56e / run38637195251:
  five required checks PASS; Windows FAIL in a different existing unit test,
  blocked_usn_keeps_heartbeat_inventory_and_shutdown_independent, expecting two
  delivered heartbeat records within4s but observing one. Native groups14 + 41
  + 109 + 81 PASS; USN96 PASS / 1 FAIL. The final native HTTPS integration did
  not execute; the original delay cause remains UNKNOWN. No installed apply.
- Controlled delayed-ACK RED reproduces that old4s assumption. GREEN holds an
  injected scheduler clock at0 until actual heartbeat ACK, inventory completion
  and blocked-USN poll; then advances one configured period and requires second
  ACK/completed inventory. Acknowledged receipts must have no retained batch:
  creation receipts alone do not count as ACK. Startup/USN remains BOOTSTRAP with
  unknown cursor, one USN child starts/stops, caught failures are empty and the
  run lock is released. Wall40s is fixture emergency protection, not latency
  acceptance; native strict15s freshness checks and production timing unchanged.
- The same10s delayed ACK now GREEN (10.34s). Focus65 PASS / 4 native SKIP
  (4.43s), global Ruff and Linux-target mypy137 PASS. Independent review APPROVE:
  13 PASS, separate5s delayed-ACK GREEN, no-ACK/missing-restart/false-continuous
  negative mutations rejected with threads closed. Public-source secret scan
  zero findings. New exact head/main CI required.

## Fixed native journal-race work

- PR38 head3fafc695f8d465c1019d5997d734ef61e569b41d / run38639577545:
  five required checks PASS; Windows FAIL in the unchanged native rollback-journal
  stress test:20 commits in its5s window versus assertion greater than20. No
  validation/writer failure was reported; CLI14 / directory41 / Audit109 and
  service-group80 PASS. Remaining USN/integration groups did not execute. Exact
  hardware/scheduling delay cause UNKNOWN; installation remains BLOCKED.
- Controlled RED with0.3s writer commit delay produced17 commits in the old5s
  window. GREEN uses fixed32 native commits with validation concurrent with the
  writer; initial handshake requires validation of a real open rollback journal
  before commits can finish. Yield0 avoids validator busy-spin starvation. Guard40s
  is fixture protection, not disk-throughput acceptance; native work is increased,
  not reduced. Finally stops/releases/joins the owned writer even on startup error.
- Final witnesses require32 completed commits, nonzero validation, persisted
  counter32, no writer failures, closed thread and SQLite quick_check=ok. Existing
  hardlink/reparse/persistent-zero-link rejection tests and production unchanged.
  Same delayed writer GREEN (9.85s); focus61 PASS / 4 native SKIP (3.83s), Ruff
  and diff check PASS. Independent review APPROVE:53 PASS / 4 SKIP; early20 work,
  absent validation and connection failure mutations rejected with writer closed.
  Global Ruff, Linux-target mypy137 and public-source secret scan PASS. Fresh
  exact head/main CI required.

## SCM removal completion

- PR38 head80bbcae96df778fd178f320497bb98a6cefe3b54 / run38641875108:
  five required checks PASS; Windows FAIL after native second-crash recovery:
  stop/uninstall completed, but immediate status still reported STOPPED instead
  of absent. CLI14 / directory41 / Audit109 and service80 PASS; USN/integration
  did not execute. Previous unit/race fixes were not represented as final native
  acceptance. No corrected package installed.
- Source-verified completion defect: native delete returned on STOPPED while its
  own service handle was still held. Win32 DeleteService only marks deletion;
  absence requires stop and all service handles closed. Canonical references:
  [Microsoft DeleteService](https://learn.microsoft.com/en-us/windows/win32/api/winsvc/nf-winsvc-deleteservice)
  and matching Context7 Win32 documentation. Exact external handle owner in that
  CI failure remains UNKNOWN.
- RED6 / GREEN7 portable API timelines: close own drain handles, then read-only
  OpenService/close probes; only1060 means absent,1072 remains pending, other
  errors fail. Drain and absence share one150s budget. No repeated Delete/Stop,
  force kill, registry edit or mutation of a possible replacement registration.
- Focus68 PASS; global Ruff, Linux-target mypy137 and diff check PASS. An initial
  wider local focus had75 PASS plus one old stored-heartbeat test setup error
  because TEST_DATABASE_URL was absent; full disposable PostgreSQL regression
  is required separately. Fresh frozen PostgreSQL full regression1026 PASS /
  91 platform SKIP / 74 upstream warnings (366.20s). Strict deploy mypy7,
  OpenAPI and public-source secret scan PASS. Installed-code witness includes SCM.
  Independent review APPROVE: portable7 PASS; early return,1072-as-absent, second
  deadline, foreign Delete and handle-leak mutations rejected. Actual PS5.1 code
  witness rejects wrong SCM hash/path. Existing USN live runtime remains on its
  accepted prior code. New exact head/main CI required before Audit apply.

## Corrected runtime exact-SHA acceptance

- PR38 final head4e8122738af1ee0b0146e4c4537183ff336a9d6f /
  run38644651966 and merged main9296ca51357635207325e50c447f2213997e4093 /
  run38645998236: all six required checks PASS. Native groups14 + 41 + 109 + 81
  + 97 + 1 PASS on both revisions, including real SCM crash recovery/removal and
  strict HTTPS/USN replay. Sonar SKIPPED remains unverified, not Quality Gate PASS.
  Earlier failures and UNKNOWN scheduling causes above remain recorded.
- Exact merged-main wheel SHA256
  `059587b0a4dfd05e7a109a9bc61b9c792a4bee0e80049ca0d8105129f333e698`;
  all138 packaged Python/PowerShell members matched the committed Git archive.
  Protected offline installation and four installed module path/hash witnesses
  PASS. Both lifecycle/SACL locks and all four QUIESCENT owner journals checked.
- Audit switched while stopped, preserving the same protected state/generation
  and exact SQLite bytes across registration replacement; then started RUNNING.
  Original runtime and private receipts retained. Existing USN registration,
  command, PID, state and running disposition unchanged; no additional SACL,
  policy, GPO, baseline, Security-channel or production-file mutation.
- Installed Audit9296ca51357635207325e50c447f2213997e4093; central API/worker/Web
  and existing USN remain927e4c5107785765b5040f571dd6b9cf6f119014, schema0009.
  Publication, central deployment and installed collector revisions are distinct.

## Final migration and bounded live verification

- Fresh read-only verification2026-10-14 around22:30 UTC: PostgreSQL uses the
  approved additional250GiB filesystem UUID; schema0009; all historical table
  counts at least the closed pre-stop baseline; original data copy retained.
  Free248991617024 bytes (about231.9GiB). Existing off-VM restore-verified backup
  and initial full file manifest remain retained. No second format or migration.
- All four containers healthy with enforced PostgreSQL2048/API768/worker512/
  Web128MiB limits and no recorded OOM. Finite admission/pools/queues remain;
  no automatic history deletion or unlimited-retention promise.
- Owned strict-TLS storage_admin browser/UI read and confirmed logout/revocation
  PASS. Four samples22:26:50–22:28:06 UTC: AuditHEALTHY, directoryCURRENT208 users,
  exact UI count, only enabled WINDOWS/AUDIT_WINDOWS collectors. Three distinct
  completed readiness probes cover51988 objects; durations23.64–24.25s,
  published proof ages31.09–32.70s, complete/non-stale, policy/SACL verified.
- Fresh local read22:29:50 UTC: AuditHEALTHY with advancing observed-through,
  full readiness24.16s, no readiness/bounds error; Audit/directory queues empty,
  no GAP, suspension or quarantine. USN retains two roots, approved addition,
  empty queue, one volume stream and ordinary3600s inventory cadence.
- Old pilot object identity is still readable through the sensitive API. The
  bounded Activity sample contains100 of121 recent rows and zero selected-root
  rows. Activity qualityUNAVAILABLE/continuityUNKNOWN remains an honest live
  limitation; exact cause is not established by this check. This sample is not
  proof that no events exist outside the sampled rows or that new-root history
  and attribution have passed acceptance. Audit last accepted batch remains NULL
  during this quiet interval; directory delivery is independently CURRENT.
- Requested CI correction and approved disk migration are complete. Permanent
  Audit remains RUNNING as authorized. Task5 ordinary-event/history acceptance
  remains PENDING, without synthetic production CRUD, outage injection, relaxed
  freshness/continuity gates or a new scheduled monitor. Original001 PASS and
  historical USN-SOAK FAIL/GAP are unchanged. Stop this execution after recording
  these results; no full department acceptance claim.
- Independent final documentation review APPROVE: all three changed documents,
  private CI/install/migration/live receipts and all138 wheel members verified;
  no material discrepancy. Documentation-only diff check and secret scan PASS.

## Activity recovery requested2026-10-15

- Operator requested root-cause correction and completion of selected-root live
  acceptance, avoiding unnecessary working-file changes. Original single-root,
  history/RBAC, bounded resources and no synthetic production CRUD constraints
  remain. Current main before correction50d130b380de983831723eb4f4e6b92a00853a36.
- Fresh API proof: source UNKNOWN/COLLECTION_ERROR despite current continuous USN
  cursor; heartbeat errorSTATE_MISMATCH. Read-only state proves inventory still
  uses the committed transition's old scope. Scope extension updated USN/config
  but omitted the inventory checkpoint. That mismatch prevents real inventory
  completion and correctly prevents Activity COMPLETE; no freshness gate relaxed.
- RED3 plus rollback control PASS; GREEN33 scope tests. Future transitions now
  atomically rebind inventory with completed=false. An explicit stopped-runtime
  same-scope retry repairs only a verified completed transition, retaining its
  prior inventory witness and preserving USN cursor/GAP, credentials and queue.
  Independent scope review APPROVE:12 tests including exact queued bytes/digests,
  foreign receipt/hash/credential rejection and late transaction rollback.
- Fresh selected-root evidence exists: bounded API pagination found93 rows;
  original quiet-interval sample was insufficient acceptance. Audit has31 retained
  batches52 records, no accepted Audit batch, suspended with AUTH_REQUIRED. Exact
  first-batch HTTPS replay instead returns403 AUDIT_VOLUME_REQUIRED; configured
  token/collector match enrollment. Generic transport's403 label does not prove
  a bad credential. Local volume mapping incorrectly used the native GUID alias.
- Audit scope now emits the stable canonical volume GUID identity. Ingest maps an
  exact native volume GUID alias only to an already registered same-source volume;
  indexed volume identity is canonical, original evidence payload/digest and batch
  replay remain immutable. Unknown/other-source volumes and malformed/path-suffixed
  aliases are refused. No drive-letter inference or higher confidence rule.
- Typed PostgreSQL route RED1/GREEN8; portable volume/events/runtime55 PASS.
  Independent review found malformed hyphen positions accepted by UUID parsing:
  actual RED then strict8-4-4-4-12 GUID GREEN. Final independent Audit review
  APPROVE,72 portable checks; source/identity/coverage/delete rules unchanged.
- Fresh complete read-only scan51997 objects in23.30s found two ordinary files with
  empty, unprotected SACL. The configuration-change GAP is genuine; the cause of
  missing ACEs is unproven. No SACL repair, GAP clearing, baseline, service or
  production-file mutation has yet been performed during this correction.
- Frozen PostgreSQL full regression1037 PASS /91 platform SKIP /74 upstream
  warnings (400.52s); global Ruff, mypy136 plus strict deploy7 and OpenAPI PASS.
  New scope/volume tests are included in native Windows CI. Exact head/main CI,
  protected recovery helpers and live acceptance remain PENDING before apply.
- Fresh schema0009 backup/off-VM DPAPI decrypt/hash verification PASS; isolated
  PostgreSQL16 restore PASS at512MiB. First comparison against changing post-dump
  counts failed (archive992 changes versus post-dump993). Restored schema and
  counts then verified within the retained closed-baseline/post-dump bounds;
  no exact active-database snapshot equality claimed, no production restore.


## Live recovery verification2026-10-15

- Source PR #40 merged as1540c2e9a0f7d4169e90b0417cebdeb9136ae13d.
  Exact head9bc52ecd6b0102922f410827af337099f464c2de
  [CI38701674972](https://github.com/BorisDruzak/storage-console/actions/runs/38701674972)
  and exact merged-main
  [CI38702966626](https://github.com/BorisDruzak/storage-console/actions/runs/38702966626)
  each pass backend/frontend/windows-pilot/compose-smoke/production-smoke/secrets.
  Sonar SKIPPED/unverified. Independent source and protected-operator reviews
  APPROVE; findings were corrected before the affected apply operation.
- Central API/worker/Web deployed1540; schema remains0009. The exact wheel has
  139 source members checked against Git and SHA-256
  b401c00c000dd4fad58d6f94cb17faa0aab18a2f1715515376af3572d9e24bfd.
  It is a protected operator artifact for the stopped-state repair. Existing USN
  runtime927e4c5107785765b5040f571dd6b9cf6f119014 and Audit runtime
  9296ca51357635207325e50c447f2213997e4093 remain installed; no unsupported
  claim that both services were upgraded to the deployed central SHA.
- Explicit receipt-bound USN inventory repair PASS: stopped complete state/SQLite
  backup retained; exact queued bytes/digests, unrelated checkpoints/cursor/GAP,
  configuration and credentials unchanged. Original registration/runtime restarted.
  A real full inventory then completed with the new scope, removing STATE_MISMATCH.
  Repeated API reads now show sourceHEALTHY/CURRENT and ActivityCOMPLETE with
  CONTINUOUS_SINCE_BASELINE and advancing continuous progress. Gates not relaxed.
- First immutable retained Audit batch changed from403 AUDIT_VOLUME_REQUIRED to202
  on the corrected central API. After stopped-state backup/hash verification, all
  31 batches/52 records replayed with unchanged original bodies. Delivery resumed
  through the existing store/HTTPS delivery API. Old GAP/bookmark/configuration
  and the full encrypted pre-replay queue backup remain preserved.
- Fresh pre-apply scan51996 objects/23.65s found three ordinary PDFs with empty,
  unprotected SACL, including one additional file since the first diagnostic scan.
  The exact three-target before/intent/after receipts are retained privately.
  Restored only inherited versions of the approved11 Success ACEs. DACL/owner/
  group, root/parent SACL and policy remain unchanged. No business-file content read/write,
  test production CRUD or broad recursive ACL replacement. Metadata size/times
  remained unchanged during the bounded handle checks; no atomic NTFS transaction
  or share-mode prevention of hardlink creation is claimed.
- Full readiness51996 PASS before explicit fresh Audit generation/state. Same
  host/source/collector credentials, directory scope and existing SCM name/runtime;
  canonical volume mapping. Both services RUNNING, operation ownersQUIESCENT.
  Original Audit state/GAP and complete Audit/USN backups retained. The old stream
  observed-through06:02:35 UTC and new baseline08:35:17 UTC remain separate;
  the historical coverage gap is not cleared or represented as covered.
- Strict-TLS owned Chromium/admin UI PASS on desktop/mobile: actual selected-root
  USN row, two linked4663/4624 evidence cards, native account/LogonId/client fields,
  separate current AD observation/provenance and explicit unknown mutation actor.
  Missing-CSRF search403, anonymous sensitive reads401, confirmed logout204 and
  session revocation401; no page errors or body overflow. User browser untouched.
  No roles or business ACL/SMB permissions changed.
- At08:43:44 UTC, bounded fixed24h API window read171 of171 rows:125 exact-root rows, comprising
  34 CREATE/30 WRITE/20 RENAME/30 DELETE and11 METADATA_CHANGE. Administrative SACL
  changes are not ordinary-operation proof. Among114 ordinary changes,29 are
  ACCESS_OBSERVED,10 AMBIGUOUS,75 UNKNOWN;39 have candidates using23 unique genuine
  audit records, event IDs4663/4624. No confirmed mutation actor, new department
  CORRELATED_HIGH or4660 proof claimed. Native client fields are shown only where
  present; current DNS/AD names do not establish historical workstation identity.
- These matched ordinary events are genuine retained OLD-GENERATION observations,
  accepted through replay during this recovery. The fresh generation is quiet in
  the bounded observation interval: zero pending Audit/directory batches and no
  accepted new Audit batch. Its positive ordinary-operation path is not claimed
  as separately exercised. Independent live-evidence review approves the bounded
  ordinary/history/evidence-honesty portion with this explicit limitation.
- Final08:47 UTC local snapshots: USN queue0/0 bytes, completed inventory with
  correct scope; Audit/directory queues0, no new GAP/error/suspension/quarantine,
  full non-stale readiness51996 in24.76s and advancing observed-through. Central
  jobs pending0/failed0. Inventory catch-up completed without increasing limits.
  All12 retained history-table counts remain at least the protected migration
  baseline;62222 objects/path-history rows and997 changes. The three administrative
  SACL changes are SECURITY_CHANGE observations, excluded from ordinary-operation
  proof. Final08:48:15 UTC API read174/174 rows,128 scoped including those three;
  the114 ordinary changes and their29/10/75 classifications remain unchanged.
- Post-drain measured container memory PostgreSQL334/API100.4/worker57.8/Web6.4MiB,
  enforced memory==swap limits2048/768/512/128MiB; all healthy, no OOM. Worker use
  fell after catch-up; VM available RAM about13.5GiB. Data and history remain on
  the approved250GiB filesystem UUID, free231.4GiB; original database copy and
  off-VM backup retained. No second format, automatic history purge or promise
  of unlimited history retention. This is a bounded measured acceptance window,
  not a fleet, reboot, long soak or future-capacity guarantee.
- Task5 ordinary selected-root history/evidence/UI/resource gate PASS with the
  old-generation replay limitation above. Final independent acceptance review
  and documentation publication witnesses are attached to the follow-up PR.
  Permanent Audit and existing USN remain RUNNING. Original001 acceptance and
  USN-SOAK failure retained; no5145/WEF/SIEM/version restore/mass audit. STOP.


## Publication CI correction2026-10-15

- Documentation PR #41 head4707e070d2414f066e2f9804540f486d0d85d4eb
  [run38709396635](https://github.com/BorisDruzak/storage-console/actions/runs/38709396635)
  failed native Audit restart:112 PASS/1 FAIL, IDLE_RESTART_CHANGED_BOOKMARK.
  The Security bookmark advanced; the nature of those intervening host records
  was not established. No unchanged rerun was used as a fix.
- Original equality assertion reproduced RED on legitimate checkpoint progress.
  Separate PR #42 adds21 positive/negative controls, identity/counter/bookmark
  continuity and exact retained encrypted-queue prefix checks. Native SCM now
  requires a distinct owned4663 written while stopped to appear after restart.
  These file operations run only in the disposable Windows CI fixture.
  Portable regression79 PASS, Ruff/diff check/Gitleaks PASS, independent review
  APPROVE and21 independent portable controls PASS. Production unchanged.
- Earlier PR-head run labels identify GitHub check metadata. PR #41 checkout
  actually used a synthetic merge SHA. PR #42 explicitly selects the requested
  PR-head or push SHA in all seven jobs and verifies git HEAD after checkout.
  The new CI receipts supersede metadata-only claims of exact PR-head checkout;
  historical failure and source/deployment receipts remain retained.
- Read-only live recheck09:17 UTC: Activity COMPLETE/CONTINUOUS_SINCE_BASELINE,
  source/Audit HEALTHY, full non-stale readiness51996, actual desktop/mobile
  evidence UI and CSRF/anonymous-read/logout checks PASS. The128 scoped rows
  and114 ordinary changes retain29 ACCESS_OBSERVED/10 AMBIGUOUS/75 UNKNOWN.
  Fresh-generation positive ordinary-event limitation remains unchanged.
  Audit/directory queues empty; USN briefly contained one497-byte pending batch
  during an active sample, without collection error or continuity gap. Central
  jobs pending0/failed0, history counts preserved, approved data UUID and
  resource limits verified, free231.4GiB. Both services RUNNING, ownersQUIESCENT.
- PR #42 head7e1c50dc333adfa5376c0f0853c170715c835682
  [run38711751323](https://github.com/BorisDruzak/storage-console/actions/runs/38711751323):
  all six required jobs PASS with actual checkout verification; backend1058 PASS/
  91 platform SKIP, native groups14/41/134/81/101/1 PASS. Sonar SKIPPED/unverified.
  Merged source successor1ad32b43114c16e50558ba2560ba18aab1f6adb8 uses
  [main run38713384088](https://github.com/BorisDruzak/storage-console/actions/runs/38713384088).
  Terminal main and documentation-head/main receipts must be verified before
  final publication; their SHA/run/verdict records are attached to PRs #42/#41.
  This test/CI-only successor is not a production deployment.

## Fresh-generation ordinary evidence2026-10-15

- Later09:36/09:38 UTC read-only checks supersede the earlier quiet-generation
  limitation. Without operator file operations, six new ordinary selected-root
  USN changes occurred09:22-09:25 UTC: two CREATE, two WRITE, two DELETE.
  Four CREATE/WRITE changes link to two unique native4663 records, both observed
  and first received after the fresh baseline. Evidence host/boot/generation and
  collector match current API health; read-only protected configuration and SQLite
  checkpoint independently confirm that active identity. No rebaseline or replay
  of old-generation records is used for these four fresh matches.
- Fresh matches remain ACCESS_OBSERVED, actor NULL; the two DELETE changes are
  UNKNOWN with no candidate. No fresh4660/HIGH or proven mutation actor is claimed.
  Native client IP/workstation are absent in these fresh4663 records; account and
  logon session are shown, without substituting DNS/AD as historical client proof.
- Owned strict-TLS desktop/mobile UI09:38:59 PASS: exact selected change ID
  matched the rendered detail response; current-generation4663/account/LogonId
  card visible, unknown actor retained, no page errors/overflow. CSRF/anonymous
  rejection and confirmed logout/revocation PASS. API184/184 rows,134 scoped,
  120 ordinary:33 ACCESS_OBSERVED/10 AMBIGUOUS/77 UNKNOWN;43 with candidates.
  Source/Audit HEALTHY, Activity COMPLETE/CONTINUOUS_SINCE_BASELINE, full51996
  readiness non-stale, Audit/directory queues0. This exercises the fresh ordinary
  capture/delivery/correlation/UI path and closes the prior quiet limitation.
- Regular hourly inventory created a bounded USN queue87 batches/23.3MiB, later
  70/19.1MiB and decreasing; continuity and current heartbeat preserved. No forced
  inventory, limit increase or production CRUD. Measured worker58.1/API91.4/
  PostgreSQL335.2/Web6.5MiB within enforced caps, no OOM; VM available13.5GiB.
- PR #42 merged-main1ad32b43114c16e50558ba2560ba18aab1f6adb8
  [run38713384088](https://github.com/BorisDruzak/storage-console/actions/runs/38713384088):
  all six required jobs PASS, Sonar SKIPPED/unverified. Final documentation-head/
  main exact-checkout receipts and queue disposition are attached to PR #41.

## Merge-CI diagnostic follow-up2026-10-15

- Documentation main2b439a8d221ddef40c7732cc93d89aa3bd85da61
  [run38716886593](https://github.com/BorisDruzak/storage-console/actions/runs/38716886593):
  backend FAIL1057 PASS/1 FAIL/91 platform SKIP; Windows/frontend/compose/production/
  secrets PASS, Sonar SKIPPED. The default30s USN-proof test observed only the
  initial heartbeat; its runtime thread reported RUNTIME_FAILED in delivery.
  The underlying state error was not captured. This run is not publication PASS.
- Twenty ordinary and100 high-thread-switch Linux repetitions with diagnostic
  instrumentation PASS. Neither those repetitions nor a timing/ACK review prove
  the original failure cause; it remains UNKNOWN. A transient sidecar condition
  is a hypothesis only. No production Outbox/collector behavior changed.
- The test now captures background exceptions with existing sanitized metadata,
  prints bounded runtime/SQLite diagnostics on delivery/progress/shutdown failure
  paths and asserts no
  background failure at shutdown. Original5s emergency bounds, fake-clock values,
  proof-age bound and30s configured heartbeat assertion remain unchanged.
  It does not swallow failures or rerun the unchanged failing revision for green.
- Fault-injection control: original witness RED INNER_FAILURE_WITNESS_MISSING;
  instrumented witness GREEN with inner delivery/Outbox metadata and no exception
  text. Focused runtime/recovery/sidecar regression43 PASS; final targeted1 PASS,
  Ruff/diff check PASS. Independent review and successor exact head/main CI are
  required before publication closes; their receipts are attached to the follow-up
  PR. A later green result must not be called proof of the original failure RCA.
- Read-only production recheck10:06 UTC: Activity COMPLETE/CONTINUOUS_SINCE_BASELINE,
  source/Audit HEALTHY, full non-stale readiness51997, Audit/directory/USN queues0.
  Both original runtimes RUNNING, ownersQUIESCENT, old GAP/backups/history retained;
  data UUID and limits verified, central failed jobs0, two young pending jobs
  about2s old during the active sample. No service/policy/SACL/file operation.
