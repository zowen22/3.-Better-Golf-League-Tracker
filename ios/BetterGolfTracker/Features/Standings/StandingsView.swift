import SwiftUI

private struct ShareableText: Identifiable {
    let id = UUID()
    let value: String
}

struct StandingsView: View {
    @State private var viewModel = StandingsViewModel()
    @State private var showRecord = true
    @State private var shareItem: ShareableText?
    @AppStorage("selectedSeasonId") private var selectedSeasonId: Int = 0

    var body: some View {
        NavigationStack {
            List {
                if viewModel.standings.isEmpty && !viewModel.isLoading {
                    ContentUnavailableView(
                        viewModel.errorMessage ?? "No standings yet",
                        systemImage: "chart.bar"
                    )
                } else {
                    ForEach(Array(viewModel.standings.enumerated()), id: \.element.id) { i, standing in
                        StandingRow(standing: standing, position: i + 1, showRecord: showRecord)
                    }
                }
            }
            .listStyle(.insetGrouped)
            .navigationTitle("Standings")
            .safeAreaInset(edge: .top) {
                if viewModel.isShowingCached {
                    Label("Showing cached data — pull to refresh", systemImage: "wifi.slash")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .padding(.vertical, 6)
                        .frame(maxWidth: .infinity)
                        .background(.bar)
                }
            }
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    HStack(spacing: 4) {
                        if viewModel.seasons.count > 1 {
                            Menu {
                                ForEach(viewModel.seasons) { season in
                                    Button {
                                        viewModel.selectedSeasonId = season.seasonId
                                        selectedSeasonId = season.seasonId
                                        Task { await viewModel.loadSeason(season.seasonId) }
                                    } label: {
                                        if season.seasonId == viewModel.selectedSeasonId {
                                            Label(season.seasonName, systemImage: "checkmark")
                                        } else {
                                            Text(season.seasonName)
                                        }
                                    }
                                }
                            } label: {
                                Image(systemName: "calendar")
                            }
                        }
                        NavigationLink {
                            PodiumView()
                        } label: {
                            Image(systemName: "trophy.fill")
                        }
                    }
                }
                ToolbarItem(placement: .navigationBarLeading) {
                    Menu {
                        Toggle("Show Record", isOn: $showRecord)
                        Button {
                            shareItem = ShareableText(value: buildShareText())
                        } label: {
                            Label("Copy for Group Text", systemImage: "doc.on.doc")
                        }
                    } label: {
                        Image(systemName: "square.and.arrow.up")
                    }
                }
            }
            .sheet(item: $shareItem) { item in
                ShareSheet(items: [item.value])
            }
            .refreshable { await viewModel.load() }
            .task {
                await viewModel.loadSeasons()
                if selectedSeasonId != 0 {
                    viewModel.selectedSeasonId = selectedSeasonId
                }
                await viewModel.load()
            }
            .overlay { if viewModel.isLoading { ProgressView() } }
        }
    }

    private func buildShareText() -> String {
        let seasonName = viewModel.seasonName ?? "Season"
        var lines = [seasonName + " Standings", ""]
        for (i, s) in viewModel.standings.enumerated() {
            let pts = Int(s.points.rounded())
            let rec = s.ties > 0 ? "\(s.wins)-\(s.losses)-\(s.ties)" : "\(s.wins)-\(s.losses)"
            let line = showRecord
                ? "\(i + 1). \(s.shortName)  \(pts) pts  (\(rec))"
                : "\(i + 1). \(s.shortName)  \(pts) pts"
            lines.append(line)
        }
        return lines.joined(separator: "\n")
    }
}

struct StandingRow: View {
    let standing: Standing
    let position: Int
    var showRecord: Bool = true

    var rankColor: Color {
        switch position {
        case 1: return .yellow
        case 2: return Color(white: 0.7)
        case 3: return Color(red: 0.8, green: 0.5, blue: 0.2)
        default: return .secondary
        }
    }

    var body: some View {
        HStack(spacing: 12) {
            // Rank badge
            ZStack {
                Circle()
                    .fill(position <= 3 ? rankColor.opacity(0.15) : Color.clear)
                    .frame(width: 34, height: 34)
                Text("\(position)")
                    .font(.subheadline.bold())
                    .foregroundStyle(position <= 3 ? rankColor : .secondary)
            }

            // Team info
            VStack(alignment: .leading, spacing: 2) {
                Text(standing.shortName)
                    .font(.subheadline.bold())
                HStack(spacing: 6) {
                    if showRecord {
                    Text("\(standing.wins)W–\(standing.losses)L–\(standing.ties)T")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    }
                    if standing.roundsPlayed > 0 {
                        Text("·")
                            .foregroundStyle(.secondary)
                            .font(.caption)
                        Text("\(standing.roundsPlayed) rounds")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
            }

            Spacer()

            // Points
            VStack(alignment: .trailing, spacing: 1) {
                Text(String(format: "%.1f", standing.points))
                    .font(.title3.bold())
                Text("pts")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(.vertical, 4)
    }
}
