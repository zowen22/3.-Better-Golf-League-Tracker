import SwiftUI

struct StatsHubView: View {
    var body: some View {
        NavigationStack {
            List {
                Section {
                    statsRow(
                        title: "Season Leaders",
                        subtitle: "Low gross, high points, most wins",
                        icon: "medal.fill",
                        color: .yellow,
                        destination: StatsLeadersView()
                    )
                    statsRow(
                        title: "All-Play Standings",
                        subtitle: "Head-to-head record vs every team",
                        icon: "person.3.fill",
                        color: .blue,
                        destination: StatsAllPlayView()
                    )
                    statsRow(
                        title: "Points Trend",
                        subtitle: "Cumulative points week over week",
                        icon: "chart.line.uptrend.xyaxis",
                        color: .green,
                        destination: StatsTrendView()
                    )
                    statsRow(
                        title: "Weekly Scores",
                        subtitle: "Full results for each completed round",
                        icon: "calendar.badge.checkmark",
                        color: .orange,
                        destination: StatsWeeklyView()
                    )
                    statsRow(
                        title: "Season Records",
                        subtitle: "Best and worst single-round performances",
                        icon: "star.fill",
                        color: .purple,
                        destination: StatsRecordsView()
                    )
                    statsRow(
                        title: "Handicap Breakdown",
                        subtitle: "How each player's index is calculated",
                        icon: "function",
                        color: .teal,
                        destination: HandicapPlayerListView()
                    )
                }
            }
            .listStyle(.insetGrouped)
            .navigationTitle("Stats")
        }
    }

    @ViewBuilder
    private func statsRow<D: View>(title: String, subtitle: String, icon: String, color: Color, destination: D) -> some View {
        NavigationLink(destination: destination) {
            HStack(spacing: 14) {
                ZStack {
                    RoundedRectangle(cornerRadius: 8)
                        .fill(color.opacity(0.15))
                        .frame(width: 38, height: 38)
                    Image(systemName: icon)
                        .foregroundStyle(color)
                        .font(.system(size: 16, weight: .semibold))
                }
                VStack(alignment: .leading, spacing: 2) {
                    Text(title).font(.subheadline.bold())
                    Text(subtitle).font(.caption).foregroundStyle(.secondary)
                }
            }
            .padding(.vertical, 4)
        }
    }
}
