package wiki.notemeld.agent.harness

import androidx.test.ext.junit.runners.AndroidJUnit4
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicReference
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import wiki.notemeld.agent.Runtime

@RunWith(AndroidJUnit4::class)
class NativeSmokeTest {
    @Test fun nativeAgentHandlesUnicodeAndEmitsTerminalEvent() {
        val terminal = CountDownLatch(1)
        val terminalType = AtomicReference<String>()
        Runtime("""{"schema_version":"1"}""", {
            """{"schema_version":"1","ok":true,"result":{"chunks":[{"type":"content_delta","delta":"你好😀"}],"completion":{"content":"你好😀","tool_calls":[],"finish_reason":"stop","usage":{"input_tokens":1,"output_tokens":1,"cache_read_tokens":0,"cache_write_tokens":0}}}}"""
        }, { event ->
            if (event.contains("\"type\":\"turn.succeeded\"")) {
                terminalType.set("turn.succeeded"); terminal.countDown()
            }
        }).use { runtime ->
            val token = runtime.submitTurn("""{"schema_version":"1","request_id":"cccccccc-cccc-4ccc-8ccc-cccccccccccc","session_id":"android-harness","input":{"text":"你好😀","attachments":[],"context_refs":[]},"model_override":null,"approval_mode":"interactive"}""")
            assertTrue(token != 0uL)
            assertTrue(terminal.await(5, TimeUnit.SECONDS))
            assertEquals("turn.succeeded", terminalType.get())
            assertEquals(0, runtime.wait(token, 5_000u))
            assertEquals(-6, runtime.steer(token, """{"text":"later"}"""))
        }
    }
}
