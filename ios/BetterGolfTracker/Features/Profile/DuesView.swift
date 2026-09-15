import SwiftUI

@Observable
final class DuesViewModel {
    var response: DuesResponse?
    var isLoading = false
    var errorMessage: String?

    func load(seasonId: Int? = nil) async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            response = try await APIClient.shared.request(.dues(seasonId: seasonId))
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

struct DuesView: View {
    @State private var vm = DuesViewModel()

    var body: some View {
        Group {
            if vm.isLoading {
                ProgressView()
            } else if let r = vm.response {
                List {
                    Section {
                        HStack(alignment: .top) {
                            VStack(alignment: .leading, spacing: 4) {
                                Text(r.duesAmount.map { String(format: "$%.2f", $0) } ?? "—")
                                    .font(.system(size: 34, weight: .bold))
                                if let due = r.duesDueDate {
                                    Text("Due \(due)")
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                            }
                            Spacer()
                            statusBadge(r.myPaid)
                        }
                        .padding(.vertical, 4)
                    } header: {
                        Text("My Dues")
                    } footer: {
                        Text("\(r.paidCount) of \(r.totalCount) players have paid this season.")
                    }

                    Section("Payment History") {
                        if r.myPayments.isEmpty {
                            Text("No payments recorded yet")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        } else {
                            ForEach(r.myPayments) { p in
                                HStack {
                                    VStack(alignment: .leading, spacing: 2) {
                                        Text(String(format: "$%.2f", p.amount)).font(.subheadline.bold())
                                        if let method = p.method, !method.isEmpty {
                                            Text(method).font(.caption).foregroundStyle(.secondary)
                                        }
                                    }
                                    Spacer()
                                    if let date = p.paidDate {
                                        Text(date).font(.caption).foregroundStyle(.secondary)
                                    }
                                }
                            }
                        }
                    }
                }
                .listStyle(.insetGrouped)
            } else if let err = vm.errorMessage {
                ContentUnavailableView(err, systemImage: "exclamationmark.triangle")
            }
        }
        .navigationTitle("Dues")
        .navigationBarTitleDisplayMode(.inline)
        .task { await vm.load() }
        .refreshable { await vm.load() }
    }

    @ViewBuilder
    private func statusBadge(_ paid: Bool) -> some View {
        Text(paid ? "PAID" : "UNPAID")
            .font(.caption2.bold())
            .padding(.horizontal, 8).padding(.vertical, 4)
            .background((paid ? Color.green : Color.orange).opacity(0.15))
            .foregroundStyle(paid ? .green : .orange)
            .clipShape(Capsule())
    }
}
