# Separate SDK example evidence

The native system images remained frozen while this example was added.
`source/` retains the five example files and its CPU workflow test, with their
SHA-256 hashes. `build/` retains both sealed PRGs, listings, symbols and the
validated manifest/hash report. `cpu-report.json` records 15 passing workflows
on the same frozen kernel.

These are additional SDK checks, separate from the original 22 native CPU
suites, ten emulator workflows and 51 distinct host fault checks. They cover
modeled IEC formats and Ultimate contexts, complete console screens, warm
calls, original-source reload, counter wrap, explicit retry and ownership
cleanup. The SDK example has no separate physical qualification claim.

With Python plus `py65`, `64tass` and the same C128 ROM fixtures installed,
[verify-sdk-example.py](../verify-sdk-example.py) reconstructs the source tree
in a temporary directory, using this archive's original harness and frozen
kernel. It rebuilds both example PRGs, repeats all 15 workflows and compares
the complete report and program bytes. It uses no live repository source,
network or cartridge access.
