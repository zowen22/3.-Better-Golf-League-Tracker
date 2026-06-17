import SwiftUI

struct ScheduleView: View {
    @State private var viewModel = ScheduleViewModel()

    var body: some View {
        NavigationStack {
            List {
                ForEach(viewModel.matchups) { matchup in
                    VStack(alignment: .leading) {
                        Text("Week \(matchup.weekNumber)")
                            .font(.headline)
                        Text("\(matchup.team1.name) vs \(matchup.team2.name)")
                            .font(.subheadline)
                        Text(matchup.status.rawValue.capitalized)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
            }
            .navigationTitle("Schedule")
            .refreshable { await viewModel.load() }
            .task { await viewModel.load() }
            .overlay {
                if viewModel.isLoading {
                    ProgressView()
                } else if viewModel.matchups.isEmpty {
                    ContentUnavailableView(
                        viewModel.errorMessage ?? "No schedule data",
                        systemImage: "calendar"
                    )
                }
            }
        }
    }
}
