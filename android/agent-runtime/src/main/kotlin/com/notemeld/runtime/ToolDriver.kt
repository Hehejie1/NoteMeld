package com.notemeld.runtime

import org.json.JSONObject

/** Host-owned tool adapter. Tool policy remains in the host and SDK runtime. */
fun interface ToolDriver {
    fun invoke(payload: JSONObject): JSONObject
}
