#!/usr/bin/env python3
"""Execute the production single-task runner with real coroutine jobs and short deadlines."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
ROOT = Path(__file__).resolve().parents[1]
CACHE = Path(os.environ.get('GRADLE_USER_HOME', Path.home() / '.gradle')) / 'caches/modules-2/files-2.1'
source = (ROOT / 'app/src/main/java/io/github/aoguai/sesameag/task/TaskRunner.kt').read_text()
method = source.split('    private suspend fun executeSingleTask(', 1)[1].split('    private fun scheduleNext()', 1)[0]
legacy = source.split('    private data class LongRunningJob(', 1)[1].split('    /**', 1)[0] if 'private data class LongRunningJob(' in source else None
code = r'''
import kotlinx.coroutines.*
import kotlinx.coroutines.sync.Semaphore
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.ConcurrentLinkedQueue
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicInteger
class Field<T>(var value: T)
object BaseModel { val taskTimeout = Field<Long?>(40); val energyTime = Field("") }
object ApplicationHookConstants { fun isOffline() = false }
object ManualTask { var isManualRunning = false }
object TaskCommon { const val IS_ENERGY_TIME = false; fun update() {} }
sealed class AccountSessionCheck { data object Current : AccountSessionCheck() }
object Log { fun record(t: String, m: String) {}; fun error(t: String, m: String) {} }
open class ModelTask(val duration: Long = 200, val cleanup: Long = 0) {
    val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
    lateinit var job: Job
    val started = CompletableDeferred<Unit>()
    var stopped = false
    var finished = false
    var refuseWait = false
    fun getName() = this.javaClass.simpleName
    fun addRunCents() {}
    fun startTask(force: Boolean, rounds: Int): Job {
        job = scope.launch {
            try { started.complete(Unit); delay(duration) }
            finally { withContext(NonCancellable) { delay(cleanup); finished = true } }
        }
        return job
    }
    fun stopTask() { stopped = true; job.cancel() }
    suspend fun stopTaskAndWait(timeoutMs: Long = 5000): Boolean {
        stopTask()
        if (refuseWait) return false
        return withTimeoutOrNull(timeoutMs) { job.join(); true } ?: false
    }
}
class AntForest : ModelTask()
class AntFarm : ModelTask()
class AntSports : ModelTask()
class Runner {
    val TAG = "test"
    val DEFAULT_TASK_TIMEOUT = 40L
    val successCount = AtomicInteger()
    val failureCount = AtomicInteger()
    val skippedCount = AtomicInteger()
    val taskExecutionTimes = ConcurrentHashMap<String, Long>()
    val taskConcurrencyLimiter = Semaphore(1)
    val longRunningTaskLimiter = Semaphore(1)
    fun runSessionCheck(): AccountSessionCheck = AccountSessionCheck.Current
    fun runSessionCheckDescription(check: AccountSessionCheck) = "session changed"
    suspend fun run(task: ModelTask) = executeSingleTask(task, 1)
'''
if legacy:
    code += '    private val longRunningJobs = ConcurrentLinkedQueue<LongRunningJob>()\n    private data class LongRunningJob(' + legacy
code += '    private suspend fun executeSingleTask(' + method + r'''
}
fun main() = runBlocking {
    for (task in listOf(AntForest(), AntFarm(), AntSports(), ModelTask())) {
        val runner = Runner()
        withTimeout(1000) { runner.run(task) }
        check(task.stopped && task.finished) { "${task.getName()} bypassed timeout or released its slot before cleanup" }
        check(runner.failureCount.get() == 1 && runner.successCount.get() == 0)
        val next = ModelTask(1)
        runner.run(next)
        check(next.finished && runner.successCount.get() == 1) { "Next scheduled task stayed blocked" }
        task.scope.cancel(); next.scope.cancel()
    }
    val runner = Runner()
    val task = ModelTask(1000, 30)
    val execution = launch { runner.run(task) }
    task.started.await(); execution.cancelAndJoin()
    check(task.stopped && task.finished) { "Cancelling runner leaked a live task" }
    check(runner.taskConcurrencyLimiter.availablePermits == 1)
    task.scope.cancel()
    val stuck = ModelTask(1000, 100).apply { refuseWait = true }
    check(runCatching { Runner().run(stuck) }.exceptionOrNull() is IllegalStateException) {
        "Incomplete cleanup must fail the round, not merely cancel an async child"
    }
    stuck.job.join(); stuck.scope.cancel()
    println("PASS: module timeout, cleanup, next task, cancellation and incomplete cleanup abort")
}
'''
jars = []
for group, artifact in [('org.jetbrains.kotlin','kotlin-compiler-embeddable'),
                        ('org.jetbrains.kotlin','kotlin-stdlib'), ('org.jetbrains.kotlin','kotlin-script-runtime'),
                        ('org.jetbrains.kotlin','kotlin-reflect'), ('org.jetbrains.intellij.deps','trove4j'),
                        ('org.jetbrains.kotlinx','kotlinx-coroutines-core-jvm'), ('org.jetbrains','annotations')]:
    matches = sorted(CACHE.glob(f'{group}/{artifact}/*/*/*.jar'))
    if matches:
        jars.append(matches[-1])
classpath = os.pathsep.join(map(str, jars))
java = str(Path(os.environ['JAVA_HOME']) / 'bin/java') if os.environ.get('JAVA_HOME') else shutil.which('java')
assert java and jars, 'Build once with JDK 17 to populate the Kotlin compiler cache'
with tempfile.TemporaryDirectory() as directory:
    path = Path(directory)
    (path / 'Check.kt').write_text(code)
    subprocess.run([java, '-cp', classpath, 'org.jetbrains.kotlin.cli.jvm.K2JVMCompiler',
                    '-no-stdlib', '-no-reflect', '-classpath', classpath, '-d', str(path / 'classes'),
                    str(path / 'Check.kt')], check=True)
    subprocess.run([java, '-cp', str(path / 'classes') + os.pathsep + classpath, 'CheckKt'], check=True)
