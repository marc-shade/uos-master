; CPU-only document harness. The real editor includes the same model.
.include "../src/native/api.inc"
* = N_APPBASE
.include "../src/native/document.inc"
document_probe_end:
        .cerror * > N_APPBASE+$4000, "document probe exceeds app reservation"
