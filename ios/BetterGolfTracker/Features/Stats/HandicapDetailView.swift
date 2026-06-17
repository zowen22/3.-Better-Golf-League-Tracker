import SwiftUI
import Charts

// MARK: - Player picker

@Observable
final class HandicapPlayerListViewModel {
    var players: [LeaguePlayer] = []
    var isLoading = false
    var errorMessage: String?
    var searchText = ""

    var filtered: [LeaguePlayer] {
        guard !searchText.isEmpty else { return players }
        return players.filter {
            $0.displayName.localizedCaseInsensitiveContains(searchText)
        }
    }

    func load() async {
        isLoading = true; errorMessage = nil
        defer { isLoading = false }
        do {
            let r: LeaguePlayersResponse = try await APIClient.shared.request(.leaguePlayers)
            players = r.players
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

struct HandicapPlayerListView: View {
    @Environment(AuthViewModel.self) private var authVM
    @State private var vm = HandicapPlayerListViewModel()

    var body: some View {
        List {
            if vm.isLoading {
                HStack { Spacer(); ProgressView(); Spacer() }
            } else if let err = vm.errorMessage {
                Text(err).foregroundStyle(.secondary)
            } else {
                ForEach(vm.filtered) { player in
                    NavigationLink {
                        HandicapDetailView(player: player)
                    } label: {
                        playerRow(player)
                    }
                }
            }
        }
        .listStyle(.insetGrouped)
        .searchable(text: $vm.searchText, prompt: "Search players")
        .navigationTitle("Handicap Breakdown")
        .task { await vm.load() }
        .refreshable { await vm.load() }
    }

    @ViewBuilder
    private func playerRow(_ player: LeaguePlayer) -> some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text(player.displayName)
                    .font(.subheadline.bold())
                Text(player.lastName)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            if let hcp = player.handicapIndex {
                VStack(alignment: .trailing, spacing: 1) {
                    Text(String(format: "%.1f", hcp))
                        .font(.title3.bold())
                    Text("HCP")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            } else {
                Text("N/A")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(.vertical, 2)
    }
}

// MARK: - Detail view

@Observable
final class HandicapDetailViewModel {
    var detail: HandicapDetailResponse?
    var isLoading = false
    var errorMessage: String?

    func load(playerId: Int) async {
        isLoading = true; errorMessage = nil
        defer { isLoading = false }
        do {
            detail = try await APIClient.shared.request(.handicapDetail(playerId: playerId))
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

struct HandicapDetailView: View {
    let player: LeaguePlayer
    @State private var vm = HandicapDetailViewModel()

    var body: some View {
        Group {
            if vm.isLoading {
                ProgressView()
            } else if let d = vm.detail {
                detailContent(d)
            } else if let err = vm.errorMessage {
                ContentUnavailableView(err, systemImage: "exclamationmark.triangle")
            }
        }
        .navigationTitle(player.displayName)
        .navigationBarTitleDisplayMode(.inline)
        .task { await vm.load(playerId: player.playerId) }
        .refreshable { await vm.load(playerId: player.playerId) }
    }

    @ViewBuilder
    private func detailContent(_ d: HandicapDetailResponse) -> some View {
        List {
            // ── Summary cards ──
            summarySection(d)

            // ── Window rounds ──
            windowSection(d)

            // ── All rounds ──
            allRoundsSection(d)

            // ── History trend ──
            if d.hcpHistory.count > 1 {
                historySection(d)
            }
        }
        .listStyle(.insetGrouped)
    }

    // MARK: Summary

    @ViewBuilder
    private func summarySection(_ d: HandicapDetailResponse) -> some View {
        Section {
            HStack(spacing: 0) {
                summaryTile(
                    label: "Current Index",
                    value: d.currentHandicap.map { String(format: "%.1f", $0) } ?? "N/A",
                    sub: d.lastCalcDate.map { "as of \($0)" } ?? "starting HCP"
                )
                Divider()
                summaryTile(
                    label: "Rounds",
                    value: "\(d.realCount)",
                    sub: "min \(d.settings.minRounds) required"
                )
                Divider()
                summaryTile(
                    label: "Window",
                    value: "\(d.settings.window)",
                    sub: "last \(d.settings.window) rounds"
                )
                Divider()
                summaryTile(
                    label: "Averaged",
                    value: "\(d.settings.roundsToAvg)",
                    sub: dropSub(d.settings)
                )
            }
            .frame(maxWidth: .infinity)

            if !d.hasEnough {
                Label("Need \(d.settings.minRounds - d.realCount) more round(s) for a calculated index",
                      systemImage: "info.circle")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            if d.committeeAdjustment != 0 {
                HStack {
                    Label("Committee adjustment", systemImage: "person.badge.plus")
                        .font(.subheadline)
                    Spacer()
                    Text(String(format: "%+.1f", d.committeeAdjustment))
                        .font(.subheadline.bold())
                        .foregroundStyle(d.committeeAdjustment > 0 ? .red : .green)
                }
                if let reason = d.adjReason {
                    Text(reason)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
        } header: {
            Text("Overview")
        }
    }

    @ViewBuilder
    private func summaryTile(label: String, value: String, sub: String) -> some View {
        VStack(spacing: 3) {
            Text(value)
                .font(.title2.bold())
            Text(label)
                .font(.caption2)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
            Text(sub)
                .font(.system(size: 9))
                .foregroundStyle(.tertiary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 10)
    }

    private func dropSub(_ s: HandicapSettings) -> String {
        var parts: [String] = []
        if s.highDrop > 0 { parts.append("-\(s.highDrop) high") }
        if s.lowDrop  > 0 { parts.append("-\(s.lowDrop) low") }
        return parts.isEmpty ? "no drops" : parts.joined(separator: ", ")
    }

    // MARK: Window

    @ViewBuilder
    private func windowSection(_ d: HandicapDetailResponse) -> some View {
        Section {
            if d.combinedWindow.isEmpty {
                Text("No rounds in calculation window yet.")
                    .foregroundStyle(.secondary)
            } else {
                ForEach(d.combinedWindow) { round in
                    windowRow(round, settings: d.settings)
                }

                if let avg = countingAvg(d.combinedWindow), d.hasEnough {
                    Divider()
                    HStack {
                        Text("Avg differential")
                            .font(.subheadline)
                        Spacer()
                        Text(String(format: "%.2f", avg))
                            .font(.subheadline.bold())
                    }
                    HStack {
                        Text("× \(Int(d.settings.hcpPct))% =")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Spacer()
                        if let idx = d.computedIndex {
                            Text(String(format: "%.1f", idx))
                                .font(.headline.bold())
                                .foregroundStyle(.green)
                        }
                    }
                }
            }
        } header: {
            Text("Calculation Window (\(d.settings.window) rounds)")
        } footer: {
            windowLegend
        }
    }

    @ViewBuilder
    private func windowRow(_ round: HandicapRound, settings: HandicapSettings) -> some View {
        HStack(spacing: 10) {
            // Status indicator
            statusDot(round.status)

            VStack(alignment: .leading, spacing: 2) {
                if let wk = round.weekNumber {
                    Text("Week \(wk)")
                        .font(.subheadline.bold())
                } else {
                    Text(round.courseName)
                        .font(.subheadline.bold())
                }
                HStack(spacing: 6) {
                    if let date = round.roundDate {
                        Text(date).font(.caption).foregroundStyle(.secondary)
                    }
                    if round.weekNumber != nil {
                        Text(round.courseName).font(.caption).foregroundStyle(.secondary)
                    }
                }
            }

            Spacer()

            VStack(alignment: .trailing, spacing: 2) {
                Text(diffLabel(round.diff))
                    .font(.subheadline.bold())
                    .foregroundStyle(diffColor(round.diff))
                Text("\(round.gross) / \(round.par)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            statusLabel(round.status)
        }
        .padding(.vertical, 2)
        .opacity(round.status == "outside" ? 0.45 : 1.0)
    }

    @ViewBuilder
    private var windowLegend: some View {
        HStack(spacing: 14) {
            legendItem(color: .green, label: "Counting")
            legendItem(color: .orange, label: "Dropped high")
            legendItem(color: .blue, label: "Dropped low")
        }
        .font(.caption2)
        .padding(.top, 2)
    }

    @ViewBuilder
    private func legendItem(color: Color, label: String) -> some View {
        HStack(spacing: 4) {
            Circle().fill(color).frame(width: 7, height: 7)
            Text(label).foregroundStyle(.secondary)
        }
    }

    // MARK: All rounds

    @ViewBuilder
    private func allRoundsSection(_ d: HandicapDetailResponse) -> some View {
        Section("All Rounds (\(d.realCount))") {
            if d.rounds.isEmpty {
                Text("No completed rounds yet.")
                    .foregroundStyle(.secondary)
            } else {
                ForEach(d.rounds) { round in
                    HStack {
                        VStack(alignment: .leading, spacing: 2) {
                            if let wk = round.weekNumber {
                                Text("Week \(wk)").font(.subheadline)
                            }
                            Text(round.courseName)
                                .font(.caption).foregroundStyle(.secondary)
                            if let date = round.roundDate {
                                Text(date).font(.caption2).foregroundStyle(.tertiary)
                            }
                        }
                        Spacer()
                        VStack(alignment: .trailing, spacing: 2) {
                            Text(diffLabel(round.diff))
                                .font(.subheadline.bold())
                                .foregroundStyle(diffColor(round.diff))
                            Text("\(round.gross) gross")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }
                    .padding(.vertical, 2)
                    .opacity(round.inWindow ? 1.0 : 0.5)
                }
            }
        }
    }

    // MARK: History chart

    @ViewBuilder
    private func historySection(_ d: HandicapDetailResponse) -> some View {
        Section("Index History") {
            Chart {
                ForEach(Array(d.hcpHistory.reversed().enumerated()), id: \.offset) { i, entry in
                    LineMark(
                        x: .value("Calc", i + 1),
                        y: .value("HCP", entry.index)
                    )
                    .symbol(Circle())
                    .symbolSize(25)
                    .foregroundStyle(Color.green)
                    PointMark(
                        x: .value("Calc", i + 1),
                        y: .value("HCP", entry.index)
                    )
                    .foregroundStyle(Color.green)
                }
            }
            .frame(height: 120)
            .chartYAxis {
                AxisMarks(position: .leading)
            }
            .chartXAxis(.hidden)
            .padding(.vertical, 8)
        }
    }

    // MARK: Helpers

    private func countingAvg(_ rounds: [HandicapRound]) -> Double? {
        let diffs = rounds.filter { $0.status == "counting" }.map(\.diff)
        guard !diffs.isEmpty else { return nil }
        return diffs.reduce(0, +) / Double(diffs.count)
    }

    private func diffLabel(_ diff: Double) -> String {
        diff >= 0 ? "+\(String(format: "%.1f", diff))" : String(format: "%.1f", diff)
    }

    private func diffColor(_ diff: Double) -> Color {
        diff < 0 ? .green : diff == 0 ? .secondary : .red
    }

    @ViewBuilder
    private func statusDot(_ status: String) -> some View {
        Circle()
            .fill(statusColor(status))
            .frame(width: 8, height: 8)
    }

    @ViewBuilder
    private func statusLabel(_ status: String) -> some View {
        switch status {
        case "dropped_high":
            Text("HIGH")
                .font(.system(size: 9, weight: .bold))
                .foregroundStyle(.orange)
                .padding(.horizontal, 5).padding(.vertical, 2)
                .background(Color.orange.opacity(0.15))
                .clipShape(Capsule())
        case "dropped_low":
            Text("LOW")
                .font(.system(size: 9, weight: .bold))
                .foregroundStyle(.blue)
                .padding(.horizontal, 5).padding(.vertical, 2)
                .background(Color.blue.opacity(0.15))
                .clipShape(Capsule())
        case "padding":
            Text("PAD")
                .font(.system(size: 9, weight: .bold))
                .foregroundStyle(.secondary)
                .padding(.horizontal, 5).padding(.vertical, 2)
                .background(Color.secondary.opacity(0.1))
                .clipShape(Capsule())
        default:
            EmptyView()
        }
    }

    private func statusColor(_ status: String) -> Color {
        switch status {
        case "counting":      return .green
        case "dropped_high":  return .orange
        case "dropped_low":   return .blue
        case "padding":       return .gray
        default:              return .clear
        }
    }
}
