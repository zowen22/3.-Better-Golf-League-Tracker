import SwiftUI

@Observable
final class NotificationsViewModel {
    var items: [NotificationItem] = []
    var unreadCount = 0
    var isLoading = false
    var errorMessage: String?

    func load() async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            let r: NotificationsResponse = try await APIClient.shared.request(.notifications)
            items = r.items
            unreadCount = r.unreadCount
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    /// Fetches only the unread count -- used by toolbar bell badges on other
    /// screens that don't want the full feed loaded.
    func refreshUnreadCount() async {
        do {
            let r: NotificationsResponse = try await APIClient.shared.request(.notifications)
            unreadCount = r.unreadCount
        } catch {
            // Non-fatal -- badge just doesn't update this pass.
        }
    }

    func markRead(_ item: NotificationItem) async {
        guard !item.isRead else { return }
        if let idx = items.firstIndex(where: { $0.id == item.id }) {
            items[idx] = NotificationItem(kind: item.kind, itemId: item.itemId, type: item.type,
                                           message: item.message, createdAt: item.createdAt, isRead: true)
            unreadCount = max(0, unreadCount - 1)
        }
        do {
            let _: OkResponse = try await APIClient.shared.request(.markNotificationRead(kind: item.kind, id: item.itemId))
        } catch {
            // Optimistic update already applied; a failed mark-read isn't worth
            // surfacing an error over -- worst case it shows read again next load.
        }
    }

    @discardableResult
    func markAllRead() async -> Bool {
        for i in items.indices { items[i] = NotificationItem(kind: items[i].kind, itemId: items[i].itemId,
                                                               type: items[i].type, message: items[i].message,
                                                               createdAt: items[i].createdAt, isRead: true) }
        unreadCount = 0
        do {
            let _: OkResponse = try await APIClient.shared.request(.markAllNotificationsRead)
            return true
        } catch {
            errorMessage = error.localizedDescription
            return false
        }
    }
}

/// Notification Center: a combined feed of admin-posted announcements and
/// auto-created league events (round completed, sub assigned, etc.), with
/// per-user read tracking. Reachable via the bell icon on ScheduleView's
/// toolbar and from ProfileView.
struct NotificationsView: View {
    @State private var vm = NotificationsViewModel()

    var body: some View {
        Group {
            if vm.isLoading && vm.items.isEmpty {
                ProgressView()
            } else if vm.items.isEmpty {
                ContentUnavailableView(
                    vm.errorMessage ?? "No notifications yet",
                    systemImage: "bell"
                )
            } else {
                List(vm.items) { item in
                    NotificationRow(item: item)
                        .contentShape(Rectangle())
                        .onTapGesture {
                            Task { await vm.markRead(item) }
                        }
                }
                .listStyle(.plain)
            }
        }
        .navigationTitle("Notifications")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            if vm.unreadCount > 0 {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Mark All Read") {
                        Task { await vm.markAllRead() }
                    }
                    .font(.caption)
                }
            }
        }
        .task { await vm.load() }
        .refreshable { await vm.load() }
    }
}

private struct NotificationRow: View {
    let item: NotificationItem

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Circle()
                .fill(item.isRead ? Color.clear : Color.accentColor)
                .frame(width: 8, height: 8)
                .padding(.top, 6)

            VStack(alignment: .leading, spacing: 3) {
                Text(item.message)
                    .font(.subheadline)
                    .fontWeight(item.isRead ? .regular : .semibold)
                if let date = item.createdAt {
                    Text(date)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }
            Spacer()
        }
        .padding(.vertical, 2)
    }
}
