import SwiftUI

struct StandingsView: View {
    @State private var viewModel = StandingsViewModel()

    var body: some View {
        NavigationStack {
            List(viewModel.standings) { standing in
                HStack {
                    Text("\(standing.rank)")
                        .font(.headline)
                        .frame(width: 32)
                    VStack(alignment: .leading) {
                        Text(standing.teamName)
                            .font(.headline)
                        Text("\(standing.wins)-\(standing.losses)-\(standing.ties)")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                    Text("\(standing.points, format: .number) pts")
                        .font(.subheadline.bold())
                }
            }
            .navigationTitle("Standings")
            .refreshable { await viewModel.load() }
            .task { await viewModel.load() }
            .overlay {
                if viewModel.isLoading { ProgressView() }
            }
        }
    }
}
