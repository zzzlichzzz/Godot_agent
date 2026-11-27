# ADR-0089: relative editor/resource references fail before engine IO

Date: 2026-11-22. Narrow extension of SEC-T1-OVERLAY/ADR0086–87.

The quoted-reference scanner must not skip relative editor plugin configurations
or executable-looking resource paths simply because they have no URI/drive prefix.
Native outside-read/execution is not claimed. Six new bounded spy cases establish
the required pre-engine refusal without executing an external plugin/script.

Classify parent/dot-relative paths, backslash/escaped references and code/config
filename suffixes as references. Non-shader references must be canonical readable
res:// paths; compiled .gdc is an executable dependency too. Keep native engine
argv, SDK behavior, safe-asset materialization and the sole B executor unchanged.
Code/config-looking scalar strings, escaped settings and parent-relative node
strings can therefore fail closed: explicit safety gap, not semantic parity.

Require genuine six-case RED→paired same-ID GREEN, current mutation of this
discriminator, fresh native/B comparisons/full/gates/selfchecks/clients and
inventory-bound readback before seal LAST/ZIP. No live/provider/browser claim,
unsafe native experiment, global security waiver or old assertion weakening.
