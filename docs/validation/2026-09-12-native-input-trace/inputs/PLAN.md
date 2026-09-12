# Bounded native input trace

Base: signed `81a21418a0a5bde52f78935945bbce514d6ff7ae`; runtime images unchanged.
This is a diagnostic of uncommanded input, not physical app qualification.

The host verifies an idle native desktop with the original keyboard gateway,
ROM key-check callback, keyboard input channel, idle file service and free
bank-0 pages $50..$57. It borrows those eight pages under the exclusive idle
diagnostic. No heap allocation is claimed. The page map must remain unchanged.

A temporary N_KEYIN wrapper calls the original implementation, records each
nonzero result, and returns zero to the desktop. This holds keys during the
test without starting a redraw or app. N_KEYS/N_LASTKEY retain actual consumed
input. Neither counter is reset or restored by the diagnostic.

A 32-byte mapping gate at $3fc0 records the ROM key-check callback before
chaining to its original address. The gate saves registers, flags and MMU;
its body lives in the borrowed pages. The existing 435-byte IRQ observer ends
before the gate; its command region starts at $3ff0. Its borrower comparisons
remain unchanged. Captures that encounter input still fail and keep their
first bytes, even though the desktop holds the key.

The first 20 records are retained; later records increment a saturating
overflow count without replacing evidence. Foreground and scan callbacks
use separate scratch records. Entry state may precede the key's arrival; an
empty before-buffer does not prove corruption. The scan stream is necessary
to distinguish ROM production from the known buffer-insertion test fixture.

Each record holds type/key/phase, flags, MMU, jiffy time, KERNAL key-table and
queue state, ten buffer bytes, function-key data, native input counters and
CIA port samples. Scan records also retain original X/Y, extended keyboard
lines and CIA direction registers. Reading these ports does not acknowledge
interrupts; neither CIA interrupt-control register is read or written.

Physical phases: 30 seconds of CPU execution without host requests, twelve
pause/read/resume batches, then at most six normal IRQ captures. There is no
scripted physical input and no modem/configuration mutation. Any capture
rejection propagates after trace restoration; it is not counted as a pass.

The host detaches both hooks, allows bounded in-flight routines to finish,
restores and compares all borrowed bytes, then the existing hardware harness
restores the original desktop, drives, nine settings bytes and DOS paths.
It independently verifies and removes its two owned uploads. A trace read or
decode failure still attempts hook and code restoration; raw bytes are saved
before decoding. The frozen runner admits exact image hashes and uses an
exclusive physical-attempt file, so it cannot be rerun accidentally.

Software checks execute the real native/KERNAL GETIN, check both mapping-gate
contexts, interleaved producers, bounded records and flag preservation. Four
host controls cover a normal lease, occupied-page refusal, partial write and
corrupt journal. VICE uses XTest to reach the real ROM matrix scanner, explicit
buffer insertion as a separate control, an input-induced capture rejection,
full restoration and normal desktop navigation, then the shared physical
workflow. The X fixture alone temporarily disables key repeat to make its
synthetic holds deterministic at accelerated emulator speed; physical key
repeat configuration is observed unchanged.
