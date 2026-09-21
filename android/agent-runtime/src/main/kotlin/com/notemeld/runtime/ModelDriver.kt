package com.notemeld.runtime

import org.json.JSONObject

/** Host-owned model adapter. The canonical SDK invokes it through its JNI driver callback. */
fun interface ModelDriver {
    fun request(payload: JSONObject): JSONObject
}
