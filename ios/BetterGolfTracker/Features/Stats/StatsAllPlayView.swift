import SwiftUI

@Observable
final class StatsAllPlayViewModel {
    var response: StatsAllPlayResponse?
    var isLoading = false
    var errorMessage: String?

    func load() async {
        isLoading = true; errorMessage = nil
        defer { isLoading = false }
        do {
            response = try await APIClient.shared.request(.statsAllPlay)
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

struct StatsAllPlayView: View {
    @State private var vm = StatsAllPlayViewModel()

    var body: some View {
        List {
            if let r = vm.response {
                if r.rows.isEmpty {
                    Text("No completed rounds yet").foregroundStyle(.secondary)
                } else {
                    ForEach(r.rows) { row in
                        HStack(spacing: 12) {
                            Text("\(row.rank)")
                                .font(.headline)
                                .frame(width: 28)
                                .foregroundStyle(.secondary)
                            VStack(alignment: .leading, spacing: 2) {
                                Text(row.teamName)
                                    .font(.subheadline.bold())
                                Text(String(format: "%.3f pct", row.pct))
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                            Spacer()
                            VStack(alignment: .trailing, spacing: 2) {
                                Text("\(row.w)-\(row.l)-\(row.t)")
                                    .font(.subheadline.bold())
                                Text(String(format: "%.1f pts", row.seasonPts))
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        }
                    }
                }
            }
        }
        .navigationTitle("All-Play")
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
