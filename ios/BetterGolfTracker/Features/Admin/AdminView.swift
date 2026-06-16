import SwiftUI

struct AdminView: View {
    @State private var viewModel = AdminViewModel()

    var body: some View {
        NavigationStack {
            List {
                ForEach(viewModel.pendingSubmissions) { submission in
                    VStack(alignment: .leading) {
                        Text(submission.submittedByName ?? "Unknown")
                            .font(.headline)
                        Text("Week \(submission.weekNumber)")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                    }
                    .swipeActions {
                        Button("Approve") {
                            Task { await viewModel.approve(submissionId: submission.id) }
                        }
                        .tint(.green)
                    }
                }
            }
            .navigationTitle("Admin")
            .task { await viewModel.loadPending() }
            .overlay {
                if viewModel.isLoading { ProgressView() }
            }
        }
    }
}
