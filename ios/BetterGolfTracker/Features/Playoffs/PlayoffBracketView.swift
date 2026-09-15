import SwiftUI

@Observable
final class PlayoffBracketViewModel {
    var rounds: [PlayoffRound] = []
    var champion: PlayoffTeamRef?
    var isLoading = false
    var errorMessage: String?
    var isSavingResult = false

    func load(seasonId: Int? = nil) async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            let r: PlayoffBracketResponse = try await APIClient.shared.request(.playoffs(seasonId: seasonId))
            rounds = r.rounds
            champion = r.champion
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    @discardableResult
    func saveResult(matchupId: Int, team1Points: Double, team2Points: Double, winnerTeamId: Int?, seasonId: Int?) async -> Bool {
        isSavingResult = true
        errorMessage = nil
        defer { isSavingResult = false }
        do {
            let _: PlayoffResultResponse = try await APIClient.shared.request(
                .savePlayoffResult(matchupId: matchupId, team1Points: team1Points, team2Points: team2Points, winnerTeamId: winnerTeamId)
            )
            await load(seasonId: seasonId)
            return true
        } catch {
            errorMessage = error.localizedDescription
            return false
        }
    }
}

/// Playoff bracket — read-only for all members, with an inline result-entry
/// affordance for admins. Reached from `StatsHubView`'s menu, alongside the
/// Contests entry Tier 1 added there.
struct PlayoffBracketView: View {
    @State private var vm = PlayoffBracketViewModel()
    @Environment(AuthViewModel.self) private var authVM
    @State private var editingMatchup: PlayoffMatchup?

    var isAdmin: Bool { authVM.currentUser?.isAdmin == true }
    private var seasonId: Int? { authVM.currentUser?.seasonId }

    var body: some View {
        Group {
            if vm.isLoading {
                ProgressView()
            } else if vm.rounds.isEmpty {
                ContentUnavailableView(
                    vm.errorMessage ?? "No playoff bracket yet",
                    systemImage: "trophy"
                )
            } else {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(alignment: .top, spacing: 20) {
                        ForEach(vm.rounds) { round in
                            roundColumn(round)
                        }
                        if let champ = vm.champion {
                            championColumn(champ)
                        }
                    }
                    .padding()
                }
            }
        }
        .navigationTitle("Playoffs")
        .navigationBarTitleDisplayMode(.inline)
        .task { await vm.load(seasonId: seasonId) }
        .refreshable { await vm.load(seasonId: seasonId) }
        .sheet(item: $editingMatchup) { matchup in
            PlayoffResultSheet(matchup: matchup, isSaving: vm.isSavingResult) { t1, t2, winner in
                await vm.saveResult(matchupId: matchup.id, team1Points: t1, team2Points: t2, winnerTeamId: winner, seasonId: seasonId)
            }
        }
    }

    @ViewBuilder
    private func roundColumn(_ round: PlayoffRound) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(round.label)
                .font(.subheadline.bold())
                .foregroundStyle(.secondary)
            ForEach(round.matchups) { matchup in
                playoffMatchupCard(matchup)
            }
        }
        .frame(width: 190)
    }

    @ViewBuilder
    private func playoffMatchupCard(_ matchup: PlayoffMatchup) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            playoffTeamRow(matchup.team1, points: matchup.team1Points, isWinner: matchup.winnerTeamId == matchup.team1?.teamId)
            Divider()
            playoffTeamRow(matchup.team2, points: matchup.team2Points, isWinner: matchup.winnerTeamId == matchup.team2?.teamId)

            if isAdmin, matchup.team1 != nil, matchup.team2 != nil {
                Button {
                    editingMatchup = matchup
                } label: {
                    Label(matchup.winnerTeamId == nil ? "Enter Result" : "Edit Result", systemImage: "pencil")
                        .font(.caption2.bold())
                }
                .padding(.top, 2)
            }
        }
        .padding(10)
        .background(Color.secondary.opacity(0.08))
        .clipShape(RoundedRectangle(cornerRadius: 10))
    }

    @ViewBuilder
    private func playoffTeamRow(_ team: PlayoffTeamRef?, points: Double?, isWinner: Bool) -> some View {
        HStack {
            Text(team?.label ?? "TBD")
                .font(.caption.weight(isWinner ? .bold : .regular))
                .foregroundStyle(isWinner ? .primary : .secondary)
                .lineLimit(1)
            Spacer()
            if let points {
                Text(String(format: "%.1f", points))
                    .font(.caption.bold())
                    .foregroundStyle(isWinner ? .green : .secondary)
            }
        }
    }

    @ViewBuilder
    private func championColumn(_ champion: PlayoffTeamRef) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Champion")
                .font(.subheadline.bold())
                .foregroundStyle(.secondary)
            VStack(spacing: 8) {
                Image(systemName: "trophy.fill")
                    .font(.title)
                    .foregroundStyle(.yellow)
                Text(champion.label)
                    .font(.subheadline.bold())
                    .multilineTextAlignment(.center)
            }
            .frame(maxWidth: .infinity)
            .padding()
            .background(Color.yellow.opacity(0.12))
            .clipShape(RoundedRectangle(cornerRadius: 10))
        }
        .frame(width: 160)
    }
}

private struct PlayoffResultSheet: View {
    let matchup: PlayoffMatchup
    let isSaving: Bool
    let onSave: (Double, Double, Int?) async -> Bool
    @Environment(\.dismiss) private var dismiss
    @State private var team1Points: String = ""
    @State private var team2Points: String = ""
    @State private var winnerTeamId: Int?
    @State private var errorMessage: String?

    var body: some View {
        NavigationStack {
            Form {
                Section("Score") {
                    LabeledContent(matchup.team1?.label ?? "Team 1") {
                        TextField("Points", text: $team1Points)
                            .keyboardType(.decimalPad)
                            .multilineTextAlignment(.trailing)
                    }
                    LabeledContent(matchup.team2?.label ?? "Team 2") {
                        TextField("Points", text: $team2Points)
                            .keyboardType(.decimalPad)
                            .multilineTextAlignment(.trailing)
                    }
                }
                if isTied {
                    Section("Winner (tied — pick one)") {
                        Picker("Winner", selection: $winnerTeamId) {
                            Text("—").tag(Int?.none)
                            if let t1 = matchup.team1 { Text(t1.label).tag(Int?.some(t1.teamId)) }
                            if let t2 = matchup.team2 { Text(t2.label).tag(Int?.some(t2.teamId)) }
                        }
                    }
                }
                if let errorMessage {
                    Section {
                        Text(errorMessage).font(.caption).foregroundStyle(.red)
                    }
                }
                Section {
                    if isSaving {
                        HStack { Spacer(); ProgressView(); Spacer() }
                    } else {
                        Button("Save Result") { Task { await save() } }
                            .frame(maxWidth: .infinity, alignment: .center)
                            .font(.headline)
                    }
                }
            }
            .navigationTitle("Playoff Result")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
            }
            .onAppear {
                if let p = matchup.team1Points { team1Points = String(p) }
                if let p = matchup.team2Points { team2Points = String(p) }
                winnerTeamId = matchup.winnerTeamId
            }
        }
    }

    private var isTied: Bool {
        guard let t1 = Double(team1Points), let t2 = Double(team2Points) else { return false }
        return t1 == t2
    }

    private func save() async {
        guard let t1 = Double(team1Points), let t2 = Double(team2Points) else {
            errorMessage = "Enter valid point values for both teams."
            return
        }
        if t1 == t2 && winnerTeamId == nil {
            errorMessage = "Scores are tied — pick a winner."
            return
        }
        let success = await onSave(t1, t2, winnerTeamId)
        if success { dismiss() } else { errorMessage = "Failed to save result." }
    }
}
