import SwiftUI

@Observable
final class AnnouncementsViewModel {
    var active: [Announcement] = []
    var expired: [Announcement] = []
    var isLoading = false
    var errorMessage: String?

    func load() async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            let r: AnnouncementsResponse = try await APIClient.shared.request(.announcements)
            active = r.active
            expired = r.expired
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

/// Embedded inside `LeagueBoardView` as the "Announcements" segment — not a
/// standalone navigation destination, so it owns no navigationTitle/toolbar.
struct AnnouncementsView: View {
    @State private var vm = AnnouncementsViewModel()
    @State private var showExpired = false

    var body: some View {
        Group {
            if vm.active.isEmpty && vm.expired.isEmpty && !vm.isLoading {
                ContentUnavailableView(
                    vm.errorMessage ?? "No announcements",
                    systemImage: "bell"
                )
            } else {
                List {
                    if vm.active.isEmpty {
                        Text("No active announcements")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    } else {
                        ForEach(vm.active) { a in
                            announcementRow(a, expired: false)
                        }
                    }

                    if !vm.expired.isEmpty {
                        Section {
                            DisclosureGroup("Expired (\(vm.expired.count))", isExpanded: $showExpired) {
                                ForEach(vm.expired) { a in
                                    announcementRow(a, expired: true)
                                }
                            }
                        }
                    }
                }
                .listStyle(.plain)
            }
        }
        .overlay { if vm.isLoading { ProgressView() } }
        .task { await vm.load() }
        .refreshable { await vm.load() }
    }

    @ViewBuilder
    private func announcementRow(_ a: Announcement, expired: Bool) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                if let type = a.type, !type.isEmpty {
                    Text(type.uppercased())
                        .font(.caption2.bold())
                        .foregroundStyle(.secondary)
                }
                Spacer()
                if let date = a.createdDate {
                    Text(date).font(.caption2).foregroundStyle(.secondary)
                }
            }
            Text(a.message)
                .font(.subheadline)
                .foregroundStyle(expired ? .secondary : .primary)
        }
        .padding(.vertical, 4)
    }
}
