package dev.turbodesktop.remote

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Test

class HubJsonTest {
    @Test fun pairReplyNeeds() {
        val j = JSONObject("""{"deviceId":"abc","hubPub":"k","totpEnroll":true,"needs":{"totp":false,"biometric":true}}""")
        assertEquals(Needs(totp = false, biometric = true), HubJson.needs(j))
        assertEquals(true, j.optBoolean("totpEnroll", false))
    }

    @Test fun missingNeedsMeansAskForEverything() {
        assertEquals(Needs(totp = true, biometric = true), HubJson.needs(JSONObject("""{"deviceId":"abc"}""")))
        assertEquals(Needs(totp = true, biometric = true), HubJson.needs(null))
    }

    @Test fun policyReply() {
        val j = JSONObject("""{"preset":"easy","needs":{"totp":false,"biometric":false},"sessionHours":12}""")
        assertEquals(Needs(false, false), HubJson.needs(j))
    }

    @Test fun enrollReply() {
        val j = JSONObject("""{"otpauth":"otpauth://totp/turbo-desktop:pc?secret=ABCD&issuer=turbo-desktop","secret":"ABCD","issuer":"turbo-desktop","account":"pc","digits":6,"period":30}""")
        assertEquals(TotpEnroll(j.getString("otpauth"), "ABCD", "turbo-desktop", "pc"), HubJson.totpEnroll(j))
    }
}
