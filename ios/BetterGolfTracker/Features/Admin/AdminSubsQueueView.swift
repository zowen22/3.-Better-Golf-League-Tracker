import SwiftUI

@Observable
final class AdminSubsQueueViewModel {
    var requests: [AdminSubRequest] = []
    var players: [LeaguePlayer] = []
    var isLoading = false
    var errorMessage: String?

    func load() async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            async let requestsResponse: AdminSubsPendingResponse = APIClient.shared.request(.adminSubsPending)
            async let playersResponse: LeaguePlayersResponse = APIClient.shared.request(.leaguePlayers)
            let (r, p) = try await (requestsResponse, playersResponse)
            requests = r.requests
            players = p.players
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    @discardableResult
    func assign(requestId: Int, subPlayerId: Int, adminNotes: String?) async -> Bool {
        do {
            let _: AdminSubActionResponse = try await APIClient.shared.request(
                .adminSubAssign(requestId: requestId, subPlayerId: subPlayerId, adminNotes: adminNotes)
            )
            requests.removeAll { $0.id == requestId }
            return true
        } catch {
            errorMessage = error.localizedDescription
            return false
        }
    }

    @discardableResult
    func dismiss(requestId: Int, adminNotes: String?) async -> Bool {
        do {
            let _: AdminSubActionResponse = try await APIClient.shared.request(
                .adminSubDismiss(requestId: requestId, adminNotes: adminNotes)
            )
            requests.removeAll { $0.id == requestId }
            return true
        } catch {
            errorMessage = error.localizedDescription
            return false
        }
    }
}

/// Admin open sub-requests queue — assign a sub or dismiss, reached from
/// `AdminView`, the natural neighbor to the existing pending-self-reports
/// section there.
struct AdminSubsQueueView: View {
    @State private var vm = AdminSubsQueueViewModel()
    @State private var assigningRequest: AdminSubRequest?

    var body: some View {
        Group {
            if vm.isLoading {
                ProgressView()
            } else if vm.requests.isEmpty {
                ContentUnavailableView(
                    vm.errorMessage ?? "No open sub requests",
                    systemImage: "person.badge.plus"
                )
            } else {
                List {
                    ForEach(vm.requests) { req in
                        requestRow(req)
                    }
                }
                .listStyle(.insetGrouped)
            }
        }
        .navigationTitle("Sub Requests")
        .navigationBarTitleDisplayMode(.inline)
        .task { await vm.load() }
        .refreshable { await vm.load() }
        .sheet(item: $assigningRequest) { req in
            AssignSubSheet(request: req, players: vm.players) { subPlayerId, notes in
                await vm.assign(requestId: req.id, subPlayerId: subPlayerId, adminNotes: notes)
            }
        }
    }

    @ViewBuilder
    private func requestRow(_ req: AdminSubRequest) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                if let week = req.weekNum {
                    Text("Week \(week)").font(.subheadline.bold())
                } else {
                    Text("Matchup #\(req.matchupId ?? 0)").font(.subheadline.bold())
                }
                Spacer()
                if let date = req.weekDate {
                    Text(date).font(.caption).foregroundStyle(.secondary)
                }
            }
            Text("\(req.team1Label) vs \(req.team2Label)")
                .font(.caption).foregroundStyle(.secondary)
            Text("Out: \(req.playerName)")
                .font(.caption.bold())
            if let notes = req.notes, !notes.isEmpty {
                Text(notes).font(.caption).foregroundStyle(.secondary)
            }
            HStack(spacing: 12) {
                Button("Assign Sub") { assigningRequest = req }
                    .font(.caption.bold())
                Button(role: .destructive) {
                    Task { await vm.dismiss(requestId: req.id, adminNotes: nil) }
                } label: {
                    Text("Dismiss").font(.caption.bold())
                }
            }
        }
        .padding(.vertical, 4)
    }
}

private struct AssignSubSheet: View {
    let request: AdminSubRequest
    let players: [LeaguePlayer]
    let onAssign: (Int, String?) async -> Bool
    @Environment(\.dismiss) private var dismiss

    @State private var selectedPlayerId: Int?
    @State private var adminNotes: String = ""
    @State private var isSaving = false
    @State private var errorMessage: String?

    var body: some View {
        NavigationStack {
            Form {
                Section("Filling In For") {
                    Text(request.playerName)
                }
                Section("Substitute Player") {
                    Picker("Sub", selection: $selectedPlayerId) {
                        Text("Select a player").tag(Int?.none)
                        ForEach(players) { p in
                            Text(p.displayName).tag(Int?.some(p.playerId))
                        }
                    }
                }
                Section("Admin Notes") {
                    TextField("Optional", text: $adminNotes, axis: .vertical)
                        .lineLimit(2...4)
                }
                if let errorMessage {
                    Section { Text(errorMessage).font(.caption).foregroundStyle(.red) }
                }
                Section {
                    if isSaving {
                        HStack { Spacer(); ProgressView(); Spacer() }
                    } else {
                        Button("Assign") { Task { await save() } }
                            .frame(maxWidth: .infinity, alignment: .center)
                            .font(.headline)
                    }
                }
            }
            .navigationTitle("Assign Sub")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
            }
        }
    }

    private func save() async {
        guard let selectedPlayerId else {
            errorMessage = "Pick a substitute player."
            return
        }
        isSaving = true
        defer { isSaving = false }
        let notes = adminNotes.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? nil : adminNotes
        let success = await onAssign(selectedPlayerId, notes)
        if success { dismiss() } else { errorMessage = "Failed to assign sub." }
    }
}
