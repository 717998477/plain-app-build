package com.ismartcoding.plain.platform.system

import android.app.Activity
import android.app.ActivityManager
import android.content.Context
import android.os.Build
import com.ismartcoding.plain.mainActivity

// 照抄 Prox5 隐藏方案：SharedPreferences 存储 + Window flag + setExcludeFromRecents
private const val PREFS_NAME = "cfg"
private const val KEY_HIDE_FROM_RECENTS = "hide_from_recents"
private const val FLAG_HIDE_FROM_RECENTS = 0x8000000

internal actual fun isHideFromRecentsEnabled(): Boolean =
    mainActivity?.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        ?.getBoolean(KEY_HIDE_FROM_RECENTS, false) ?: false

internal actual fun setHideFromRecents(enabled: Boolean) {
    val activity = mainActivity ?: return
    activity.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        .edit().putBoolean(KEY_HIDE_FROM_RECENTS, enabled).apply()
    applyHideFromRecents(activity, enabled)
}

internal fun applyHideFromRecents(activity: Activity, enabled: Boolean) {
    val window = activity.window
    if (enabled) {
        window.addFlags(FLAG_HIDE_FROM_RECENTS)
    } else {
        window.clearFlags(FLAG_HIDE_FROM_RECENTS)
    }
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
        val am = activity.getSystemService(Context.ACTIVITY_SERVICE) as ActivityManager
        val tasks = am.appTasks
        if (tasks.isNotEmpty()) {
            tasks[0].setExcludeFromRecents(enabled)
        }
    }
}
