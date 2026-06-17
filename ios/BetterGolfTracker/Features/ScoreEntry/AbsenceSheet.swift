import SwiftUI

/// Bottom sheet presented from ScoreInputView to mark absent players and assign subs.
struct AbsenceSheet: View {
    let players: [MatchupPlayer]
    let leaguePlayers: [MatchupPlayer]   // full league roster for sub selection
    @Binding var absences: [AbsenceInput]
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            List {
                Section {
                    Text("Mark players who won't play. Optionally assign a sub from the league roster.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }

                Section("Matchup Players") {
                    ForEach(players) { player in
                        AbsenceRow(
                            player: player,
                            leaguePlayers: leaguePlayers.filter { $0.id != player.id },
                            absences: $absences
                        )
                    }
                }
            }
            .listStyle(.insetGrouped)
            .navigationTitle("Absences / Subs")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Done") { dismiss() }
                        .fontWeight(.semibold)
                }
            }
        }
    }
}

struct AbsenceRow: View {
    let player: MatchupPlayer
    let leaguePlayers: [MatchupPlayer]
    @Binding var absences: [AbsenceInput]

    private var isAbsent: Bool { absences.contains { $0.playerId == player.id } }
    private var subId: Int? { absences.first(where: { $0.playerId == player.id })?.subPlayerId }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Toggle(isOn: Binding(
                get: { isAbsent },
                set: { absent in
                    if absent {
                        absences.append(AbsenceInput(playerId: player.id, subPlayerId: nil))
                    } else {
                        absences.removeAll { $0.playerId == player.id }
                    }
                }
            )) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(player.displayName).font(.subheadline.bold())
                    if let hcp = player.handicap {
                        Text("HCP \(hcp, format: .number)").font(.caption).foregroundStyle(.secondary)
                    }
                }
            }

            if isAbsent {
                Picker("Sub", selection: Binding(
                    get: { subId },
                    set: { newSub in
                        if let idx = absences.firstIndex(where: { $0.playerId == player.id }) {
                            absences[idx] = AbsenceInput(playerId: player.id, subPlayerId: newSub)
                        }
                    }
                )) {
                    Text("No sub (forfeit)").tag(Optional<Int>.none)
                    ForEach(leaguePlayers) { p in
                        Text(p.displayName).tag(Optional(p.id))
                    }
                }
                .pickerStyle(.menu)
                .padding(.leading, 4)
            }
        }
        .padding(.vertical, 2)
    }
}
