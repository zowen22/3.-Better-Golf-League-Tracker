import SwiftUI

@Observable
final class StatsTrendViewModel {
    var response: StatsTrendResponse?
    var isLoading = false
    var errorMessage: String?

    func load() async {
        isLoading = true; errorMessage = nil
        defer { isLoading = false }
        do {
            response = try await APIClient.shared.request(.statsTrend)
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

struct StatsTrendView: View {
    @State private var vm = StatsTrendViewModel()

    var body: some View {
        List {
            if let r = vm.response {
                if r.teams.isEmpty {
                    Text("No completed rounds yet").foregroundStyle(.secondary)
                } else {
                    ForEach(Array(r.teams.enumerated()), id: \.element.id) { i, team in
                        HStack {
                            Circle()
                                .fill(trendColor(i))
                                .frame(width: 10, height: 10)
                            VStack(alignment: .leading, spacing: 2) {
                                Text(team.teamName).font(.subheadline.bold())
                                if !team.points.isEmpty {
                                    Text("Wk by Wk: " + team.points.map { String(format: "%.1f", $0) }.joined(separator: " → "))
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                        .lineLimit(2)
                                }
                            }
                            Spacer()
                            Text(String(format: "%.1f", team.finalPts))
                                .font(.subheadline.bold())
                        }
                    }
                }
            }
        }
        .navigationTitle("Points Trend")
        .task { await vm.load() }
        .refreshable { await vm.load() }
        .overlay {
            if vm.isLoading { ProgressView() }
            else if vm.response == nil, let err = vm.errorMessage {
                ContentUnavailableView(err, systemImage: "exclamationmark.triangle")
            }
        }
    }

    private func trendColor(_ index: Int) -> Color {
        let colors: [Color] = [.green, .blue, .red, .orange, .purple, .teal, .pink, .indigo]
        return colors[index % colors.count]
    }
}
