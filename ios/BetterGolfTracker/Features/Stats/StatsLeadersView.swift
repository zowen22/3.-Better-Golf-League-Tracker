import SwiftUI

@Observable
final class StatsLeadersViewModel {
    var response: StatsLeadersResponse?
    var isLoading = false
    var errorMessage: String?

    func load() async {
        isLoading = true; errorMessage = nil
        defer { isLoading = false }
        do {
            response = try await APIClient.shared.request(.statsLeaders)
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

struct StatsLeadersView: View {
    @State private var vm = StatsLeadersViewModel()

    var body: some View {
        List {
            if let r = vm.response {
                leaderSection("Low Gross Rounds", entries: r.lowGross) { $0.totalGross.map { "\($0)" } }
                leaderSection("High Points (Single Match)", entries: r.highPoints) { $0.totalPoints.map { String(format: "%.1f pts", $0) } }
                leaderSection("Most Match Wins", entries: r.mostWins) { $0.wins.map { "\($0) wins" } }
            }
        }
        .navigationTitle("Season Leaders")
        .task { await vm.load() }
        .refreshable { await vm.load() }
        .overlay {
            if vm.isLoading { ProgressView() }
            else if vm.response == nil, let err = vm.errorMessage {
                ContentUnavailableView(err, systemImage: "exclamationmark.triangle")
            }
        }
    }

    @ViewBuilder
    private func leaderSection(_ title: String, entries: [LeaderEntry], valueKey: @escaping (LeaderEntry) -> String?) -> some View {
        Section(title) {
            if entries.isEmpty {
                Text("No data yet").foregroundStyle(.secondary).font(.footnote)
            } else {
                ForEach(Array(entries.enumerated()), id: \.offset) { i, entry in
                    HStack {
                        Text("\(i + 1).")
                            .font(.caption.bold())
                            .foregroundStyle(.secondary)
                            .frame(width: 20)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(entry.playerName).font(.subheadline.bold())
                            Text(entry.teamName).font(.caption).foregroundStyle(.secondary)
                        }
                        Spacer()
                        if let val = valueKey(entry) {
                            Text(val).font(.subheadline.bold()).foregroundStyle(.green)
                        }
                    }
                }
            }
        }
    }
}
