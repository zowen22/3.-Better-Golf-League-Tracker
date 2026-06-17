import SwiftUI

@Observable
final class StatsRecordsViewModel {
    var response: StatsRecordsResponse?
    var isLoading = false
    var errorMessage: String?

    func load() async {
        isLoading = true; errorMessage = nil
        defer { isLoading = false }
        do {
            response = try await APIClient.shared.request(.statsRecords)
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

struct StatsRecordsView: View {
    @State private var vm = StatsRecordsViewModel()

    var body: some View {
        List {
            if let r = vm.response {
                recordSection("Low Gross Rounds", entries: r.lowGross) {
                    $0.totalGross.map { "\($0)" } ?? "—"
                }
                recordSection("High Gross Rounds", entries: r.highGross) {
                    $0.totalGross.map { "\($0)" } ?? "—"
                }
                recordSection("Best Individual Points", entries: r.highIndivPts) {
                    $0.totalPoints.map { String(format: "%.1f pts", $0) } ?? "—"
                }
                recordSection("Lowest Individual Points", entries: r.lowIndivPts) {
                    $0.totalPoints.map { String(format: "%.1f pts", $0) } ?? "—"
                }
            }
        }
        .navigationTitle("Season Records")
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
    private func recordSection(_ title: String, entries: [LeaderEntry], value: (LeaderEntry) -> String) -> some View {
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
                            HStack(spacing: 8) {
                                Text(entry.teamName).font(.caption).foregroundStyle(.secondary)
                                if let wk = entry.weekNumber {
                                    Text("Wk \(wk)").font(.caption).foregroundStyle(.secondary)
                                }
                            }
                        }
                        Spacer()
                        Text(value(entry)).font(.subheadline.bold()).foregroundStyle(.green)
                    }
                }
            }
        }
    }
}
