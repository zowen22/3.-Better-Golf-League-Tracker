import SwiftUI

@Observable
final class OverridePointsViewModel {
    var overrides: [PointOverride] = []
    var isLoading = false
    var isSaving = false
    var errorMessage: String?

    func loadOverrides(matchupId: Int) async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            let r: MatchupOverridesResponse = try await APIClient.shared.request(.matchupOverrides(matchupId: matchupId))
            overrides = r.overrides
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    @discardableResult
    func save(matchupId: Int, values: [(playerId: Int, totalPoints: Double)], reason: String) async -> Bool {
        isSaving = true
        errorMessage = nil
        defer { isSaving = false }
        do {
            let _: OverridePointsResponse = try await APIClient.shared.request(
                .overridePoints(matchupId: matchupId, values: values, reason: reason)
            )
            await loadOverrides(matchupId: matchupId)
            return true
        } catch {
            errorMessage = error.localizedDescription
            return false
        }
    }

    @discardableResult
    func clear(matchupId: Int, playerId: Int) async -> Bool {
        isSaving = true
        errorMessage = nil
        defer { isSaving = false }
        do {
            let _: OkResponse = try await APIClient.shared.request(.clearOverridePoints(matchupId: matchupId, playerId: playerId))
            await loadOverrides(matchupId: matchupId)
            return true
        } catch {
            errorMessage = error.localizedDescription
            return false
        }
    }
}

/// Admin per-player point-value override editor for a matchup, reached from
/// `MatchupDetailView`'s admin section. Requires a reason whenever any value
/// actually changes (mirrors the web app's validation — see api.py).
struct OverridePointsView: View {
    let matchup: Matchup
    @State private var vm = OverridePointsViewModel()
    @State private var editedValues: [Int: String] = [:]
    @State private var reason: String = ""
    @State private var saveSuccess = false
    @Environment(\.dismiss) private var dismiss

    private var allPlayers: [MatchupPlayer] {
        matchup.team1.players + matchup.team2.players
    }

    var body: some View {
        Form {
            Section("Players") {
                ForEach(allPlayers) { player in
                    playerRow(player)
                }
            }

            if !vm.overrides.isEmpty {
                Section("Active Overrides") {
                    ForEach(vm.overrides) { o in
                        HStack {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(playerName(o.playerId))
                                    .font(.caption.bold())
                                if let reason = o.reason, !reason.isEmpty {
                                    Text(reason).font(.caption2).foregroundStyle(.secondary)
                                }
                            }
                            Spacer()
                            Button("Clear") {
                                Task { await vm.clear(matchupId: matchup.id, playerId: o.playerId) }
                            }
                            .font(.caption.bold())
                            .foregroundStyle(.red)
                        }
                    }
                }
            }

            Section("Reason (required to save)") {
                TextField("Why are you overriding these points?", text: $reason, axis: .vertical)
                    .lineLimit(2...4)
            }

            if let err = vm.errorMessage {
                Section {
                    Text(err).font(.caption).foregroundStyle(.red)
                }
            }

            Section {
                if vm.isSaving {
                    HStack { Spacer(); ProgressView(); Spacer() }
                } else if saveSuccess {
                    Label("Saved.", systemImage: "checkmark.circle.fill").foregroundStyle(.green)
                } else {
                    Button("Save Overrides") { Task { await save() } }
                        .frame(maxWidth: .infinity, alignment: .center)
                        .font(.headline)
                }
            }
        }
        .navigationTitle("Override Points")
        .navigationBarTitleDisplayMode(.inline)
        .task { await vm.loadOverrides(matchupId: matchup.id) }
    }

    @ViewBuilder
    private func playerRow(_ player: MatchupPlayer) -> some View {
        LabeledContent(player.displayName) {
            TextField("Points", text: Binding(
                get: { editedValues[player.id] ?? currentValue(player.id) },
                set: { editedValues[player.id] = $0 }
            ))
            .keyboardType(.decimalPad)
            .multilineTextAlignment(.trailing)
        }
    }

    private func currentValue(_ playerId: Int) -> String {
        if let o = vm.overrides.first(where: { $0.playerId == playerId }) {
            return String(o.overrideValue)
        }
        return ""
    }

    private func playerName(_ playerId: Int) -> String {
        allPlayers.first { $0.id == playerId }?.displayName ?? "Player \(playerId)"
    }

    private func save() async {
        let values: [(playerId: Int, totalPoints: Double)] = editedValues.compactMap { pid, text in
            guard let v = Double(text) else { return nil }
            return (playerId: pid, totalPoints: v)
        }
        guard !values.isEmpty else { return }
        let success = await vm.save(matchupId: matchup.id, values: values, reason: reason)
        if success {
            saveSuccess = true
            editedValues.removeAll()
        }
    }
}
