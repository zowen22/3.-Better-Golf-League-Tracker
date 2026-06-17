import SwiftUI
import Charts

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

    private let palette: [Color] = [.green, .blue, .red, .orange, .purple, .teal, .pink, .indigo]

    var body: some View {
        List {
            if let r = vm.response, !r.teams.isEmpty {
                // Chart section
                Section {
                    Chart {
                        ForEach(r.teams) { team in
                            ForEach(Array(team.points.enumerated()), id: \.offset) { j, pts in
                                LineMark(
                                    x: .value("Week", j + 1),
                                    y: .value("Points", pts)
                                )
                                .symbol(Circle())
                                .symbolSize(30)
                                .foregroundStyle(by: .value("Team", team.teamName))
                            }
                        }
                    }
                    .chartLegend(.hidden)
                    .frame(height: 220)
                    .padding(.vertical, 8)
                }

                // Legend + final standings table
                Section("Season Totals") {
                    let originalOrder = Dictionary(uniqueKeysWithValues: r.teams.enumerated().map { ($0.element.id, $0.offset) })
                    ForEach(r.teams.sorted { $0.finalPts > $1.finalPts }) { team in
                        HStack(spacing: 12) {
                            let colorIdx = originalOrder[team.id, default: 0]
                            Circle()
                                .fill(palette[colorIdx % palette.count])
                                .frame(width: 10, height: 10)
                            VStack(alignment: .leading, spacing: 2) {
                                Text(team.teamName).font(.subheadline.bold())
                                if !team.points.isEmpty {
                                    Text(team.points.map { String(format: "%.1f", $0) }.joined(separator: " → "))
                                        .font(.caption).foregroundStyle(.secondary).lineLimit(1)
                                }
                            }
                            Spacer()
                            Text(String(format: "%.1f", team.finalPts))
                                .font(.subheadline.bold())
                        }
                    }
                }
            } else if !vm.isLoading {
                Text("No completed rounds yet").foregroundStyle(.secondary)
            }
        }
        .listStyle(.insetGrouped)
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
}
