#!/usr/bin/env python3
"""Exercise production notification recovery methods with an in-memory Android manager."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'app/src/main/java/io/github/aoguai/sesameag'
source = (BASE / 'util/Notify.kt').read_text()
assert 'fun clearNetworkAlert()' in source, 'Successful RPCs cannot clear stale network alerts'
methods = source.split('    @JvmStatic\n    @Synchronized\n    fun sendNetworkAlert', 1)[1].split('    private fun sendAlertNotification', 1)[0]
code = '''
class Context {
    companion object { const val NOTIFICATION_SERVICE = "notification" }
    fun getSystemService(name: String): Any? = manager
}
val manager = NotificationManager()
class NotificationManager {
    val alerts = mutableMapOf<Int, String?>()
    var cancels = 0
    var failCancel = false
    fun cancel(id: Int) { if (failCancel) error("service unavailable"); cancels++; alerts.remove(id) }
}
object Log { fun printStackTrace(e: Exception) {} }
object Notify {
    const val NETWORK_ALERT_NOTIFICATION_ID = 97
    var context: Context? = Context()
    var notificationManager: NotificationManager? = manager
    var networkAlertPending = true
    fun sendAlertNotification(title: String?, content: String?, notificationId: Int = 98) {
        manager.alerts[notificationId] = title
    }
    @JvmStatic
    @Synchronized
    fun sendNetworkAlert''' + methods + '''
}
fun main() {
    // Process restart: a notification outlives the process that posted it.
    manager.alerts[97] = "old network failure"
    manager.alerts[98] = "verification required"
    manager.alerts[99] = "running"
    Notify.clearNetworkAlert()
    check(97 !in manager.alerts && manager.alerts.size == 2)
    val cancels = manager.cancels
    repeat(100) { Notify.clearNetworkAlert() }
    check(manager.cancels == cancels) // no binder traffic on every healthy RPC
    repeat(3) { Notify.sendNetworkAlert("network failure", "details") }
    check(manager.alerts[97] == "network failure") // persistent failures keep alert
    Notify.clearNetworkAlert()
    check(97 !in manager.alerts && manager.alerts[98] == "verification required")
    Notify.sendNetworkAlert("new failure", "details")
    manager.failCancel = true
    Notify.clearNetworkAlert()
    check(97 in manager.alerts && Notify.networkAlertPending)
    manager.failCancel = false
    Notify.clearNetworkAlert()
    check(97 !in manager.alerts)
    println("PASS: recovery, repeated failure, restart, unrelated alerts, cancel retry, healthy fast path")
}
'''
bridge = (BASE / 'hook/rpc/bridge/AriverRpcBridge.kt').read_text()
success = bridge.split('if (!rpcEntity.hasError) {', 1)[1].split('return rpcEntity', 1)[0]
assert 'Notify.clearNetworkAlert()' in success
assert 'Notify.sendNetworkAlert(' in bridge
constants = (BASE / 'hook/ApplicationHookConstants.kt').read_text()
assert 'Notify.sendNetworkAlert(' in constants
cache = Path(os.environ.get('GRADLE_USER_HOME', Path.home() / '.gradle')) / 'caches/modules-2/files-2.1'
jars = []
for group, artifact in [('org.jetbrains.kotlin', 'kotlin-compiler-embeddable'),
                        ('org.jetbrains.kotlin', 'kotlin-stdlib'), ('org.jetbrains.kotlin', 'kotlin-script-runtime'),
                        ('org.jetbrains.kotlin', 'kotlin-reflect'), ('org.jetbrains.intellij.deps', 'trove4j'),
                        ('org.jetbrains.kotlinx', 'kotlinx-coroutines-core-jvm'), ('org.jetbrains', 'annotations')]:
    matches = sorted(cache.glob(f'{group}/{artifact}/*/*/*.jar'))
    if matches: jars.append(matches[-1])
classpath = os.pathsep.join(map(str, jars))
java = str(Path(os.environ['JAVA_HOME']) / 'bin/java') if os.environ.get('JAVA_HOME') else shutil.which('java')
with tempfile.TemporaryDirectory() as directory:
    path = Path(directory)
    (path / 'Check.kt').write_text(code)
    subprocess.run([java, '-cp', classpath, 'org.jetbrains.kotlin.cli.jvm.K2JVMCompiler',
                    '-no-stdlib', '-no-reflect', '-classpath', classpath, '-d', str(path / 'classes'),
                    str(path / 'Check.kt')], check=True)
    subprocess.run([java, '-cp', str(path / 'classes') + os.pathsep + classpath, 'CheckKt'], check=True)
