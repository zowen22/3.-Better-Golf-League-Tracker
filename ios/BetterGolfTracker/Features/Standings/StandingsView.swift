import SwiftUI

struct StandingsView: View {
    @State private var viewModel = StandingsViewModel()

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
                        StandingRow(standing: standing, position: i + 1)
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
            .refreshable { await viewModel.load() }
            .task { await viewModel.load() }
            .overlay { if viewModel.isLoading { ProgressView() } }
        }
    }
}

struct StandingRow: View {
    let standing: Standing
    let position: Int

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
                    Text("\(standing.wins)W–\(standing.losses)L–\(standing.ties)T")
                        .font(.caption)
                        .foregroundStyle(.secondary)
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
