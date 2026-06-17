import SwiftUI

struct ScheduleView: View {
    @State private var viewModel = ScheduleViewModel()
    @State private var selectedWeek: Int? = nil  // nil = all weeks

    var weekOptions: [Int] {
        Array(Set(viewModel.matchups.map(\.weekNumber))).sorted()
    }

    var displayedMatchups: [Matchup] {
        guard let week = selectedWeek else { return viewModel.matchups }
        return viewModel.matchups.filter { $0.weekNumber == week }
    }

    var body: some View {
        NavigationStack {
            List {
                ForEach(displayedMatchups) { matchup in
                    NavigationLink(destination: MatchupDetailView(matchupId: matchup.id)) {
                        VStack(alignment: .leading) {
                            Text("Week \(matchup.weekNumber)")
                                .font(.headline)
                            Text("\(matchup.team1.shortName) vs \(matchup.team2.shortName)")
                                .font(.subheadline)
                            HStack {
                                StatusBadge(status: matchup.status)
                                if let date = matchup.scheduledDate {
                                    Text("· \(date)")
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                            }
                        }
                    }
                }
            }
            .navigationTitle("Schedule")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Menu {
                        Button("All Weeks") { selectedWeek = nil }
                        Divider()
                        ForEach(weekOptions, id: \.self) { week in
                            Button("Week \(week)") { selectedWeek = week }
                        }
                    } label: {
                        Label(selectedWeek.map { "Week \($0)" } ?? "All Weeks",
                              systemImage: "line.3.horizontal.decrease.circle")
                    }
                }
            }
            .refreshable { await viewModel.load() }
            .task { await viewModel.load() }
            .overlay {
                if viewModel.isLoading {
                    ProgressView()
                } else if displayedMatchups.isEmpty {
                    ContentUnavailableView(
                        viewModel.errorMessage ?? "No schedule data",
                        systemImage: "calendar"
                    )
                }
            }
        }
    }
}
