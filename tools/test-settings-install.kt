// Exercises CobaltSettings.copyAtomically(), the part that decides whether the
// renderer finds a usable config.json.
//
// Extracted from install() and free of Android types precisely so this can run here:
// the android.jar on the compile path is stubs only, and subclassing Context or
// AssetManager against it is not possible. What is left is plain file IO, which is
// where every failure this file is about actually lives.
//
// Built and run by tools/test-settings-install.sh.

import me.shadow.cobalt.CobaltSettings
import java.io.File
import java.io.IOException
import java.io.InputStream

private var failures = 0

private fun check(ok: Boolean, msg: String) {
    println(if (ok) "ok    $msg" else "FAIL  $msg")
    if (!ok) failures++
}

private val settingsPath = "plugin/config/cobalt-settings.json"

private fun settingsBytes(): ByteArray = File(settingsPath).readBytes()

private fun tmpdir(name: String): File =
    File(System.getProperty("java.io.tmpdir"), "cobalt-settings-$name").also {
        it.deleteRecursively()
        it.mkdirs()
    }

private fun stream(bytes: ByteArray) = object : InputStream() {
    var at = 0
    override fun read(): Int = if (at < bytes.size) bytes[at++].toInt() else -1
}

fun main() {
    println("CobaltSettings.copyAtomically")

    val expected = settingsBytes()

    println("\n-- writes the file")
    val d1 = tmpdir("basic")
    val t1 = File(d1, "cobalt/config.json")
    val r1 = CobaltSettings.copyAtomically(stream(expected), t1)
    check(r1 != null, "returns the target")
    check(t1.isFile, "file exists")
    check(t1.readBytes().contentEquals(expected), "bytes match the source settings")

    println("\n-- no temporary left behind")
    val leftovers = File(d1, "cobalt").listFiles()!!.map { it.name }.filter { it != "config.json" }
    check(leftovers.isEmpty(), "only config.json in the directory (found: $leftovers)")

    println("\n-- creates the parent directory")
    val d2 = tmpdir("mkdir")
    check(!File(d2, "cobalt").exists(), "cobalt/ does not exist beforehand")
    val t2 = File(d2, "cobalt/config.json")
    check(CobaltSettings.copyAtomically(stream(expected), t2) != null, "writes into a new directory")

    println("\n-- overwrites, rather than keeping the first version")
    // The signing key is generated per build, so a reinstall always means an
    // uninstall and a fresh install. "Only if missing" would therefore freeze the
    // settings from whichever version happened to be installed first.
    t2.writeText("{\"maxGlslCacheSize\": 1}")
    CobaltSettings.copyAtomically(stream(expected), t2)
    check(
        t2.readBytes().contentEquals(expected),
        "an existing config.json is replaced, so a settings change can reach an installed plugin",
    )

    println("\n-- an interrupted copy cannot leave a partial file")
    // The failure this guards: a truncated config.json is worse than none, because
    // config_refresh() fails to parse it rather than failing to find it, and the
    // renderer logs neither.
    val d3 = tmpdir("truncated")
    val t3 = File(d3, "cobalt/config.json")
    val throwing = object : InputStream() {
        override fun read(): Int = throw IOException("simulated read failure")
    }
    var threw = false
    try {
        CobaltSettings.copyAtomically(throwing, t3)
    } catch (e: IOException) {
        threw = true
    }
    check(threw, "a read failure propagates rather than being swallowed")
    check(!t3.isFile, "no partial config.json left at the target")
    val tmps = File(d3, "cobalt").listFiles()?.map { it.name } ?: emptyList()
    check(tmps.none { it.endsWith(".tmp") }, "the temporary file is cleaned up (found: $tmps)")

    println("\n-- an existing file survives a failed copy")
    val d4 = tmpdir("preserve")
    val t4 = File(d4, "cobalt/config.json")
    CobaltSettings.copyAtomically(stream(expected), t4)
    try {
        CobaltSettings.copyAtomically(
            object : InputStream() {
                override fun read(): Int = throw IOException("simulated")
            },
            t4,
        )
    } catch (e: IOException) {
        // expected
    }
    check(t4.readBytes().contentEquals(expected), "the previous file is left intact, not truncated")

    for (d in listOf(d1, d2, d3, d4)) d.deleteRecursively()

    println("\n" + if (failures == 0) "all tests passed" else "$failures FAILURES")
    if (failures > 0) kotlin.system.exitProcess(1)
}