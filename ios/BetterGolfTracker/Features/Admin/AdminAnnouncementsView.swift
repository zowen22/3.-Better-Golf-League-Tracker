import SwiftUI

@Observable
final class AdminAnnouncementsViewModel {
    var announcements: [AdminAnnouncement] = []
    var isLoading = false
    var isSaving = false
    var errorMessage: String?

    func load() async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            let r: AdminAnnouncementsListResponse = try await APIClient.shared.request(.adminAnnouncements)
            announcements = r.announcements
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    @discardableResult
    func create(type: String, message: String, displayUntil: String?) async -> Bool {
        isSaving = true; errorMessage = nil
        defer { isSaving = false }
        do {
            let _: AnnouncementCreateResponse = try await APIClient.shared.request(
                .createAdminAnnouncement(type: type, message: message, displayUntil: displayUntil)
            )
            await load()
            return true
        } catch {
            errorMessage = error.localizedDescription
            return false
        }
    }

    @discardableResult
    func update(notifId: Int, type: String, message: String, displayUntil: String?) async -> Bool {
        isSaving = true; errorMessage = nil
        defer { isSaving = false }
        do {
            let _: OkResponse = try await APIClient.shared.request(
                .updateAdminAnnouncement(notifId: notifId, type: type, message: message, displayUntil: displayUntil)
            )
            await load()
            return true
        } catch {
            errorMessage = error.localizedDescription
            return false
        }
    }

    func delete(notifId: Int) async {
        do {
            let _: OkResponse = try await APIClient.shared.request(.deleteAdminAnnouncement(notifId: notifId))
            await load()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func toggle(notifId: Int) async {
        do {
            let _: AnnouncementToggleResponse = try await APIClient.shared.request(.toggleAdminAnnouncement(notifId: notifId))
            await load()
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

/// Admin announcements list + add/edit form + active toggle, reached from
/// `AdminView`. Manages the `notifications` table (routes/announcements.py) —
/// distinct from `LeagueBoardView`'s `/board` posts.
struct AdminAnnouncementsView: View {
    @State private var vm = AdminAnnouncementsViewModel()
    @State private var showingAddForm = false
    @State private var editingAnnouncement: AdminAnnouncement?

    var body: some View {
        Group {
            if vm.isLoading {
                ProgressView()
            } else if vm.announcements.isEmpty {
                ContentUnavailableView(
                    vm.errorMessage ?? "No announcements yet",
                    systemImage: "megaphone"
                )
            } else {
                List {
                    ForEach(vm.announcements) { a in
                        announcementRow(a)
                    }
                }
                .listStyle(.insetGrouped)
            }
        }
        .navigationTitle("Announcements")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button { showingAddForm = true } label: {
                    Image(systemName: "plus")
                }
            }
        }
        .task { await vm.load() }
        .refreshable { await vm.load() }
        .sheet(isPresented: $showingAddForm) {
            AdminAnnouncementFormView(announcement: nil, viewModel: vm)
        }
        .sheet(item: $editingAnnouncement) { a in
            AdminAnnouncementFormView(announcement: a, viewModel: vm)
        }
    }

    @ViewBuilder
    private func announcementRow(_ a: AdminAnnouncement) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                if let type = a.type, !type.isEmpty {
                    Text(type.uppercased()).font(.caption2.bold()).foregroundStyle(.secondary)
                }
                Spacer()
                Toggle("", isOn: Binding(
                    get: { a.isActive },
                    set: { _ in Task { await vm.toggle(notifId: a.id) } }
                ))
                .labelsHidden()
            }
            Text(a.message)
                .font(.subheadline)
                .foregroundStyle(a.isActive ? .primary : .secondary)
            HStack {
                if let date = a.createdDate {
                    Text(date).font(.caption2).foregroundStyle(.secondary)
                }
                if let until = a.displayUntil {
                    Text("until \(until)").font(.caption2).foregroundStyle(.secondary)
                }
                Spacer()
                Button("Edit") { editingAnnouncement = a }
                    .font(.caption.bold())
                Button(role: .destructive) {
                    Task { await vm.delete(notifId: a.id) }
                } label: {
                    Text("Delete").font(.caption.bold())
                }
            }
        }
        .padding(.vertical, 4)
    }
}

private struct AdminAnnouncementFormView: View {
    let announcement: AdminAnnouncement?
    var viewModel: AdminAnnouncementsViewModel
    @Environment(\.dismiss) private var dismiss

    @State private var type: String
    @State private var message: String
    @State private var displayUntil: String

    init(announcement: AdminAnnouncement?, viewModel: AdminAnnouncementsViewModel) {
        self.announcement = announcement
        self.viewModel = viewModel
        _type = State(initialValue: announcement?.type ?? "general")
        _message = State(initialValue: announcement?.message ?? "")
        _displayUntil = State(initialValue: announcement?.displayUntil ?? "")
    }

    var body: some View {
        NavigationStack {
            Form {
                Section("Type") {
                    TextField("e.g. general, urgent", text: $type)
                        .autocapitalization(.none)
                }
                Section("Message") {
                    TextField("Announcement text", text: $message, axis: .vertical)
                        .lineLimit(3...6)
                }
                Section("Display Until (optional, YYYY-MM-DD)") {
                    TextField("2026-12-31", text: $displayUntil)
                        .autocapitalization(.none)
                }
                if let err = viewModel.errorMessage {
                    Section { Text(err).font(.caption).foregroundStyle(.red) }
                }
                Section {
                    if viewModel.isSaving {
                        HStack { Spacer(); ProgressView(); Spacer() }
                    } else {
                        Button(announcement == nil ? "Post Announcement" : "Save Changes") {
                            Task { await save() }
                        }
                        .frame(maxWidth: .infinity, alignment: .center)
                        .font(.headline)
                    }
                }
            }
            .navigationTitle(announcement == nil ? "New Announcement" : "Edit Announcement")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
            }
        }
    }

    private func save() async {
        guard !message.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }
        let until = displayUntil.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? nil : displayUntil
        let success: Bool
        if let announcement {
            success = await viewModel.update(notifId: announcement.id, type: type, message: message, displayUntil: until)
        } else {
            success = await viewModel.create(type: type, message: message, displayUntil: until)
        }
        if success { dismiss() }
    }
}
