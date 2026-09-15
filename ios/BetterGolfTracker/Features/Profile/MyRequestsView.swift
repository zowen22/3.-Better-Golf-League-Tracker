import SwiftUI

@Observable
final class MyRequestsViewModel {
    var requests: [SubRequest] = []
    var isLoading = false
    var errorMessage: String?

    func load() async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            let r: SubsMineResponse = try await APIClient.shared.request(.subsMine)
            requests = r.requests
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func cancel(requestId: Int) async {
        do {
            let _: SubCancelResponse = try await APIClient.shared.request(.subCancel(requestId: requestId))
            await load()
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

struct MyRequestsView: View {
    @State private var vm = MyRequestsViewModel()

    var body: some View {
        Group {
            if vm.isLoading {
                ProgressView()
            } else if vm.requests.isEmpty {
                ContentUnavailableView(
                    vm.errorMessage ?? "No sub requests yet",
                    systemImage: "person.badge.plus"
                )
            } else {
                List(vm.requests) { req in
                    requestRow(req)
                }
                .listStyle(.insetGrouped)
            }
        }
        .navigationTitle("My Sub Requests")
        .navigationBarTitleDisplayMode(.inline)
        .task { await vm.load() }
        .refreshable { await vm.load() }
    }

    @ViewBuilder
    private func requestRow(_ req: SubRequest) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                if let week = req.weekNumber {
                    Text("Week \(week)").font(.subheadline.bold())
                } else {
                    Text("Matchup #\(req.matchupId)").font(.subheadline.bold())
                }
                Spacer()
                statusBadge(req.status)
            }
            if let notes = req.notes, !notes.isEmpty {
                Text(notes).font(.caption).foregroundStyle(.secondary)
            }
            if let subName = req.subPlayerName {
                Text("Sub: \(subName)").font(.caption).foregroundStyle(.green)
            }
            if let adminNotes = req.adminNotes, !adminNotes.isEmpty {
                Text("Admin note: \(adminNotes)").font(.caption).foregroundStyle(.secondary)
            }
            if req.status == "open" {
                Button(role: .destructive) {
                    Task { await vm.cancel(requestId: req.requestId) }
                } label: {
                    Text("Cancel Request").font(.caption.bold())
                }
            }
        }
        .padding(.vertical, 4)
    }

    @ViewBuilder
    private func statusBadge(_ status: String) -> some View {
        let color: Color = status == "open" ? .orange : status == "assigned" ? .green : .secondary
        Text(status.capitalized)
            .font(.caption2.bold())
            .padding(.horizontal, 6).padding(.vertical, 2)
            .background(color.opacity(0.15))
            .foregroundStyle(color)
            .clipShape(Capsule())
    }
}
