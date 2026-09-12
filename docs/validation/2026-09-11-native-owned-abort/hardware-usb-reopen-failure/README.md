# Physical USB saved-file reopen interruption

This is a failed run of kernel `45281b86a55f93c6402a7b0159075148d0f19086471c504bf859332c0b25e63d`
from `/var/tmp/arc-scratch/uos-hardware-native-directories-8i8_6075`.
The executed 132-file harness is retained in `run-harness`, including the
physical overrides checked against the live harness before recovery edits.
The images and native sources are retained in `native-build`.

Navigation through ordinal 256, calculator export, app launch failures, picker
module loading, small-file save, large-file edit and the editor's complete
66,056-byte save verification passed. The later reopen through DOS context 2
failed with editor status 9, no displayed document and a retained file owner.
The file descriptor records position 64,000 and 2,056 bytes remaining. The
transport snapshot was taken after attempted CLOSE, which can overwrite the
initiating read status; it does not establish the first fault. The direct UCI
register observation is retained but is not independently CPU-verified.

The desktop restoration completed and all build images remained unchanged.
The host recorded one read-only RAM observation retry and one TCP connection
retry before any request bytes were sent. No host RAM write had uncertain
acceptance. These facts do not establish a connection between host observation
and the native read failure.

The first cleanup preflight stopped before any deletion because DOS context 2
still held the read handle. Read-only inspection identified `LARGE COPY.TXT`
with the expected 66,056-byte extent. All of those bytes were compared through
the retained handle before a checked CLOSE. The cleanup then independently
compared all twelve owned files, totaling 332,431 bytes, and removed the fourteen
exact owned file/directory paths. Both DOS paths, settings, mounted drives and
the live desktop were verified afterward. No host write had uncertain
acceptance. The original failed report is unchanged; this recovery does not
qualify the failed attempt. Physical IEC has not been started for this candidate.

The recovery harness and its 36 specific scope/fault checks are retained in
`recovery-harness`; the fourteen original cleanup checks also still pass. A
lost seek/CLOSE reply is never replayed automatically. Changed contents prevent
CLOSE and all deletions. The original stopped preflight, subsequent metadata
inspection and successful recovery each retain their own journal.

Inspection of local Ultimate FPGA source shows that command submission changes
the state to busy in the same control-write handler. A delayed firmware
acceptance alone therefore does not support the proposed transient-idle
explanation. This source inspection does not determine the physical cause.
