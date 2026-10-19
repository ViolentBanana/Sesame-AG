# Bounded task execution regression

All automatic modules, including Forest, Farm and Sports, use the configured per-module timeout. Waiting for a concurrency slot does not consume that timeout. On timeout or cancellation, the runner requests cancellation of the separate ModelTask scope and waits for cleanup. If cleanup does not finish within the existing five-second stop timeout, the current round fails instead of starting further batches. Coroutine cancellation cannot forcibly terminate blocking native calls.

The upstream 0.2.5 dependency-aware scheduling and SUCCESS/FAILED/SKIPPED/CANCELLED/DEFERRED outcomes are retained. Failed, cancelled and deferred results must not count as success or mark all daily tasks complete.

Run `JAVA_HOME=/path/to/jdk17 python3 tools/check_task_timeout.py` after a Gradle build has populated the Kotlin compiler cache. The check executes extracted production methods with real coroutine jobs; Android and business tasks are stubbed. It covers timeout cleanup, following-task progress, external cancellation, incomplete cleanup and preservation of upstream non-success outcomes.

Executor recovery additionally retries an Active executor whose execution prerequisites are not yet available. Every retry retains consent, identity, account-session and offline guards. This does not disable OEM process management or guarantee overnight delivery.
