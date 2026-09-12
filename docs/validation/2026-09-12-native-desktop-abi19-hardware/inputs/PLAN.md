# One ABI 1.9 desktop hardware qualification

Use the exact signed a90fadf build and integrated observer. The shared VICE
workflow passed 66 captures, 101,274 payload bytes and 647 paused batches.
The physical workflow checks the running native image, boot and selected
desktop surfaces, Calculator 12+30=42, Editor C128 text/discard, Files,
selection retained after app returns, final workspace, free heap and mode.

The original idle legacy deployment, drive mounts, settings, DOS paths and
borrowed controls are recorded before native boot. Prepare and verify the
private restoration loader before switching disks. Use one native reset and
the established 60-second quiet boot interval.

Every RAM write retains an exact accepted-range receipt; captures use bounded
pause/resume batches including mode snapshots. Do not accept differing or
short readbacks. Retain all first observations and any initiating error.

Restore the original deployment after the workflow, including on capture
failure. Completely read back both owned temporary files before deleting them,
confirm their absence, and check original drives/settings/controls/liveness.
If restoration or readback fails, retain the recovery resources and report.
The exclusive physical-attempt journal permits only one invocation.

Do not edit frozen inputs or run any other workflow against this C128 while
the attempt is active. Further development uses a separate source tree.
