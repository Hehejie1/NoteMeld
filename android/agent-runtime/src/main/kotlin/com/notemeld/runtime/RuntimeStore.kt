package com.notemeld.runtime

/** Durable projection seam; it never replaces the SDK's canonical turn state machine. */
interface RuntimeStore {
    fun saveSession(sessionId: String, projection: String)
    fun loadSession(sessionId: String): String?
}
