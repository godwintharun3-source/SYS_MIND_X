# Release Acceptance Gates

A feature is not complete until all relevant gates pass.

1. Functional: requirement implemented and demonstrated.
2. Tests: unit/integration/regression tests run with real results.
3. Security: trust boundaries, permissions, data handling and threat model reviewed.
4. Reliability: error paths, timeouts, partial failures and recovery tested.
5. Platform: capability is labelled supported, partial or unsupported for each tested platform.
6. Documentation: operation, limitations and recovery procedure documented.
7. Evidence: test artifacts, logs with secrets redacted, screenshots or reproducible steps recorded.
8. Human review: user inspects code diff and confirms day completion.

No unsupported capability may be labelled complete. No file scan may be described as a guarantee of safety. No user app update may be included in the OS updater.
