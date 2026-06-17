import SwiftUI

@Observable
final class ScorecardViewModel {
    var response: ScorecardResponse?
    var isLoading = false
    var errorMessage: String?

    func load(roundId: Int) async {
        isLoading = true; errorMessage = nil
        defer { isLoading = false }
        do {
            response = try await APIClient.shared.request(.scorecard(roundId: roundId))
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

struct ScorecardView: View {
    let roundId: Int
    @State private var vm = ScorecardViewModel()

    var body: some View {
        Group {
            if vm.isLoading {
                ProgressView()
            } else if let r = vm.response {
                scorecardContent(r)
            } else if let err = vm.errorMessage {
                ContentUnavailableView(err, systemImage: "exclamationmark.triangle")
            }
        }
        .navigationTitle("Scorecard")
        .task { await vm.load(roundId: roundId) }
        .refreshable { await vm.load(roundId: roundId) }
    }

    @ViewBuilder
    private func scorecardContent(_ r: ScorecardResponse) -> some View {
        List {
            // Summary header
            Section {
                LabeledContent("Date", value: r.roundDate)
                LabeledContent("Week", value: "Week \(r.weekNumber)")
            }

            // Per-player sections
            ForEach(r.players) { player in
                Section {
                    // Points summary row
                    HStack {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(player.playerName).font(.subheadline.bold())
                            Text(player.teamName).font(.caption).foregroundStyle(.secondary)
                        }
                        Spacer()
                        VStack(alignment: .trailing, spacing: 2) {
                            if let pts = player.totalPoints {
                                Text(String(format: "%.1f pts", pts))
                                    .font(.subheadline.bold())
                                    .foregroundStyle(.green)
                            }
                            if let hcp = player.handicapAtTimeOfPlay {
                                Text("HCP \(hcp, format: .number)")
                                    .font(.caption).foregroundStyle(.secondary)
                            }
                        }
                    }

                    // Hole scores grid
                    if !player.holes.isEmpty {
                        HoleScoreGrid(holes: player.holes)
                    }
                } header: {
                    Text(player.playerName)
                }
            }
        }
    }
}

struct HoleScoreGrid: View {
    let holes: [HoleScore]

    var body: some View {
        VStack(spacing: 4) {
            // Header row
            HStack(spacing: 0) {
                Text("Hole").font(.caption2).foregroundStyle(.secondary).frame(width: 36)
                ForEach(holes, id: \.holeNumber) { h in
                    Text("\(h.holeNumber)").font(.caption2).foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity)
                }
            }
            Divider()
            // Par row
            HStack(spacing: 0) {
                Text("Par").font(.caption2).foregroundStyle(.secondary).frame(width: 36)
                ForEach(holes, id: \.holeNumber) { h in
                    Text(h.par.map { "\($0)" } ?? "—")
                        .font(.caption2).foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity)
                }
            }
            // Gross row
            HStack(spacing: 0) {
                Text("Gross").font(.caption2).foregroundStyle(.secondary).frame(width: 36)
                ForEach(holes, id: \.holeNumber) { h in
                    Text("\(h.grossScore)")
                        .font(.caption2.bold())
                        .frame(maxWidth: .infinity)
                }
            }
            // Net row
            HStack(spacing: 0) {
                Text("Net").font(.caption2).foregroundStyle(.secondary).frame(width: 36)
                ForEach(holes, id: \.holeNumber) { h in
                    Text("\(h.netScore)")
                        .font(.caption2)
                        .foregroundStyle(h.netScore < (h.par ?? 4) ? .green : .primary)
                        .frame(maxWidth: .infinity)
                }
            }
        }
        .padding(.vertical, 4)
    }
}
