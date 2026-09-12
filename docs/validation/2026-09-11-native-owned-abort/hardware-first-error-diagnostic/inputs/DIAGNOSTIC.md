# First native read-error diagnostic

This private harness uses the unchanged owned-abort kernel and disk. It performs
the existing Ultimate editor workflow with three private source fixtures and
two saved outputs. After the save and existing-file checks, it repeats the
large-file reopen through DOS context 2 six times.

Immediately before those reopens, the harness verifies the loaded editor's
`JSR ed_close_owned` at `$8a3e`, then temporarily replaces those three bytes
(`20 dd 88`) with three NOPs (`ea ea ea`). This affects only automatic release
on the Open rollback path. The pending document is still discarded and the
editor returns to its input loop. The initiating file/DOS/transport status can
then be observed through the native CPU capture before another file command.
The original instruction is restored and verified in a finally block before
the outer hardware harness restores the deployed desktop.

This is instrumentation, not a product fix or an unmodified-product
qualification. Leaving carry unchanged may preserve the editor's close-error
message even though this diagnostic deliberately deferred the close. The raw
file/DOS/transport state is the evidence of interest. If a handle remains open,
the exact file must be independently verified before its eventual recovery.

Six CPU workflows pass, including an unpatched short-read negative control,
short read, DOS error, overlong packet, timeout and normal success. The original
instruction and all file/heap ownership are restored after each modeled case.
These checks establish the instrumentation's behavior, not a physical cause.

Kernel SHA-256:
`45281b86a55f93c6402a7b0159075148d0f19086471c504bf859332c0b25e63d`.
Product images and assembly are unchanged. The main workspace and the private
display kernel are not modified by this diagnostic.
