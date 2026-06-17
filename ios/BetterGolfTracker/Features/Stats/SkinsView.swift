import SwiftUI

@Observable
final class SkinsViewModel {
    var response: SkinsResponse?
    var isLoading = false
    var errorMessage: String?

    func load() async {
        isLoading = true; errorMessage = nil
        defer { isLoading = false }
        do {
            response = try await APIClient.shared.request(.skins)
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

struct SkinsView: View {
    @State private var vm = SkinsViewModel()

    var body: some View {
        Group {
            if vm.isLoading {
                ProgressView()
            } else if let r = vm.response {
                List {
                    ForEach(r.weeks) { week in
                        Section {
                            ForEach(week.skins) { skin in
                                skinRow(skin)
                            }
                        } header: {
                            HStack {
                                Text("Week \(week.week)")
                                if let date = week.roundDate {
                                    Text("— \(formattedDate(date))")
                                        .foregroundStyle(.secondary)
                                }
                            }
                        }
                    }
                }
                .listStyle(.insetGrouped)
                .overlay {
                    if r.weeks.isEmpty {
                        ContentUnavailableView("No skins recorded yet", systemImage: "dollarsign.circle")
                    }
                }
            } else if let err = vm.errorMessage {
                ContentUnavailableView(err, systemImage: "exclamationmark.triangle")
            }
        }
        .navigationTitle("Skins")
        .navigationBarTitleDisplayMode(.inline)
        .task { await vm.load() }
        .refreshable { await vm.load() }
    }

    @ViewBuilder
    private func skinRow(_ skin: SkinsResult) -> some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 6) {
                    Text("Hole \(skin.hole)")
                        .font(.subheadline.bold())
                    if skin.isCarryover {
                        Text("CARRY")
                            .font(.caption2.bold())
                            .foregroundStyle(.orange)
                            .padding(.horizontal, 5).padding(.vertical, 1)
                            .background(Color.orange.opacity(0.12))
                            .clipShape(Capsule())
                    }
                }
                if let name = skin.winnerName {
                    Text(name)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                } else {
                    Text("Carryover — no winner")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            Spacer()
            VStack(alignment: .trailing, spacing: 2) {
                Text(String(format: "$%.2f", skin.pot))
                    .font(.subheadline.bold())
                    .foregroundStyle(skin.winnerName != nil ? .green : .secondary)
                if skin.carryIn > 0 {
                    Text(String(format: "+$%.2f carry", skin.carryIn))
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }
        }
        .padding(.vertical, 2)
    }

    private func formattedDate(_ raw: String) -> String {
        let f = DateFormatter(); f.dateFormat = "yyyy-MM-dd"
        guard let d = f.date(from: String(raw.prefix(10))) else { return raw }
        let out = DateFormatter(); out.dateFormat = "MMM d"
        return out.string(from: d)
    }
}
