# Focused second-context read diagnostic

The physical diagnostic completed successfully on the owned-abort candidate.
Six repeated opens of the saved 66,056-byte document through DOS context 2
returned success, with zero file, DOS and transport errors in the preserved
samples. The intermittent failure did not reproduce. This result does not
identify its cause or qualify the full unmodified USB browser/picker workflow.

The kernel and disk are unchanged from the failed full USB run: kernel SHA256
`45281b86a55f93c6402a7b0159075148d0f19086471c504bf859332c0b25e63d`.
This smaller workflow opens/edits/saves documents through the native Ultimate
backend without the full USB app/browser and large-directory picker stages.

Immediately before the repeated opens, the harness replaced the editor's
rollback `JSR ed_close_owned` at `$8a3e` (`20 dd 88`) with three NOPs. A failing
Open would then retain its first I/O status until the CPU observer read it.
The six-model probe suite includes an unpatched short-read negative control:
ordinary cleanup overwrites its original transport status, whereas the patched
probe retains short-read, DOS, overlong-reply and timeout errors. The patch is
instrumentation, not an installed product change or a proposed error fix.

CPU captures verify the original bytes before installation, the patched bytes,
and restoration of the original bytes afterward. All six actual opens took the
normal success/close path. Their document metadata and both visible editor
screens match; the harness did not recapture and compare every byte of all six
in-memory documents. Separately, all five closed fixture/output files were read
in full and compared, including the saved 66,056-byte file. Both temporary
inputs were also read and compared before deletion.

The run returned all heap/file ownership, preserved both 8 KiB workspace
patterns and 256 function-key bytes, restored both DOS paths, original drives,
settings and the deployed desktop, and removed its owned private directory
and temporary inputs. No uncertain host write or connection retry occurred.
Temporary-input removals were confirmed by file-info 404 responses; private
file/directory deletions used acknowledged DOS commands.

The exact 257 frozen inputs, probe model source/results and instructions are
in `inputs/`; all physical reports, raw captures, readbacks and logs are in
`run/`. The offline auditor checks the patch, original observer build, native
boot bytes, CPU observations, all editor screens and complete file proofs:

```
python3 verify.py
sha256sum --check --quiet SHA256SUMS
```

`verify.py --record` writes `verification.json`; otherwise it is read-only.
This directory is a sealed diagnostic subarchive. The parent owned-abort
qualification remains open pending the full unmodified USB/IEC runs.
