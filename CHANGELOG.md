---
this_file: CHANGELOG.md
---

## 1.2.10 (2026-11-16)

- `install.vfpy` is now the short fontlab-instamix stub. It installs
  fontlab-instamix from PyPI when it is missing, then installs this checkout from
  its `[tool.fontlab-install]` table. The large legacy installer is gone.
- Private machine paths are removed from `realuse/manifest.json` and `PLAN.md`;
  `realuse/provenance.json` records the scrubbed manifest's hash. `tests/test_public_api_gaps.py`
  reads the Glyphs SDK only from `GLYPHS_SDK_PATH`.
- `tests/test_installer_archive.py` tests the stub, the install table and the sdist.
- README describes the stub install.

## 2026-11-15 — Shared installer source alignment

Copied the reviewed shared installer exactly: dependency constraints and managed origins remain protected; inactive conditional dependencies are filtered before sibling execution in the resolver target Python. FontLab imports remain standard-library-only. Package identity, runtime APIs, dependency declarations, scripts, bundles and legal files are unchanged. The real source-archive check now includes the exact root installer; the prior omission was reproduced before the single allowlist addition.

Focused checks: 6 passed in 1.00s. This qualifies the local source candidate only. Independent review, combined-main/full delivery gates, genuine release/downloads, installed provider closure and admitted FontLab/native workflows remain separate. No owner-folder installation or native operation ran.



## 2026-11-14 — documentation comparison main delivery

- Independent review accepted the documentation-test repair at source/main/hook/exact-CI scope. Source `ab0269ccfffb1997c436cf85d00f40946f77514b` has reviewed tree `8130d0b0e6e7b32b6d357aa231870bc28d6d4a07`; generated main `cf59e760d95ea65bf14ba19174d39511582e2303` changes only the two sitemap outputs. All 62 generated paths remain tracked.
- The ordinary unchanged pre-push hook passed 7,495 tests with nine skips under arm64 Python 3.11.18, then 869 Pens tests with 95.76% coverage against its unchanged 80% floor. Individual hook case IDs and skip reasons were not captured. The separate author run remains 7,498 passes/six existing skips with all 7,504 ordered IDs under arm64 Python 3.11.14; no case or skip parity is inferred.
- [Documentation run 43567583082](https://github.com/fontlabcom/fontlab-glyport/actions/runs/43567583082) passed both jobs for the exact source SHA. The qualifier bound that source, its generated child and source epoch 1794638333; strict parity and all 37 documentation tests passed. This establishes source/main/CI delivery only.
- Required bare Ruff 0.14.10 still fails with the exact retained 94 diagnostics; explicit Ruff 0.16.7 success does not clear that gate. Native-driver coverage of 0–50.98%, full providers/new ordinary tuple, all 17 native rows, root installer, themes, typing, history, Undo/Redo and save/reopen remain open. Current graph Method.method_fts Invalid UTF-8/BM25 degradation, 739-candidate/process caps and UNKNOWN remain. Actual hook App/Pens raw-index failures and earlier author Glyport/App/Pens setup UNKNOWNs remain unresolved; no bytes were restored and no broad preservation clearance follows. Release, installation and native acceptance remain separate; Issue 123 and private Pages holds remain.

## 2026-11-14 — guarded documentation comparison source checks

- Reproduced the unchanged documentation suite's 35 passes and one failure after all 62 generated-output hashes matched. The final comparison now requests an explicit Git patch with external/textconv diffs disabled, retaining working-tree versus index semantics.
- A real-Git five-state regression accepts timestamp-only and staged/index-equal changes, and detects unstaged content, deletion and executable-mode changes. The old oracle fails exactly the two timestamp cases; the repaired class passes both tests with unchanged raw fixture indexes and modes. Every original cross-date hash/count/epoch/lineage assertion remains.
- All 37 locked Python 3.13 documentation tests pass. Strict rebuilding at current source HEAD's epoch preserves all 62 output hashes and modes. Additional explicit Ruff 0.16.7 checks pass on src/tests/native-drivers and the changed test; the required unversioned gate remains failed because the recipe selects Homebrew Ruff 0.14.10 and reproduces the historical 94-finding output exactly. Both results and the old failed receipts remain; this test-only change repairs no production lint issue.
- One complete arm64 Python 3.11 source run passes 7,498 tests with the same six existing skips and identical ordered 7,504 IDs as the accepted audit. No fixture-driven unskip or skip-policy change occurred. Source editables do not qualify ordinary installation or native behavior.
- Independent review, fresh-main combined qualification, actual hook/main/CI delivery, release and installation remain pending. Complete native-driver coverage, full provider/consumer closure and all installed/native workflow gates remain open. Issue 123 stays paused and private Pages operations stay held.
## 2026-11-14 — Functional work order documented

- Added the owner's functional-progress-first guidance and repository-specific priorities, including cross-package compatibility and a later detailed testing pass. Existing mandatory hooks, holds and unfinished work remain in force.
- This change updates guidance and planning only; it establishes no new runtime, installed, native or release result.

## 2026-11-13 — Issue 255 verified release qualification

- [fontlab-glyport v1.2.8](https://github.com/fontlabcom/fontlab-glyport/releases/tag/v1.2.8) is released at `7404fe26629701dcf7a2e91f3ca83bd6b88d8a42`. Reviewed main/tag delivery, applicable CI and actual downloads match the qualified artifacts.
- The three Scripts, launcher, authored native-driver payloads and active examples use Fly; launcher ownership/refusal protections remain intact.
- 7,494 source tests pass with 10 inherited skips; all four complete changed-module gates and 36 documentation tests pass. Genuine wheel/sdist ordinary cohorts pass 62 consumer checks each; 16 actual archive checks pass without skips. Reviewed main/tag hooks, CI and actual release downloads are qualified.
- Ordinary external installation is qualified; installed FontLab/native acceptance remains unproved under D43. Consumer setup still requires separately installing matching Fly >=1.3 in the same interpreter. Provider source installers do not automatically supply or enforce this prerequisite; no reverse mandatory Fly dependency is claimed.

## 2026-11-13 — Issue 255: Fly consumers and bounded launcher source selection

- Three menu Scripts, the generated launcher, authored current native-driver API payloads and active examples use Fly. User-facing requirements name `fontlab-fly>=1.3.0`; source recipes explicitly select sibling Fly source. Runtime `src` imports/dependencies, shared installer, original compatibility fixtures, real-use oracles/manifests and provenance are unchanged. External Remopy transport stays direct.
- Launcher source switches refuse while tracked live handles remain; active cleanup failures remain retryable; terminal failed handles remain tracked and report unresolved cleanup on subsequent calls. Admitted reloads clear Glyport's canonical and Fly root/child caches together, preserve unrelated aliases and assert source/identity. Driver bootstrap refuses existing canonical or Fly Glyport modules before source selection, and bootstrap failure closes only its owned external transport; realuse teardown retains provider aliases after reported cleanup failures. No native execution is claimed.
- Exact explicit-source arm64 CPython 3.11.14 full suite with branch coverage: **7494 passed, 10 skipped**. Three changed Scripts: **100% each**; complete launcher template: **93.05%**; deploy helper: **97.53%**. Real-Fly `-I` regression explicitly selects/validates sibling Fly source and checks cached root/child refresh, live refusal, failed close and same-source reuse. Actual RunHandle cleanup failure and post-release no-op semantics are covered. Additional checks cover menu cancellation, all 14 authored native-driver Python sources/payload imports and host-free preflight/teardown branches.
- Ruff 0.16.7 passes src/tests/native-drivers/Scripts/tools/deploy; existing CLI tests receive only import sorting and explicit `check=False`. Six active guide pins were updated after independent semantic review; the three frozen guide pins and catalogue/canonicalization/anchor assertions remain unchanged. Independent specification/quality review passed. Controller full source checks passed **7494 tests with 10 inherited skips** in 148.31s; all four complete changed production modules exceed 80% combined coverage with zero excluded lines. The hash-locked strict docs build and all **36 documentation tests** passed. Genuine released artifacts, ordinary installed consumers, delivery and native behavior remain separate open acceptance tasks.

## 2026-11-12 — D46 documentation pass (Issue 250)

- Landed on `main` this session: `d4d0440` (last two MIT test headers now Apache-2.0); `10b6975` (Python 2 string warnings located with the fissix tree); `69b7297` and `0ef3244` (shipped tests run from a lone sdist or wheel, C13-35); `c06a6f2` (emptied cache key directory rebuilt); `a7903ce` and `acc6806` (Python 2 `except A, e` detected under 3.14); `27f56df` and `e3364e0` (App floor 1.2.10, NUL-key menu fallback deleted); `dbf24d6`, `e3f773b` and `26a831b` (CLI edge paths and `python -m` entry point covered); `db40f26` (1 s deadline for the escaped-descendant cleanup test); `e8077a7` (sdist ships `tools/migrate_app_paths.py`); `df86604`, `eede138` and `3e9b88e` (`install.vfpy` synced with the App installer); `f4e06d9` (pens v1.0.2 wiring). No source changed in this pass.
- New open TODO rows: the paused Issue 123/201 branch series and the `WORK.md` prose pointers. Native checks stay open.
- `WORK.md` is a short status stub; its earlier content stays archived on the workspace data volume.

## 2026-11-12 — Licence audit: Glyport is Apache-2.0 throughout (Issue 250, owner Q5)

- Two test oracle modules (`tests/color_ui_originals.py`, `tests/table_item_originals.py`, FontLab-owned donor methods) carried `MIT` SPDX headers; they now read `Apache-2.0`. Package metadata, `LICENSE` and `NOTICE` were already Apache-2.0.
- Unchanged on purpose: `Unicode-3.0` data (`LICENSE-UNICODE-3.0`) and CC0 fixtures are third-party terms, not relicensable. Wheel data-file classification (`public_script_suffixes.json` CC0; `unicode17_*` Unicode-3.0) is still unverified and stays with C13-35.

## 2026-11-12 — Python 3.14: `ur''` literals no longer break adaptation (Issue 250)

- Fix: `tests/test_adaptation_cache.py::test_combined_literals_and_raw_string` failed under Python 3.14.10 with `AdaptationError("'u' and 'r' prefixes are incompatible", (4, 7))`.
  - Cause: the `PY2_STRING_AMBIGUITY` scan in `_adaptation_pipeline._pipeline` ran the running interpreter's stdlib `tokenize` over the original Python 2 source. The tokenizer in 3.14 raises `TokenError` on `ur''`; those in 3.11–3.13 split the literal into NAME `ur` plus STRING.
  - The scan now walks the fissix Python 2 parse tree, which is already parsed for the raw-unicode warning. Each warning sits at the literal's first character, prefix included. Before the fix, a `ur''` warning on 3.11–3.13 pointed at its quote.
- New test `test_string_ambiguity_when_raw_unicode_then_python2_parser_locates_literals` replaces the stdlib tokenizer with one that raises, as on 3.14, and pins the positions `[(1, 5), (1, 9), (2, 7)]`. It failed before the fix with the 3.14 error. A mutant that reports quote columns also fails it.
- The adaptation, cache and runtime-review tests pass on both 3.11 and 3.14: 52 each.
- A differential over 523 repository `.py` files under 3.11 found that the old and new string positions are identical in all 468 files both parsers accept. The other 55 files are unparseable by one parser or the other.
- Evidence: `reports/glyport-row12/`.

## 2026-11-12 — C13-35 payload half: fresh wheel and sdist audited and tested in independent environments (Issue 250)

- Fix: two shipped migration tests failed outside a workspace because `tools/migrate_app_paths.py` read App's `_legacy.py` only from a sibling `../fontlab-fontlabapp` checkout. `legacy_path()` still prefers the sibling checkout. Without one, it finds the installed App's `_legacy.py` with `importlib.util.find_spec` and does not import App. With neither present, `FileNotFoundError` names both sources. Three new tests cover these cases. Three mutants each fail at least one test: no installed fallback, importing App to locate the file, and preferring the installed App over the sibling.
- `test_source_origin_is_this_worktree` keeps its strict source-tree assertion. With `GLYPORT_TEST_INSTALLED=1`, it instead requires a `site-packages` origin outside the tree, and that branch fails a source-tree run.
- Artifacts built at 69b7297 with arm64 Python 3.11.14:
  - wheel `7060328578fa260a989471d741f3aad0993af617de86b83e95057fad849894b8`
  - sdist `6b2e4cb75858216aa8e75afb77f09dd2a82e95d0ae86e8e0cb672ef238798945`
- `GLYPORT_DISTRIBUTION_DIR` archive contract: `tests/test_issue111_distribution.py` passed 10 of 10. It checks the payload against source bytes, privacy paths, licence files, metadata, extras, the entry point and sdist Markdown links.
- The wheel holds 189 files: 178 `.py`, four data files and seven dist-info files. The sdist holds 628 files.
- The wheel `METADATA` README has 10 relative links, which do not resolve on an index page. They do resolve in the sdist.
- Independent environments, each a fresh venv with App 1.2.12 (d6c2b1b) and pens a2efd35 installed as wheels, with no sibling checkouts and `--no-sources`:
  - Extracted sdist, installed editable from the extraction: 7459 passed, 10 skipped. The receipt shows `fontlab_glyport` imported from the extracted `src`.
  - Installed wheel, running the shipped tests from a second extraction with `-o pythonpath=` and `GLYPORT_TEST_INSTALLED=1`: 7459 passed, 10 skipped. The receipt shows `fontlab_glyport`, `fontlabapp` and `fontlab_pens` imported from the venv's `site-packages`.
  - The 10 skips are the four archive tests, which ran separately above; three cases without `pathops`; and three that need sibling echopy or SDK checkouts.
- Before the fix, the same lone environments failed the two migration tests, plus the origin test in the wheel run.
- The licensing half stays open in TODO and is reported to the integrator's inventory. Evidence: `reports/glyport-row59/`.

## 2026-11-12 — Escaped-descendant cleanup test: race on an 0.08 s deadline, fixed (Issue 250)

- Cause: `test_process_cleanup_does_not_wait_for_escaped_descendant_eof` gave `run_process` an 0.08 s deadline. In that time the child had to start Python, fork the grandchild and print its pid. When fork or startup was slow, the child was killed before it printed, so the test failed on `int('')` at line 190. The shared runtime cache played no part: `dependencies.py` has no cache reference.
- Measured (arm64 3.11.14):
  - The time between `Popen` and the pid line grows with the parent's RSS, because fork cost scales with it: median 31/49/83 ms and maximum 71/104/194 ms with 0/2000/4000 MB of touched ballast.
  - With 4000 MB of ballast, the old test failed 5 of 5 runs with the same `int('')` error. Without ballast it passed 30 of 30 under load average 16 and under 48 CPU spinners; CPU load alone does not reproduce the failure.
  - A full suite under coverage peaks at 854 MB RSS. The failure seen in this lander's gate run at 015616e (1 failed, 7458 passed) came under that load plus about 16 concurrent agent processes.
- Fix (test only): the deadline is 1.0 s, the grandchild holds stdout for 30 s, and the test asserts that a pid was printed and that `elapsed < timeout + 0.6`. A cleanup that waited for the grandchild's EOF would take about 30 s.
- New test results: 5 of 5 passed with 4000 MB of ballast and 10 of 10 without. It kills an unbounded `communicate()` in `_cleanup_process` and a variant that does not close the pipes before reaping, failing each at 30.03 s against the 1.6 s bound.

## 2026-11-12 — `'auto' != 'glyphs2'` launcher-profile failure explained and closed (Issue 250)

- `tests/test_realuse_deploy.py::test_launcher_profile_when_source_is_python2_then_glyphs2_else_auto` failed once in the integrator's Glyport t11 run at ccde27d. That commit predates the launcher fixes a7903ce and acc6806.
- Reproduced at ccde27d under Python 3.14.10: line 221 fails with `'auto' == 'glyphs2'`. Python 3.14 accepts `except A, e:` (PEP 758), so the old parse check missed the Python 2 helper. Under 3.11.14 at ccde27d the test passes.
- At main a64f90d the test passes twice under 3.11.14 and twice under 3.14.10 (arm64), each run in its own TMPDIR. The `("A, e", "glyphs2")` cases added by a7903ce pin the fix.
- Not a flake. The row is closed as fixed by a7903ce/acc6806; no source change.
## 2026-11-12 — C13-27 closed: NOTICE wording already agrees (Issue 250)

- The remaining blocker was an expected App `NOTICE` row. The two files already agree, so none will follow.
- `fontlab-fontlabapp/NOTICE` lines 4-9 state that code adapted from fontlab-glyport was first released under MIT and is relicensed by its copyright owner under Apache-2.0.
- Glyport `NOTICE` lines 4-5 state that Glyport is Apache-2.0 and was first published under MIT, relicensed by its copyright owner; `LICENSE` is the Apache-2.0 text.
- TODO row C13-27 removed; the helper inventory above stays the record.

## 2026-11-12 — C13-27 helper inventory: not duplicates (Issue 250)

- The Glyport suite emits no warnings (7456 passed, 8 skipped; arm64 3.11.14, offscreen).
- Bodies read against App 1361354. No pair is the same logic under a different input type:
  - `model/kerning.py:34 master_id(font, key)` checks that a string id is one of a Glyphs proxy font's own master ids and raises TypeError/ValueError. App has no master-id validator (`def master_id` finds nothing in App `src`).
  - `model/attachment.py:7 target_master(font, source)` maps a copied Glyphs layer proxy to a master of the target font, by session-local owner token else by unique master name, else refuses. App has no equivalent (`def target_master` finds nothing).
  - `model/metrics.py:43 font_metrics(font)` returns a `ProxySequence` of `GSMetric` records for a proxy font; App `studios/font_audit/session.py:44 font_metrics(package)` returns Font Overview rows `(master, ascender, caps, x-height, descender, kerning pair count)` from `fontlab.FontMetrics`.
  - `model/metrics.py:51 master_metrics(master)` returns `{metric.id: GSMetricValue}` for a proxy master; App `studios/vertical_metrics/diagram.py:244 master_metrics(package, master)` returns `[(label, y)]` diagram rows from `fontlab.FontMetrics`.
- The App-owned NOTICE wording (`fontlab-fontlabapp/NOTICE` lines 4-9) stays tracked in the Glyport TODO until the App row lands. No source change.

## 2026-11-12 — `python -m fontlab_glyport --help` covered (Issue 250)

- `tests/test_main_module.py` runs the module as a subprocess and in-process via `runpy`; both assert exit 0 and the `usage: glyport` text, so `__main__.py` is exercised by the per-module gate. No exemption added.

## 2026-11-12 — App floor raised to 1.2.10; NUL-key menu fallback deleted (Issue 250, C13-26)

- `pyproject.toml` (both declarations), README, DEPENDENCIES, `src_docs/md` and the pins in `tests/test_public_api_gaps.py` and `tests/test_issue111_distribution.py` now require `fontlab-fontlabapp>=1.2.10`, the first App tag with `OwnedMenus.own_menu` (owner approval, C13-25).
- `FontLabPluginHost._menu` returns `self.own_menu()` for unmapped names; the `getattr(super(), "own_menu", None)` / `"\x00owned"` fallback is gone.
- `tests/test_issue122_t15_host.py`: the legacy-fallback test is replaced by one that fails if any fallback returns (without `own_menu`, `_menu("FILTER_MENU")` raises `AttributeError` and searches no title).
- Native menu behaviour stays open as TODO C13-26N.


## 2026-11-12 — Python 3.14 raw-unicode adaptation failure recorded (Issue 250)

- Reproduced `tests/test_adaptation_cache.py::test_combined_literals_and_raw_string` failing only under Python 3.14.10 (`AdaptationError: 'u' and 'r' prefixes are incompatible` at line 4, column 7, raised from `adaptation.py:176`); Python 3.11 passes. Recorded as a low TODO row with the next check; no code change.

## 2026-11-12 — Installer: unreachable blocked skip removed (Issue 250, review M-10)

- `install.vfpy` synced byte-identically from App (sha256 `2eb71691…` → `bbe8104e…`):
  `remove_old_dist` drops the `path.name in blocked` skip. Every blocked top-level
  name is also held, and a non-empty held refuses before anything is deleted, so the
  skip never ran. App's `tests/test_install_superseded.py` pins that invariant.

## 2026-11-12 — Runtime cache rebuilds an emptied key directory (Issue 250)

- `src/fontlab_glyport/adaptation.py` `adapt_source` treats a cache entry as a hit only when its `manifest.json` exists; `src/fontlab_glyport/adaptation_modern.py` `adapt_modern` only when both `source.py` and `map.json` exist. Otherwise the key directory is removed and rebuilt. Before, any existing key directory counted as a hit, so macOS temp cleaning (which left 160 of 161 key directories empty under `$TMPDIR/fontlab-glyport-runtime-cache`) failed 44 tests with `FileNotFoundError` on `source.py`. A complete entry that fails its integrity check still raises.
- Tests: `tests/test_adaptation_cache.py` (emptied and source-only key directory rebuild; complete entry still a hit) and `tests/test_runtime_acceptance_edges.py` (modern cache, three survivor sets); the five rebuild cases failed before the change. Full solo suite on Python 3.11, fresh TMPDIR, branch-inclusive: 7454 passed, 10 skipped, 0 failed; `adaptation.py` 95%, `adaptation_modern.py` 89%.

## 2026-11-12 — CLI edge tests (Issue 250)

- New `tests/test_cli_edges.py` (17 tests): malformed manifests, invalid runner evidence, `INVALID_NATIVE_RECEIPT`, `--runner` errors and a working runner, verify without `--output`, inspect output inside or equal to the source refused, inspect writes once with exit 0 and a refused second write exits 2 leaving the first bytes unchanged, and a subprocess `python -B -m fontlab_glyport` run. Seven mutants were killed by reviewer2.
- Coverage (measured on e3f773b before the later merges; the pre-push hook run is the evidence for the merged tree): full solo suite, fresh TMPDIR, branch-inclusive (the gate's `branch = True` measure, same as the earlier 76.77%): `cli.py` 96% (138 statements, 3 missed; missing 101, 245, 277->281, 287); 7448 passed, 10 skipped, 0 failed. Closes the TODO row "Raise cli.py coverage to at least 80%".
- The 44 failures seen with the default TMPDIR were environmental (empty key directories in the shared runtime cache after temp cleaning), not source: see the new TODO row. The `--native` branch (233-248) stays open in TODO.

## 2026-11-11 — Lock refresh and pens suite in the pre-push gate (Issue 250, C13-57)

- `uv lock` refresh against the current App metadata: adds the `uharfbuzz` test-extra requirement. `fontlab-python-pens` stays a path-editable source (workspace convention shared with App and Fontport, and what the live FontLab site-packages use); an editable lock entry cannot pin a version, so the released tag is recorded here instead: latest pens tag v1.0.2, sibling checkout v1.0.2 plus 5 commits (05792a4).
- The workspace gate recipe (`.metaswarm/repos.sh`, fontlab-glyport case) now runs the pens suite (80% coverage floor) after the Glyport suite and fails on a pens failure; the pens editable install was already in the recipe.
- Verified (closes the C13-57 confirmation row): the real pre-push gate on the merged tree ran the pens suite after the Glyport suite and passed (7434 passed, 7 skipped; pens 857 passed, 95.76% coverage, floor 80%; gate5-gly.log, pushed as 87f39f4).

## 2026-11-11 — NUL-key menu fallback: App tag audit (Issue 250)

- `git tag --contains 1c41ec4` in fontlab-fontlabapp lists only `v1.2.10` (remote tag `46e8dd8`). `1c41ec4` added `OwnedMenus.own_menu` (`src/fontlabapp/qt/menus.py:404`); App 1.2.0 to 1.2.9 lack it. The declared floor `>=1.2.0` therefore does not supply the seam, so the fallback in `FontLabPluginHost._menu` stays. No code changed.
- TODO row C13-26 reworded to the floor bump to `>=1.2.10` it depends on, with the files to update. Native menu behaviour stays open.

## 2026-11-11 — Launcher-profile test failure not reproduced

- Not reproduced: `tests/test_realuse_deploy.py -k launcher_profile` (run as `pytest -q tests/test_realuse_deploy.py -k launcher_profile` with editable pens, App and Glyport in a fresh clone) gave 1 passed on clean d7cbdeb and 6 passed on 43ace93. The earlier `auto` != `glyphs2` result is most likely a stale installed copy; that cause was not proven. The full Glyport gate also passed at 43ace93 (7432 passed, 9 skipped). The TODO row is removed on that basis; reopen it if the failure returns.

## 2026-11-11 — Issue 250 C13 backlog and offline artifact triage

- Classify all 58 original open rows with stable C13 identifiers: 3 offline artifact rows, 32 native/platform rows, 12 owner/publication rows and 11 provider/repository rows. Preserve every original requirement and add a concrete next check; Issue 123 remains paused.
- Complete C13-14 for clean source `d7cbdebecacf429f39050fd1600cd1ecdd1a3664`: fresh baseline wheel/sdist distribution and portable-fixture checks pass all 15 tests, including the three archive checks. Both archives reproduce byte-for-byte (625 sdist members; 189 wheel members). This scoped archive completion does not close C13-35/C13-38 or establish native/release acceptance.
- Fix the C13-35 sdist packaging gap: include the existing `tools/migrate_app_paths.py` required by two shipped migration tests. The new exact-byte archive regression first fails against the missing helper, then passes; all 16 focused archive/portable-fixture checks pass after the manifest fix. Runtime code and the wheel inclusion rules are unchanged.
- Reconcile PLAN's stale lint status with a current repository-root Ruff 0.16.7 check: zero findings in src/tests/native-drivers. No production module, existing test/oracle, dependency floor or protected menu seam changed.
- The exact workspace gate (network available) runs on the merged tree before push; its result is the pre-push suite run. The shipped migration test needs a sibling `fontlab-fontlabapp` checkout, so it is not standalone from an extracted sdist.

## 2026-11-11 — Launcher profile detection under Python 3.14

- `tools/deploy/launcher_template.py` `detect_profile`: Python 3.14 (PEP 758) parses the Python 2 form `except A, e:` as a tuple of types, so `ast.parse` no longer raised and such scripts returned `auto` instead of `glyphs2`. A new check treats an unparenthesised exception tuple as `glyphs2`. Reproduced with `test_launcher_profile_when_source_is_python2_then_glyphs2_else_auto` under Python 3.14; passes under 3.14 and the host 3.11. The FontLab host runs 3.11, so installed behaviour was unaffected; the defect was interpreter-dependent. The test requires a single balanced parenthesised group, so Python 2 `except (A, B), e:` is also `glyphs2`. `except A, B:` (valid on 3.14) is `glyphs2` on every version: an accepted ambiguity with Python 2 `except A, e:`. Parametrized tests cover the parenthesised, `as`, `(A, B), e`, `A, e` and `A, B` forms.

## 2026-11-11 — Issue 250 test environment qualification

- Full Glyport suite via the workspace recipe with network and loopback sockets: 7,424 passed, 8 skipped. The earlier 51 failures were environmental (incomplete shared adaptation cache, missing sibling App alias source, sandbox-denied loopback binds); no product bug or stale expectation. Document the requirements in DEPENDENCIES.md.


## 2026-11-10 — Issue 250: strict App-floor doc check

- `tests/test_issue122_t15_docs.py`: `APP_VERSION` is strict (`fontlab-fontlabapp>=X.Y.Z[.devN]`, no prefix or extra version digits). A loose detector finds any `App`/`fontlab-fontlabapp` comparison, and the doc check fails when a document has a mention the strict form does not accept, so near-misses cannot hide. A new test pins the near-miss forms.

## 2026-11-10 — Issue 250: own-menu lookup seam

- `FontLabPluginHost._menu` uses App's `own_menu()` for unmapped Glyphs names. The NUL-key lookup remains only as a fallback for App releases without the seam; tests cover both the seam and the fallback.

## 2026-11-10 — live font editing rule (Issue 250, D44)

- AGENTS.md: agents test and edit the font open in FontLab 9, starting from the Desktop VFJs, and may save them.

## 2026-11-10 — Issue 250 Ruff lint cleanup

- Resolve all 192 findings from the installed Ruff 0.16.7 tool: final `ruff check .` reports zero. Apply safe fixes and reviewed manual changes without changing Ruff configuration, public names or `__all__`; preserve legacy integer formatting and intentional re-exports.
- Retain line-specific exceptions for public/fixture re-exports, lazy property fallbacks, open-only error handling, the existing ValueError contract, parent-thread failure assertions, distinct malformed UTF-16 cases, owned documentation execution and the ProperDocs side-effect import.
- Full offline pytest before and after: **7,372 passed, 9 skipped, 49 failed, 2 errors** (isolated worktree run without the sibling App checkout; the installed push gate, with the sibling App linked, passed 7424 passed / 8 skipped at e669f51); all 51 failed/error node IDs are identical. Existing failures concern missing runtime-cache source files, the absent sibling App migration source and sandbox-denied socket binds. No new failures. Documentation unittest suite: **36 passed** before and after.
- No formatting sweep, installation, FontLab operation, commit or publication. Historical/frozen paths and excluded third-party code remain unchanged. Reproduction commands and environment limits are in WORK.md.

## 2026-11-10 — isolated graph guidance proposal

Prepare append-only AGENTS guidance for separate task-owned graph HOME and storage, ordinary-analysis scope and independently reviewed bounded recovery. Preserve existing integration rules and acceptance holds. This documentation proposal records no new runtime, test, native, integration or publication result.

## 2026-11-10 — verified integration-round guidance

- Record current-main reconciliation in a new isolated successor, preservation
  of concurrent work and exact reviewed staging, combined repository/graph
  checks, independent merge review, required hooks and actual remote proof.
- Keep solved tasks in cumulative history and unfinished acceptance in the
  future queue. Native, installation, adoption, Issue 123 and private Pages
  boundaries remain unchanged. This entry records documentation only.

## 2026-11-10 — install.vfpy always reinstalls scripts and dependencies

- Every install copies all files from `Scripts/` afresh and replaces any file
  already at the same path. A symlinked script folder is replaced by a real
  folder; the link target is never written. A directory where a script file
  belongs is still refused.
- Required packages are installed on every run. Packages that no package
  index carries (the fontlab-* packages, pythonqtside) are installed from
  checkouts beside this one through their own `install.vfpy`, once per run
  and safe against cycles. uv receives every other requirement, so version
  ranges, markers and extras are enforced. Without uv, sibling checkouts are
  still installed and only the remaining missing requirements are reported.
- The installer is byte-identical across all eleven installer repositories.

## 2026-11-07 — bounded native and ordinary-artifact qualification

Bounded owned-font native checks passed through the actual public
Model(FontLabBackend).GSLayer.getPen route on unhinted space/Regular: a closed
triangle and open cubic produced exactly two appended shapes and the independent
point record, persisted across save/reopen. An actual owned Glyph window was
shown and captured after reopening. Hinted writes and the rest of the consumer
UI/workflow are not qualified by this finite case.

Ordinary precommit artifacts have matching source/sdist/wheel/site package
payloads in the normal 19-distribution cohort: App 620, Fontport 38 and Glyport
182 files; 2,011 installed RECORD entries were checked. These dirty-VCS
artifacts are separate from the bounded native runs. The consumer candidates
remain uncommitted; canonical adoption, clean committed artifact requalification
and delivery are not complete. Native notification can restamp 40 unrelated
glyph timestamps; the exact per-run date inventory remains explicit. No
whole-font history safety or general UI/workflow acceptance is claimed.

## 2026-11-07 — pen protocols from fontlab-python-pens (Issue 235)

`model.pens` (`draw_info`, `LayerPen`) and
`model.outline_geometry` (`correctPathDirection`) take their point/segment
adapters, reverse pen, area pen and point-inside pen from `fontlab_pens`
instead of `fonttools_module(...)`. The Glyphs-model pens stay in Glyport.
`GSLayer.draw`, `getPen` and `correctPathDirection` therefore work without
fontTools. Offline tests only; native FontLab behaviour remains unverified.

## 2026-11-06 — ordinary package contract repair

Include the existing public PLAN.md and TODO.md in the sdist so README links resolve. Runtime, dependencies and existing archive/link/licence oracles are unchanged.

At this precommit checkpoint, the isolated candidate was uncommitted; genuine dirty-VCS artifacts, normal installation and tests were recorded separately. Native acceptance, clean committed artifact requalification and controller review were still pending.

## 2026-11-05 — independently approved documentation applied

[Task 2 final review](../verification/issue-230/task-2-fix2-review.md) records
SPEC PASS / QUALITY APPROVED. The [78-file application receipt](../verification/issue-230/task-2-apply.json)
includes this repository's six guides and preserves all 21 repository heads,
branches, indexes and non-selected diffs. This is applied documentation evidence,
not a new product test, installed artifact, native result or publication.

[Round 2 independent review](../verification/issue-230/round-2/repair-review.md),
[application](../verification/issue-230/round-2/apply.json) and
[controller verification](../verification/issue-230/round-2/controller-verification.json)
include this repository's `TODO.md`. The complete round
has 26 successors across the workspace; its acceptance is source/documentation-
receipt scope, not runtime/native acceptance.

The complete earlier handoff/history below retains its proposal-stage statements
and dated source pins. Later review, application and delivery status belong in the
[live workspace ledger](../verification/issue-230/progress.md). Original future,
native, artifact and preservation contracts remain binding.

## 2026-11-05 — documentation reconciliation proposal

Prepared repository-specific organization, test and MVP/delivery guidance from current source/test configuration and retained Issue 207–211 evidence. Distinguished current canonical layout from qualified candidates, future plugin ownership and unfinished native/artifact gates. Preserved all prior work and changelog evidence; no runtime completion, installation or publication is claimed. Completed historical task rows were removed from the active checklist and consolidated below from existing local CHANGELOG/WORK receipts. Unfinished native, artifact and integration checks remain open.

## Retained scoped completion receipts — corrected evidence map

These are dated results at the stated source/version and acceptance surface. They do not establish current integrated, installed, native or published acceptance. Full receipts and hashes are indexed in the workspace Issue 230 task-2 manifest. Canonical-preimage line ranges below refer to the unchanged historical documents, before these new entries.

- Issue205 scoped delta:72 focused;5177 full+223skips;0/41 below80%;Ruff.
  Historical receipt: CHANGELOG.md:16–24.

- Issue205 mirror signed/rotated round trips;72 focused;5177/223;94.94% proxy coverage.
  Historical receipt: WORK.md:42–85.

- Issue205 portable SDK path:4 override/fallback tests and actual reference audit pass;full5177/223;0/41 below80%.
  Historical receipt: WORK.md:59–85.

- Issue205 node type refusal before backend/Undo;72focused;5177/223;all41 modules above80%.
  Historical receipt: CHANGELOG.md:16–24.

- Issue205 SDK constants/host-free plugin entry points;public API review5149/223 and0/41 below80%.
  Historical receipt: WORK.md:91–172.

- Issue205 detached constructors/transforms/writes/reverse;44 behavioural cases;5149/223;all41 above80%.
  Historical receipt: CHANGELOG.md:27–39.

- Issue205 support docs/App>=1.2.0 floor recorded;genuine unresolved sibling floor retained;5149/223.
  Historical receipt: CHANGELOG.md:27–39.

- Issue205 scoped full gate5177/223;all41 above80%;changed-fileRuff.
  Historical receipt: CHANGELOG.md:16–24.

- Issue205 lazy facade111 exports+7plugins;activation identity;wheel smoke;5138/152;23focused+29docs checks.
  Historical receipt: WORK.md:272–318.

- Issue205 both-backend outline/pen/save operations;5138/152;23focused;native-call doubles only;native persistence still open.
  Historical receipt: WORK.md:287–318.

- Issue205 geometry tests:12new pass;15boolean checks;5103/223 coverage run;97.83%/98.72%;full5173/153.
  Historical receipt: WORK.md:174–209.

## 2026-11-05 — planning chronology reconciliation

Chronological source-only limitations and repair instructions are superseded by later recorded manager/Unicode/metadata/public API implementations. Do not reinstate active-font-first lookup, missing case/script, old constructor/discovery work, ENOSPC/no-archive, D35pending or later-superseded152/85/25failure states as current. D35is resolved; failed receipts/recovery pins remain. Complete custom/default/resource/ABI/version/original/native acceptance remains open. Historical passing results retain their dated source and acceptance scope in the entries above and original history below. This documentation change creates no new runtime acceptance.

---
this_file: CHANGELOG.md
---

## 2026-11-04 — v1.2.1: re-exports that static docs tools can resolve

- `plugins.host` now re-exports App's paint-layer names (`AFTER_NATIVE_LAYER`,
  `BEFORE_NATIVE_LAYER`, `LAYER_FILTERS`, `PaintContext`) in the explicit
  `X as X` form, so documentation tools treat them as public aliases.
- `GlyphsApp._binding` and `GlyphsApp._exports` use absolute imports.
  `_public/` is served through `fontlab_glyport.__path__`, and relative imports
  pointed static tools at a nonexistent `_public` package.
- Runtime behaviour is unchanged: the same objects are imported.
  Gate: 5177 passed, coverage PASS 0/41.

## 2026-11-03 — Issue 205 scoped API re-review

- Restore native node/component selection clearing and replacement alongside
  anchors/guides; explicit unsupported selections still refuse before writes.
- Preserve the mirrored axis at zero rotation and test rotated affine round trips.
- Discover the optional SDK reference via environment/workspace-relative paths.
- Reject invalid live node types before any backend access or Undo activity.
- Add 28 regression/path cases; focused suites: 72 passed. Equivalent full gate:
  5,177 passed, 223 skipped; Coverage PASS (0/41 below 80%); changed-file Ruff clean.


## 2026-11-03 — Issue 205 public API review

- Correct/audit SDK constants and add scalar vocabulary/GSGuideLine aliases;
  plugin base classes now import without a backend or FontLab.
- Add explicit detached font/master constructors, affine component properties,
  path reversal and four-kind layer selection with native kind refusals.
- Route node type, anchor name, font metadata and master name/basic-metric writes
  through existing guarded Undo paths; preserve rename identities and originals.
- Raise both App dependency floors to >=1.2.0; retain/document the local sibling's
  genuine 1.1.x resolution failure until its release is tagged.
- Add 44 behavioural cases and update obsolete refusal assertions/support docs.
  Gate: 5,149 passed, 223 skipped; Coverage PASS across 41 changed modules.
  Native runtime acceptance remains separate; no commit or live host changes.


## 2026-11-03 — Issue 205 canonical module paths

- Migrate shared App imports, monkeypatch targets and documentation to the
  canonical domain modules without changing runtime behavior.
- Reuse the reviewed path migration tool with boundary and idempotence tests;
  update the shared-mechanics table check for nested module names.

## 2026-11-03 — Issue 205 geometry coverage

- Added twelve behavioural tests for detached geometry/Boolean pen conversion,
  staged outline publication, selection, Undo counts and failed-edit recovery.
- Requested full-suite line coverage: detached_geometry.py 97.83% (90/92),
  outline_ops.py 98.72% (77/78). No runtime-code changes or coverage exclusions.

## 2026-11-03 — Issue 205 independent-review repairs

- Preserve closed-path rotation in extrema insertion; skip history and writes for
  unchanged extrema/overlap operations, and omit duplicate Boolean closing nodes.
- Save native fonts by ID through fontpr to verified absolute `.vfj`/`.vfc` files;
  support makeCopy without changing the recorded path and refuse formatVersion.
- Require explicit ignoreChanges=True before discarding unsaved font edits.
- Add public unbind(), host-free export discovery, and one Undo step per pen
  session (context manager or doneDrawing); correct plugin-binding documentation.
- Add regression cases for all six review findings; native calls use doubles.

## 2026-11-03 — Issue 205: public GlyphsApp API and live outlines

- Added lazy `fontlab_glyport.GlyphsApp` and `.plugins`, including explicit
  `use_backend()` for offline callers and `fly.gp.GlyphsApp` usage. Public exports
  reuse the existing facade; active bootstrap objects retain their identity.
  Independent public binding followed by activation is explicitly refused.
- Added live layer overlap removal (existing boolean extra), recursive component
  decomposition, winding correction, exact Bezier extrema and point/segment pens
  through both backends and the existing Undo/collection guards.
- Added font save/close; retained filepath/familyName readers. Native persistence
  uses documented workspace/package calls; FakeBackend writes first-master UFOs.
- Added offline import, geometry, pen, rollback and native-call contract tests.
  Native FontLab Undo/Redo and persistence qualification remain separate.

## 2026-11-03 — fixes from runs inside FontLab 9

- Adaptation manifests are read as UTF-8 (FontLab's Python defaults to ASCII).

## 2026-11-03 — installer options, licence and cleanup

- `install.vfpy` reads optional `[tool.fontlab-install]` keys: `name` (the distribution
  record), `packages` (`[]` installs scripts only) and `dependencies` (what FontLab needs,
  instead of `project.dependencies`). Symlinks inside `Scripts/` are not copied.
- Relicensed under Apache-2.0 by the copyright owner (previously MIT). `LICENSE` now
  holds the Apache License 2.0 text; `LICENSE-APACHE-2.0` is gone. Expression: `Apache-2.0 AND Unicode-3.0`.
- Removed the Issue 106 round reports (`ISSUE106-*.md`, `ISSUE-GLYPHS80-COMPARESTRING.md`)
  and `plans/` (kept in Git history).

## 2026-11-03 — install.vfpy fixes from runs inside FontLab 9

Verified by installing all nine packages inside FontLab 9 (Python 3.11.6, arm64).
- Dependencies with console scripts (glyphsLib, fontTools) failed: uv writes them to
  `site-packages/../../../bin`, which resolves through the venv link to the FontLab
  folder. `bin`, `share` and `include` there now link back into `.venv`.
- A failed install appends a `"failed"` record with the traceback and uv's output to
  `install.log`; List/Uninstall ignore failed records.
- Package records include `WHEEL`, so `uv pip check` accepts them.
- Scripts are copied file by file into FontLab's `Scripts` folder, from a package's
  `Scripts/` folder (exact case) and from folders listed in `[tool.fontlab-install] scripts`.
  Folders shared by several packages merge, e.g. two packages' `Scripts/Kerning`. The
  installer refuses to overwrite a file another package or the user put there; uninstall
  removes only its own files, their `.pyc`, and folders left empty. An older install's
  folder link (`Scripts/Aidus Code`) is replaced by copied files.
- `*.vfpyc` (FontLab's compiled `install.vfpy`) is ignored by Git.

## 2026-11-03 — install.vfpy creates FontLab's venv

FontLab's `python/3.11/site-packages` is now always a real folder; packages are
symlinked into it, so no `.pth` processing is needed. `install.vfpy` creates `.venv` with
uv from FontLab's exact Python version and processor type, and links the venv's
site-packages to FontLab's folder, so `uv pip install --python .venv/bin/python` installs
into FontLab. An older layout (FontLab's folder linked into `.venv`) is migrated.

## 2026-11-03 — reverse-domain extension id and install.log

`[tool.fontlab-install] id = "com.fontlab.glyport"` names this extension. `install.vfpy` keeps
`Extensions/com.fontlab.glyport/install.log` (JSON Lines; the last line lists every installed file),
puts copied code in `Extensions/com.fontlab.glyport/lib/`, and adds Scripts > Extensions >
List Extensions and Uninstall com.fontlab.glyport.

## 2026-11-03 — install.vfpy without uv

`install.vfpy` now needs only FontLab's Python. It asks FontLab for its data folder
(`flPreferences().dataPathDefault`), links a Git checkout or copies a plain folder into
`Extensions/`, and writes a `.pth` plus `.dist-info` into `python/3.11/site-packages`.
uv is used only to add missing dependencies. It never replaces folders it does not own.

## 2026-11-03 — release scripts

Added `build.sh` (uv build into dist/), `publish.sh` (`uv publish`; refuses a dirty
tree or an untagged HEAD) and `install.vfpy` (editable install into FontLab's venv
from inside FontLab). Version stays hatch-vcs from `vX.Y.Z` tags.

<!-- workspace-handoff:2026-11-03 -->
## 2026-11-03 — documentation handoff for November 2–3

November 2–3 isolated features repair metadata/local-manager/generation/resource/state contracts and foreground identities;25baa7b is a tests/docs companion to runtime 40ac49ab.

Latest accepted runtime is genuine dev196; source/ordinary evidence does not prove actual default resources or native behavior.

Observed canonical checkout: `main` at `94d4226dc644`. No source integration is performed by this update.

Updated the requested AGENTS/TODO/PLAN/CHANGELOG/README documentation and
recorded the paused state. Existing project text, examples and history remain;
no runtime source, installation, native session, branch/ref, release or site was
changed by this documentation maintenance. Source/archive/ordinary/native and
promotion acceptance remain separate claims. Detailed workspace evidence is
recorded in the root CHANGELOG and retained verification reports.
<!-- /workspace-handoff -->
## Final review fixes — 2026-11-03 (issue 201)

- `customParameters.remove(p)` now removes `p` itself. Before, it deleted the
  first parameter with the same name, which could be a different one. A
  parameter that is not in the collection raises `ValueError`.
- Flat custom-parameter keys edited outside glyport no longer make the
  collection unreadable. The flat keys win, and a `CUSTOM_PARAMETERS_REBUILT`
  warning is reported.
- A name that is not a string raises `TypeError`.
- Document events return the same `GSDocument` as `Glyphs.currentDocument`.
- A failing error sink no longer reaches FontLab's canvas paint.
- Activating a tool twice no longer doubles its painters. A failing
  `willDeactivate` no longer leaves the painters attached.
- `glyphInfoForName(name, font=<not a font>)` raises `TypeError`.
- Source docstrings describe behaviour only.

## Tool bridge review fixes, round 2; real-use harness on 3.12 — 2026-11-03

The synthetic `Glyphs.currentEvent()` now gives `locationInWindow()` in the
active window's points with y up, as in Cocoa. With no active window it gives
screen points. An error sink that raises no longer reaches FontLab: both errors
are printed. A key event before any mouse event now maps the cursor, not widget
pixel (0, 0).

Real-use harness: the deadline escalation (`RealuseEscalation`) did not end code
that swallows every exception on CPython 3.12+, and the 3.12 `./test.sh` run
hung or failed in `test_realuse_harness.py`. 3.12 creates an injected exception
as soon as it is raised, inside the `try`. The armed trace raised on that
"exception" event, the bare `except` swallowed the halt, and CPython dropped
the raising trace. The trace now waits for the handler's next line, as already
happened on 3.11, FontLab's version. The in-host guard module is version 5, so
a host that still holds the old version reloads it. The tests no longer skip
under coverage. Instead, each test suspends the outer tracer for itself and
the threads it starts.

## Tool bridge review fixes — 2026-11-03 (issue 201)

No tool bridge callback raises into FontLab any more: an error from the event,
the viewport or the plugin goes to the host sink, and the callback returns
False or None. The registration token keeps the bridge alive, and native painter
entries keep their Python callbacks; on FontLab 9.0.9802 a registered tool and
its painters still work after `gc.collect()`. A tool's refused background paints
as an overlay with the R054 note, like a reporter's. The native painter entry is
recorded before `destroyed` is connected, and removal attempts every step.
`editViewController()` works during the tool's own paint, and
`getActiveLocation_(None)` or a foreign event reads the cursor. Nested events
restore the outer view. Outside tool events `Glyphs.currentEvent()` is a
synthetic event with live modifier flags instead of None.
`NSClassFromString("GlyphsToolSelect")` resolves, and `drawTextAtPoint` logs an
unknown `align`. Natively, event positions, the painter device and the paint
maths all use logical viewport pixels on a HiDPI display.

## Shared API gaps from native plugin triage — 2026-11-03 (issue 201)

Native triage of corpus Reporters showed shared gaps. `GlyphsApp.plugins` now
re-exports the SDK's Cocoa/GlyphsApp names that glyport provides (34 corpus
plugins use `NSClassFromString` from it); `ReporterPlugin.drawTextAtPoint` follows
the SDK (28 plugins); `NSOffsetRect`, `NSPointInRect` and `NSStr` are added; the
editor `view().window().windowController()` chain resolves to a select-tool draw
delegate; a reporter's `graphicView().getActiveLocation_` maps the live cursor
(or a tool event) to glyph units. `NSContainsRect` is added, and `NSScreen` reads
QScreen geometry as the PythonQt property it is (two General plugins failed at
import). Text field cells answer `setScrollable_`/`isScrollable` (Qt line edits
always scroll), and vanilla `Window._window` offers `contentMinSize`/
`contentMaxSize` for the mekkablue shared helper (eight scripts lost their saved
preferences on the former, three failed on the latter). Fake-backed tests cover
each addition. `Glyphs.currentEvent()` returns the tool event being handled, else
None, so `getActiveLocation_(Glyphs.currentEvent())` in a reporter reads the cursor.
Final native triage on FontLab 9.0.9802 (98 corpus targets, no filter applied):
55 pass, 12 partial, 31 fail; the workspace triage record lists each target.

## Native canvas painters and Python tools — 2026-11-03 (issue 201)

On FontLab builds with `flCanvas.appendPythonPainter`, editor painters attach
native `UnderOwner`/`OverOwner` painters per glyph canvas instead of overlay
widgets: Reporter backgrounds and `DRAWBACKGROUND` callbacks now paint under
the outlines (R054 fallback only on older builds). `SelectTool` plugins register
through `flWorkspace.registerPythonTool`; a tool bridge maps Qt mouse/key events
to `mouseDown_`/`mouseDragged_`/`mouseMoved_`/`mouseUp_`/`mouseDoubleDown_`/
`keyDown_`/`keyUp_`, and offers `editViewController().graphicView()` with
`getActiveLocation_`. Keys are never claimed, so FontLab shortcuts keep working.
Native pixel check on the running build: an Under fill leaves glyph ink visible,
an Over fill covers it. A probe SelectTool in FontLab received activation,
hover, press, release, a key, background and foreground paint, and deactivation
on close (the viewport height is a PythonQt int property, not a method).
Suite 7007 passed/221 skipped; new modules 100%/99%.

## Plugin priority consumer checks — 2026-11-03

Correct Qt flag shapes in test doubles and add four plugin priority/close tests.
App333 is red; genuine App334 passes7210installed checks in both prefixes.
Normal7132/79existing skips, all58modules>80%; unchanged source-origin guard
passes separately. Runtime/artifact identity remains40ac49ab/dev196; actual
FontLab stacking, lifetime and complete native acceptance remain open.

## Foreground identity projection and history exposure — 2026-11-02

The native finder selects each declared master's concrete identity; all other
valid nonmask/nonservice stored foregrounds retain separate tokens in native
order, including same-name and interpolating/master-like records. Native
isMasterLayer is name-derived and cannot identify a declared slot. Master-ID/
ordinal lookup and pending no-create slots keep their existing contract.
Auxiliary resolution uses the same selected-ID set. A glyph history marker is
captured when a layer handle is exposed, so a first later read can rebind a
wrapper replaced by external history instead of treating the new epoch as old.

Thirteen initial regressions fail against U; repaired focused126cases pass.
Full plain7203pass/3fresh-archive skips includes every existing source-context
case. Four exact documented helpers add one further passing case. The complete
unchanged normal gate then passes7128/79existing skips: all58main-relative modules
86.46–100%, native backend93.31%. No new coverage exclusion or policy change.
All297other inherited test files are exact; one inherited file corrects two
source-backed role/slot expectations and retains all mask/service/stale guards.
Original test preimage and precise correction remain in external Zevidence.

Commands: rtk proxy <arm64-python> -I -B foreground-layer-identity-20261102/
record_tests.py full-source-final tests, exit0; identity-doc-green14pass, exit0;
rtk proxy /bin/sh .metaswarm/quality.sh coverage <this-checkout> fontlab-glyport,
exit0. Exact argv/versions/logs/JUnit/coverage are in external
foreground-layer-identity-20261102/{full-source-final,identity-doc-green,normal-quality}.
Initial baseline missed139owned GetGo controls through an absent sibling alias;
restoring the exact accepted read-only alias makes the final full run execute
all139. Initial gate lacked upstream; local tracking of actual origin/main
restores its full main-relative scope. Failed receipts retained, no gate bypass.

New docs/LAYER_IDENTITIES.md has four executable read-only helpers and explicit
stored/pending/native-role/declared-slot limits; it is included in the source
archive list. README stays199lines. Genuine archives, matching Echopy/ordinary
qualification and actual native four-font/full preservation/cache/lifetime/
history/Undo/Redo/save-reopen remain separate. Full Transform, real window
priority, Aidus retirement, complete bindings/resources/version and publication
remain open. No canonical, native or owner installation changed.

## Manager guide source-archive inclusion — 2026-11-02

The first genuine manager archive preserved all committed declared members and
reproduced its whole wheel, but its unchanged relative-link check found the new
manager guide omitted by the explicit sdist list (8pass/1fail). Include the guide
in that list; retain the failed archive and receipts. Fresh archive qualification
follows; no production behavior or inherited test changes.

## Manager state source gate accepted — 2026-11-02

Implements retained raw accessor/setter identity, lazy script/sidebar-category
ranking, initDebug queue/group allocation, observer/cache/recovery selectors and
explicit superclass deallocation over individual lawful primitives. Root repaired
shared construction to preserve prior localURL/state/observer flags and execute
load/drain/register in source order. No inherited test changed:295files exact.
157additive owned cases, including parser adoption/failure, cache races/current
fields and partial failures. The exact font lookup is a class selector.

Full plain7190pass/3archive skips; unchanged normal7114pass/79existing skips.
All57main-relative production modules86.46–100% combined; all3new helpers100%.
Root run_full_final.py/run_quality.py and command/JUnit/full-source/policy receipts
remain in the external manager-state-20261102 stage. Scoped Ruff/diff checks and
AST-identical root formatting pass. Child frozen bytes and24+15source/ARM pins
were directly rehashed. New95line docs/GLYPH_INFO_MANAGER.md details public,
primitive and native boundaries; README stays199lines.

Retained failed attempts: initial debug oracle confused unsupported malformed
row prefixes with ordinary parse errors; missing-file open is false/nil. No
parser or inherited oracle was weakened. First aggregate skipped6source-context
checks; only the task-owned verification alias was retargeted to the accepted S
fixture context, and final plain run executes them. Original receipts remain.

Genuine archives and matching Echopy/authored guides/ordinary tuples require
separate qualification. Actual Foundation/default resources/CF/CG/CT destruction,
NSObject substitution/once ABI/native workflows remain open. No native call,
generated/source-lock/site refresh, owner/canonical/main/tag/release action.
Full original scripts/dialog/four-font/Aidus/migration/promotion scope remains.

## Dynamic sidebar/document source gate accepted — 2026-11-02

Complete retained category/filter/tree/once/reload bodies now run, with exact
UTF16 shortcut, locks, nil policy, base allocation, setter order and reparenting.
Sidebar support includes defaults visibility, weak current-font callbacks, list
expansion/count precedence/Smallcaps/publication and precise marked exceptions.
Document URL change runs real local initialization; owned integration exercises
actual allocator/parser/finalizer/sidebar/filter/queue/current-manager graph.

167additive independent cases; no inherited test changed. Root red40fail, later
source review repairs void dispatch and nil singleton append. Initial full runs
failed README length and skipped missing GetGo paths; corrected to199lines and
restored exact retained fixture links without changing harness/tests or fonts.
Final plain7033pass/3archive skips; normal6957pass/79existing skips, all54main-
relative modules86.46–100%combined; dynamic/document100%. Scoped lint/diff pass.
Exact commands/exit receipts: external dynamic-sidebar-20261102/run_full.py and
run_quality.py, full-source-final/command.json and normal-quality-final/command.json.
Root direct spec/quality review and223Q/91sidebar/8document input-pin accounting
retained. Genuine archives and matching companions/ordinary qualification follow.

Actual default data/predicates/defaults/queues/native file observers, Foundation
copy/weak/array/once ABI and GSFont fontType adaptation remain separate. D30held;
no native app/framework/MCP/generated/reference/site/owner/canonical action.
Full original four-font/scripts/dialog/Aidus/migration/promotion scope stays open.


## Actual Chinese/Hangul generation candidate

Implemented real ten-job Chinese generation with explicit lawful bank inputs,
source-derived formatter and full queued Hangul component linking. Replaced
manager callback delegation with actual algorithms; retained source-order
barriers, current lookups, capturedmaps and component/cache/lock preservation.
80additiveownedtests;6866plain/3archive skips and unchanged6790/79gate pass,
all50modules86.46–100% and all4newmodules100%. Every inheritedassert remains;
only obsolete fixturecallbacks were replaced by explicit4bank inputs. Archive
qualification follows independently in WORK.md; native
and actualprivate/defaultresource acceptance remain open.


## Local-manager pipeline candidate

Added source-derived local construction/reload, separate base scanner/ordered
commits and sidebar item/group/rank/resource/filter/icon control paths. Owned
providers make missing platform/data capabilities explicit. Full source6,786pass/3archive skips; unchanged normal6710/79gate, all46changed
production modules86.46–100%.113new owned tests and one source-corrected historical
missing-method oracle; original assertion retained externally. Artifact
qualification follows independently in WORK.md; complete native and
original-workflow compatibility is not claimed.


## Shared allocation and plain-init receiver identity — 2026-11-02

Shared lookup now uses the fixed GSGlyphsInfo allocator under one monitor;
plain init has a separate once guard and retains its first allocated receiver.
Both use the process-global pointer rather than subtype cache slots. Direct
constructor/new/init dispatch and cached receiver preservation stay distinct.
A controlled two-thread test checks single allocation; invalid Python init
receivers fail before changing global state. Fifteen independent new cases
exercise these paths; inherited assertions are unchanged. This qualifies the
Python graph identity boundary, not complete native once-token/resource behavior.

Full plain source:6673passed/3existing fresh-archive skips. The unchanged source
quality gate passes6597/79existing skips; all38main-relative production modules
exceed80%(86.46–100%); manager100%,newhelper96.43%. Source-local only until reviewed
commit/push/artifacts. Scoped correctness/format/whitespace checks pass.
All failed attempts remain in adjacent singleton-correction/. The initial fixed-
class inference was too broad for direct init; primary-source review corrected
that oracle before acceptance. A fixture-layout repair restores145source cases.

Two static audits additionally resolve omitted typed NSException handlers,
constructor unwind without final drain, parser/non-atomic commit/error-slot rules,
current-row callback/interleaving behavior, sidebar grouping/predicate recovery,
cache/rank/filter/image semantics and lawful-resource limits. Static oracles are
not executable pipeline acceptance. Complete local/sidebar/resource initialization,
concurrency/native/original workflows, matching artifacts and promotion remain open.
Private retained resources were not copied into runtime/package inputs.


## Include the description guide in the source archive — 2026-11-02

Fresh genuine0d75e95archives expose a broken relative README link: the source
manifest omitted the existing docs/glyph-descriptions.md. Add that exact authored
guide to the sdist inclusion list. The original8pass/1fail artifact receipt and
archives remain retained; rebuilt matching archive verification follows under
the next genuine source commit. Runtime/test bytes unchanged.


## Parent-aware source and versioned wrappers: full gates pass — 2026-11-02

Complete plain source6658pass/3fresh-archive skips95.33s; unchanged normal gate
6581pass/80existing coverage skips74.02s. All37changed production modules meet
80%combined coverage (86.46–100%),baseline94d4226. Plain run covers77trace cases.
Root verifies156source/doc/config hashes unchanged across both executions.

Separate exact Glyphs2/3/4 wrappers now reach both host adapter routes, preserving
signature, integer formatting/type tests, font dispatch and overrides. Public and
retained source hashes agree. Typed dependency/nil-recipe defects repaired with
real reds; owned parsed XML fixtures retain lifecycle/Unicode/geometry/rollback
assertions. Source-correct raw/shallow/frozen and missing/outline boundaries have
preserved preimages/rulings. Public group/physical recipe gaps remain explicit.

Default Ruff146findings disclosed; scoped checks/format/whitespace pass. This is
source acceptance, not matching archives, ordinary consumers, native, canonical
promotion or publication. Full local init/reload/resources/original workflows
remain. D35resolved; D16/D29/D30/D31unchanged. Exact external H reports/logs:
full-source-final-review/,normal-quality-final-review/,wrapper-version-contract/,
wrapper-profile-implementation/,metadata-oracle-repair/,root-integration-review.json.


## Storage-restored source verification and owned lifecycle fixtures — 2026-11-02

Fresh isolated Python3.11.17arm64 verifies6genuine retained wheel hashes/versions,
40dependency pins and normal dependency check. Current BSD-hidden source passes
542selected tests. Broader controls reproduce25failures before scoped owned parser/
document-manager fixtures;55original function assertion ASTs and parameter matrices
remain unchanged. Final760pass10.07s;16whole measured modules89.47–100%,0excluded
lines. Real-public group/recipe refusals and before-write state/membership controls
remain: public refresh/resource capability gaps are not repaired by owned tests.
Nil recipe stays None; actual finalization of a missing-child token establishes[].
Exact preimages/commands/exits/coverage/reviewer reconciliation: external Issue123
parent-aware-info-20261102/known-fixture-repair/. Scoped Ruff/format/whitespace pass;
8inherited default lint findings retained. Full source/every-changed80%gate,
archives/consumers/native remain pending; candidate stays uncommitted. D35resolved,
D16/D29/D30/D31unchanged. Historical source/artifact cohorts are not requalified.


## Stored descriptions and selected-record propagation — 2026-11-02

Added GSGlyphInfo.desc from the actual selected record's nullable stored
`description` text. Global name/alias/Unicode, suffix, compound/nested/Indic donor
and existing model snapshot paths preserve that field. Synthesized records start
with nil description. Unknown external metadata sources refuse explicitly;
assignment remains read-only. No Unicode-name fallback or private dataset is used.

All 22 new checks fail against the unchanged parent and pass on current source.
Every public name and combined Unicode lookup matches its independent selected
input description: 74,247 name + 72,131 Unicode queries, with all four dependency
dictionaries unchanged. All three authored guide blocks pass through actual
session exports. Full source: 6,060 passed / three fresh-archive skips (73.68 s).
Pinned Ruff and whitespace checks pass; no dependency changed.

An initial full-suite attempt failed on test-fixture ENOSPC. Exact closed-scratch
recovery allowed the complete retry; failed attempts and fixtures remain archived.
The invalid first unparented GSGlyph.glyphInfo test fixture was corrected against
the actual wrapper; that missing parent-aware front door stays an explicit open
requirement. The owned HTML reader is a desc API control, not original-script
acceptance. Genuine matching archives, Echopy provenance, ordinary consumers,
native/original workflows, canonical promotion and publication remain separate.


## Compound source candidate — 2026-11-02

Added ordered raw Unicode-name decoding and initial compound metadata phases.
141new owned checks pass, including60decoder controls. The whole source suite
passes5849with3fresh-distribution skips. New-module combined focused coverage is
85.19–100%, with no exclusions. The full1580-input probe returns1114unqualified
values and466explicit positional gaps without unexpected exceptions or source
dictionary changes. Full factory field/state oracles, source quality gates, fresh
archives, Echopy provenance, installed consumers and native/original workflows
remain pending. This is an isolated uncommitted candidate, not a release.

## Production checkpoint review repairs — 2026-11-02

Direct checkpoint review found consumed suffix-token reclassification and a
missing encoded-font-base predicate. Native source-backed regressions first
fail12with1eligible-base control passing. The repair uses only remaining tokens,
keeps generic cap separate from global terminal-cap context, skips unencoded font
bases, and retains the existing raw snapshot contract while explicit metadata refresh
uses the corrected resolver. The13new cases and legacy/resolver controls pass125
focused checks. An attempted constructor-case override was rejected by the legacy
raw-snapshot regression and removed; the model test explicitly refreshes metadata.
Earlier failed attempts and the interim376pass state remain retained.

An inherited test asserted local overlay selection after explicitly clearing
base Unicode. Its original stored-metadata assertion is retained in an encoded
control; the new unencoded control checks global fallback and complete base
preservation. Exact preimage/reason and failed/passing commands live under
production-checkpoint-20261102/repair-evidence/ in the external issue123 tree.
Sealed earlier source/artifact tuples stay unchanged; they do not qualify these
new corrections. Echopy shims are regenerated through the CLI after the producing
class changes. Corrected full source passes5711/0skips; the unchanged quality
gate passes5635/76trace skips and all7changed modules95.23–100%combined coverage.
All trace cases pass plain; no new exclusions. Fresh dirty source wheel/sdist
contain the restored constructor. Ordinary corrected/genuine committed-artifact
qualification remains pending. Exact commands/exits:WORK.md and the external
production-checkpoint-20261102/repair-evidence/ records. Native D30 and all original/full1,580factory,
custom/local/resource/version/glyph/application requirements remain open.

This is an isolated reviewed source checkpoint candidate. D11authorizes source
commit/push after applicable gates; current main/canonical installs, generated
source-lock/site, native calls, release/tag and publication remain untouched.
Exact source checkpoint hashes, pre-push command exits and further artifact
results belong in the external production-checkpoint report; no passing claim
is made here for an unrun command or a later committed distribution.

## Stored production source acceptance — 2026-11-01

The isolated successor at parent77c936ae9 passes5,697plain tests with no skips;
full branch coverage passes5,621with76trace-guard skips, all passing in the plain
run. Whole-module combined coverage: glyph_info95.69%, glyph_metadata96.18%,
unicode_case97.96%, production_metadata95.24%; no line/branch exclusions.
Preserves raw None/empty/explicit/equal text, exact/alias shared fill, raw Unicode,
uni/u copies, represented generic/canonical suffixes and model copy boundaries.
Helper length decisions match retained NSString UTF16 units including surrogates.
Independent public XML checks cover84,701ordered names and72,131Unicode keys;
the adapter preserves all public dictionaries. The49inference differences retain
raw nil. The authored guide executes. Two pre-existing lint findings remain;
new test/import style issues were corrected, and diff/format checks pass.

Commands (rtk proxy) and exits: production-info-20261101/evidence/
plain-source-final-command.json (0), coverage-source-final-command.json (0),
coverage-json-command.json (0), guide-command.json (0); qualified-build/
commands.json (all0). New helper UTF16 regressions first fail4/43controls, then
pass47; baseline name-index checks fail4; initial15production routes fail before
implementation. Full failure/interrupt/lint histories and preimages are retained.
Standard source and complete412file sdist builds reproduce identical wheels.
After this documentation-only update, final packaging/archive recheck results
are recorded in production-info-20261101/REPORT.md and receipt.json.

Wait, but: these are bounded source checks. Of26,985old production-alias queries,
25,405reach represented routes and1,580remain required unqualified factory work.
Complex/ligature/custom/local/resource behavior, glyph production writes and
application conversion, refreshed Echopy/ordinary installs/consumer qualification,
native workflows and full original acceptance remain open. No source commit/push,
main/canonical promotion, live install, generated docs/build, release or native call.
Prior parent artifact/consumer evidence remains valid only for that parent tuple.

## Stored production and name-index source candidate — 2026-11-01

Adds read-only GSGlyphInfo.productionName backed by nullable stored metadata,
shared exact-name nil fill and detached copy semantics. Keeps direct Unicode,
uni/u-name copies, bare characters, generic suffix output and model copy branches
separate. The manager helper does not overwrite raw explicit production. Name
index construction now follows retained parser order and alias exclusions.
Public data remains unchanged; unsupported constructed metadata refuses the new
getter. Complex name/custom/local/resource, glyph writes/application conversion,
ordinary artifact/native and full original workflow acceptance remain open.
Owned regressions and exact commands are retained in production-info-20261101/;
this entry does not claim an unrun gate or native equivalence.


## Cumulative source checkpoint — 2026-11-01

Reviewed ordered custom parameters, typed Arabic-presentation settings, separate
legacy metadata/ROS refusal and global combined-index Unicode lookup together.
All six changed runtime modules pass80%combined coverage (95.23–100%, no
exclusions); full coverage5529pass/76trace-guard skips, earlier plain5605pass.
Retained wheel/sdist and exact installed-consumer evidence remains snapshot
specific. Native history/save/reopen, canonical promotion and release stay open.


## Combined Unicode index source correction — 2026-11-01

Corrected shared metadata resolution and global Unicode snapshots to index each
public record's primary and legacy encodings in record order, with last-write
precedence. The retained base parser inserts both into the same dictionary;
earlier primary-only assertions were wrong. FE8D/FE80 now select Arabic isolated
records, and duplicate legacy 0000 selects NULL. Legacy lookup preserves separate
stored encoding fields, metadata and independent component snapshots. Public
dependency data stays unchanged; standard bounded memoization follows its identity.

Added an independent pinned raw-XML oracle for all 72,131 public keys, collision,
identity replacement, exact spelling, dependency, snapshot and preservation tests.
Corrected the prior no-legacy assertion, expanded synthetic-only doubles to the
complete data boundary and retained the detached Arabic refusal. Current guides
and examples now describe the source-supported index. Historical release notes
and sealed artifact evidence remain intact. Fresh ordinary artifacts, consumers,
central docs and native workflows remain separate pending gates; no production
getter, arbitrary custom-manager support, native call or publication is added.

## Global Unicode lookup and wrapper dispatch — 2026-11-01

The application now exposes glyphInfoForUnicode(String,font=None), using exact
integer percent formatting and global primary-index lookup before synthesis.
Integer glyphInfoForName dispatch occurs before font handling and retains method
overrides. Global lookups never enter font-local ROS/presentation/stored overlays;
explicit font-local Unicode managers remain unsupported.

Audited synthesis preserves uppercase spelling in names/encodings, the UTF16
minimum and encoding-length gates, additive32bit nibble wrapping, minus/space
handling, signed naming/range checks and historical Han/PUA classification. Hex
surrogate text is accepted; malformed actual UTF16 refuses the unsafe native
NULL-pointer path. Arbitrary bridge types remain explicit unsupported inputs.
The parser is custom because Python int() cannot represent this audited native
contract. Maintained records/components and legacy separation remain unchanged.

New owned examples and source regressions cover these paths. This is a private
source/artifact candidate, not native execution or proprietary database identity.
Native workflows, local/custom managers, remaining metadata fields and a fresh
consumer/Echopy/central-doc integration remain open.

## Public legacy snapshots and ROS data boundary — 2026-11-01

GSGlyphInfo.unicodeLegacy now preserves exact maintained legacy encodings,
separately from primary Unicode, in the package's read-only snapshots. Real
GSGlyph construction resolves only the new field and preserves existing snapshot
fields; nil resolution is handled explicitly. Global lookup ignores the active
font. Native setters and the public Unicode lookup gap remain separate.

ROS processing now recognizes the audited shared manager's exact text syntax and
refuses the five shipped proprietary maps before presentation or metadata writes.
Malformed/unknown text remains a shared-bundle no-op; nontext values explicitly
refuse pending Objective-C description qualification. No proprietary maps ship.
Authored examples and source regressions cover the new boundaries; native
history, persistence, custom managers and full ROS replacement remain open.

## Arabic presentation setting and typed values — 2026-11-01

The exact spaced setting now converts Python scalar values under its audited
bool schema. macOS strings use real Foundation integer/decimal parsing, current
locale, float32 rounding and the nonzero failed-parse sentinel; numeric precision
is preserved and typed object None becomes False. Active-value lookup validates
all active duplicates while structural operations can recover inactive imported
unsupported values. NaN no longer causes a false mirror-conflict refusal.

Maintained unicodeLegacy reaches the private resolver. Generic suffixes clear
inherited legacy; the Arabic stage uses resolved script/canonical name and direct
or raw .isol legacy before stored overlays. It retains empty-vs-nil precedence,
ordered deduplication and refresh/reset behaviour. New authored examples cover
activation, duplicate selection, typed values and stored-script ordering.

Non-macOS strings, arbitrary object conversion, ROS/custom-manager combination,
native collision handling, full original workflows and native persistence/history
remain open. The public GSGlyphInfo.unicodeLegacy facade is still separate work.
No native application, preferences, live install or release was changed.

## Ordered custom parameters verified offline — 2026-11-01

Ordered lib records preserve duplicate names, active flags and stable live
objects. Effective lookup selects the first active value; membership and keyed
assignment/removal use the first matching object. Indexed replacement/removal
detaches old objects, iteration retains its initial count and missing-name
deletion is a no-op. Copies own their nested values and retain the parent pointer.
Legacy flat keys migrate without losing unrelated lib values; new external keys
are imported and conflicting mirror edits refuse before writing. Master userData
is separated from reserved parameter storage. A legacy rename/reuse identity
collision has a retained regression and repair.

The full source suite passes5283with7skips; all7skipped cases also pass in targeted
runs with their optional dependency and owned import fixture supplied. Source coverage
passes5210with80tracer/fixture skips and95.07%combined coverage for proxies.py.
Fresh ordinary wheel/sdist each pass113selected checks and the authored guide;
all9distribution checks pass, including payload/source identity, privacy, metadata
and sdist links. Packaged drivers now take corpus/wrapper paths from configuration
instead of embedding private paths; the App floor remains0.2.26.dev150. This does
not qualify native history/save/reopen, typed parameter schema validation, nested
container notification, repeated/cross-owner insertion or Arabic presentation
postprocessing. No canonical installation, release or native call changed.

## Additional-Unicode resolver verified offline — 2026-11-01

Implemented the audited additional-Unicode stage before stored overlays, using
staged name/codes and prior effective case/script. Preserves ownership gates,
Greek sentinels, dotless-I ordering/deduplication, PUA lists, keep-name bypass,
parentless Arabic behavior, legacy-only .isol no-op, reset metadata-only behavior
and rename-then-refresh caller sequencing. Shared records remain immutable.
The 22-case installed reproduction now has zero gaps, previously eight.

The bundled public Unicode17 scalar map matches actual macOS27.2 NSString and
independent CoreFoundation results for all 1,112,064 valid scalars; Python3.11
Unicode14 differs on55. Public inputs, hashes, licence and the measured version
boundary are retained. No runtime Cocoa/ICU dependency was added. A first UTF8
calibration incorrectly consumed BOM; that attempt is retained separately and
was replaced by UTF16 character construction with an explicit FEFF control.

Full source and root coverage runs each pass4,331 with3existing archive skips.
Across the two changed production modules,161/165statements and80/86branches
are covered (97.6%/93.0%), exceeding the workspace80%threshold. Fresh wheel/sdist
each pass586selected checks;119runtime/data files match source/archive/installs.
The previous wheel fails152of183new cases;31controls pass. Both fresh installed
casing functions match all1,112,064 measured scalar results. Twelve authored
guide examples pass in each install and20Python blocks compile.

The six-wheel consumer tuple has664byte-matched installed files, unchanged
versions and third-party pins, and clean pinned consumer checkouts. Examples
passes2,436; Scriptmix passes4,404 with the same56failure identities and6skips.
Only glyph_metadata.py, unicode_case.py and the public JSON data changed in the
runtime tuple. All seven read-only generated-doc fixture hashes still match.

Receipts under verification/issue-123: glyph-additional-unicode-20261101.json,
glyph-additional-unicode-artifacts-20261101.json,
docs-additional-unicode-20261101.json and cohort-additional-unicode-20261101.json.
Remaining: native Undo/Redo/persistence and complete original-script workflows;
ROS and Arabic presentation settings; full custom-manager/name/suffix/group/
direction/production/default-anchor behavior. Current casing evidence does not
qualify all Foundation versions. D16/D27/D29/D30/D31 remain unchanged; the broad
goal is active and incomplete. No original scripts or owner fonts were executed.

Exact external commands/exits: glyph-additional-unicode-20261101/
child-implementation/commands.json and coverage-commands.json (final exit0);
glyph-additional-unicode-artifacts-20261101/artifact-commands.json and
scalar-guide-commands.json (all exit0), negative-command.json (expected exit1),
contract-repro-command.json (exit0); cohort-additional-unicode-20261101/
commands.json (Scriptmix expected exit1, dependencies/Examples exit0).
Read-only diff/byte/hash/origin/comparison checks passed. The first copied
contract repro retained an old-wheel origin pin and failed before cases ran;
that failure is retained, and the corrected pin asserts the fresh installed
origin. CodeGraph was attempted first, yielded no output, and its task-owned
process/wrapper were stopped (terminal143); direct caller search was retained.
No native calls, canonical edits, commits/pushes, source-lock refresh, generated
build, browser/publication or obsolete-repository retirement occurred.

The final documentation update found a concurrent owner compression of AGENTS.md
to rules-only guidance after PLAN/TODO updates. It stopped at the missing old
heading, then resumed from the freshly read rules file, preserving that change.
Only a casing-evidence rule was added there; progress stays in WORK/CHANGELOG.

## Shared metadata resolver verified offline — 2026-11-01

Shared case/script/category/subCategory resolution now covers ordered Unicode
metadata and audited synthesis, keep-name categories, independent stored fields,
rename/reset/refresh differences, basic suffix fields, copy/append and full PUA
encoding preservation. Source: 4,147 passed, three retained archive skips.
Fresh wheel and sdist each pass 398 selected checks; 117 runtime files match.
The prior wheel fails 90 of 94 new cases. Eleven authored examples pass in both
installs; nineteen Python blocks compile. No generated build or publication.

The new six-wheel consumer tuple has 662 byte-matched installed files and
unchanged distribution versions. Examples passes 2,436; Scriptmix passes 4,404
with the same 56 failure identities and six skips. Only five Glyport runtime
files differ. Consumer checkouts remain clean at the prior pinned heads.
Receipts: verification/issue-123/glyph-metadata-resolver-20261101.json,
glyph-metadata-artifacts-20261101.json, docs-glyph-metadata-20261101.json and
cohort-glyph-metadata-20261101.json in the same directory.

Remaining: native history/persistence and complete caller workflows; full custom
manager/name/base/suffix/language behavior; complex small-cap name/production
mapping; ROS, Arabic and additional-Unicode postprocessing; group/direction and
other missing metadata. Detached/missing-record resets still refuse. Keep
D16/D27/D29/D30/D31 unchanged. This does not complete the broad goal.

Exact commands and exit codes are retained externally in
`glyph-metadata-resolver-20261101/results.json` (final source/focused exit0),
`glyph-metadata-artifacts-20261101/artifact-commands.json` (all exit0),
`negative-command.json` (expected exit1), `docs-glyph-metadata-20261101/commands.json`
(both exit0), and `cohort-glyph-metadata-20261101/commands.json` (Scriptmix expected
exit1; dependency and Examples checks exit0). Commands use rtk proxy and isolated
Python environments. Root audits/compare exited0; retained intermediate failures
are detailed in the source report. No native requests, canonical promotion,
commits, pushes, source-lock refresh or obsolete-repository retirement occurred.

## Glyph classification and shared resolver gaps reproduced — 2026-11-01

Original callers require both category/subcategory setters and independent storage
flags on drafts and attached glyphs. Installed owned probes reproduce missing
members and read-time Unicode recategorization. AST inventory records61actual
assignments across2,329files, with100parse/encoding failures retained explicitly;
UI/mocks are not counted as native behavior. Root baseline153checks pass, proving
that the old suite did not cover these missing contracts.

Following reset setters into glyphInfoForGlyph found a broader problem in the
existing case/script implementation: Unicode resolution precedes name lookup.
Root independently reproduced4conflicting-name/Unicode resets; the agent retained
matching-name/unencoded controls and independent stored-overlay controls. Static
expectations are not native observations. The keep-name early return uses Icon
and SF-Symbol; synthesis, font-local suffix/base and stored overlays matter too.
The addendum corrects the earlier unknown-name/0031 example: the full resolver
would find Unicode metadata, so this is not a genuine missing-record case.

Evidence, source/caller/binary hashes, commands and installed origins:
verification/issue-123/glyph-classification-contract-20261101.json. Root baseline
and installed repro commands exited0. No originals or retained native binary were
executed. All recorded input hashes verify; no candidate runtime bytes changed.

Authored guide and candidate compatibility notes now disclose the counterexamples
without changing historical artifact hashes. Both existing installs still pass
10offline examples;18Python blocks compile. Receipt:
verification/issue-123/docs-classification-limits-20261101.json. These examples
do not cover the new counterexamples. No generated rebuild or publication.

Next repair shared resolution and all four metadata lifecycles together; adding
two name-only setters would reproduce the defect. Native history/reopen, custom
managers and D16/D27/D29/D30/D31 remain open. The broad goal is not complete.

## Glyph script consumer tuple verified — 2026-11-01

Only three Glyport runtime files differ from the prior tuple. All661 installed
files match the six wheels;40third-party pins and46distribution versions remain
unchanged. Disposable consumer heads and working trees are unchanged/clean.
Examples passes2,436checks; Scriptmix passes4,404 with identical56failure
identities and6skips. Existing failures are not waived.

The first Examples run failed10checks because this new evidence directory lacked
the prior read-only generated-docs fixture. Initial JUnit/log/commands remain.
Linking the identical existing target fixed setup; Examples alone was rerun.
No generated reference was rebuilt or changed. Source and fixture hashes, exact
commands and exit codes are in verification/issue-123/cohort-glyph-script-20261101.json.
run.py exited1 after Examples setup failure; resume-examples.py and compare.py
exited0. Scriptmix's expected test exit remains1; both final Examples runs exit0.

No native calls, canonical changes or promotion. D16/D27/D29/D30/D31 and native,
custom-manager, detached-reset and full original-workflow acceptance stay open.

## Glyph script lifecycle source, artifacts and guide verified — 2026-11-01

Named metadata supplies script defaults, including unencoded names. Explicit
None/empty/string values, temporary assignments, storage transitions, rename,
refresh, copy and unique attachment share existing case/lib state and recovery.
The round17 fixture now uses the Gurmukhi glyph name; upstream setUnicodes does
not replace script metadata. Previous failed expectations remain in the logs.

Source suite:4,053passes/3archive skips; regression-first suite35fails/10passes.
Root independently passed141focused checks before the final parameter expansion.
Fresh wheel/sdist each pass304checks with0skips, including all70script cases and
all3distribution checks. All116runtime files match source/archives/both installs;
28distribution versions match. Prior wheel fails56new cases and passes14controls.
Both installs run10authored offline examples;18Python blocks compile. The prior
wheel fails the new example. Earlier artifact hashes in the guide stay intact.

Exact commands, environment, exits, preimages, source/archive hashes and JUnit:
verification/issue-123/glyph-script-lifecycle-20261101.json,
verification/issue-123/glyph-script-artifacts-20261101.json and
verification/issue-123/docs-glyph-script-lifecycle-20261101.json.
Commands: rtk proxy /opt/homebrew/bin/python3.11 followed by the external
artifacts-run.py, artifact-installs.py and audit.py each exited0. Installed
example check.py exited0 twice; old-artifact pytest and example controls exited1.
Read-only candidate/docs git diff --check exited0. Scoped lint passes;2inherited
E731 remain. The red run's outer tail masked its status; retained JUnit proves
35failures. No dependency changes, native calls, canonical edits or promotion.

New consumer qualification is next. D16/D27/D29/D30/D31 and native history,
save/reopen, backend atomicity, detached reset/custom managers remain open.

## Glyph-case artifacts and authored examples verified — 2026-11-01

Fresh wheel and sdist installs each pass 219 selected tests with zero skips,
including the three distribution gates. Same-process module origins remain in
the selected install; all 116 runtime files match source/archives/both installs.
Both environments have the same 28 distribution versions and pass dependency
checks. The earlier case-info-only artifact fails 52 lifecycle tests (3 controls
pass). Bounded independent source review found no implementation findings.

The authored Glyport guide adds an owned lifecycle example, preserves earlier
archive hashes and identifies the new ones separately. Each fresh install runs
all nine offline examples; all 17 Python blocks compile. The preceding artifact
fails the new example. Native snippets remain compile-only. Exact commands,
exit codes, archive/source hashes, failed controls and reports are retained in
verification/issue-123/glyph-case-artifacts-20261101.json and
verification/issue-123/docs-glyph-case-lifecycle-20261101.json. Diff check passes.

No native run, canonical promotion, generated rebuild or publication. Native
case/history/reopen, detached reset, custom metadata and the new consumer cohort
remain open; D16/D27/D29/D30/D31 are unchanged.

## Glyph case lifecycle source repair — 2026-11-01

Implemented database case defaults and explicit temporary/stored case values,
with rename/refresh, detached copying and unique attachment handling. Detached
reset refuses explicitly. Existing backend lib writes and history scopes remain
in use; failed metadata writes retain rollback failures rather than hiding them.

The first full run found nine failures. One native test double now includes its
real glyph-lib field; untouched Unicode-only workflows remain usable without
forcing a metadata lookup. The corrected full source suite passes 3,983 tests
with three archive checks skipped. Root independently passes 103 focused checks;
the owned offline documentation example and diff check pass. Native, fresh
wheel/sdist and complete original-script workflows remain unverified.

Evidence: external issue123/glyph-case-contract-20261101. Exact commands, failed
runs, source preimages, contract locations and JUnit are retained there. Root
receipt: verification/issue-123/glyph-case-lifecycle-20261101.json.

## Glyph Info case verified in installed artifacts — 2026-11-01

Fresh wheel/sdist installs each pass119selected checks, zero errors/failures/skips,
including all3archive gates. Same-process installed origins are checked before
and after tests. All116runtime files match source, archives and both installs;
changed tests and compatibility docs match sdist bytes. Twenty-six direct checks
pass outside the source tree. The prior script-only artifact fails all20new case
tests as expected; same-version archives retain distinct hashes.

Dependency checks pass; bounded read-only source review found no issues. Exact
commands, hashes, origins, JUnit and limits are retained in
verification/issue-123/glyph-info-case-artifacts-20261101.json. No live installs,
native runs, generated refresh, publication or canonical promotion. Native/full
kerning workflows, custom metadata and GSGlyph.case remain separate and open.

## Glyph Info case metadata implemented and source-tested — 2026-11-01

GSGlyphInfo.case snapshots supplied metadata. Global lookup maps database case
labels to integer enums, preserves missing-case zero and refuses unknown labels.
Twenty new cases failed before the repair;44targeted checks now pass, including
punctuation/mark/ligature values, aliases, all enum labels, snapshot immutability
and active-font independence. Six expectations also match retained native-manager
observations. No Unicode inference is added to the database route.

Full source suite:3928passed,3archive skips. Post-format44checks, scoped Ruff and
diff check pass. Constructor fixture now supplies the real case field. Exact
commands, exit codes, hashes and evidence limits are recorded in
verification/issue-123/glyph-info-case-20261101.json. Changes remain uncommitted
in the isolated candidate. Previous artifacts lack this field; fresh wheel/sdist
and installed native acceptance remain open. GSGlyph.case, custom/synthesized
metadata and complete kerning workflows remain separate. D29/D30 unchanged.

## Glyph Info script field implemented and source-tested — 2026-11-01

GSGlyphInfo.script now snapshots supplied metadata; database records forward
script directly. None/empty values remain unchanged, writes are refused, and
active-font script overrides do not replace the global lookup. No Unicode-based
inference was added. This supplies a field read by preserved kerning/text scripts;
it does not qualify those scripts' entire workflows.

Fourteen added cases first failed. Six scalar expectations match retained Glyphs4
native-manager observations; Greek/Cyrillic database, alias, snapshot/read-only
and current-font independence controls also pass. Full suite initially found one
incomplete dependency double (missing script); that fixture now matches real
record fields and checks component scripts. Failure retained. Final3908pass,
3archive skips;42targeted checks, Ruff and diff checks pass.

Exact commands, exit codes, failed logs, JUnit, source/caller hashes and evidence
limits: verification/issue-123/glyph-info-script-20261101.json. Candidate remains
uncommitted; older artifacts lack the new field. Fresh artifacts, custom databases,
full metadata and native/promotion acceptance remain open. No original execution,
live installs or native calls. D29/D30 unchanged.

## Glyph Info default lookup repaired in source — 2026-11-01

Glyphs.glyphInfoForName(name, font=None) now queries the global fallback without
reading the active font. Non-None local-data requests fail explicitly with
Glyphs.glyphInfoForName.localData; font outlines/metadata no longer masquerade as
a Glyph Info database. This restores the default query needed by Unicode-reset
scripts; the original scripts were inspected only, never executed.

Seven contract checks failed before implementation. Full source suite now passes
3894tests with3archive skips; after test-only formatting33affected checks pass.
Targeted Ruff passes. Root inspected the complete source/test diff. Exact commands,
exit codes, source hashes, JUnit and failed attempts are retained in workspace
verification/issue-123/glyph-info-global-20261101.json and its external directory.

This is an uncommitted isolated source repair. Previous wheels/sdists lack the
change. Custom-global and font-local data, synthesized names, miss semantics,
full records, installed artifacts and native/promotion acceptance remain open.
No live installs, native calls, original-script edits or completion claims.

## Glyph Info lookup limitations — 2026-11-01

The current `Glyphs.glyphInfoForName(name)` adapter reads the active font first
and falls back to glyphsLib. It does not implement the documented optional `font`
argument or global-by-default lookup. A glyph's font metadata and outlines are
not the application's global or document-local Glyph Info database.

An offline comparison with eleven retained Glyphs 4 native-manager cases matched
four represented fields (name, first Unicode, category and subcategory) in six
cases. Glyport refused `A.ss01`, `_corner.test`, `_part.test`, the empty name and
an unknown ordinary name. The retained upstream manager synthesized the first
three and returned nil for the last two. These observations do not establish
Python-wrapper behavior in every supported Glyphs version.

`GSGlyphInfo` still lacks production, script, anchors, case, direction and
other native metadata. Six matching subsets do not establish complete records.
Custom global/document-local data overrides and synthesis need a coherent lookup
contract; a direct glyphsLib production-name call does not supply that contract.
Missing dependencies must remain distinguishable from genuine database misses.
No runtime behavior was changed by this audit.

## Glyport auxiliary names repaired in source — 2026-11-01

GSLayer.name now preserves None/empty foreground auxiliary names instead of
substituting the associated master. Layer metadata types admit None. Nine added
cases cover backend/proxy reads, identity, copies, unchanged master names and
absent-background behavior. Four initial failures and three intermediate
background regressions are retained; final full source suite:3888passed,3archive
checks skipped. Ruff has only the same two pre-existing E731 findings in the
three checked files. No dependency changes.

Isolated uncommitted candidate: auxiliary-names-20261101/fontlab-glyport,
branch issue-123-auxiliary-names-20261101, base753b555. Exact commands, logs and
hashes: verification/issue-123/glyport-auxiliary-names-20261101.json and its external
evidence directory. Native import conversion, installed artifacts, deletion and
Undo/Redo/reopen remain unverified; no canonical edits/install or native calls.

## 2026-11-01 — preserve repeated objects during transform preflight

Root comparison found first preflight candidate2427929 changes repeated draft
objects only once rather than once per occurrence. Four new controls fail on
that retained wheel. Preflight now accumulates virtual per-object point/component
values in occurrence order before any writes, and preserves original write order.
Cached live proxies and identical draft objects retain identity; distinct wrappers
sharing external storage remain outside this proof.

Final177focused checks and3879full-source tests pass; three archive checks await
fresh final artifacts. Both edited modules stay above80%combined coverage with
zero exclusions. Independent review approved this correction. The earlier
candidate and its artifacts are superseded, retained as failed evidence.
Exact full command/exit: external command-final.json/full-final.log; old-wheel
regressions: alias-red-old-wheel.log. Native conversion and setter failures still
are not transactional. No native calls, canonical promotion or push.

## 2026-11-01 — preflight Python-managed transform results

Path, detached-layer and selection-aware transforms calculate all mapped points
and detached component drafts before entering history or writing geometry.
Reuse shared affine apply/concat, retaining transform order and point-before-
component writes. Native whole-layer transform and setter failures remain
separate; this is arithmetic preflight, not transactional native mutation.

Seven regressions failed first: late point/anchor/component overflow changed
previous items or entered history. They pass after precomputation, along with
an additional finite combined-matrix/rotated-component control. Full source
suite3875passed3skipped (archive tests await fresh builds), exit0; both edited
modules exceed80%combined branch/statement coverage with zero exclusions.
Independent scoped review approved. Copies/new tests Ruff passes; pre-existing
proxy E731 findings are unchanged. No native calls, canonical edits or push.

Exact command/exit and coverage are retained externally under
issue123/transform-overflow-20261101/command.json, full.log, coverage.json;
red.log retains all seven pre-fix failures. Source tests run the current-cohort
Python3.11 environment with pythonpath=src and explicit pytest_cov plugin.

## 2026-11-01 — finite transform inputs before mutation

Live/detached layers, paths and the selection-aware layer transform reject
non-finite coefficients before backend calls, history or geometry mutation.
Use math.isfinite at the four public boundaries; finite zero/negative scales
retain their behavior. No new dependency. Finite arithmetic overflow and native
transform/payload equivalence remain outside this input fix.

Tests first: initial93cases72failed21passed with backend-entry assertions;
selector extension54failed111passed before its guard. Final165focused passed.
Fixtures include nonempty nodes/anchor/component and all selector flag pairs.
Full suite3867passed3skipped (fresh distribution checks await artifacts), exit0;
combined statement/branch coverage remains above80% on both edited modules,
zero excluded lines. Independent scoped source/test review approved.
Ruff finds two pre-existing E731 lambda assignments in untouched proxy methods;
new test/copies file lint passes. No native requests/canonical edits/push.

Exact full command and exit retained in external
issue123/transform-finite-20261101/command-final.json; full-final.log and
coverage-final.json retain results. Source test command uses current-cohort env,
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONDONTWRITEBYTECODE=1, python -B -m pytest
-o pythonpath=src -p pytest_cov -p no:cacheprovider --cov branches on the two
edited modules. Original Glyphs API contract consulted at
https://docu.glyphsapp.com/#GSLayer.applyTransform; early refusal is an explicit
safety adaptation, not inferred Glyphs equivalence.

## 2026-11-01 — registration failure during owned dispatch

Added two regression cases for first-sync icon failure during an owned menu
callback, with and without closing the host inside that callback. They assert
no signal disconnect/deletion before deferred cleanup, exact callback error
ownership, no observer for failed registration, token/action/cleanup coherence,
repeated failures, later successful registration and observer release on close.
Existing runtime behavior passes; no runtime change or native claim.

Verification against ordinary installed App159/Glyport54 cohort:
- Baseline focused suite35passed; with new cases37passed.
- Full suite3705passed, exit0. Exact command: rtk proxy env
  PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONDONTWRITEBYTECODE=1
  GLYPORT_DISTRIBUTION_DIR="$ISSUE123_SCRATCH/h2/dist-f5affd54"
  "$ISSUE123_SCRATCH/current-cohort-20261101/env/bin/python"
  -I -B -m pytest -o pythonpath= -p no:cacheprovider -q -rs tests.
- rtk proxy /opt/homebrew/bin/ruff check --no-cache tests/test_issue122_t15_host.py:exit0.

Evidence: external issue123/menu-sync-dispatch-20261101/full.log and command.json.
As previously audited,14full-suite cases contain explicit source subprocesses;
no exclusively installed-wheel or native acceptance is claimed.

# Changelog

## 2026-11-12 — install.vfpy matches the App's installer, with Extensions bundle support (Issue 254)

- `install.vfpy` is now byte-identical to `fontlab-fontlabapp/install.vfpy` (pushed in App `5cac0d6`).
  The new code places `[tool.fontlab-install] extensions` bundles; this repository declares none, so
  installs behave as before. `tools/check_install_copies.py` in the App compares the copies by sha256.

## 2026-11-11 — install.vfpy synced to the App WP11A installer (Issue 250)

- `install.vfpy` is now byte-identical to fontlab-fontlabapp 79f7485 (WP11A): it records file hashes in `install.log`, removes only superseded files whose current hash matches the logged hash, keeps edited ones and reports them, refuses entries with `..` or outside the data folder and any unowned entry in the old RECORD, and supports `FONTLAB_INSTALL_DRY_RUN`. Verify with `tools/check_install_copies.py` in the App repository. The native reinstall check is owner-run and stays open in the App TODO.

## 2026-11-10 — Issue 250 documentation round

- AGENTS.md describes the delegation, integration and release workflow.
- WORK.md reset to the current round; the earlier bytes are archived on the owner's workspace data volume, not public.

## 2026-10-23 — H2 source review fixes

- Keep successfully deleted glyphs' retained component originals in package
  history until publication succeeds, preserving independent live batches and
  failed-deletion retry state.
- Recheck scope after preparation callbacks, retaining the successful checkpoint
  while refusing subsequent scalar, COW or layer/mask writes after focus changes.
- Add nine offline regression/preservation controls; final artifacts and native
  package-history/callback qualification remain open.

## 2026-10-23 — Prospective native history scope (source)

- Check App's public history scope against retained and prospective owners before
  native preparation, COW ownership, layer/mask creation, direct tags/marks,
  grouping and final cache/history publication. Font/master/identity operations
  conservatively require the matching current regular Font window.
- Refuse registered glyph and component-scratch creation before capture/builders;
  preserve creation/collection recovery and nested publication retries. Disclose
  queued native updates once per batch without clearing or blocking on the queue.
- Add realistic offline policy controls and explicit native UI/parent/queue
  fixture capabilities. Whole-source, installed-artifact and native qualification
  remain separate controller gates; no native acceptance is claimed.

## 2026-10-23 — Distribution portability and provenance

- Document a portable external scratch folder and explicit configuration-free uv
  source/artifact verification commands; retain the genuine App development floor.

## 2026-10-23 — Genuine App development contract

- Require `fontlab-fontlabapp>=0.2.26.dev150`, matching the audited genuine private
  candidate. Active development/setup instructions use ordinary resolution and
  clear version-fabrication variables. Native, cohort, release and lock refresh
  acceptance remain open; runtime and tracked lock bytes are unchanged.


## 1.2.10 (2026-11-16)

- Use App public menu ownership/dispatch state; remove source process labels.

### 2026-10-22 — Coverage tests for plugins/host

- `tests/test_cov_plugins_host.py` pins the public plugin-host contract (constants, Protocol defaults, subclassing): 100% branch coverage. Tests only.

### 2026-10-22 — Documentation and verification

- Updated dependency prerequisites, arm64 Python selection, module guidance and
  native acceptance goals. Grouped remaining UI work by functional family.
- Recorded full source suite on Python 3.11 arm64: 3627 passed, 6 skipped, exit 0.
  Offline tests do not establish native acceptance.
- Ruff retains 26 findings. Fresh archive and installed FontLab acceptance remain
  open. Test environments need writable external cache and temporary directories.

- Public API and deferred host fixes.
  - The plugin host catches App's `qtsafe.MainWindowNotFound` instead of
    matching "main window not found" text; a plain `RuntimeError` propagates.
  - Filter dialogs queue the button release with App's `_defer(first=True)`
    instead of reordering App's private `_pending`; an `on_close` error goes to
    the sink with the plugin view as owner (as before the menu refactor), not the window.
  - Fix: `register_menu` is atomic. If the first NSMenuItem sync raises, the
    token and QAction are removed before the error re-raises.
  - `_menu` sends every name outside `MENU_TITLES` (including a literal "Edit")
    to this host's own "Glyphs Plugins" menu. Two hosts never share that
    menu (a NUL lookup key skips App's title search; tested with two hosts).
  - The test-only `_Reaper` moved into `tests/test_shared_deferred_batch.py`;
    `_main_window` is gone (tests call `main_window`).
  - `ask_string` comments why it keeps raw values; `ui/session.py` has explicit
    `Callable` types; import order fixed in `ui/application*.py`.
  - Licence: new NOTICE and LICENSE-APACHE-2.0 cover the Apache-2.0
    `ui/session.py`; `license = "MIT AND Apache-2.0"`; both files ship.
  - One App floor, `fontlab-fontlabapp>=0.2.150.dev0`, in pyproject, README and
    DEPENDENCIES. README has one "Shared App mechanics" table instead of the
    repeated candidate paragraphs; DEPENDENCIES has one App section and states
    that the explicit test command, not `uv.lock`, is canonical (no relock).
    COMPATIBILITY.md gains painter/menu host notes.
  - Added eight host checks and four documentation checks.

- Vanilla session: Glyport receives `VanillaSession` from App `vanilla.py` as
  `fontlab_glyport.ui.session`, with its tests and the Vanilla native driver
  (`native-drivers/vanilla_steps.py`, from Fontport). Behaviour is unchanged
  except that the "Install fontlab-glyport" `ModuleNotFoundError` probe is gone:
  Glyport is now the home, so import errors propagate unchanged. The factory
  imports stay inside the constructor; importing the module loads no PythonQt,
  `ui.vanilla` or `ui.cocoa` (tested in a fresh interpreter). Offline only; owned Vanilla window
  open/close/teardown needs NATIVE.

- Menus and dialogs: adopt App's `owned_menus` and `qt_dialogs`. `FontLabPluginHost`
  now subclasses `fontlabapp.qt.menus.OwnedMenus`; the local token table,
  dispatch-depth guard, deferred teardown, owned menu, tool-window class and
  main-window cache are gone. The host keeps the Glyphs menu-name mapping,
  NSMenuItem sync and observers, the Apply/Cancel dialog, painters and file
  formats. `name_filters` comes from `fontlabapp.qt.dialogs` (local copy
  deleted). Fix: the host relabels only App's "main window not found" error as
  `HostUnavailable`; the off-GUI-thread refusal now propagates unchanged.
  Filter-dialog error-sink owner is now the tool window, not the view. `ask_string`
  stays on `run_owned_dialog` (App's `run_text_dialog` applies `str()` and would
  change raw values that `test_glyphs_dialog_execution` pins). Offline only;
  plugin menu, filter dialog Apply/Cancel and file-format export need NATIVE.

- Affine, painting and widget safety: adopt App's `affine`, `editor_painters` and `qtsafe`. Delete
  `ui/qtsafe.py` and the local affine maths; `drawing.context` re-exports App's
  functions, `plugins.host` re-exports App's `PaintContext` (same class object)
  and phase constants, and `drawing.editor` shrinks to a subclass that keeps the
  `UnsupportedCapability` refusal of `before_native_layer`. `FontLabPluginHost`
  translates App `main_window`'s `RuntimeError` to `HostUnavailable`. Require
  `fontlab-fontlabapp>=0.2.147.dev0`. Affine helpers now reject non-finite
  matrices with `ValueError`. Offline only; native reporter painting is
  not proven here.

- Delegate `ui.qtsafe.qt_list` to App's public helper, retaining Glyport's
  pre-delegation GUI-thread refusal, public import path and native provenance.
  Require the explicitly unreleased `fontlab-fontlabapp>=0.2.26.dev0` candidate;
  preserve normal dependency resolution and document its command-level local find-links input.
- Restore the original disabled GC state even when a callback enables GC,
  including call/iteration errors. This intentional correction follows App's
  existing implementation; it does not change thread policy or prove native UI.

- Reduce the installation/backend overview to under 200 lines and preserve the
  complete previous README as `docs/COMPATIBILITY.md`, with historical status
  statements clearly identified. Include that guide in source distributions.
- Align the retained `glyphdata` installer extra with the existing mandatory
  `glyphslib>=6.16.1` dependency. No runtime Python API or implementation changes.
- Add source/distribution checks for public lazy imports, the retained test
  backend, exact runtime payload, extras/entrypoint/license metadata and packaged
  documentation links. Artifact checks take an explicit fresh build directory.

- Add bounded public copy/rename/append of normal layers, preserving the same
  caller object with a fresh auxiliary identity after successful attachment.
  Capture independent native foreground/mask payload at copy time, repair clone
  omissions in active state, shape-data names and raw connections, and retain
  explicit component reference layers while rebinding to destination glyphs.
- Refuse unsupported edits anywhere in a rich detached copy before writes;
  rename and valid master association are supported. Preserve detached geometry
  APIs and deepcopy memo semantics. Retained detached children remain values.
  Keep session association through peers/enumeration/history, with the documented
  first-master fallback after reopen and no private metadata in saved fonts.
- Validate names, roles, master ownership, collisions and destination component
  references before insertion. Stage masks before foregrounds, restore colors
  and active selection, and roll back insertion/update/publication failures;
  failed recovery raises PartialFailure. Source coverage includes native-shaped
  doubles and failure/retry cases; native public acceptance remains pending.

- Read native layer-role flags as boolean properties in both auxiliary catalog
  enumeration and retained-layer resolution. Correct the native doubles to the
  measured FontLab 9784 property shapes; stale callable stub declarations had
  hidden a runtime TypeError. Original native failures remain retained for
  native reruns and do not become acceptance passes from this source fix.

- Expose ordinary native auxiliary foreground layers after the existing master
  layers, with distinct stable session IDs, native names and false
  `isMasterLayer`. Use the first existing master as their documented adapter
  association because FontLab has no equivalent metadata; never write that
  association into the font. Preserve direct master lookup and proxy identity.
- Clear genuinely missing backgrounds without edits, notifications or cache
  revision changes, including unmasked auto layers. Existing auto-layer masks
  still refuse. Keep auxiliary/master/background cache and history identities
  separate, validate live auxiliary membership and preserve publication
  retry/discard boundaries. Native original-script, Undo and save/reopen
  acceptance remain open; layer append/copy is not added.

- Restore ordinary mapping reads for missing, foreign and removed kerning
  master ids: indexing raises `KeyError`, `get` returns the supplied default,
  and membership is false. Retained mappings still validate font lifetime;
  assignment keeps strict master type/ownership validation. Document live
  master replacement, read-only nested snapshots, current-master group reads,
  all-independent-master group writes and the native Undo/metadata limits.

- Retain original native component shapes, shape data and builders until final
  layer/glyph history publication, including COW reference edits and direct
  one-level decomposition. Publish those originals first, keep failed batches
  retryable, and restore retained history with collection rollback. Failed COW
  reference attachment restores original shapes and peer bindings. Source tests
  reproduce the measured detached-builder failure; actual public native Undo,
  save/reopen and original-script acceptance remain native acceptance gates.

- Add live `GSGlyph.leftKerningGroup`/`rightKerningGroup` setters across every
  master of independent-class FontLab fonts. Preserve other members, opposite-side memberships and pair
  keys; refuse class-name collisions and independent edits of two-sided classes.
  Referenced empty classes survive until their last pair is removed.
- Replace the `GSFont.kerning` snapshot with a master assignment mapping:
  `font.kerning[master.id] = mapping` validates glyph ids, class sides and finite
  values before writing; `{}` clears that master's pairs. Nested mutations and
  master deletion raise explicit unsupported errors. Remove empty unreferenced
  classes during replacement, retaining shared classes used by other masters.
- Use FontLab's native class/pair tools and history, resolving all dependencies
  before writes. Cache complete kerning records by existing native revision,
  update known successful writes and invalidate readers after native errors and
  legacy pair writes. Shared class mutations, including empty-class cleanup
  during pair replacement, refuse before any edits: current native readers
  cannot establish complete metadata preservation across synchronization.
  Shared pair-only changes and membership no-ops remain available. Recheck the
  live shared flag before cache reuse. This is an interim host limitation tracked
  in https://github.com/Fontlab/fl/issues/8519; native reset/Undo acceptance is
  established separately by native tests.
- Invalidate kerning membership and write-planning snapshots on native kerning
  container Undo/Redo, including retained and peer glyph handles. Observe the
  container identity and history without widening geometry invalidation; refuse
  missing or stale native history APIs. Independent-class writes still use the
  host commands: their `killKeyGlyphs` call can clear raw main-glyph references
  which the current host cannot expose. No opaque-reference preservation is
  established (FontLab).
- Validate all masters represented by kerning writer snapshots, including an
  Undo in a noncurrent master followed by a switch back before the next access.
  Retain native history handles after bounded setup; warm validation reads their
  markers without switching masters or refetching classes/pairs. Failed or stale
  marker reads discard the snapshot before a later retry.

- Add read-only `GSEditViewController.composedLayers` as the deprecated alias
  of current live `layers`, preserving native edit-view order, repeated glyphs,
  current master, proxy identity and stale-tab/font checks. This retains the
  existing master-layer subset; feature control and general shaping are not
  added or established by the source tests.
- Export the official legacy `GlyphsApp.LTR = GSLTR = 0` alias through scoped
  execution and ordinary activation. Preserve existing non-LTR kerning refusal;
  source-only tests exercise pair updates and removal across masters without
  expanding the kerning APIs. Native originals/saved-font acceptance is separate.

- Add writable `GSComponent.name` and `componentName` aliases for live and
  detached components. Resolve live names in the containing font and refuse
  missing, cyclic or unsupported base references before changing native shapes.
- Add one-level `GSComponent.decompose()` and
  `GSLayer.decomposeComponent_(component)`. Stage FontLab's transformed native
  clones, replace only the chosen shape slot, preserve nested components and
  raw connection flags, and retain unrelated shape/node identities. The
  initiating component becomes a detached snapshot so its name remains readable;
  other removed native handles become stale. Attachment failure restores the
  original shapes and peer bindings; failed native updates block publication
  until retry. Native acceptance of the unchanged scripts remains a separate gate.
- Validate component reference graphs by resolved glyph and layer identity,
  including later references to different explicit layers of the same glyph.
  Refresh the target native builder before staging decomposition so stale empty
  or nonempty includes cannot lose or substitute shapes; refresh failures leave
  the component attached for retry.
  Retire decomposed component tokens from history aliases and ordinal slots so
  peer handles stay stale through reconciliation and native history restoration.

## v1.0.7 (2026-10-17) — tabs, connections, dialogs, area and node insertion

- Create `GSFont.newTab()` tabs empty through FontLab's native empty-text slot
  before applying requested text/layers. Preserve shaped text, placeholder-cell
  selections and old rendered-glyph activation, including first-tab creation
  from a Font Window, cross-font sources and native failure cleanup. The owned
  hidden sender is disconnected before deletion; the replacement guard remains.
- Read/write `GSNode.connection` through public raw flags, preserving handle
  coordinates, node type, selection, first-node/unrelated bits and metadata.
  Restore connection bits across copy-on-write clones before Undo checkpoint
  and attachment, including successive ungrouped edits. Host G2/Hobby reads as
  smooth; explicit plain sharp/smooth writes replace those advanced modes.
  Unsupported Glyphs connection values still raise an explicit refusal.
- Share kerning-group membership snapshots by font/current-master/side and
  revision for `GSGlyph.leftKerningGroup`/`rightKerningGroup` reads. Fetch classes
  once per side; preserve side mapping, first membership, missing groups,
  master switches without history changes, rename/removal, notified/grouped
  edits, Undo and failed-read retry behavior.
- Provide the scoped legacy import
  `robofab.interface.all.dialogs.AskString(message, value="", title="RoboFab")`
  through the existing dialog bridge. Accept returns text and cancel returns
  `None`; ordinary activation, scripts, plugins and retained callbacks share
  the provider. Refuse foreign RoboFab modules before cached imports and
  restore module identities/caller globals on exit or failure. This supplies
  only that package chain and `AskString`, rather than the RoboFab library.
- Enable real modal dialogs in the actual native-host session factory. Direct
  bridge/custom-host defaults remain unchanged. Owned native accept/cancel/
  defaults checks pass on both Cocoa routes with empty injected-answer maps,
  exact prompt/title/initial value and cleanup.
- Add `GSPath.area()` for unsigned analytic area of current live or detached
  geometry, closing open paths only for integration without mutation. Use the
  existing fontTools AreaPen traversal shared with direction. Glyphs flattens
  curves, so its approximation may differ; curved areas are not bit-identical.
- Add `GSPath.nodes.insert(index, node)` and `append(node)` for live/detached
  paths with strict Glyphs3 indices (one negative-length adjustment, len valid,
  no clamping). Attach the supplied draft/copy with its actual parent/index/
  selection; preserve retained proxy handles, same-host peers, hint targets,
  shape-local coordinates, raw flags and existing Undo/cache failure recovery.
  Native copy-on-write may rebind handles. Closed append moves the same native
  start object with insert/removeOne/insert, preserving logical order through
  incremental closing controls without reconstruction or type coercion.
  Invalid indices/coordinates/connections and implicit attached/foreign-node
  relocation are refused before edits; callers must explicitly copy nodes.

- Verification on FontLab 9.0.9784: reviewed source `23b360d` has 2,619 passing
  tests and one optional pathops skip. Parent native regression at that source
  retains all 32 targets: 17 passed, 15 classified blockers, no regressed true
  clause or changed classification. Cocoa identity, retained callbacks,
  restoration and cleanup pass. Native empty-tab/full-font/second-font and
  exact saved-XML checks pass at reviewed `9f6e39a`.
- Unchanged originals pass through both Cocoa routes: Select small paths
  28/28 with a genuine modal dialog (`2eef845`); Node Duplicator (current layer)
  27/27, Node Duplicator (all masters) 29/29 and Node Duplicator + 2 Handles
  (all masters) 27/27 (`23b360d`), including all six native saved/reopened
  results. Grouped/ungrouped closing-control append saved results also pass.
  Highest & Lowest Glyphs passes 26/26 (`04789a9`); Same Kerning Groups passes
  27/27 (`d9111a0`) under the unchanged 40-second deadline.
- The historical accepted aggregate is 56/166 distinct originals, with 77
  further passes needed for the required 133. This is not a same-head run of
  all 56. Curve All Straights remains **failed**: FontLab VFJ save/reopen turns
  a closing smooth control into an oncurve (fl#8517), despite correct runtime
  flags/coordinates. No 80% completion or general persistence claim follows.
  Whole-branch review, installed-artifact checks and canonical source
  integration passed. The wider compatibility goal remains open.

## v1.0.6 (2026-10-16) — native geometry cache updates

- Refresh layer and glyph caches at native layer-write boundaries, so warmed
  bounds can reflect node/path/shape/layer edits inside an Undo group. Reuse the
  measured native update chain; bounds reads remain read-only and auto-layer
  edits remain refused.
- Retain failed native updates and their Undo batch for retry; reject false
  update results and prevent final notification until updates succeed. Preserve
  copy-on-write baselines, peer bindings and collection rollback recovery.
- Keep stale failed-update batches unpublishable across repeated retries, and
  retire replaced node handles in owner and peer sessions before cache updates
  can fail. Explicit collection rollback restores the original bindings.
- Source verification: 2,440 passed, one optional pathops skip; 25 cache and
  recovery cases. Independently extracted source: 2,435 passed, six skips.
  Owned FontLab 9.0.9784 bounds update immediately after replacement and movement;
  installed-wheel and canonical Cocoa identity/lifecycle checks passed. The full
  native regression remains 17 passed and 15 classified blockers with no regressed
  clause. Artifact payload/privacy and Twine checks passed; source review approved.
- Highest/Lowest now reports the correct extrema and Center produces the exact
  requested geometry, on both native Cocoa and Qt from the installed wheel.
  Their separate saved metadata/UI preservation failures remain open; neither
  becomes a benchmark pass. The historical aggregate remains 50/166 and the
  broader 80% compatibility goal remains open.

## v1.0.5 (2026-10-16) — path, selection and tab APIs

- Reconstruct `GSPath.segments` from staged continuous line/cubic points, with
  exact open/closed endpoints, sharp-node defaults and finite-coordinate checks.
  Accept both point structs and `NSValue.pointValue()` boxed control points.
  Keep contour identity, attributes and the existing Undo/invalidation machinery;
  malformed later entries cannot partially replace a path.
- Add owned-node/anchor `GSLayer.addSelection_()` and `clearSelection()` using
  existing selection state. Foreign, stale and unrepresented elements fail
  explicitly; native anchor selection remains unsupported by the backend.
- Route `GSFont.newTab()` layer lists, including empty lists and newline controls,
  through the exact layer-list setter. Reject foreign, detached, non-master and
  mixed-master layers before opening a tab. String/default usage is preserved.
- Verification: 2,415 source tests passed, one optional skip; 54 focused API
  regressions passed. Independently extracted source: 2,410 passed, six skips.
  Straighten All Curves, Select partial path and Select paths pass unchanged
  with one activation line through native Cocoa and Qt in FontLab 9.0.9784,
  including installed-wheel runs and saved second-font preservation. Full native
  regression remains 17 passed and 15 classified blockers. Source review approved;
  artifact payload, Twine and Cocoa identity/lifecycle checks passed.
- Curve All Straights still fails exact geometry/smooth-flag checks; Highest and
  Lowest still fails cached-bounds/result checks. These remain benchmark failures.
  The broader 80% compatibility goal remains open; the historical aggregate is
  50/166 rather than a same-head run of the whole corpus.

### Test fixture isolation

- Give independent fake FontLab hosts separate backend registries. Retained
  cyclic test doubles reused package IDs and intermittently made creation tests
  see another fixture's pending edits. Real same-host peer safety is unchanged;
  the regression retains both fake hosts and their distinct pending state.

## v1.0.4 (2026-10-16) — GlyphData, tabs and anchor comparison

- Read glyph category/subCategory from maintained GlyphData, including spacing
  accents, production aliases and unencoded alternates. Declare glyphsLib as a
  runtime dependency; loading stays lazy and incomplete installations fail
  explicitly. Letter case is no longer misreported as a subCategory.
- Expose the legacy `Font` global as the current-font snapshot when activating
  an ordinary script, and preserve empty lines in native editor tabs.
- Support `GSLayer.compareString()` on layers with ordinary ASCII anchor names,
  preserving the reference's structural encoding and name separators. Unverified
  Unicode name collation, components and path-component hints still raise
  explicit unsupported-capability errors.

- Verification: 2,360 source tests passed, one optional skip; independently
  extracted source archive 2,355 passed, six optional skips. Full native
  regression: 17 passed, 15 classified blockers, no new failures. Categories to
  XML, Clean Classes and Recipe Dumper passed with one added line through both
  Cocoa backends in FontLab 9.0.9784; the original bodies and saved second-font
  data were preserved. Source and oracle reviews approved.
- Normal installation now brings glyphsLib automatically. Existing editable
  installations must update dependencies before category reads; Glyport never
  installs into FontLab itself. Native Cocoa still needs the optional cocoa
  extra. The broader 80% script goal remains in progress; the historical named
  benchmark is 41/166, rather than a full same-revision acceptance claim.

## v1.0.3 (2026-10-16) — ordinary imports and Cocoa backends

- Add one-line `activate()` / `deactivate()` for ordinary Glyphs imports and
  implicit GlyphsApp globals, with explicit cleanup and collision checks.
- Prefer real AppKit/Foundation/Cocoa/objc through PyObjC on macOS; default to
  Qt on other platforms. `cocoa_backend="qt"` forces translation and `"native"`
  requires macOS/PyObjC. Auto fallback exposes its reason on handles/contexts.
- Preserve native lazy imports, class identity and module metadata across Qt
  scopes. Retained scripts/plugins reject conflicting backend requests until
  closed, preserving callback and unload behavior.
- Add the optional macOS-only `cocoa` extra. Native/Qt widget interchange remains
  unsupported; Vanilla and FontLab editor/plugin bridges remain Qt-backed.
- Include reviewed glyph Unicode/draft attachment and glyph-info corrections
  from the preceding issue-106 round-34 work.
- Verification at reviewed source 9aaab0e: 2,288 tests passed, four optional skips;
  native source and independently installed wheel backend probes passed on
  FontLab 9.0.9783 / Python 3.11.6 / PyObjC 12.2.2. Four distinct original scripts
  passed with one added line through both routes. The 32-target regression ends
  at 17 passed / 15 classified blocked; an initial general-plugin host exit and
  its successful rerun are retained in workspace evidence. The broader 80%
  script-compatibility goal remains open.

## v1.0.2 (2026-10-16) — API batch 1, real-use rounds 31-33b (issue 106)

Reviewed by Codex (X4a1/X4a2 API batch, X4p24 whole range a81c6f5..2cf6880, X4p25 APPROVE 2cf6880..cab7227)
and checked natively in FontLab 9.0.9783 (pre-merge on 2cf6880: 32-target regression 17 passed / 15 classified /
0 failed, F55 filter-dialog 11/11, rename probe, creation on plum 0.13 s / rafi 0.47 s / boto 1.01 s with no
composite loss, round-27 targets; delta on cab7227: regression, F55, creation, auto-layer guard probe).

- API batch 1: GSLayer.beginChanges/endChanges (retryable undo publication), GSPath.direction (+1 for empty or
  collinear paths, as GlyphsCore), tab.layers refuses background/unsupported kinds, detached-attribute refusal on
  every attachment route including background assignment, and further Glyphs names (see ISSUE106-API1.md, removed in 6937e02; in git history).
- `GSComponent.position` / `.bounds` and `IndexedSequence.clear` (s-copydatafrommaster now 13/13).
- `kerningForPair` keeps Glyphs 3's `None` for a missing pair (GlyphsSDK wrapper threshold); scripts that compare
  it with an int fail in Glyphs 3 too.
- Edits on auto layers are refused at the backend choke point before any mutation or notification (guides,
  anchors, hints, shapes, paths, width, collection append/remove/insert/clear, background, mask): notifying an
  auto layer re-resolves every default-recipe auto layer in the font (fontlab/fl#8512).
- Round 31 (paint-only redraw) was reverted: it left FontLab's cached layer bounds stale after filter previews.
- Evidence: `verification/issue-106/evidence/glyport/` (premerge-2cf6880, premerge-cab7227, probes/auto-layer-guard*).

## v1.0.1 (2026-10-16) — real-use rounds 17-30 (issue 106)

Reviewed by Codex (X4p22 APPROVE, range 0baafb4..44e0583) and checked natively in FontLab 9.0.9783
(pre-merge on 44e0583: 32-target regression with F55 filter-dialog 11/11, rename probe, creation
probes on plum/rafi/boto, round-27 targets; evidence `verification/issue-106/evidence/glyport/`).

- Glyph and scratch-component creation preserve existing composites that FontLab's commAddGlyph
  re-resolves (default-recipe auto layers; fontlab/fl#8512): snapshot via get_glyph, restore through
  set_glyph on the existing glyph, verify, roll back with a precise refusal; refuses when a glyph to
  restore has pending in-process edits. Native creation: 0.13 s (plum), 0.45 s (rafi, 2702 glyphs),
  1.05 s (boto, 3387 glyphs).
- In-process `get_glyph` tuple-shaped JSON accepted; `renameGlyph` called positionally and
  GSGlyph.name keeps the glyph's unicodes.
- Hint cleanup reads only Python-bound flGuideLine links; name/Unicode lookups validated through
  native findName/findUnicode; refusals happen before any mutation; bulk edits stage clones first.
- Corpus results (round 6, 66 Glyphs scripts): 15 pass, 44 open tickets, 7 classified host issues;
  round-27 fixes then pass s-angularizzle, s-mastertwins, p-dottype.

Known issues: fl#8512 lock/attaching-anchor drop on notified composites (host defect; now also seen
on Light layers after glyport creation); restored layers lose the UI-only `active` flag; an unrelated
glyph (A) gained `advanceHeight`/`com.fontlab.caretAnchors` lib in one diacritics run (source under
investigation); extension-only hint links cannot be cleaned (not Python-bound); preservation reads
every candidate composite once per creation.

## 2026-10-16 — issue 106 lane G1: real-use deployment, matrix and harness (verified)

- Deployment (f73bcee, 9c38f03): `tools/deploy/deploy_launcher.py` writes
  `Glyport Launcher.py` into FontLab 9's real Scripts folder (marker line, refuses
  foreign files, links and the fontlab-user-folder link). The launcher puts this
  checkout's `src` and a dependency site first on `sys.path`, purges stale
  fontlab_glyport/GlyphsApp/vanilla modules, keeps handles (plugins stay installed),
  offers run-script/install-plugin, and picks glyphs2 for Python 2 sources. Natively:
  every real-use run executes the deployed file and asserts glyport's path.
- Real-use matrix (adf791e, a76e7fa, 9068651): `realuse/manifest.json`, 45 scripts
  and 22 plugins over all seven protocols, selected by `native-drivers/realuse/select_targets.py`
  (pure Python, no unscoped external effects, Glyphs 4 API frequency, round-robin by
  author); covers 50/50 of the most used Glyphs API names. `realuse/curation.json`
  drives each target through its own controls and states expected effects.
- Native harness (adf791e … 7fbdb31): one fl-native session per target, owned GetGo
  copies, scratch HOME/defaults/cwd, dialogs answered (never modal), FontLab-saved
  before/after VFJ diff, Output tracebacks count as failures, per-protocol plugin
  exercise, corpus code run from the event loop (no 5 s cut-off), corpus source
  scrubbed from evidence, R018 receipts. Tests: tests/test_realuse_deploy.py and
  tests/test_realuse_harness.py, 27 passed.
- Composite glyphs changing after a read-only script: FontLab's own auto-layer rebuild
  (flags 16, autoRecipe) on display, reproduced with no glyport loaded
  (parent `verification/issue-106/evidence/glyport/probes/composite-change.md`);
  the diff reports such glyphs as `auto_rebuilt` (6b1cb58).
- Baselines: 32-target regression at 1c58099 16/15/1 (filter-dialog flaky, 11/11 on
  re-run) and at d2661fd 17 passed/15 classified/0 failed; real-use round 1 (pre-fix)
  7/67 passed; round 2 after X1 41e940f (F1, F2 verified fixed) 4 passed of 63 recorded
  with stricter expectations. Tickets F1–F34 in parent
  `verification/issue-106/evidence/glyport/FIXES.md`.
- Round 2 completed at d2661fd (2026-10-16): 6 passed, 1 classified (corpus defect
  ruling), 60 failed, all failures ticketed (F3–F36); harness fixes 7ae11f8, 7fbdb31,
  0d6d59f; a FontLab crash during the run was attributed to another lane's stale
  "Save Changes?" dialog (parent probes/crash-20261016-004252.md).
- Round 3 at fd01e77 (X1 75c5ce5, 2026-10-16): 10 passed, 1 classified, 56 failed; regression
  17/15/0 after re-running host-disturbed targets; F3–F24 mostly verified fixed (F16, F19, F24
  partial); F37 (open undo discarded, from the reviewer's request) and F38–F46 filed; harness
  watchdog deadline inside FontLab (587db48) after a runaway script hung FontLab.
- Documentation (1fffb78): tools/deploy/README.md, native-drivers/realuse/README.md and a
  README.md section; `native-drivers/realuse/report_table.py` generates the report's
  per-target table (round-2 table in the parent G1 report).

## 2026-10-15 — completed checklist (moved from TODO.md, issue 104)

Verified natively (parent evidence under `verification/issue-101-ecosystem/evidence/`):

- Layer lookup for FontLab-created fonts (R021); R024 save/reopen; R023 native
  Undo/Redo. R023 ruling: one Edit > Undo reverts a group; glyport's pre-change
  notification adds one extra no-op entry (documented). Copy-on-write shapes
  (6a886c9, 700f3ce) make in-place node, start-point and contour edits undoable
  (`glyport-matrix/probe_undo_cloned_shape.json`), so the former "node
  coordinates not undone" host limit no longer applies.
- Model breadth reads (R020); writes for kerning, userData, customParameters,
  guides, tags, export/script, new glyphs and components (component creation
  through a scratch glyph: FontLab has no Python component constructor,
  fontlab/fl#8505). Kerning writes go through FontLab's kerning tools, which
  record one Undo step per pair even inside `undo_group`
  (`glyport-matrix/probe_kerning_undo.json`): documented limitation.
- Application/document behaviour (R019, R021), including DOCUMENTACTIVATED from
  the interface poll (0fc4ee9). DOCUMENTWASSAVED stays unsupported (no FontLab
  signal, probe_signals.json). Persisted defaults outside the FontLab user folder
  with `GLYPORT_DEFAULTS` (owner ruling).
- Profiles (R006), Glyphs 3/4 adaptation and import adapters (R016, R017),
  non-Mach-O pathways (R033 as narrowed by D8), `run_script`/`install_plugin`
  (R015), `verify --manifest` (R048).
- Vanilla remainder (R029), objc selectors/outlets/bindings (R030), the seven SDK
  plugin protocols (R025–R027; SelectTool has no host tool API, R054), editor
  drawing after the native layer with model layers (R032; before-native-layer
  painting and tools need host hooks, R054).
- Corpus matrix (R049) and its gaps, at gaps 7c64d6a (provisional, see WORK.md):
  16 passed, 15 classified, 1 failed (custom-nsview, waiting for two NSView
  methods on r031; it passed 7/7 when they were present). Fixes: filter Cancel
  restores deleted paths at their shape index (RR-merge P1), plain-model,
  filter-dialog, filter-no-dialog, reporter, general-plugin pass; palette-nib
  (corpus defect), external-process (policy), private-selectors (out of scope),
  fonttools (host, #8500) and remote-plugin (remote service not contacted by
  design) are classified by controller rulings.
- custom-nsview passes 7/7 with L4's NSView `setNeedsLayout_` and
  `performSelector_withObject_afterDelay_` (r031 87ba9da, merged at e3d4366).
  Provisional matrix at gaps 00a27b0 (gaps + r031 87ba9da, without r020): 17
  passed, 15 classified, 0 failed (`glyport-matrix/corpus-report-20261015T182353Z.json`).
- Wheel/sdist checks (R053) for RC 5a9bb78, and a provisional RC at 7c64d6a
  (twine PASSED, sdist 1049 passed, wheel e2e reporter passed).

## 2026-10-15 — completed checklist (moved from TODO.md)

- Create independent repository and `fontlab_glyport` package boundary.
- Implement read-only script/bundle assessment and CLI with source protection.
- Verify inspection against all 253 discovered corpus bundles.

## Historical source checkpoints — issue 104 and API batch 1

These records retain the source-stage results and pending gates as recorded
then. Later versioned entries and the current Unreleased milestone supersede
their status; the original evidence and limitations remain below.

Issue 106 API batch 1, Round 2:

- Preserve failed layer Undo publication for a successful endChanges retry.
- Reject unsupported tab layer kinds before publishing glyph names.
- Refuse detached attributes, including nested backgrounds, before live
  background attachment can discard them.
- Match GlyphsCore +1 direction for empty and collinear paths.
- Add regression cases; gate restrictions recorded in ISSUE106-API1.md (removed in 6937e02; in git history).

- 2026-10-15 (issue 104 L2m, glyport-gaps): copy-on-write shapes with token
  rebinding in every live backend; `GSGlyph.tags`, `export`/`script`/`storeScript`
  (libs), `GSGlyph(name)` + `font.glyphs.append`, `GSComponent` drafts,
  `layer.shapes` append/assign, `insert_path`; filter Cancel restore with shape
  order and selection; `glyphForUnicode_`, `textCursor`, `graphicView()`,
  `GSLayer` ascender/descender/bezierPath/completeBezierPath/glyph()/
  metricForType_/copyDecomposedLayer/next- and rightKerningForLayer;
  `Glyphs.colorDefaults`, `GSDocument.selectedLayers()`, GSCase/GSRTL/GSBIDI,
  `GSControlLayer`; `foundation.py` (NSUserDefaults over Glyphs.defaults,
  NSClassFromString, geometry, collections, NSPasteboard, NSTimer, NSScreen,
  NSDate, NSRunLoop, event-pumping NSApplication, constants, deferred
  NSBitmapImageRep/NSAlert/NSButtonCell); `GlyphsApp.UI.GlyphView`; vanilla
  VanillaBaseObject, ColorWell, SegmentedButton, ActionButton, Box styling,
  Slider ticks, List rowHeight; NSMutableParagraphStyle, `shearXBy_`; reporter
  context menus as View-menu items; DOCUMENTACTIVATED; symlinked helper packages
  in dependency directories.
- 2026-10-15 (issue 104 L4i, R031 on `issue-104-glyport-r031`): XIB/NIB view
  coverage. 181/181 corpus files decode and 164 load natively (from 115 loaded,
  8 not decoding). Number formatter limits archived as NSDecimalNumber and
  standalone formatters; NSTabView `selectedIndex` binding; NSWindow/NSPanel from
  window templates (hidden at load, delegate with title-bar veto); NSStackView,
  NSScrollView, NSBox, NSSplitView, NSGridView, NSVisualEffectView containers;
  NSImageView with bundle images (`instantiate(..., resources=...)`, passed by
  `loadNib`); NSMatrix; NSPathControl and NSURL; NSTableView (data source,
  delegate, prototype cell views as nested graphs, NSTableColumn,
  NSTableCellView, NSIndexSet); NSComboBox; NSTextView; NSSwitch;
  NSSegmentedControl; NSSearchField; NSSplitView, NSGridView,
  NSVisualEffectView; NSArrayController with table content, column-value and
  selection bindings; Glyphs' GSMouseOverButton and
  GSInspectorView emulated; button images, image positions and borders;
  NSButton `setImage_`/`setImagePosition_`/`setBordered_`; NSTextField
  `cell().setLineBreakMode_`; outlets to cells reach their control; outlets use
  KVC setters; `enabledN` bindings combine with AND; the new NS* constants are
  exported; `_Env.subclass` caches per (Qt class, factory).

- 2026-10-15 (issue 104 L2m, corpus matrix R049): bundle images as Qt images
  (`ui/images.py`: NSImage with Qt readers, QSvgRenderer, sips for PDF, `@2x`
  variants; SDK icons on FileFormat menu actions), NSCursor; archive inventory and
  choice by bytecode magic; master metrics through `fontlab.FontMetrics`,
  `GSLayer.glyphMetrics()`, `master`, `parent`, `vertWidth`/`TSB`/`BSB`; glyph
  metadata for exports (`glyphId`, Unicode-derived category/subCategory/case/
  script, note, lastChange, charString, `export` (True: no export flag found);
  `fontMasterForId_`; dialog
  paths as NSString (`NSPath`); scripts get `from GlyphsApp import *` and UTF-8
  `open()`; NIB/XIB tab views, number formatters, progress bars, Auto Layout
  constraints, symbolic spacing, multi-line titles, `untranslated_xib`; GlyphsApp
  node/metric constants, GSGlyphsInfo, GSScriptingHandler; `ui:wx` capability;
  `PluginHandle.plugin`; tab `selectedLayers`; userData answers None for a
  missing key.
- 2026-10-15 (L2m, fixes found natively): FontLab closed contours are read in
  Glyphs order (start node last) with on-curve types from the incoming segment;
  cubic control points (native type "curve") are Glyphs offcurves and are written
  back as cubic; `GSNode.makeNodeFirst()`.
- 2026-10-15 (L2m): sdist ships `native-drivers/` (its tests compile them) and no
  longer lists the missing `examples/`.

- 2026-10-15 (issue 104 merge): merged lane L2 (`issue-104-glyport-ui`, 2fd9552):
  vanilla.dialogs, Tabs, Sheet, native handles, objc subset, Qt-backed AppKit
  layer, NIB/XIB decoding and loading, the seven SDK plugin protocols on a FontLab
  host, Cocoa drawing and after-native-layer editor painters, `qtsafe.qt_list`.
- 2026-10-15 (issue 104 merge): `glyphsapp/fontlab_session.py` wires the lanes per
  execution context: `Glyphs.menu`, `*_MENU`, `GlyphsApp.plugins`, model adapter and
  layer resolver, DRAWFOREGROUND painters (DRAWBACKGROUND refused, R054),
  AppKit/Foundation/Cocoa/objc with L2's names over L3's values, vanilla.dialogs;
  `plugins.register_plugin` makes `install_plugin` load real plugins.
- 2026-10-15 (issue 104 L1, review R-L1 fixes): GlyphsApp exports GSAxis, GSInstance,
  GSGuide, GSHint, GSCustomParameter, GSClass, GSFeature, GSFeaturePrefix and the hint/
  LTR constants; nested bridge dispatches share a depth and tear down after the
  outermost; every layer is prepared as [layer, glyph]; preparations are recorded
  and groups closed only after their notification succeeded (a failed `end_undo`
  keeps its changes for a retry; `undo_group` keeps the body's exception); tab
  proxies are bound to their text block and go stale when another tab replaces it;
  tab text keeps space glyphs (delimiters only before a following character).
- 2026-10-15 (issue 104 merge): merged lane L3 (`issue-104-glyport-runtime`,
  8501e2b): profiles, Glyphs 3/4 adaptation and scoped Cocoa/objc adapters,
  dependency routes (pyc, ZIP, subprocess, HTTP), `run_script`/`install_plugin`
  handles and receipts, `verify --manifest` with native receipts. `driver_common.py`
  gained the sys.path `__file__` guard.
- 2026-10-15 (issue 104, owner ruling): `fontlab_glyphsapp_provider` persists `Glyphs.defaults` by default at `~/Library/Application Support/FontLab/Glyport/defaults.json`, overridable with `GLYPORT_DEFAULTS`.
- 2026-10-15 (issue 104 L1, gaps from L6b): `GSLayer.name`, `bounds`, `LSB`/`RSB`
  read and write, `applyTransform`; stored `GSAnchor` position/x/y writes;
  `GSFont.selectedFontMaster`; no-op `disable/enableUpdateInterface`. Native driver
  passes against FontLab's own glyph metrics.
- 2026-10-15 (issue 104 L1, R020): read glyph components natively (a FontLab component is both `isComponent` and `isComposite`; it used to raise).
- 2026-10-15 (issue 104 L1, R023): notify each layer's pre-change state before its
  first change in a group, so a script's first edit of an existing glyph and a
  group spanning several glyphs are one Undo step. Native driver extended and
  passing; a FontLab redo limitation is recorded.
- 2026-10-15 (issue 104 L1, R020): read-only `font.classes` (OpenType classes from `fgFont.groups`), natively compared with the VFJ's own classes.
- 2026-10-15 (issue 104 L1, R019): `font.currentTab`, `font.newTab`, `tab.text`
  (Glyphs text with `/name` tokens and line breaks), `tab.layers`,
  `font.selectedLayers`. Native driver passes.
- 2026-10-15 (issue 104 L1, R019): DOCUMENTOPENED/DOCUMENTCLOSED callbacks on FontLab's
  `flItems.instance().qobject` signals, with the event's GSDocument; deferred
  disconnect while dispatching. Native driver passes.
- 2026-10-15 (issue 104 L1, R019): `JsonFileStore`, a persisted JSON store for `Glyphs.defaults` with explicit conversions.
- 2026-10-15 (issue 104 L1, R019/R021): `model.font` follows FontLab's active font
  (`fontpr.get_active_font`), `None` when FontLab has none; `GSNode.selected`
  read/write and `GSLayer.selection`. Native document-switching driver passes.
- 2026-10-15 (issue 104 L1, R020): read-only glyph `leftKerningGroup`/`rightKerningGroup`.
- 2026-10-15 (issue 104 L1, R020 slice 2): axes, master coordinates, instances,
  kerning (read, set, remove; `@MMK` groups mapped to FontLab classes through
  `fontpr`), guides (read, append; hint guidelines excluded) and read-only hints.
  Native driver passes with the MCP readers as oracle and a VFJ reopen.
- 2026-10-15 (issue 104 L1, R023): layer edits notify `[layers..., glyph]` in one
  list, the native form that creates one Edit > Undo step; layer-only notifications
  were skipped by Undo. Native undo/redo and R024 save/reopen pass (WORK.md).
- 2026-10-15 (issue 104 L1, R020 slice 1): `userData` on font/glyph/layer,
  `GSFont.customParameters` (glyphsLib lib keys, duplicate names refused) and
  read-only `features`/`featurePrefixes`; backend `lib`/`set_lib` verify writes by
  reading back. Native round trip passes.
- 2026-10-15 (issue 104 L1, R021 layer lookup): glyphs without a native layer
  for a master (FontLab-created fonts) no longer raise `UnsupportedCapability`.
  The layer reads as empty with width 0 and is created by the first write, keeping
  its token; master layers are now keyed by glyph and master. Native save/reopen
  proof pending (WORK.md).
- 2026-10-14 (GlyphsApp integration, task 2: FontLab bridge):
  - New `glyphsapp/fontlab_bridge.py`: `FontLabGlyphsBridge` and
    `fontlab_glyphsapp_provider(ctx, version=...)`. Native modules load
    lazily. Output goes to the context sink, and FontLab's Output panel is
    shown or cleared only with `output_panel=True`. Notifications use the
    status bar, and `redraw` calls `UpdateActiveCanvas()`.
  - `UPDATEINTERFACE` callbacks come from one owned `QTimer`, which fires on
    changes to the current package or glyph. Teardown runs disconnect, stop,
    then `deleteLater`. Other events raise `UnsupportedCapability`.
  - New `glyphsapp/fontlab_dialogs.py`. `Message` is non-modal. The other
    dialogs use injected answers, or a modal `exec()` only with
    `interactive=True`.
  - None of this is natively verified yet. WORK.md has the acceptance
    checklist.
  - `Glyphs._remove_all_callbacks` is consumed when it runs, so an
    `addCallback` after `ctx.close()` is rejected. It catches `BaseException`
    for each token and re-raises process exits first.
  - `PartialFailure.errors` is a declared `()` default. The
    `UnsupportedAttribute` docstring now mentions the property guard.

- 2026-10-14 (GlyphsApp integration, task 1, follow-up):
  - A close hook that raises `SystemExit` or `KeyboardInterrupt` no longer
    skips the hooks after it. `close()` re-raises the first such exit after
    teardown.
  - `PartialFailure` messages name each hook failure.
  - Vanilla `close_windows` closes the remaining windows when a close bind
    exits.
  - Probe misses no longer resolve a column: `caller_location` returns the
    line only, and a miss takes 4.7 us instead of 223 us in a 300-line script.
- 2026-10-14 (GlyphsApp integration, task 1):
  - Unknown reads on model proxies now raise `UnsupportedAttribute` with their
    capability and script line, so `hasattr`/`getattr(obj, name, default)`
    probes work. Unknown writes stay plain `UnsupportedCapability`.
  - Properties on model proxies and on `Glyphs`/`GSDocument` are guarded: an
    `AttributeError` raised inside a property is reported as an
    `UnsupportedCapability` naming the inner capability.
  - `ExecutionContext.on_close(hook)` is new. `close()` runs each hook once,
    newest first, before unloading, and then raises `PartialFailure` if any
    hook failed.
  - `glyphsapp_provider` and `vanilla_provider` (and their `make_*` functions)
    accept `on_close=ctx.on_close`. `ctx.close()` then removes every Glyphs
    callback and closes every open vanilla window.
  - `_remove_all_callbacks` attempts every token and re-raises the first
    failure.
- 2026-10-14 (GlyphsApp host services, task 1, fix round 1): added
  `UnsupportedAttribute` (subclass of `UnsupportedCapability` and
  `AttributeError`). Unknown reads on `Glyphs` and `GSDocument` raise it, so
  `hasattr`/`getattr(..., default)` probes work; module-level names are
  unchanged. A callback token is dropped only after `bridge.remove` succeeds.
  The bridge docstring notes that a raising `error_sink` reaches host dispatch;
  `localize` of other values is documented and tested; `@runtime_checkable` is
  gone from `GlyphsBridge`.
- 2026-10-14 (GlyphsApp host services, task 1): Added the opt-in
  `fontlab_glyport.glyphsapp` package. `make_glyphsapp_module(model, bridge,
  error_sink=...)` and `glyphsapp_provider(...)` give a `GlyphsApp` module with
  `Glyphs`, the 13 SDK callback event constants, `Message`, `AskString`,
  `GetFolder`, `GetOpenFile`, `GetFile`, `GetSaveFile` and the model classes.
  `Glyphs` covers `font`, `fonts`, `currentDocument`, `defaults`,
  `boolDefaults`, `intDefaults`, `registerDefault`, `showMacroWindow`,
  `clearLog`, `showNotification`, `redraw`, `localize`, `addCallback`,
  `removeCallback`, `versionNumber` and `buildNumber`. Host effects go through
  the `GlyphsBridge` protocol; defaults live in an injected mapping. Unknown
  names raise `UnsupportedCapability` at the script line. execution.py defaults
  are unchanged. The in-memory bridge double is `tests/glyphsapp_doubles.py`.
  No native FontLab bridge exists yet.
- 2026-10-14 (vanilla slice 2, final review): a stored autosave frame with a
  value that overflows float conversion or exceeds Qt's widget size limit
  (16777215) is now ignored. The Box and List Python subclasses default
  `_owner` to None.
- 2026-10-14 (vanilla slice 2, task 2, fix round 1): fixes for two defects
  found in FontLab.
  - ComboBox reports each user commit exactly once. Popup picks come through
    `activated`. Typed commits come through `editingFinished` and are gated on
    the line edit's `isModified()`, because Qt 5.15 emits `editingFinished` on
    every focus loss. `continuous=True` uses `textEdited`. Programmatic
    `setCurrentIndex`/`set`/`setItems` never fire the callback.
  - Box refits its content widget to `contentsRect()` on show (after the
    style polish), on resize and on `setTitle`, so children no longer overlap
    the title.
  - `List[slice]` returns items.
- 2026-10-14 (vanilla slice 2, task 2): Added RadioGroup, RadioButton,
  ComboBox, TextEditor, SquareButton, HelpButton, ProgressBar, Box and List in
  the new `fontlab_glyport.ui.vanilla_controls` module, exported by the
  `vanilla` module. Each control records a graph node and its connections,
  tracks its signal connections for teardown, and keeps programmatic setters
  silent. List records `selection`, `doubleClick` and `edit` graph events.
  `_Control._wire` now takes a signal source, a graph event name and a
  per-signal filter, and `_Control._track` records extra connections. Doubles
  for the new Qt classes live in `tests/ui_doubles_controls.py`; QComboBox
  doubles now model editable mode. Native acceptance passed in FontLab 9.0.9780
  (evidence: `verification/issue-101-ecosystem/evidence/glyport-vanilla/`,
  `native-slice2-t2*.json` and `native-slice2-extra.json`); a real mouse popup
  pick and typed-match Return in ComboBox stay unverified (WORK.md).
- 2026-10-14 (vanilla slice 2, task 1): Added `setToolTip` to every control.
  TextBox and EditText now take `alignment` (mapped to Qt flags; unknown
  values raise UnsupportedCapability), and TextBox takes `selectable`.
  Windows gain `makeKey()`, `center()`, `getNSWindow()` and
  `setDefaultButton()`, with Return/Enter routed to the default button by the
  window widget. `autosaveName` restores and saves window frames in an injected
  `settings` mapping (new `settings=` parameter on `make_vanilla_module` and
  `vanilla_provider`; default is a process-wide in-memory dict). The doubles
  now model QCheckBox and QLineEdit as siblings of QPushButton and QLabel, as
  they are natively. Native acceptance passed in FontLab 9.0.9780 (before and
  after 341b450; `native-slice2-t1.json` in the same evidence directory).
- 2026-10-14: Added the first vanilla UI slice (`fontlab_glyport.ui.vanilla`).
  Window, FloatingWindow, Group, TextBox, EditText, Button, CheckBox,
  PopUpButton, Slider and the Horizontal/VerticalLine controls are built as Qt
  widgets through an injected `qt` namespace. They record UI graph nodes and
  connections, and layout uses resolve_frame. Callback errors go to an error
  sink. Close teardown runs disconnect first and is idempotent.
  `vanilla_provider(qt, sink)` is an opt-in ExecutionContext provider; the
  execution.py defaults are unchanged. Test doubles are strict and shaped like
  PythonQt. Native acceptance passed in FontLab 9
  (evidence: `verification/issue-101-ecosystem/evidence/glyport-vanilla/` in the
  parent workspace; see WORK.md).
- 2026-10-14 (fix round 1): Reassigning a control attribute and `del` now
  retire the old control: it is disconnected, unparented, deleted and its graph
  nodes are marked `detached`. Callbacks can run through `wrap=ctx.wrap`, so
  print and imports inside them follow the ExecutionContext. A disconnect
  failure is sent to the sink and teardown continues. `open()` after `close()`
  is a no-op.

- 2026-10-14: Added the versioned, host-independent UI graph (R028):
  `fontlab_glyport.ui.graph` with `UIGraph`, `Node`, `Connection`, `Frame`,
  JSON round trip (version 1) and `resolve_frame` for vanilla posSize rules.

- 2026-10-14: Retain the source fgFont in OwnedPackage and route owned metadata
  through it, avoiding the crashing unregistered flPackage.fgPackage getter.
- Resolve owned editing glyphs by retained source names; add a regression test
  that rejects any owned fgPackage access. Workspace behavior is unchanged.

- 2026-10-14: Replaced eager FontLab document traversal with on-demand package,
  glyph-metadata and single-layer reads; stale checks use cached native handles.
- Added explicit `FontLabBackend(packages=...)` isolation and
  `owned_test_package(glyph_names)` for native acceptance on owned data only.
- Added counting-native tests for lazy reads, scoped access, mutations and helper
  construction; no FontLab execution or user-document access.

- 2026-10-14: Added the first R019–R022 live model slice: explicit ModelBackend
  protocol, Glyphs 3 proxies, document identity caches, stale-object checks,
  supported geometry mutations and exception-balanced undo groups.
- Added an in-memory test backend and a lazy FontLab 9 backend derived from
  native stubs; native calls and undo assumptions require controller verification.
- Added model, collection, mutation, lifetime, import-safety and node-mapping tests.

- 2026-10-14: Added R017 owned execution contexts with private sibling/package
  imports, bundle resources, scoped adapter providers and explicit unsupported
  capability locations; no host/Qt imports.
- Added serialized activation, restoration/partial-import cleanup, retained
  callback imports, optional shared globals and adaptation, stdout/stderr sinks,
  SystemExit stage records and idempotent close.
- Added seven execution tests and documented in-process isolation limitations.


- 2026-10-14: Implemented R016/R017 host-independent Python 2 source adaptation
  with 13 ordered transformation IDs, receipt hash chains and composed span maps.
- Added content/profile/version cache identities, atomic publication, verified
  reuse, original-byte preservation and Python 3.11 AST pass-through.
- Added classic division runtime dispatch, future-division handling, original
  traceback filenames, original-location errors and string/semantic diagnostics.
- Added fissix under R046; documented semantic limits and tested owned fixtures.

- Added host-independent, frozen execution receipt records for R018 schema v1,
  structural validation, explained unknown facts and public path checks.
- Added atomic UTF-8 JSON receipt publication with overwrite refusal, concurrent
  writer protection and cleanup on failure or process interruption.
- Added the `GlyportError` hierarchy with stable codes and original-source
  diagnostic conversion, preserving existing assessment exports and semantics.
- Added receipt/error/import tests and documented the version-one schema choices.
- Created standalone Glyport repository and `fontlab_glyport` namespace.
- Added immutable, source-only script/bundle assessments and inspection CLI.
- Record original hashes, lexical imports, SDK protocols, bundle metadata,
  source syntax errors, resource/native requirements and unresolved symlinks.
- Protect originals and existing outputs during assessment writing.
- Native runtime integration, model/plugin execution and GUI translation remain
  pending; static inspection does not certify compatibility.

## 2026-10-15 — verified R020/R031 groups archived

- R020 writes at 2e91b34: eight controller-native receipts, 90 assertions,
  and RR4-r020 APPROVE. CR/CRLF/LF feature comments, changed backend instance
  identities and positional-ID removal fixes are included. Identical-content
  replacement with an identical native ID remains a documented host boundary.
- R031 at cefda33: 181/181 XIB/NIB decode, 164 native loads, 17 D8 compiled
  plugin-class blockers and no failed loads; 16 native fixtures and the
  observer-reentry replay pass. RR4-r031 APPROVE. Decode graph connection-loss
  diagnostics remain in the receipts and are not claimed as solved.
- Both branches are now merged in canonical Glyport 1c58099. Fresh source
  regression: 1,209 passed. Final merged-head native drivers, the complete
  32-target matrix, whole-branch review and release candidate remain required.

Evidence: workspace verification/plan-todo-audit-20261015/verified-groups.json;
verification/issue-104/reports/RR4-r020.md and RR4-r031.md; native receipts under
verification/issue-101-ecosystem/evidence/glyport-r020 and glyport-r031.

## Historical source checkpoint — API surface batch 1

Issue 106 API surface batch 1:

- Added model path selectors, Bézier direction, handle smoothing, layer change
  scopes, detached layer metadata, outline comparison and edit-layer assignment
  for the supported current-master subset.
- Added menu/export constants, popup title selection, objc signature metadata and
  named NSSize results for attributed-string measurement.
- Added explicit host refusals and reject unsupported layer metadata before
  attachment instead of dropping it. Partial/deferred names: ISSUE106-API1.md (removed in 6937e02; in git history).
- Added 32 model/UI contract tests; full-suite environment restrictions recorded
  in WORK.md. fontlab_backend.py and dependencies unchanged.


## Historical source checkpoint — ordinary-import activation

- Add explicit `activate()` / `deactivate()` for ordinary GlyphsApp, AppKit,
  Foundation, Cocoa, objc and vanilla imports in FontLab's GUI thread.
- Retain the existing native session until explicit cleanup; refuse foreign
  module collisions and activation/deactivation inside an active scoped run.
- Supply GlyphsApp exports in caller script globals with collision checks and
  identity-safe restoration; explicit namespace and multiple callers supported.
- Add 14 unit import/lifecycle tests; full suite 2261 passed, 4 skipped.
  Native acceptance remains separate; no dependency or scoped-run changes.


### Activation review fix

- Repeated activation now obeys GUI dispatch and active-scope refusal before
  binding caller globals, including calls from retained callbacks. Three new
  regressions pass; full suite 2264 passed, 4 skipped.

## Historical source checkpoint — Cocoa backend selection

- Explicit `cocoa_backend=auto|native|qt` for activation and ExecutionOptions;
  macOS auto prefers real PyObjC, other platforms default Qt. Required native
  fails clearly; auto fallback exposes its reason on handle/context.
- Preserve native lazy imports, class identity and module metadata; forced Qt
  masks/restores known preloaded PyObjC modules. GlyphsApp stays FontLab-backed;
  cross-toolkit native/Qt widget interchange is unsupported.
- Add optional platform-marked `cocoa` dependency extra.

- Review correction: recognise real PyObjC runtime/provenance independently of
  installation directory, refuse foreign native impostors, and keep cold
  ordinary helper imports on the explicitly selected Qt route.

- Retained script/plugin contexts now block conflicting later activations and
  scoped requests until every matching handle closes, including failed cleanup.
  README reconciles implemented APIs and qualified native acceptance limits.


## Historical source checkpoint — legacy script Font global

- Supply a current-font snapshot as `Font` in each activation caller namespace,
  matching older menu scripts that use `Font.newTab(...)`. No document yields
  None. Existing conflicting globals are refused before exports are published;
  cleanup preserves replacements made by the script.
- Add regression cases for per-caller snapshots, absent document, collision
  refusal and cleanup. Native script result acceptance remains separately gated.


## Historical source checkpoint — preserve empty editor-tab lines

- Reconstruct empty native editor lines from flTextBlock.symbolList() carriage
  return markers, preserving leading, internal and trailing blank lines that
  getAllGlyphs() omits. No cached script text substitutes for the native state.
- Add three blank-line regressions. Native original-script acceptance is a
  separate gate; existing source suite passes 2294 tests, four optional skips.

## Historical source checkpoint — legacy AskString and unsigned path area

- Provide the legacy `robofab.interface.all.dialogs.AskString` import through
  FontLabSession's existing dialog bridge, retaining RoboFab defaults and real
  answer/cancel/error behavior. Unknown RoboFab APIs remain unsupported.
- Cover ordinary and scoped nested/importlib imports, public script/plugin
  entrypoints and retained callbacks; refuse foreign RoboFab collisions even
  after scoped providers have been cached, with identity-safe cleanup.
- Add read-only `GSPath.area()` using the same analytic fontTools integration
  as path direction, including open closure, reverse winding and stale proxies.
  Curved results may differ from Glyphs' flattened approximation.
- Add22 source regressions; full suite2534passed/1optionalpathops skip.
  Parent-owned native original-script acceptance remains a separate gate.
- Enable requested interactive dialogs in the actual native GUI host's session
  constructor. Direct bridge/custom-host defaults remain explicit; six new
  constructor/control regressions and138covering tests pass. Real modal
  acceptance remains parent-owned.


## 1.2.10 (2026-11-16)

Delegate resource lookup, high-DPI sibling selection, PDF IO and Qt raster/SVG
rendering to App image_resources. Preserve Glyport public signatures/defaults,
AppKit localization and extension order, NSSize values, NSImage/NSCursor policy
and PDF scratch prefix. Require the explicitly unreleased App0.2.27.dev0
prerequisite; no fallback or native acceptance claim.


## 1.2.10 (2026-11-16)

Delegate Node records and ordered UIGraph recording/serialization to App's
ui_graph, preserving public constructors/defaults/Frame JSON, tree/connection
ordering and ID/reference errors. Keep Vanilla Frame, auto/posSize validation
and resolution in Glyport; no duplicated graph algorithm or fallback. Require
the explicit unreleased App0.2.28.dev0 prerequisite; native UI acceptance pending.


## 1.2.10 (2026-11-16)

Delegate generic QMessageBox/QFileDialog construction/execution and retained
box lifecycle to App qt_dialogs. Preserve all Vanilla public APIs/defaults,
callbacks, injected answers, capability/source-location errors, style/parent
conversion and file filters. Require the unreleased App0.2.29.dev0 prerequisite;
normal dependency resolution and native acceptance remain release gates.


## 1.2.10 (2026-11-16)

Share configure/exec/result/deleteLater in App. Glyphs input/file dialogs keep
raw argument/default/answer/cancel/filter policy in Glyport and delegate only
the owned execution edge. Vanilla message/file helpers use the same boundary.
No signals, application loop or native acceptance is introduced.


## Issue120 O1 layout backend candidate

- Share the existing binding-free required/weak linear solver in App. Vanilla syntax, intrinsic hints, nonnegative-size adjustment, geometry writes and compatibility errors remain in Glyport. No new third-party dependency.
- Preserve ordered elimination, free-variable defaults, tolerance and malformed-input errors; translate only generic inconsistent-equation errors at the foreign boundary. Native artifact regression remains pending.


## Issue120 P2 legacy API candidate

- Repair parseable legacy dictionary attribute loads on the selected Glyphs2 route, preserving real custom/native attributes, descriptor failures, receiver evaluation, arguments and live iterators. Modern profile passthrough stays unchanged.
- Add Python2 builtin aliases only to the per-execution Glyphs2 builtins copy; preserve user bindings and imported-helper context.
- Track the wrapper stage/maps and reject reserved helper collisions; version the cache for the new semantics. Preserve original source bytes, comments, encodings and f-string syntax. No runtime dependency added.
- Owned offline controls pass; original/native source workflow acceptance remains pending.

Issue120 S1 candidate: share native text-tab sender ownership, rendered-block lookup and existing activation contexts in App. Preserve App and Glyphs caller-specific font/deadline/restore/error policies. No new dependency beyond the reviewed App API floor; native regression pending.


Issue120 Z3: NSStackView delegates distribution arithmetic to App.stack_layout;
Vanilla VerticalStackView uses the same adapter. Cocoa orientation/insets/hidden
views/natural-size caching, foreign enums and lifecycle remain in Glyport.
Requires unpublished reviewed App>=0.2.50.dev0; use its candidate artifact.
Native stack/render/plugin regression and released dependency gates remain open.


## Issue120 shared key routing Z8

Z8 shares the complete handled-key acceptance/unhandled explicit-native-base mechanism through host-free App.key_events. All five existing consumers remain: App glyph browser and sequence canvas, Glyport Cocoa stepping field, Vanilla list and Vanilla window. Each keeps its original key/owner/callback/error/cleanup policy. No super() protected-slot lookup or new widget inheritance layer.28newApp/12newGlyport tests pass; complete source suites2033App and2996Glyport/4existing skips. All6whole changed production modules exceed80%statements/branches,zero exclusions. Five real offscreen Qt6 controls pass; this does not prove compiled PythonQt/native-font/history/reopen acceptance.


## Issue120 Z12 — shared message-box ownership candidate

Generic custom-button/accessory QMessageBox execution, original-parent restoration,
modeless configuration/retention and hidden-box retirement now belong in App.
Glyport retains Cocoa NSAlert answer injection, style/button numbering/default
policy and Glyphs message text/title/button semantics. Existing Vanilla/Glyphs
modal/file helpers continue using the same shared module. Unreturned prepared
message boxes now delete on setup errors. Parent-restoration failure still
propagates before deleting a box with borrowed children; this preserves the
existing ordering and is not a claim of recovery from invalid native wrappers.

Requires reviewed unpublished App 0.2.56.dev0; normal candidate wheels must be
installed together. No live install or original/corpus execution. Full native
PythonQt ownership/modal/teardown and font/history/persistence regression,
integration/released dependency and all original goal gates remain pending D25.

Z12 rendered Qt5 control exposed a narrow accessory field: the old fixed two-column span clips controls in QMessageBox layouts with more columns. Shared execution now spans the full native grid; a tests-first measured-width regression and retained before/after render cover the correction. Native PythonQt qualification remains pending.


## Issue120 Z14 — shared image presentation candidate

App.image_view now owns generic QLabel clearing, proportional-down, proportional
up/down, unscaled and stretched presentation, point-to-pixel rendering scales,
smooth stretching and display DPR normalization. It accepts an injected Qt
namespace, label and renderer; imports remain host-free. Glyport keeps NSImage
resource/size/retina/SVG/PDF behavior, Cocoa scaling enum/unknown fallback and
Vanilla image sources/alignment/placement. Both current Cocoa/Vanilla paths
share the helper. Source behavior, including zero natural/frame rules and error
propagation, is retained. No new widget or lifecycle framework is introduced.

Requires reviewed unpublished App>=0.2.58.dev0; native PythonQt/image/plugin/
font/history/cache/reopen regression, released dependencies, integration and all
original goal gates remain pending D25. No original/corpus body, live installation
or FontLab driver is used. Owned standalone Qt pixels are not FontLab proof.

## 1.2.10 (2026-11-16)

- Share eight programmatic callback suppression scopes through App.callback_guard; nested setters restore the prior state on all exits. Preserve unrelated Qt signals and existing Cocoa/Vanilla policy. Native qualification is pending.

## 1.2.10 (2026-11-16)

- Centralize exact signal connection tracking and reverse teardown in App for both Cocoa and Vanilla control bases. Preserve every callback/error/owner cleanup policy and unrelated listener. Native qualification remains pending.

## Issue120 resize-event extraction candidate

Share explicit native-base resize dispatch and dimensions forwarding through
App.resize_events. Preserve owner lookup timing, exception identity and foreign
Cocoa/Vanilla policies. Native qualification and released dependencies pending.


## 1.2.10 (2026-11-16)

NSWindow and NSPanel now delegate their existing Qt resize forwarding to the
reviewed App.resize_events helper, completing its fourth current caller.
Owner lookup, dimension evaluation, exception propagation, content/autoresize,
close/delegate and ownership policy remain in their original adapters.
No API or dependency changes; App>=0.2.67.dev0 remains an unpublished reviewed
prerequisite. Candidate Glyport1.0.8.dev30 has source/artifact verification only;
actual PythonQt/native workflow and every integration/release gate remain open.

## 1.2.10 (2026-11-16)

Share the existing explicit Qt property-or-method read through host-free App qt_properties.value. Keep all four original callable paths, metadata, signatures, exception and caller policies. Glyport requires local candidate App>=0.2.69.dev0. Full source, ordinary artifact/consumer and standalone Qt5 gates are recorded in WORK.md; native FontLab and whole issue acceptance remain open.

## 1.2.10 (2026-11-16)

- Move the exact titled Box content-rectangle geometry mechanism to host-free
  App.content_geometry.fit_contents. Keep Glyport's old wrapper and all four
  callers, event/owner order, raw values and exception timing.
- Require candidate App>=0.2.72.dev0 for Glyport. Source/artifact/standalone Qt
  results are recorded in WORK.md; native and original full-goal gates stay open.

## 1.2.10 (2026-11-16)

- Integrate the exact named Qt property reader and Box content geometry helper,
  keeping original adapters, caller policies and cleanup unchanged.
- Exclude local Finder metadata from expected-source artifact comparisons while
  retaining strict wheel/source equality and forbidden archive-member checks.


## 2026-10-21 — N127 shared deferred batch (.108 / Glyport .33)

Move only complete generic zero-timer coalescing and snapshot draining to App. Keep host registry, dispatch-depth refusals, foreign ownership and errors in Glyport. Initial missing-module RED retained; 38 focused controls and eleven exact original AST scheduling traces pass, including duplicates, reentrancy, equality/start/processor failures. Actual standalone Qt5 timer, nested-dispatch refusal, owned-widget destruction and drained-host collection pass. Final ordinary wheel/sdist, full consumer and unchanged original-baseline80/80 zero-exclusion gates are bound in private shared-ui-next-z39 evidence; native qualification remains pending. No canonical/live/native/push work.

## 2026-10-21 — N137 shared table selection (.113 / Glyport .34)

Move complete generic Qt model-row selection and table-range selection/read
mechanics to injected host-free App.table_selection. Preserve distinct native
strategies, original order/duplicates/int conversion/extension/bounds, signal
timing and propagated errors. Keep Cocoa/Vanilla suppression, notifications,
bindings, data and foreign policy in Glyport. Regression-first focused cases,
original AST traces, full source/ordinary archives/current consumers and
unchanged original whole-module80/80 floors with zero exclusions are recorded
in workspace verification/issue-120/shared-ui-next-z42. Native FontLab and
complete preservation qualification remain separate; no live/canonical/push.


## 1.2.10 (2026-11-16)

Combine complete DeferredBatch scheduling with both distinct Qt model-row/table-range selection mechanisms. Existing .106 workflows and all foreign ownership, callback, dispatch and lifecycle policy remain intact. Glyport requires matching reviewed App>=0.2.115.dev0, supplied by explicit local ordinary artifacts; public registry and native qualification remain pending.


## 2026-10-21 — N143 shared editable choice commits (.116 / Glyport .36)

Move complete generic editable-QComboBox setup, Qt5 activation-overload
filtering, user-modified commit acknowledgement and programmatic text reset
to injected host-free App.editable_choices. Both Cocoa and Vanilla combo
paths use it; Cocoa text/path fields use the same existing commit primitive.
Retain callback/continuous/quiet scopes, datasource, conversions, completion,
public APIs, errors and ownership in Glyport. Regression-first source,
original full-method traces, actual Qt signals/lifecycle, ordinary wheel/sdist,
seven consumers and unchanged whole-module80/80 zero-exclusion evidence:
workspace verification/issue-120/shared-ui-next-z43. No native/canonical/push.


N162 combined source candidate: The current combined candidate requires unpublished reviewed fontlab-fontlabapp>=0.2.122.dev0 with Glyport1.0.8.dev37. Deferred batching, distinct table selection and editable-choice extraction preserve all original public entry points and local foreign callback, conversion and lifecycle policy. Earlier candidate floors above record their original checkpoints; normal local-artifact lock resolution is required. Native qualification remains pending.

### N181 shared proportional Qt numeric ranges

- Move four Cocoa/Vanilla callers’ repeated range setup, proportional conversion and rounded setter mechanics into App `qt_numeric`; preserve all clamping, exact caches, tick snapping, callbacks, busy state and error/mutation order in the adapters. App .131 / Glyport .38 remain source/artifact candidates, native qualification pending.

N197: integrate the complete reviewed proportional Qt numeric extraction with all .126 workflows, retaining every prior runtime/menu byte except the four declared Glyport adapters.

N227: share complete native Qt text/checkbox item construction, flags/check-state ordering and table ownership across Cocoa NSTableView and Vanilla List through App.table_items; preserve every existing public consumer and foreign policy.


## N267 — shared Qt color presentation

Extract complete generic color/style/palette/dialog mechanics into App; retain every Cocoa/Vanilla conversion, callback, quiet, ownership and failure policy in Glyport. Native qualification remains pending.

## 2026-10-15 — verified R020/R031 groups archived

- R020 writes at 2e91b34: eight controller-native receipts, 90 assertions,
  and RR4-r020 APPROVE. CR/CRLF/LF feature comments, changed backend instance
  identities and positional-ID removal fixes are included. Identical-content
  replacement with an identical native ID remains a documented host boundary.
- R031 at cefda33: 181/181 XIB/NIB decode, 164 native loads, 17 D8 compiled
  plugin-class blockers and no failed loads; 16 native fixtures and the
  observer-reentry replay pass. RR4-r031 APPROVE. Decode graph connection-loss
  diagnostics remain in the receipts and are not claimed as solved.
- Both branches are now merged in canonical Glyport 1c58099. Fresh source
  regression: 1,209 passed. Final merged-head native drivers, the complete
  32-target matrix, whole-branch review and release candidate remain required.

Evidence: workspace verification/plan-todo-audit-20261015/verified-groups.json;
verification/issue-104/reports/RR4-r020.md and RR4-r031.md; native receipts under
verification/issue-101-ecosystem/evidence/glyport-r020 and glyport-r031.

### Superseded lane ledger

The following snapshot contains both historical completed checks and then-open
work. Its open requirements remain below or in the workspace plan; this is
provenance, not a declaration that those requirements were completed.

# Plan

Authority: parent `issues/101.md` R015–R033, G02 and G05–G07. All Glyphs
compatibility code stays in this repository; shared controls and PySide2
adaptation come from Fontlabapp and Pythonqtside. Completed work is summarised in
README.md "Status". Remaining work, in order:

1. **Persistence (G05).** Done natively on 2026-10-15 (WORK.md): missing master
   layers (R021), R024 save/reopen and R023 Edit > Undo/Redo.
2. **Model breadth (R019–R022).** Done natively (WORK.md 2026-10-15): userData,
   customParameters, features/prefixes, axes/instances, kerning and glyph kerning
   groups, guides, hints, selection, tabs/editor text, document switching, stale
   objects, DOCUMENTOPENED/CLOSED, persisted defaults, OpenType classes (read).
   Open: writes for axes/instances/hints/features, kerning writes inside `undo_group`
   (each is its own native Undo step today), DOCUMENTACTIVATED/WASSAVED (no native
   signal found), default location of the persisted defaults file (owner).
3. **Profiles, adaptation and dependencies (R006, R016, R017, R033).** Done by
   lane L3 (merged 2026-10-15; native drivers 02/03 pass from the merged checkout).
4. **Public entry points (R015, R048).** `run_script` and `verify --manifest` done
   (drivers 04/05). `install_plugin` waits for the L2 merge (`plugins.load_plugin`).
5. **UI translation (R028–R031).** Done by lane L2 (merged 2026-10-15): R029
   remainder (native real events, dialogs, Tabs, Sheet, GSSteppingTextField,
   GSPaletteView), R030 (target/action, outlets, KVC/KVO, four bindings), R031
   decoders and loader. Open: NIB/XIB resources and the remaining view classes.
6. **Plugin protocols and hooks (R025–R027, R032).** Done by L2 and wired in the
   merge: seven protocols with FontLab registrations and deterministic unload,
   after-native-layer editor painting with model layers, `install_plugin`. Open:
   SelectTool and before-native-layer painting (host hooks, R054).
7. **Acceptance and release.** Native corpus matrix run done 2026-10-15 (lane
   L2m, parent evidence `glyport-matrix/corpus-report-20261015T162953Z.json`):
   10 of 32 targets pass every acceptance clause, 12 are blocked with a precise
   classification (D8, host limitations R054, wx backend, DrawBot dependency,
   four targets awaiting a controller decision), 10 fail with named glyport
   gaps. Release candidate 5a9bb78 built and checked (parent
   `release-104/glyport.md`); tagging is the controller's.
8. **Remaining glyport gaps from the matrix** (each names its first failing
   member; WORK.md 2026-10-15 L2m):
   - plain-model: the mekkablue helper package (corpus folder name differs from
     its import name), then Anchor Mover's window controls.
   - filter-dialog: dialog preview, Cancel and Apply, customParameters.
   - reporter: `GSEditViewController.graphicView` (visibleRect, activePosition),
     then layer metrics, `bezierPath` and glyph creation inside paint.
   - palette-nib: `GSGlyph.tags`, `GSEditViewController.textCursor`.
   - general-plugin: `GlyphsApp.UI.GlyphView`.
   - custom-nsview: `vanilla.VanillaBaseObject`.
   - remote-plugin: AppKit `NSBitmapImageRep`/`NSWindow` group (install).
   - external-process: Foundation `NSMutableOrderedSet` group (install).
   - fonttools: `DOCUMENTEXPORTED` (FontLab export event), `GSCallbackHandler`,
     `GSGlyphReference`.
   - private-selectors: AppKit `NSApp`, gesture recognizers, `NSPasteboard`,
     `NSScreen`, `NSTimer`.
   - Undo: each group adds a no-op pre-change entry (FontLab needs the stored
     pre-change state), so a filter shows two Undo entries; this contradicts
     R023's "one Edit > Undo step" (controller to review).

Removed as not feasible (workspace DECISIONS.md D8): native/ABI routes for the 25
no-Python Objective-C bundles and other compiled Mach-O dependencies (R033/G08),
and native outcomes for every corpus file beyond the 32-target matrix and the
entry points exercised above.

# Tasks

- [x] Fix layer lookup for fonts created by FontLab (`.notdef` of an MCP `new_font` font has no layer under the master name); add a test (R021).
- [x] Pass the R024 save/reopen driver: explicit save, independent VFJ parse, missing/unwritable paths, reopen and semantic comparison.
- [x] Native undo/redo through FontLab history with before/after geometry and metadata snapshots (R023). Host limits: node coordinates moved from Python are not restored by Undo; Undo after Redo also reverts redone glyphs (parent evidence glyport-model/crash/R054-*).
- [x] Model breadth: components, guides, hints, kerning, features/classes, custom parameters, userData, instances/axes (R020). Reads natively verified for all; writes for kerning, userData, customParameters and guides. Open: writes for axes/instances/hints/features/classes, kerning writes inside undo_group.
- [x] Application/document behaviour: selection, current tab and editor text, defaults, notifications, document switching and stale objects (R019, R021). Native drivers pass; DOCUMENTACTIVATED/DOCUMENTWASSAVED stay unsupported (FontLab emits no signal for them through its tools; probe_signals.json).
- [x] Version profiles `glyphs2`/`glyphs3`/`glyphs4`: auto-selection from source/bundle metadata, explicit override and ambiguity diagnostics (R006). L3 `profiles.py`; host-free tests.
- [x] Glyphs 3/4 source adaptation and scoped AppKit/Foundation/Cocoa/objc import adapters retained for callbacks (R016, R017). Native driver 02 passes (parent evidence glyport-merge/l3-*.json); native selectors/UI bindings stay with R030.
- [x] Non-Mach-O pathways for required entry points: pyc magic/version checks, ZIP archives, Python dependencies (DrawBot, fontTools/fontParts), external processes and services with error/cancel behaviour (R033, as narrowed by D8). Native driver 03 passes (parent evidence glyport-merge/l3-*.json); installed DrawBot/fontTools/fontParts and remote services not claimed.
- [x] Public `run_script` and `install_plugin` with handles and receipts (R015). Native: L3 driver 04 and the merge end-to-end reporter check (parent evidence glyport-merge/e2e-reporter-run1.json).
- [x] `verify --manifest` CLI over the 32-target regression matrix (R048). Native driver 05 passes (parent evidence glyport-merge/l3-*.json); all 32 corpus targets stay blocked until R049.
- [x] Vanilla remainder: real popup mouse pick, typed-match Return, doubleClick on non-editable List columns; tabs, sheets, dialogs, GSSteppingTextField, GSPaletteView (R029). L2, native.
- [x] objc selectors, outlets and bindings on Qt (R030). L2: target/action, outlets, KVC/KVO, four bindings; native.
- [ ] XIB/NIB decoding into the shared UI graph with resources (R031). Decoders and loader done (78/78 XIB, 103/103 NIB decode; 55/78 and 61/103 load before L2m); L2m added tab views, number formatters, progress bars, Auto Layout constraints (parsed, not solved), symbolic spacing, multi-line titles and untranslated_xib, and bundle images (NSImage, @2x); EOD's XIB and NIB pass natively. Remaining view classes open.
- [x] All seven SDK plugin protocols with real host registrations and deterministic unload (R025–R027). Except SelectTool (no host tool API, R054).
- [ ] Editor drawing: after-native-layer overlays with glyph-local transforms work natively, with model layers (merge e2e check); before-native-layer painting and tools blocked on R054 (R032).
- [x] Native run of the 32-target regression matrix (R049): every target run and recorded natively with R018 receipts; 10 pass, 12 classified, 10 fail with named gaps (parent glyport-matrix/corpus-report-20261015T162953Z.json, at 1aa8553).
- [x] Wheel/sdist checks in FontLab (R053): RC 5a9bb78 built, twine PASSED, sdist 939 tests passed, wheel e2e reporter and initial regression (27/32, 5 blocked by design) from the installed wheel (parent release-104/glyport.md).
- [ ] Release tag for the RC (controller).
- [ ] Matrix gaps: mekkablue helper import (plain-model); FilterWithDialog preview/Cancel/Apply (filter-dialog); GSEditViewController.graphicView, layer metrics in paint (reporter); GSGlyph.tags, tab textCursor (palette-nib); GlyphsApp.UI.GlyphView (general-plugin); vanilla.VanillaBaseObject (custom-nsview); AppKit NSBitmapImageRep/NSWindow (remote-plugin); Foundation NSMutableOrderedSet (external-process); DOCUMENTEXPORTED, GSCallbackHandler, GSGlyphReference (fonttools); NSApp/NSPasteboard/NSScreen/NSTimer (private-selectors).

## 2026-11-01 — Final metadata candidate consolidation

Merged the retained glyph case/script/additional-Unicode and auxiliary-layer
name candidate, preserving the newer history guards and repeated-object transform
preflight. The dependency-note conflict retains Unicode provenance and shared
Qt-list behavior; removed the obsolete fabricated-version build recipe.

Full source gate:5,046passed221skipped, exit0 for tests. The initial coverage
gate failed on empty Protocol bodies. Owner decision D32 permits declaration-only
Protocol exclusion; the gate's regression proves concrete Protocol methods still
require tests. Only ModelBackend is excluded here; backend.py executable coverage
is98.62%, all eight changed runtime modules exceed80%. No source tests skipped
or runtime exclusions added to obtain that result.

Command from workspace root: `rtk proxy sh .metaswarm/quality.sh coverage
"$CHECKOUT" fontlab-glyport`, with CHECKOUT naming this isolated checkout.
Initial gate exit1, declaration-only re-report exit0. Both reports retained in
the workspace consolidation evidence. Native and installed-artifact acceptance
remain separate and open.

## Arabic parameter contracts advanced — 2026-11-01

Working from integrated94d4226 in isolated arabic-parameters-after-consolidation.
Fresh baseline:5118passed149skipped, exit0. Six parameter-object regression cases
first failed, then passed with name/value/active setters and the exact four curly
quote substitutions; focused suite58passed, exit0. Collection reads still return
detached objects: this intermediate candidate is NOT ready for promotion. Five
source-backed ordered collection regressions are red and remain implementation
work: insertion order/live objects, first-active duplicate selection, first-object
assignment/removal, strict indexes and remove-by-first-name. No native claim.

Read-only collection review resolves missing-key deletion as a no-op, strict index
bounds and parent/cache notification. Numeric calibration contains220string/locale
and12NSNumber observations. Retained ARM disproves the decompiler's nil-parse0:
localizedFloatValue returns float2^63, which validation stores without comparison.
Malformed decimal-containing strings can therefore enable the setting. Retained
first attempt is superseded; no generalized parser or dependency was introduced.
Next: coherent ordered persistence/legacy migration with unrelated lib and master
isolation controls, then schema conversion and presentation stage. D30 remains.
Evidence: verification/issue-123/arabic-parameters-after-consolidation/ (external
source worktree and bounded contract/numeric reports).

## Verified compound source gates — 2026-11-02

Twenty new regressions repair a lone-dot production suffix and split-surrogate
text across the fixed11-unit replacement window. Prior module fails4/20; current
module passes20/20, with standalone CoreFoundation reference controls. Complete
plain suite passes6029with3fresh-archive skips. The unchanged quality command
passes5953/79skips and all17changed modules86.46–100%combined; plain tests exercise
its76trace-guard skips. README196-line contract is repaired by soft-wrap changes
without removing tokens or code examples. No test/gate/threshold is weakened.
Independent shared-state public fields remain matched; existing recipes/optional
metadata and native/original scope stay open. Fresh artifacts fail ENOSPC before
creation. Source stays private/uncommitted; no canonical/native/release acceptance.


## Synthesized sort keys and full source recheck — 2026-11-02

Synthesized Unicode records now retain uni0/unj sort prefixes at the audited
signed boundary. Nine new cases fail before repair;55focused metadata checks pass
afterward, including compound capture. Retained ARM/literal checks independently
confirm the branch. Full plain6038pass/3archive skips; unchanged quality5962/79,
all17modules86.46–100%. Independent public/state and64fill-event controls pass.
Source remains uncommitted; fresh archives/ordinary/native gates remain open.


## Preserve UTF8 in archive metadata verification — 2026-11-02

Compare original Core Metadata payload bytes with README bytes. The previous
legacy email text accessor replaced non-ASCII text despite byte-identical correct
metadata. Real archive red7pass/1failure becomes9pass/0skip after the documented
byte-read correction; all metadata/source/link assertions remain. Runtime is
unchanged. Genuine4ee3f76archives build after lossless owned TMP recovery; the
new test source needs fresh committed distributions and separate ordinary/native
qualification.

## Parent-aware source preparation — 2026-11-02

The isolated successor at597f4ec adds an internal manager record/index and custom
merge core. It is not integrated or delivered.67owned source checks pass; three
whole modules100% statement/branch coverage with zero exclusions.247prior metadata
controls pass. Exact rtk proxy replay/exits and source audits are under external
issue123/parent-aware-info-20261102/REPORT.md and record-core-final-commands.json.
The public-selector regressions remain11fail/1pass. Complete real document/shared
selection, bound recursive resolution, six fields, loader/error/lifetime contracts
and full normal gates before source delivery. Native/artifact/promotion holds stay.

## Parent-aware integrated checkpoint — 2026-11-02

Actual public selector chain, document/shared manager graphs, application dispatch,
raw/resolved views and all six stored fields are implemented in the isolated H
successor.170selected tests pass,7new modules100%statement/branch coverage,zero
exclusions. The broader247control run is222pass/25fail, all retained source-gap
refusals; no full-gate/delivery claim. Two scalar empty-source fixtures now bind
the real index; all35old assertion ASTs remain identical. Six independent review
findings repaired with genuine red controls. Custom loader P01-P32 is pinned but
unimplemented. REPORT.md and exact command/log/coverage files are authority.
Uncommitted; no main/canonical/artifact/native/publication action. All holds/full
original scope remain, and both bounded children are terminal.

## Custom GlyphData source core — 2026-11-02

H now implements byte-token/plist parsing, streamed custom mutation, bounded
regular-file reads/ordered file errors and lazy-base materialization.359selected
tests pass7.44s;11new whole modules100%statement/branch coverage,521+204,zero
exclusions. Broader247controls remain222pass/25fail:24unavailable-group refresh
and1physical recipe. No full-gate/source delivery claim. Exact commands/failed
attempts/independent source reviews:parent-aware-info-20261102/REPORT.md.
The public error methods' raw B32@0:8@16^@24 has no out qualifier; None/NULL/error
ABI and public local init/discovery/high-level component/resource finalization
remain open. No speculative tuple facade added. Unknown optional smallcap recipes
now leave independently known fields readable, while recipe access still refuses.
Uncommitted; all artifact/native/canonical/promotion/publication holds remain.

## Public Glyph Info source integration — 2026-11-02

H remains uncommitted. Explicit URL/error selectors use the qualified raw-encoding/
default-PyObjC profile: None/objc.NULL returns bool only. Owned NULL is truthy.
alloc/init/new preserve singleton initialization. Explicit updateComponentsInfos
uses receiver dispatch, ordered component identities/marks/anchors, base strings
and Arabic joining; unknown private fields stay unavailable. Known fresh Unicode
lists, empty suffix lists and source-order lazy materialization repair genuine
reds. No old assertion/resource boundary was waived.

457selected tests pass7.81s;13whole measured modules89.47-100%combined coverage,
zero exclusions. This is not the full-source/every-changed-module gate. Broader
controls remain222pass/25fail, identical failures.32Python files format/headers/
whitespace pass; only2inherited Ruff E731findings remain. Exact evidence:
verification/issue-123/parent-aware-info-20261102/REPORT.md. No commit/push/artifact/
native/promotion claim. Local constructors/discovery, document replacement,
private resources and full original scope remain open.

## Glyph Info discovery source checkpoint — 2026-11-02

Added three class selectors with pinned binary identity: candidate composition
retains P/PInfo/parent/parentInfo and exact-home suppression; per-folder discovery
filters names before resolution; supplied-folder arrays concatenate in receiver
order without deduplication. ARM confirms Objective-C receiver dispatch.
Canonical POSIX/macOS provider preserves scandir order and closes on failures,
skips dot/Finder-hidden entries using OS-only SDK getxattr, resolves ordinary
symlinks and explicitly refuses Finder aliases/unknown metadata. No Foundation
order/alias or full local-constructor parity is claimed. Argument helpers moved
unchanged to keep the manager195lines.539selected pass7.96s;16whole measured
modules89.47-100%,zero exclusions. Original os.getxattr draft/fixture case-collision
failures retained. Broader25failures remain; no full gate/commit/push/native claim.
Evidence:verification/issue-123/parent-aware-info-20261102/REPORT.md.

Issue 201 archive successor: the sdist includes the owned deploy helper/template,
67 behavior-only oracles, the portable 67-target manifest and three unmodified
GetGo fixtures with upstream licenses and byte provenance. The frozen original
manifest remains source-only; only its two private provenance locations differ
in the portable successor. Offline helpers require no workspace; native execution
requires the real workspace and its safety runner. Wheel runtime is unchanged.
Verification results are retained separately; native/original-corpus acceptance remains open.

Archive successor verification: the unchanged full D20 gate passes7289tests
with one optional pathops skip and all28complete modules above80%combined.
Ordinary archive-context/source-origin acceptance remains a separate claim.

Archive identity follow-up: missing project .git selects actual PKG-INFO
independently of an ancestor workspace marker. A dedicated regression retains
the demonstrated nested-archive case; actual Git-source identity is unchanged.

Outside-workspace harness closure: five mocked-native tests now explicitly
stub their native workspace boundary alongside their fake Run/transport.
A direct regression retains refusal before transport at both native entrypoints;
no production guard, native watchdog or source-origin assertion was changed.

## 2026-11-06 — Private source/build documentation candidate

Added five core website pages and all nine maintained guides, preserving the complete compatibility catalogue and lawful Apache/Unicode/CC0 attribution. Updated precise source-doc sdist paths and affected guide/distribution tests; the packaged normative index preserves relative guide navigation. Added the separate hash-locked every-main source/output workflow while retaining all runtime, dependency and native boundaries. Private Pages operations remain held.


## 2026-11-07 — Exact frontend notices and English search assets

Added exact upstream frontend notices and source-map provenance for the existing MaterialX 10.1.8 payload. Explicit English configuration and a small build hook reject language, corpus, reference, asset-set or hash drift before omitting the 35 unused language helpers. All nine retained core assets, original product legal files, guides, catalogue rows, media, runtime and dependency/build locks are preserved.

The strict site build and all 35 documentation tests pass. The complete new hook has 100% statement/branch coverage; real Git staging, checkout and archives preserve exact legal bytes. An independently installed matching lock reproduces all 62 output bytes and modes. Existing immutable source/output, epoch, concurrency and full-parity workflow checks remain active. Browser and independent review evidence are separate from these local checks.

Private Pages configuration, grants, requests and publication remain owner-held; this source follow-up adds none.
No product release or installation is claimed. Prior ordinary artifacts remain bound to their recorded revisions; a later Git revision changes genuine hatch-vcs metadata. Full current source archives include these documentation additions; no unchanged-sdist or whole-wheel identity is asserted. Native acceptance and owner installation remain separate.


## 2026-11-07 — installed icon path-tuple inventory refinement

The current HTML/CSS contains 45 distinct ordered SVG path tuples. A complete scan of the four installed MaterialX icon families finds 43 exact installed matches and two unmatched Lucide tuples, refining the earlier known-candidate inventory. The additional installed match is the Font Awesome version caret-down. Its existing CSS header and full notice retain Font Awesome Free 7.1.0, Fonticons and CC-BY-4.0 icon attribution. The official NPM caret SVG has different raw path bytes; no unmodified-primary SVG, whole-geometry or optimizer-recipe equivalence is claimed. The two unmatched Lucide tuples retain their pinned SCSS source attribution.

A new actual-output regression derives these counts and checks installed matches, unmatched CSS references and the caret header. It fails against the prior 42 count and passes with the corrected metadata. All 36 current documentation tests pass; full strict and independent exact-lock builds match every output byte and mode. Only the legal paragraph, corresponding inventory and legal search row change in the site. Runtime, packaging, generators, vendor assets, full notices, existing guidance and the Fly search fix remain exact. Fresh browser verification and independent review are recorded separately. No private Pages operation, delivery, installed-product upgrade or native acceptance is claimed.

## 2026-11-09 — Issue 242 shared-pens main candidate

Model drawing uses the shared fontlab-python-pens adapters (Issue 235 commit cc89da7, fast-forwarded). The dependency is declared as `fontlab-python-pens>=1.0.0` with a sibling-checkout `[tool.uv.sources]` entry, like the other fontlab-* dependencies; `uv.lock` is refreshed. Source tests only: 7,416 passed, 9 skipped on Python 3.11. No native acceptance is claimed.

## 2026-11-10 — categorized package demos

- Add three functional Scripts-menu demos using detached package data and existing functional category names.
- Include Scripts in source distributions; document optional Fly/App snapshot reporting and host-free result access.
- Add real API result, menu wiring and report-failure tests. Native UI acceptance is separate from offline execution.

## 2026-11-10 — demo documentation index parity

Mirror the Scripts demo README paragraph in the authored website index, preserving the existing complete README/index oracle. Link to the demo guide at its delivered source commit. Keep the concurrent shared-installer and agent-guidance changes intact; runtime, dependency configuration, tests and generated documentation are unchanged by this correction.
