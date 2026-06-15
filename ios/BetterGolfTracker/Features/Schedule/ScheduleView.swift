import SwiftUI

struct ScheduleView: View {
    @State private var viewModel = ScheduleViewModel()

    var body: some View {
        NavigationStack {
            List(viewModel.matchups) { matchup in
                VStack(alignment: .leading) {
                    Text("Week \(matchup.weekNumber)")
                        .font(.headline)
                    Text("\(matchup.team1.name) vs \(matchup.team2.name)")
                        .font(.subheadline)
                    Text(matchup.status.capitalized)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            .navigationTitle("Schedule")
            .refreshable { await viewModel.load() }
            .task { await viewModel.load() }
            .overlay {
                if viewModel.isLoading { ProgressView() }
            }
        }
    }
}
