# Earlier development failures

These reports precede the frozen qualification images and are excluded from
the twenty passing CPU suites. The USB dispatcher failure led to retaining
the app allocation handle separately from the closed source-file handle.
The redraw failure led to emitting reverse-off only after the caret cell,
which bounds output at width+3 console calls per field. Their image hashes
identify the earlier development kernel. The frozen package reproduces the
later prompt-spacing failure separately in `cpu-initial`.
