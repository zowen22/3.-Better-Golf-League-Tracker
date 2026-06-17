import SwiftUI

// Admin-only tab: lists scheduled matchups for score entry.
// Reuses ScheduleViewModel but filters to scheduled/in_progress only.
struct ScoreEntryView: View {
    @State private var viewModel = ScheduleViewModel()

    var scheduledMatchups: [Matchup] {
        viewModel.matchups.filter { $0.status == .scheduled || $0.status == .inProgress }
    }

    var body: some View {
        NavigationStack {
            List {
                if scheduledMatchups.isEmpty && !viewModel.isLoading {
                    ContentUnavailableView(
                        "No pending matchups",
                        systemImage: "flag.fill",
                        description: Text("All scheduled rounds have been recorded.")
                    )
                } else {
                    ForEach(scheduledMatchups) { matchup in
                        NavigationLink(destination: ScoreInputView(matchup: matchup)) {
                            scoreEntryRow(matchup)
                        }
                    }
                }
            }
            .listStyle(.insetGrouped)
            .navigationTitle("Score Entry")
            .refreshable { await viewModel.load() }
            .task { await viewModel.load() }
            .overlay {
                if viewModel.isLoading { ProgressView() }
            }
        }
    }

    @ViewBuilder
    private func scoreEntryRow(_ m: Matchup) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text("Week \(m.weekNumber)")
                    .font(.subheadline.bold())
                Spacer()
                StatusBadge(status: m.status)
            }
            Text("\(m.team1.shortName)  vs  \(m.team2.shortName)")
                .font(.caption)
                .foregroundStyle(.secondary)
            HStack(spacing: 10) {
                if let date = m.scheduledDate {
                    Label(formattedDate(date), systemImage: "calendar")
                        .font(.caption2).foregroundStyle(.secondary)
                }
                if let teeTime = m.teeTime {
                    Label(teeTime, systemImage: "clock")
                        .font(.caption2).foregroundStyle(.secondary)
                }
            }
        }
        .padding(.vertical, 2)
    }

    private func formattedDate(_ raw: String) -> String {
        let f = DateFormatter(); f.dateFormat = "yyyy-MM-dd"
        guard let d = f.date(from: raw) else { return raw }
        let out = DateFormatter(); out.dateFormat = "MMM d"
        return out.string(from: d)
    }
}
