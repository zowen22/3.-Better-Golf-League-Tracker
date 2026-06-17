import SwiftUI

@Observable
final class MatchupDetailViewModel {
    var matchup: Matchup?
    var roundId: Int?
    var isLocked = false
    var isLoading = false
    var isTogglingLock = false
    var errorMessage: String?

    func load(matchupId: Int) async {
        isLoading = true; errorMessage = nil
        defer { isLoading = false }
        do {
            let response: MatchupDetailResponse = try await APIClient.shared.request(.matchupDetail(matchupId))
            matchup = response.asMatchup
            roundId = response.roundId
            isLocked = response.isLocked
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func toggleLock(matchupId: Int) async {
        isTogglingLock = true
        defer { isTogglingLock = false }
        do {
            let r: LockResponse = try await APIClient.shared.request(.toggleLock(matchupId: matchupId))
            isLocked = r.locked
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

struct MatchupDetailView: View {
    let matchupId: Int
    @Environment(AuthViewModel.self) private var authVM
    @State private var vm = MatchupDetailViewModel()

    var isAdmin: Bool { authVM.currentUser?.isAdmin == true }

    var body: some View {
        Group {
            if vm.isLoading {
                ProgressView()
            } else if let m = vm.matchup {
                List {
                    // Match header
                    Section {
                        HStack {
                            teamColumn(m.team1)
                            Spacer()
                            Text("vs").font(.caption).foregroundStyle(.secondary)
                            Spacer()
                            teamColumn(m.team2)
                        }
                    }

                    // Details
                    Section("Details") {
                        LabeledContent("Week", value: "Week \(m.weekNumber)")
                        if let date = m.scheduledDate {
                            LabeledContent("Date", value: date)
                        }
                        if let teeTime = m.teeTime {
                            LabeledContent("Tee Time", value: teeTime)
                        }
                        if let hole = m.startingHole {
                            LabeledContent("Starting Hole", value: "\(hole)")
                        }
                        if let course = m.courseName {
                            LabeledContent("Course", value: course)
                        }
                        if let tee = m.teeName {
                            LabeledContent("Tee", value: tee)
                        }
                        LabeledContent("Status") {
                            HStack(spacing: 6) {
                                StatusBadge(status: m.status)
                                if vm.isLocked {
                                    Image(systemName: "lock.fill")
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                            }
                        }
                    }

                    // CTAs
                    Section {
                        if let roundId = vm.roundId {
                            NavigationLink("View Scorecard") {
                                ScorecardView(roundId: roundId)
                            }
                            if isAdmin {
                                lockToggleRow(matchupId: m.id)
                            }
                        } else if m.status == .scheduled, isAdmin {
                            NavigationLink("Enter Scores") {
                                ScoreInputView(matchup: m)
                            }
                        }
                    }
                }
                .listStyle(.insetGrouped)
                .navigationTitle("Week \(m.weekNumber)")
            } else if let err = vm.errorMessage {
                ContentUnavailableView(err, systemImage: "exclamationmark.triangle")
            }
        }
        .task { await vm.load(matchupId: matchupId) }
        .refreshable { await vm.load(matchupId: matchupId) }
    }

    @ViewBuilder
    private func lockToggleRow(matchupId: Int) -> some View {
        if vm.isTogglingLock {
            HStack { Spacer(); ProgressView(); Spacer() }
        } else {
            Button {
                Task { await vm.toggleLock(matchupId: matchupId) }
            } label: {
                Label(vm.isLocked ? "Unlock Round" : "Lock Round",
                      systemImage: vm.isLocked ? "lock.open" : "lock")
                    .foregroundStyle(vm.isLocked ? .orange : .secondary)
            }
        }
    }

    @ViewBuilder
    private func teamColumn(_ team: MatchupTeam) -> some View {
        VStack(alignment: .center, spacing: 4) {
            Text(team.shortName)
                .font(.subheadline.bold())
                .multilineTextAlignment(.center)
            ForEach(team.players) { player in
                HStack(spacing: 4) {
                    Text(player.displayName.split(separator: " ").last.map(String.init) ?? player.displayName)
                        .font(.caption)
                    if let hcp = player.handicap {
                        Text("(\(hcp, format: .number))")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                }
            }
        }
        .frame(maxWidth: .infinity)
    }
}
