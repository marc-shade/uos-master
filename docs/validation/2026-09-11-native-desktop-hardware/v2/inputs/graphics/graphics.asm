; Isolated library harness. The later app includes the same source in its core.
.include "api.inc"
* = $6000
.include "graphics-core.inc"
.include "text-core.inc"
.cerror * > $6c00, "graphics library exceeds its twelve-page test allocation"
