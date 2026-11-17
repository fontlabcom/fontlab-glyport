---
this_file: AGENTS.md
---

## Owner priority: functional progress first (2026-11-15)

Future agents must make large, swift advances in working functionality. Prioritize visible user problems and useful, coherent feature increments. This instruction sets the work order and supersedes older requirements to complete exhaustive testing or build test infrastructure before ordinary implementation.

Keep packages coherent and compatible. Check shared APIs, imports and lazy aliases, data formats, dependency direction, object ownership and lifetime, installers, launchers and examples. Update affected providers and consumers together; preserve existing supported behavior and avoid dependency cycles.

During implementation, use the smallest meaningful smoke checks and focused regression tests for the changed behavior and affected package boundaries. Detailed testing, exhaustive coverage, broad performance studies and full acceptance matrices can follow in a later testing pass. Do not let test harnesses, sandbox/supervisor design, repeated unchanged suites, evidence machinery or review paperwork become the main project. Build such infrastructure only when a concrete functional defect or necessary safety constraint requires it.

Record deferred checks and known limits plainly. Do not call untested native, installed or published behavior verified. Keep existing mandatory delivery hooks, preservation rules, licence/privacy obligations, repository exclusions and explicit native/publication holds intact. When one action is held, continue other authorized functional work instead of expanding unrelated infrastructure.

Choose the next substantial useful feature or shared fix and carry its affected providers and consumers together. Timebox supporting investigation; once focused checks establish a usable increment, continue functionality work. Queue detailed testing for a later pass with its concrete remaining checks instead of letting test infrastructure displace product delivery.

## Current scope — 2026-11-05

Issue 230 documentation reconciliation is current. Issue 123 remains paused. The qualified Issue 207 isolated candidate is separate from canonical source, installed artifacts, native acceptance and publication. Reconcile that candidate with later work before integration. Issue 210 specifies future architecture; Issue 211 retains unfinished follow-up checks. Retained dated receipts describe their original source and acceptance surface only.

Canonical source inspected for this proposal: `45dabb4ee3d3`. This is a dated source observation, not an installed or native acceptance claim.

Reconcile the qualified Issue 207 candidate with the current runtime and its real consumer scenarios; preserve original provenance and public compatibility requirements.

Qualify actual native objects, wrapper versions, resources, panels, complete-font/history and save/reopen behavior; source doubles and installed imports are separate evidence.

## Organization and checks

`src/` owns the compatibility runtime; `tests/` contains owned offline contracts; `realuse/` and `native-drivers/` retain full consumer drivers; `src_docs/md/guides/` states public compatibility limits.

Use the explicit-source arm64 Python 3.11 recipe in README Development with pytest, fontTools, fissix, glyphsLib and matching App. Do not blindly use `test.sh`: its lock still refers to a removed registry.

# Glyport rules

## Owner priority: functional progress first (2026-11-15)

Future agents must make large, swift advances in working functionality. Prioritize visible user problems and useful, coherent feature increments. This instruction sets the work order and supersedes older requirements to complete exhaustive testing or build test infrastructure before ordinary implementation.

Keep packages coherent and compatible. Check shared APIs, imports and lazy aliases, data formats, dependency direction, object ownership and lifetime, installers, launchers and examples. Update affected providers and consumers together; preserve existing supported behavior and avoid dependency cycles.

During implementation, use the smallest meaningful smoke checks and focused regression tests for the changed behavior and affected package boundaries. Detailed testing, exhaustive coverage, broad performance studies and full acceptance matrices can follow in a later testing pass. Do not let test harnesses, sandbox/supervisor design, repeated unchanged suites, evidence machinery or review paperwork become the main project. Build such infrastructure only when a concrete functional defect or necessary safety constraint requires it.

Record deferred checks and known limits plainly. Do not call untested native, installed or published behavior verified. Keep existing mandatory delivery hooks, preservation rules, licence/privacy obligations, repository exclusions and explicit native/publication holds intact. When one action is held, continue other authorized functional work instead of expanding unrelated infrastructure.

Choose the next substantial useful feature or shared fix and carry its affected providers and consumers together. Timebox supporting investigation; once focused checks establish a usable increment, continue functionality work. Queue detailed testing for a later pass with its concrete remaining checks instead of letting test infrastructure displace product delivery.


Bridge supported Glyphs.app scripts, plugins and Cocoa/Vanilla APIs to FontLab.

## Boundaries

- Host code: Python 3.11 arm64. Keep host imports lazy; run_python has a fixed 5 s limit.
- General UI/FontLab mechanics go in fontlabapp. Fontport holds fontParts/UFO; Glyport holds Glyphs compatibility. New scripts use App through Fly (`from fly import ap`).
- Keep ask_string raw values and Glyphs error semantics. App run_text_dialog coerces to str.
- FontLab editable installs are owner-managed. Never install/uninstall there or edit canonical checkouts. Preserve owner changes, original corpus bytes and retained evidence.
- Read-only Git: `GIT_OPTIONAL_LOCKS=0 /opt/homebrew/bin/git --no-optional-locks ...`. No checkout/reset/clean/stash, commits, tags, pushes or releases without explicit authorization.

## Checks

Prerequisites: arm64 CPython 3.11 installed, the reviewed App checkout at
`../fontlab-fontlabapp` and Fly >=1.3.0 source at `../fontlab-fly`, uv and Ruff on PATH, and network for uncached packages.
Use README.md's `FONTLAB_SCRATCH` setup to create writable TMP/cache folders on
your chosen external drive. Select a fresh cache if App metadata is stale. uv installs both packages editable only in its external test environment.
Clear all inherited `SETUPTOOLS_SCM_PRETEND_VERSION*` variables first, using the
loop in DEPENDENCIES.md; real Git versions must satisfy the App floor.

```bash
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH="src:../fontlab-fly/src" uv run --no-config --python cpython-3.11-macos-aarch64-none --no-project --with pytest --with fonttools --with fissix --with glyphslib --with-editable ../fontlab-fontlabapp --with-editable . python -B -m pytest -q -p no:cacheprovider
```

Docs checks:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH="src:../fontlab-fly/src" uv run --no-config --python cpython-3.11-macos-aarch64-none --no-project --with pytest --with fonttools --with fissix --with glyphslib --with-editable ../fontlab-fontlabapp --with-editable . python -B -m pytest -q -p no:cacheprovider tests/test_*docs.py tests/test_*distribution.py
```

Lint requires Ruff on PATH:

```bash
ruff check --no-cache --output-format concise src tests native-drivers
```

The cold-import child uses `-I`; App must be installed in the test interpreter.
`test.sh` uses the stale registry in uv.lock; use the explicit sources above.
Archive checks need GLYPORT_DISTRIBUTION_DIR with one fresh wheel and sdist.
Without it, three archive checks skip. Ruff has 26 existing findings.

## Applicable host landmines

- PythonQt widgets/models are in QtGui; QObject is in private. Native instances reject extra attributes; Python subclasses cannot shadow native slots. Call protected native event handlers on their native class explicitly.
- Disconnect owned signals before close/deleteLater. Table-item lookups lose Python subclass attributes; retain Python-side state separately. Never negate Qt wrappers; negate coordinates.
- Catch paintEvent exceptions and end QPainter in finally; an escaping exception with an active painter can crash FontLab.
- Imported modules persist across Remopy calls. After closing old handles, load this checkout first, purge stale modules and assert module.__file__; installed canonical sources otherwise shadow tests.
- Client timeouts do not stop host execution. Enforce host deadlines/cancellation through cleanup and receipt writes. Never clear async exceptions with PyThreadState_SetAsyncExc(..., NULL).
- Never read fgPackage on an unregistered flPackage. Use keyword arguments for optional native constructor parameters; positional overload dispatch differs from stubs.
- cloneCustom with a nonempty contour map failed on 9784. Shape clones can alter raw connection bits and drop ShapeData notes; node clones on 9787 lose explicit zero/fractional corner_smooth and other scalars. Prove detached ownership and preserve all raw fields.
- Rebinding cloned layers requires takeShapes then re-add after assigning the destination glyph. removeAllShapes drops owner registrations. Prove explicit component reference layers after save/reopen.
- Never notify auto layers; notification can rebuild unrelated composites. Refuse unsafe automatic-dependency renames. UpdateAll can queue unrelated semantic updates; check successive edits and never clear queues or normalize dates to hide changes.
- VFJ save/reopen on 9784 can convert a trailing Smooth cubic control to On. Check reopened node types and closed topology, not coordinates alone.
- Existing pin moves to origin can fail Redo on 9784; new named pins need explicit appearance. Metadata scans through fgGlyph can clear the FontGate note mirror. Preserve native notes, history and dirty state.
- FL.fl.Select/Unselect can crash with a Glyph window active. Require a verified active Font window before selection writes.
- Native text paths can truncate NUL or lose input-method text. Standalone Qt repairs do not clear the PythonQt hold. QFileDialog/QColorDialog can touch shared state despite non-native options; retain dialog restoration gates.

## Native proof

History scope is prospective: retain all prepared, changed and pending-layer
owners before each write; component-history tuples are dependencies, not glyphs.
Package/creation/master-write scope needs App's matching current Font-window
predicate plus GUI-thread history check. Recovery restores before publication
checks and retains failures for retry. Never clear the native pending queue.

Offline tests, imports, stubs and standalone Qt are not native proof. Run owned
fixtures through the shared serialized native runner and Remopy;
assert the installed artifact paths and actual FontLab build. Preserve complete
fonts, UI/cache state, dirty state, Undo/Redo and saved/reopened artifacts.
Use flPackage.getProperty("__has_history_changes") for dirty state; window flags
alone are insufficient. Keep source/artifact, partial-native and full-workflow
results separate. Never promote selected fixtures to corpus-wide acceptance.

## Milestones and delivery

Read [PLAN.md](PLAN.md), [TODO.md](TODO.md) and [WORK.md](WORK.md) before work.
Make the smallest complete MVP for one named acceptance task. Find all callers,
tests, fixtures, exports and documentation first. Use graph impact before source
symbol edits; confirm stale or unknown graph results against current source.
Keep product work in isolated successors and preserve the owner's checkout.

Run this repository's exact checks and the unchanged 80% gate for each complete
changed production module. Use an independent review before a milestone commit.
Under the current owner task, commit and push reviewed, passing milestones;
verify remote heads rather than inferring delivery from local tracking refs.
Before main integration, reconcile concurrent work and all consumers, run graph
change analysis and repeat the required acceptance on the combined source.

Before removing obsolete branches or files, prove integration, retain recoverable
unique work and check fresh owner/worktree attachments. Preserve sealed reports,
licences, archives and private data. Do not rewrite history by implication.
Remove verified completed work from PLAN/TODO and record scoped evidence in
CHANGELOG. Keep implemented-only native/artifact checks open in TODO. Issue 123
remains paused; no instruction here authorizes driving the owner's FontLab,
installing into its user folder or publishing a site.

## Source/build-only documentation

Authored public guides live in `src_docs/md/guides`; five core pages provide website navigation. Use the separate 31-package hash-locked Python 3.13 documentation environment and `sh src_docs/build.sh`; run `python -m unittest discover -s tests_docs -v`. Generated `docs` is immutable output. The every-main workflow verifies source/output lineage, a shared source epoch and complete tracked plus ignored/untracked parity. All twelve private P/L holds remain; no Pages grant, helper or request belongs here. Preserve native/owner-install gates.

## Owner workflow — 2026-11-10

After each important round, reconcile current team work and integrate independently reviewed, verified changes into main using the repository's delivery gates. Preserve owner branches, indexes and unrelated work. Move only verified solved TODO items into cumulative CHANGELOG, update PLAN for remaining work, and continue the authorized backlog. Keep unverified native checks and owner-paused tasks open; this workflow does not authorize installation or bypass preservation gates.

Build each round on a fresh `origin/main` in an isolated branch or worktree, resolve conflicts by keeping both our work and teammates' work, and never force-push. `install.vfpy` is shared: keep it byte-identical in every installer repository.

## Verified integration rounds — 2026-11-10

After each important independently reviewed round, recheck actual upstream
`main` and owner/worktree attachments. Fetch in a new isolated successor based
on current `origin/main`, merge the round's reviewed work, and resolve conflicts
by preserving both sides' intent, newer fixes and teammates' changes. Preserve
owner checkouts, branches, indexes, refs and configuration; never pull, switch
or rebase an owner's or another agent's active worktree. Stage only the exact
reviewed residual delta. Run the repository's applicable full suite, lint and
graph change gates on the combined tree, obtain independent merge review, then
commit and push under the current owner task's authority. Keep required hooks,
including the installed Dismisser pre-push gate, active; never bypass them or
force-push or rewrite history. Verify the actual remote head and required
main-triggered Actions; a local tracking ref is not delivery proof.

Move only evidenced solved tasks from future PLAN/TODO into cumulative
CHANGELOG, retaining every unrelated entry and placing new progress first. Keep
TODO flat and unchecked, update PLAN to remaining work, and continue the next
authorized task. Unverified native, SDK, UI, history, artifact, adoption and
publication checks stay open. The workspace root remains non-Git. Preserve
excluded repositories, recovery, licences and private data; this workflow does
not authorize FontLab installation or native operations, resume Issue 123, or
lift private Pages holds. Native upstream fixes use reviewed PRs to the
cause-appropriate Proteus, FontGate or pyfontgate repository.

## Isolated successors

Overrides generic bootstrap/MCP.

For graph work in an isolated successor, use the qualified installed CLI or backend with both `GITNEXUS_HOME` and `GITNEXUS_STORAGE_PATH` set to separate task-owned locations before the first invocation, including index discovery and analysis. A private storage path alone can still register the successor in global control files. During ordinary analysis, do not fall back to global MCP defaults, global `list-repos` or global setup/bootstrap, and do not make unreviewed global registry edits. Retain exact command/selected environment and before/after owned metadata; record expected task-owned `.git/info/exclude` additions and preserve unrelated state. If discovery or indexing escapes the owned scope, preserve evidence and obtain independent bounded control-file review before integration. Any necessary recovery must be separately reviewed, use fresh guarded current bytes and reviewed writer coordination, and change only the proven task-owned entry while preserving all other current records and bytes; never restore an old whole global registry.

## Agent workflow (Issue 250, 2026-11-10)

- Plan with `superpowers:subagent-driven-development`: one fresh implementer per task, a separate read-only reviewer, then the controller runs the gates and commits.
- Send bulk, well-specified work to Codex via the `codex-delegate` skill (`node ~/.agents/skills/codex-delegate/scripts/relay.mjs --brief BRIEF --cd WORKTREE`, in the background). Use `claude-delegate` or `cursor-delegate` for second opinions or independent lanes. Delegates never commit, push or tag.
- Work in a fresh worktree of `origin/main` on the workspace data volume; never pull, switch or reset the owner checkout. Merge `origin/main` again before pushing, keep both sides' CHANGELOG/PLAN/TODO entries, rerun the full suite, lint and graph change analysis, push through the pre-push hook where one is installed (never force), verify the remote SHA and the CI run where a workflow is configured. Held private Pages operations (workspace D41) stay held.
- Release: tag the next semver above the latest tag and publish a GitHub release. Install released, gated packages into `~/Library/Application Support/FontLab/FontLab 9/` and test live in FontLab 9. This owner route (Issue 250) supersedes, for released packages only, every older line in this guide that forbids installing into the FontLab user folder or its site-packages, owner-managed editable installs, or starting FontLab for a live test (the owner's canonical editable checkouts themselves stay owner-managed): record the previous installed distribution first so it can be restored, and never touch FontLab preferences (owner fonts and documents: see live font editing below); native work goes through the workspace `verification/issue-104/fl-native.sh` gate.
- Documents: CHANGELOG holds verified completed work; TODO only open or to-verify items; PLAN the major remaining changes; WORK.md the current round only (older WORK bytes are archived on the owner's workspace data volume, not public).
- Native defects: issues at github.com/fontlab/fl; fixes as pull requests to fontlab/Proteus, fontlab/FontGate or fontlab/pyfontgate. Never commit to the local C++ snapshot.
- Older "work directly" or "no delegation" lines in this guide are superseded by this section (Issue 250).
- Live font editing (owner, 2026-11-10; workspace D44): test, verify and edit the font open in FontLab 9, and do not stop because the owner might be working in it. Open a VFJ from `~/Desktop` first (those files are for agents), then add glyphs, kerning pairs, elements, contours, masters or whatever the test needs, and save them freely. This supersedes, for live testing, every older line here that forbids mutating owner fonts or documents or requires owned fixtures only. FontLab preferences, Output folders and global update queues stay untouched. Keep the serialized host lock (`fl-native.sh`, one native run at a time; `--mutating` now allows open fonts); do not quit or restart FontLab and do not close fonts from Python, which has crashed the host.
