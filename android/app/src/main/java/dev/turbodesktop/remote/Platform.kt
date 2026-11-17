package dev.turbodesktop.remote

import android.app.Application
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.BroadcastReceiver
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.IBinder
import android.provider.Settings
import androidx.biometric.BiometricManager.Authenticators
import androidx.biometric.BiometricPrompt
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import androidx.fragment.app.FragmentActivity
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlin.coroutines.resume

class TurboApp : Application() {
    override fun attachBaseContext(base: Context) = super.attachBaseContext(AppLang.wrap(base))

    override fun onCreate() {
        super.onCreate()
        Graph.init(this)
        // After a process restart (e.g. the system killed us) resume the connection if a session is still valid.
        if (Graph.prefs.paired && Graph.sessionOpen) {
            HubService.start(this)
            Graph.startConnection()
        }
    }
}

/** BiometricPrompt wrapper: strong biometric or device credential. One success unlocks the Keystore auth key for 30 s. */
object Biometric {
    suspend fun authenticate(activity: FragmentActivity): Boolean = suspendCancellableCoroutine { cont ->
        val prompt = BiometricPrompt(activity, ContextCompat.getMainExecutor(activity),
            object : BiometricPrompt.AuthenticationCallback() {
                override fun onAuthenticationSucceeded(result: BiometricPrompt.AuthenticationResult) { if (cont.isActive) cont.resume(true) }
                override fun onAuthenticationError(errorCode: Int, errString: CharSequence) { if (cont.isActive) cont.resume(false) }
            })
        val authenticators = if (Build.VERSION.SDK_INT >= 30) Authenticators.BIOMETRIC_STRONG or Authenticators.DEVICE_CREDENTIAL
        else Authenticators.DEVICE_CREDENTIAL
        val info = BiometricPrompt.PromptInfo.Builder().setTitle(activity.getString(R.string.biometric_title))
            .setAllowedAuthenticators(authenticators).build()
        prompt.authenticate(info)
        cont.invokeOnCancellation { prompt.cancelAuthentication() }
    }
}

/** High-priority notifications with Allow/Deny actions. The actions open the app, which asks for biometric before signing. */
object Notifier {
    const val CH_APPROVALS = "approvals"
    const val CH_STATUS = "status"
    const val EXTRA_APPROVAL = "approval_id"
    const val EXTRA_DECISION = "decision"
    const val SERVICE_NOTIF_ID = 1

    fun createChannels(ctx: Context) {
        val nm = ctx.getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(NotificationChannel(CH_APPROVALS, ctx.getString(R.string.notif_channel_approvals),
            NotificationManager.IMPORTANCE_HIGH))
        nm.createNotificationChannel(NotificationChannel(CH_STATUS, ctx.getString(R.string.notif_channel_status),
            NotificationManager.IMPORTANCE_LOW))
    }

    fun serviceNotification(ctx: Context): Notification =
        NotificationCompat.Builder(ctx, CH_STATUS).setSmallIcon(android.R.drawable.stat_notify_sync)
            .setContentTitle(ctx.getString(R.string.notif_service_title))
            .setContentText(ctx.getString(R.string.notif_service_text)).setOngoing(true)
            .setContentIntent(open(ctx, 0, null, null)).build()

    private fun open(ctx: Context, code: Int, approval: String?, decision: String?): PendingIntent {
        val i = Intent(ctx, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_NEW_TASK)
        if (approval != null) i.putExtra(EXTRA_APPROVAL, approval).putExtra(EXTRA_DECISION, decision)
        return PendingIntent.getActivity(ctx, code, i, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
    }

    private fun idFor(approvalId: String) = 1000 + (approvalId.hashCode() and 0xFFFF)

    fun showApproval(ctx: Context, a: Approval) {
        val n = NotificationCompat.Builder(ctx, CH_APPROVALS).setSmallIcon(android.R.drawable.ic_dialog_alert)
            .setContentTitle(ctx.getString(R.string.notif_approval_title, a.control))
            .setContentText(ctx.getString(R.string.notif_approval_text, a.action, a.control, a.window))
            .setPriority(NotificationCompat.PRIORITY_MAX).setCategory(NotificationCompat.CATEGORY_ALARM)
            .setAutoCancel(true).setContentIntent(open(ctx, idFor(a.id), a.id, null))
            .addAction(0, ctx.getString(R.string.notif_deny), open(ctx, idFor(a.id) + 1, a.id, "deny"))
            .addAction(0, ctx.getString(R.string.notif_allow), open(ctx, idFor(a.id) + 2, a.id, "allow")).build()
        try { ctx.getSystemService(NotificationManager::class.java).notify(idFor(a.id), n) } catch (_: SecurityException) {}
    }

    fun showAlert(ctx: Context, text: String) {
        val n = NotificationCompat.Builder(ctx, CH_APPROVALS).setSmallIcon(android.R.drawable.ic_dialog_alert)
            .setContentTitle(text).setAutoCancel(true).setContentIntent(open(ctx, 7, null, null)).build()
        try { ctx.getSystemService(NotificationManager::class.java).notify(text.hashCode(), n) } catch (_: SecurityException) {}
    }

    fun cancelApproval(ctx: Context, approvalId: String) =
        ctx.getSystemService(NotificationManager::class.java).cancel(idFor(approvalId))
}

/** Foreground service: keeps the process alive so the single hub connection (SSE) survives on aggressive ROMs. No FCM. */
class HubService : Service() {
    override fun onBind(intent: Intent?): IBinder? = null
    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        startForeground(Notifier.SERVICE_NOTIF_ID, Notifier.serviceNotification(this))
        Graph.startConnection()
        return START_STICKY
    }

    companion object {
        fun start(ctx: Context) = try { ContextCompat.startForegroundService(ctx, Intent(ctx, HubService::class.java)) } catch (_: Exception) {}
        fun stop(ctx: Context) { ctx.stopService(Intent(ctx, HubService::class.java)) }
    }
}

class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        Graph.init(context.applicationContext as Application)
        if (Graph.prefs.paired && Graph.sessionOpen) HubService.start(context)
    }
}

/** Opens the right screens so a Xiaomi/HyperOS (or any) ROM does not kill the connection. MIUI/HyperOS intents first, generic fallbacks last. */
object BatteryGuide {
    fun intents(ctx: Context): List<Intent> {
        val pkg = ctx.packageName
        return listOf(
            Intent().setComponent(ComponentName("com.miui.securitycenter", "com.miui.permcenter.autostart.AutoStartManagementActivity")),
            Intent("miui.intent.action.POWER_HIDE_MODE_APP_LIST").addCategory(Intent.CATEGORY_DEFAULT),
            Intent().setComponent(ComponentName("com.miui.powerkeeper", "com.miui.powerkeeper.ui.HiddenAppsConfigActivity"))
                .putExtra("package_name", pkg).putExtra("package_label", ctx.getString(R.string.app_name)),
            Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS, Uri.parse("package:$pkg")),
            Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS),
            Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:$pkg")),
        )
    }

    /** Opens the n-th available screen (index into [available]). */
    fun available(ctx: Context): List<Intent> = intents(ctx).filter { ctx.packageManager.resolveActivity(it, 0) != null }

    fun open(ctx: Context, intent: Intent) {
        try { ctx.startActivity(intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) } catch (_: Exception) {}
    }
}

/** Opens an otpauth:// link in an authenticator app. False when none is installed. */
fun openInAuthenticator(ctx: Context, otpauth: String): Boolean = try {
    ctx.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(otpauth)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
    true
} catch (e: android.content.ActivityNotFoundException) { false }

/** Copies a secret to the clipboard; on Android 13+ marks it sensitive so the preview toast and keyboard history hide it. */
fun copySensitive(ctx: Context, label: String, text: String) {
    val cm = ctx.getSystemService(android.content.ClipboardManager::class.java)
    val clip = android.content.ClipData.newPlainText(label, text)
    if (Build.VERSION.SDK_INT >= 33) {
        clip.description.extras = android.os.PersistableBundle().apply { putBoolean(android.content.ClipDescription.EXTRA_IS_SENSITIVE, true) }
    }
    cm.setPrimaryClip(clip)
}

/**
 * Per-app language. "" = follow the system. API 33+ uses the platform LocaleManager (also shown in system Settings);
 * on API 29-32 the choice lives in prefs and [wrap] applies it from attachBaseContext (the UI must recreate the activity after [set]).
 */
object AppLang {
    private fun prefs(ctx: Context) = ctx.getSharedPreferences("turbo", Context.MODE_PRIVATE)

    fun current(ctx: Context): String =
        if (Build.VERSION.SDK_INT >= 33) {
            val l = ctx.getSystemService(android.app.LocaleManager::class.java).applicationLocales
            if (l.isEmpty) "" else l[0].language
        } else prefs(ctx).getString("lang", "") ?: ""

    fun set(ctx: Context, tag: String) {
        if (Build.VERSION.SDK_INT >= 33) {
            ctx.getSystemService(android.app.LocaleManager::class.java).applicationLocales =
                if (tag.isBlank()) android.os.LocaleList.getEmptyLocaleList() else android.os.LocaleList.forLanguageTags(tag)
        } else prefs(ctx).edit().putString("lang", tag).apply()
    }

    /** For attachBaseContext. A no-op on API 33+, where the platform applies the choice. */
    fun wrap(base: Context): Context {
        if (Build.VERSION.SDK_INT >= 33) return base
        val tag = prefs(base).getString("lang", "") ?: ""
        if (tag.isBlank()) return base
        val loc = java.util.Locale.forLanguageTag(tag)
        java.util.Locale.setDefault(loc)
        val conf = android.content.res.Configuration(base.resources.configuration)
        conf.setLocale(loc)
        return base.createConfigurationContext(conf)
    }
}
