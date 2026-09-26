# Native AES component

The AES is the shared service behind the [GEM layer](GEM-LAYER-DESIGN.md):
alerts, events, menus, windows and desk accessories will be added to it in
later steps. This page covers what exists now (step 1): a persistent bank-1
component that apps load once and later apps attach to.

## What persists

`AESVC.PRG` is an NBK1 image loaded at bank-1 `$9000` (`AE_BASE`) and owned
by owner 30 (`N_AESOWNER`). App cleanup releases only owner 32, so the image
and its state stay resident after `N_EXIT`. The next app attaches to the same
bytes instead of loading them again. `ae_unload` frees the image and returns
its pages. The current component is one page.

The component's identity block sits at image offset 32: `NAES`, major and
minor version, capability bits. The AES version is independent of the kernel
ABI (`src/native/aes-api.inc`).

## Client

Include `api.inc`, `aes-api.inc` and `aes-client.inc` in the retained app
core. The client is a second, block-scoped instance of the
[banked executor](NATIVE-BANKED.md) configured for owner 30 at `$9000`, so
it coexists with an app's own `$6000` component.

| Entry | Contract |
|---|---|
| `ae_attach` | Adopt the resident AES and register this app. Carry set with `A=N_BADHANDLE`: none is resident. `A=N_BADIMAGE`: the resident image failed validation. |
| `ae_load` | Load `AESVC.PRG` from the owner-32 stream in `N_FHANDLE`, then register. `ae_stream_taken` is nonzero when the loader took the stream (it then closes it); zero means the caller still owns it. A failed load frees any partial image. |
| `ae_call` | `A` = operation, packet in `N_BUFFER`; returns the AES's `A`/carry. |
| `ae_detach` | Forget the attachment before exit; the AES stays resident. |
| `ae_unload` | Free the AES image and its pages. |

Register (`AE_OP_ATTACH`, 0) passes the executor's app cookie (app slot and
allocation generation). The reply in `N_BUFFER` is: major, minor,
capabilities, 0, attach count (word), distinct app count (word), a byte that
is 1 when this attach changed the foreground app, and the current cookie.
`AE_OP_STATUS` (1) returns the same reply without registering.

## Validation on attach

Attach finds the single owner-30 allocation at bank 1 page `$90` in the
handle table and reads its first 40 bytes through the heap service. It
requires the NBK1 header rules the loader enforces (format, ABI, flags, bank,
page count, entry range, exit stub, zero reserved bytes), the `NAES` identity
and major version, matching page tags, and a nonzero callback import. The
loader writes that import only after the body, CRC and source close have all
succeeded, so a zero import marks an interrupted load. The image cannot be
CRC-checked on attach because the import is live state; a stray write that
keeps the header intact is not detected. Attach then points the import at
the attaching app's executor.

## Example and test

`examples/native-aes` builds `AESDEMO.PRG` and `AESVC.PRG`. The demo attaches
or loads, shows the counters on both screens, and offers status (Return),
exit leaving the AES resident (Esc) and unload (U).

```sh
~/.venvs/uos-tests/bin/python -B tests/ci_native_aes.py --report /tmp/aes.json
```

The test runs several apps in one machine and checks:
- the first app loads the component, which survives its exit;
- a second app attaches without loading and sees the persisted counters;
- unload returns every page;
- a wrong identity and a zero callback import are refused with `N_BADIMAGE`;
- an occupied `$9000` range is refused cleanly;
- corrupt and missing `AESVC.PRG` files leave nothing resident.

Not yet verified: the AES alongside VDSVC in one app, and physical hardware.

The [qualification record](validation/2026-09-25-native-aes-persistent/README.md)
keeps the reports and the byte-identity evidence.
