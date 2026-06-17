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
        .navigationBarTitleDisplayMode(.inline)
        .task { await vm.load(roundId: roundId) }
        .refreshable { await vm.load(roundId: roundId) }
    }

    @ViewBuilder
    private func scorecardContent(_ r: ScorecardResponse) -> some View {
        List {
            Section {
                LabeledContent("Date", value: r.roundDate)
                LabeledContent("Week", value: "Week \(r.weekNumber)")
            }

            ForEach(r.players) { player in
                Section {
                    // Summary row
                    HStack {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(player.playerName).font(.subheadline.bold())
                            HStack(spacing: 6) {
                                Text(player.teamName).font(.caption).foregroundStyle(.secondary)
                                if player.isSub {
                                    Text("(sub)").font(.caption).foregroundStyle(.orange)
                                }
                            }
                        }
                        Spacer()
                        VStack(alignment: .trailing, spacing: 2) {
                            if let pts = player.totalPoints {
                                Text(String(format: "%.1f pts", pts))
                                    .font(.subheadline.bold())
                                    .foregroundStyle(.green)
                            }
                            HStack(spacing: 8) {
                                if let h = player.holePoints {
                                    Text(String(format: "H:%.1f", h))
                                        .font(.caption2).foregroundStyle(.secondary)
                                }
                                if let o = player.overallPoint {
                                    Text(String(format: "O:%.1f", o))
                                        .font(.caption2).foregroundStyle(.secondary)
                                }
                                if let hcp = player.handicapAtTimeOfPlay {
                                    Text("HCP \(hcp, format: .number)")
                                        .font(.caption2).foregroundStyle(.secondary)
                                }
                            }
                        }
                    }

                    if !player.holes.isEmpty {
                        HoleScoreGrid(holes: player.holes)
                    }
                } header: {
                    Text(player.playerName)
                }
            }
        }
        .listStyle(.insetGrouped)
    }
}

struct HoleScoreGrid: View {
    let holes: [HoleScore]

    private var totalGross: Int { holes.reduce(0) { $0 + $1.grossScore } }
    private var totalNet: Int   { holes.reduce(0) { $0 + $1.netScore } }
    private var totalPar: Int   { holes.compactMap(\.par).reduce(0, +) }

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            VStack(spacing: 4) {
                headerRow
                Divider()
                parRow
                grossRow
                netRow
                Divider()
                totalsRow
            }
            .padding(.vertical, 4)
        }
    }

    private var headerRow: some View {
        HStack(spacing: 0) {
            Text("Hole").font(.caption2).foregroundStyle(.secondary).frame(width: 40, alignment: .leading)
            ForEach(holes, id: \.holeNumber) { h in
                Text("\(h.holeNumber)").font(.caption2.bold()).foregroundStyle(.secondary)
                    .frame(width: 30)
            }
            Text("Tot").font(.caption2.bold()).foregroundStyle(.secondary).frame(width: 36)
        }
    }

    private var parRow: some View {
        HStack(spacing: 0) {
            Text("Par").font(.caption2).foregroundStyle(.secondary).frame(width: 40, alignment: .leading)
            ForEach(holes, id: \.holeNumber) { h in
                Text(h.par.map { "\($0)" } ?? "—")
                    .font(.caption2).foregroundStyle(.secondary).frame(width: 30)
            }
            Text(totalPar > 0 ? "\(totalPar)" : "—")
                .font(.caption2).foregroundStyle(.secondary).frame(width: 36)
        }
    }

    private var grossRow: some View {
        HStack(spacing: 0) {
            Text("Gross").font(.caption2).foregroundStyle(.secondary).frame(width: 40, alignment: .leading)
            ForEach(holes, id: \.holeNumber) { h in
                Text("\(h.grossScore)").font(.caption2.bold()).frame(width: 30)
            }
            Text("\(totalGross)").font(.caption2.bold()).frame(width: 36)
        }
    }

    private var netRow: some View {
        HStack(spacing: 0) {
            Text("Net").font(.caption2).foregroundStyle(.secondary).frame(width: 40, alignment: .leading)
            ForEach(holes, id: \.holeNumber) { h in
                Text("\(h.netScore)")
                    .font(.caption2)
                    .foregroundStyle(h.par.map { h.netScore < $0 } == true ? .green : .primary)
                    .frame(width: 30)
            }
            Text("\(totalNet)").font(.caption2.bold()).frame(width: 36)
        }
    }

    private var totalsRow: some View {
        HStack(spacing: 0) {
            Text("+/−").font(.caption2.bold()).foregroundStyle(.secondary).frame(width: 40, alignment: .leading)
            ForEach(holes, id: \.holeNumber) { h in
                let diff = h.netScore - (h.par ?? h.netScore)
                Text(diff == 0 ? "E" : (diff > 0 ? "+\(diff)" : "\(diff)"))
                    .font(.caption2)
                    .foregroundStyle(diff < 0 ? .green : diff == 0 ? .secondary : .orange)
                    .frame(width: 30)
            }
            let totalDiff = totalNet - totalPar
            Text(totalPar == 0 ? "—" : (totalDiff == 0 ? "E" : (totalDiff > 0 ? "+\(totalDiff)" : "\(totalDiff)")))
                .font(.caption2.bold())
                .foregroundStyle(totalDiff < 0 ? .green : totalDiff == 0 ? .secondary : .orange)
                .frame(width: 36)
        }
    }
}
