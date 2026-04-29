# Bridge Notes

Primary backend: Tart. It supports automation-oriented Apple Silicon macOS VMs and headless `run --no-graphics`.

Fallback backend: UTM. It supports `utmctl start --hide`, `--disposable`, `clone`, `exec`, guest file push/pull, and IP lookup. UTM's source also exposes SPICE input commands, but the Codex bridge should prefer the guest agent for performance.

Guest agent: a Python HTTP server backed by a Swift helper. The helper uses `screencapture` for PNG frames, CGEvent for input, and NSPasteboard plus Command-V for reliable text entry.
