import SwiftUI
import UserNotifications

@main
struct BetterGolfTrackerApp: App {
    @State private var authViewModel = AuthViewModel()
    @UIApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(authViewModel)
                .onReceive(NotificationCenter.default.publisher(for: .didReceiveAPNsToken)) { note in
                    guard let token = note.object as? String else { return }
                    Task { try? await APIClient.shared.request(.registerAPNs(deviceToken: token)) as EmptyResponse }
                }
        }
    }
}

// Thin delegate: handles APNs token + notification presentation.
final class AppDelegate: NSObject, UIApplicationDelegate, UNUserNotificationCenterDelegate {

    func application(_ application: UIApplication,
                     didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?) -> Bool {
        UNUserNotificationCenter.current().delegate = self
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .badge, .sound]) { granted, _ in
            if granted { DispatchQueue.main.async { UIApplication.shared.registerForRemoteNotifications() } }
        }
        return true
    }

    func application(_ application: UIApplication,
                     didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data) {
        let token = deviceToken.map { String(format: "%02.2hhx", $0) }.joined()
        NotificationCenter.default.post(name: .didReceiveAPNsToken, object: token)
    }

    func application(_ application: UIApplication,
                     didFailToRegisterForRemoteNotificationsWithError error: Error) {
        // Silently ignore — APNs not available in simulator
    }

    func userNotificationCenter(_ center: UNUserNotificationCenter,
                                 willPresent notification: UNNotification) async -> UNNotificationPresentationOptions {
        [.banner, .sound, .badge]
    }

    func userNotificationCenter(_ center: UNUserNotificationCenter,
                                 didReceive response: UNNotificationResponse) async {
        let userInfo = response.notification.request.content.userInfo
        let category = response.notification.request.content.categoryIdentifier
        // Route based on category or explicit "deep_link" key in payload
        let deepLink = (userInfo["deep_link"] as? String) ?? category
        switch deepLink {
        case "score_submission", "pending_approval":
            NotificationCenter.default.post(name: .deepLinkAdmin, object: nil)
        case "score_approved", "score_rejected":
            NotificationCenter.default.post(name: .deepLinkSchedule, object: nil)
        default:
            break
        }
    }
}

extension Notification.Name {
    static let didReceiveAPNsToken = Notification.Name("didReceiveAPNsToken")
    static let deepLinkAdmin    = Notification.Name("deepLinkAdmin")
    static let deepLinkSchedule = Notification.Name("deepLinkSchedule")
}

// Codable wrapper for endpoints that return an empty/ignored body
struct EmptyResponse: Codable {}
