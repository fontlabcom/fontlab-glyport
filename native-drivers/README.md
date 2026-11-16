---
this_file: native-drivers/README.md
---
# Runtime native drivers

Run with a **Python 3.11** environment containing `fontlab-remopy` and a running
FontLab 9. These drivers belong in the package checkout; copy evidence separately.
Supply the worktree explicitly. Keep `driver_common.py` beside the four drivers.
The controller must run every native command through
`verification/issue-104/fl-native.sh --lane glyport-runtime -- COMMAND`.

```bash
python native-drivers/native_02_adaptation_callbacks.py --repo /path/to/worktree --output /new/evidence/02.json
python native-drivers/native_03_dependency_routes.py --repo /path/to/worktree --output /new/evidence/03.json
python native-drivers/native_04_public_handles.py --repo /path/to/worktree --output /new/evidence/04.json
python native-drivers/native_05_manifest_verification.py --repo /path/to/worktree --manifest /path/to/corpus-regression-matrix.json --output /new/evidence/05.json
```

Outputs refuse overwrite. Each driver purges `fontlab_glyport` from the host's
module table **before importing**, retains owned contexts across short Remopy
calls, then closes them and restores the host import path. Run after previous
Glyport handles have been closed. Each measured check asserts a native duration
below two seconds; process/HTTP calls use subsecond timeouts. Nothing creates
fonts, preferences, menus, or Output-panel content. Driver 04 creates and closes
one owned Vanilla window. Scratch files are
owned and removed. Modern adaptation caches used by public handles persist in
the system temporary `fontlab-glyport-runtime-cache` namespace for receipts.

- **02:** Glyphs 3/4 byte-identical source/map caching, scoped Cocoa/objc value
  imports, callbacks invoked in a later host call, restored host module entries,
  and rejection after close. Native selectors/UI bindings remain unsupported.
- **03:** host-generated 3.11 bytecode execution and rejection of foreign magic;
  ZIP source imports despite a misleading filename; DrawBot's explicit rendering
  backend requirement and fontTools/fontParts route detection; process output,
  nonzero exit, timeout, cancellation; controlled local HTTP success/error/cancel.
  It does not claim installed DrawBot/fontTools/fontParts or real remote service
  acceptance. Default HTTP reads enforce one overall deadline and check
  cancellation between incremental socket reads, including header reads.
- **04:** default FontLab GUI gateway, public script handles, delayed callbacks,
  snapshot receipts, a real owned Vanilla window/button, and idempotent close.
  A synthetic plugin registrar proves
  registration/teardown ownership; a missing registrar is a typed failure.
  SDK menus, filters, tools and UI registration await the protocol workers.
- **05:** metadata-only report of all 32 actual matrix rows, deterministic JSON,
  the CLI, and an injected native stage called once per row. All corpus targets
  remain **blocked**: testing the verifier in FontLab is not corpus acceptance.

## Integration seams

`ExecutionOptions(source_root, dependency_paths, receipt_path)` is the public
typed options record. Relative entry/dependency paths resolve against the source
root; ZIP entry points require `__main__.py`/`__main__.pyc`. Ordinary directories,
bundles and package-relative imports remain owned by `ExecutionContext`.
`run_script`/`install_plugin` accept an optional explicit `ExecutionHost` for
GUI dispatch, current-font lookup, per-context adapters and hook registration.
The default FontLab gateway accepts an `OwnedPackage` as `font`; other font
types need an adapter factory. It rejects off-main-thread calls; dispatching
from a worker requires an injected GUI dispatcher.

Handles expose `id`, `state`, `windows`, `context`, snapshot `receipt`, `wrap`,
`close`, and `invalidate_document`; plugin handles add `unload`. Failures are
re-raised with `.handle`/`.receipt` attached after cleanup. Snapshot receipt
files are private (`public=False`); adapt source/map identities before publishing.
Document invalidation is explicit: the orchestrator must wire its close event.

The default native host now wires the existing Qt Vanilla provider with wrapped
callbacks and window-close hooks. `handle.windows` follows the provider's current
open windows. Plugin registration imports `fontlab_glyport.plugins` lazily and
calls `register_plugin(context, assessment) -> PluginRegistration`. This is the
protocol worker's integration contract. A missing module or callable raises
`UnsupportedCapability` naming `fontlab_glyport.plugins.register_plugin`;
dependencies failing inside an existing registrar are not misreported as absent.
Unload and invalid-registration rollback both run inside the execution context.
Adaptation warnings, including their original locations, remain in snapshots.

Owned scripts importing `subprocess` receive a scoped `run` adapter requiring
an explicit timeout and captured text output. `context.cancel()` signals its
cooperative cancellation; timeout/cancel kills and reaps the process group on
macOS. Cleanup drains for at most 50 ms, then closes pipes and waits up to 100 ms
for the killed direct child; an escaped descendant cannot hold cleanup at EOF.
Completed negative signal exits obey the normal `check` contract.
`Popen`, shell invocation and other process options require an injected
provider and otherwise raise a located unsupported-capability error. Host-held
subprocess modules remain unchanged. HTTP helpers require an explicit timeout;
they never start or contact an endpoint implicitly.

`verify_manifest(path, runner=callable)` and CLI
`verify --manifest MATRIX --host fontlab --output NEW.json --runner module:function`
load only matrix metadata. Runners return a status and nonempty evidence strings;
non-applicability additionally requires `requested=False`, `role`, and `reason`.
Each acceptance runner is responsible for its target's actual assertions.
CLI exits: 0 all passed/exempt, 1 failed, 2 blocked/unexecuted. No runner means
all 32 targets stay blocked. The verifier never reads or executes corpus paths.

## Host-side native CLI

In a host-side environment containing `fontlab-remopy` and this package:

```bash
python -m fontlab_glyport verify --manifest MATRIX.json --native --output NEW-DIRECTORY
```

Run that command through `fl-native.sh` as above. Without `--output` it creates
`glyport-initial-regression/report.json` and `receipts/` in the working directory.
A JSON output path instead creates a sibling `<stem>.receipts/` directory.
Both formats refuse existing outputs. No pyproject dependency was added;
missing Remopy gets an explicit `DependencyUnavailable` diagnostic.

The report scope is **initial-regression**. Each attempted row gets a validated,
private R018 receipt, including blocked and failed cases. Native receipts identify
the owned embedded fixture's hash and observed host environment. Target metadata
stays in the report; `corpus_acceptance` remains `unexecuted`, and receipt target
capabilities remain `unexecuted`. Passing an owned fixture does not pass the
pinned corpus target. Compiled/protocol/backend requirements outside these
fixtures remain blocked with evidence. Custom runners emit validated embedded
receipts too, including on exceptions; cancellation preserves remaining rows.

The built-in runner uses one short Remopy call per case, purges stale Glyport
modules before importing, restores the host import path, and closes owned
resources before returning. Each check enforces a two-second native budget;
external processes use a 600 ms deadline with bounded cleanup. No corpus source
is read or executed, and there are no retries after unknown transport outcomes.

Driver bootstrap refuses any existing canonical Glyport module or Fly gp alias because it cannot prove ownership of existing resources. `Driver.call` reuses its admitted state/key; a later independent bootstrap may refuse. No automatic unload or host restart is performed.
