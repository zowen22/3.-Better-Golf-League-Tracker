import SwiftUI

struct AdminView: View {
    @State private var viewModel = AdminViewModel()

    var body: some View {
        NavigationStack {
            List {
                if viewModel.pendingSubmissions.isEmpty && !viewModel.isLoading {
                    ContentUnavailableView(
                        "No pending submissions",
                        systemImage: "tray",
                        description: Text("All self-reports have been reviewed.")
                    )
                } else {
                    Section("Pending Self-Reports (\(viewModel.pendingSubmissions.count))") {
                        ForEach(viewModel.pendingSubmissions) { submission in
                            NavigationLink(destination: PendingSubmissionDetailView(
                                submission: submission,
                                onApprove: { await viewModel.approve(submissionId: submission.id) }
                            )) {
                                PendingSubmissionRow(submission: submission)
                            }
                        }
                    }
                }
            }
            .listStyle(.insetGrouped)
            .navigationTitle("Admin")
            .refreshable { await viewModel.loadPending() }
            .task { await viewModel.loadPending() }
            .overlay { if viewModel.isLoading { ProgressView() } }
            .alert("Error", isPresented: Binding(
                get: { viewModel.errorMessage != nil },
                set: { if !$0 { viewModel.errorMessage = nil } }
            )) {
                Button("OK") { viewModel.errorMessage = nil }
            } message: {
                Text(viewModel.errorMessage ?? "")
            }
        }
    }
}

struct PendingSubmissionRow: View {
    let submission: PendingSubmission

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text("Week \(submission.weekNumber)")
                    .font(.subheadline.bold())
                Spacer()
                Text(submission.submittedAt.prefix(10))
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            if let t1 = submission.team1Name, let t2 = submission.team2Name {
                Text("\(t1) vs \(t2)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            HStack(spacing: 10) {
                if let name = submission.submittedByName {
                    Label(name, systemImage: "person")
                        .font(.caption2).foregroundStyle(.secondary)
                }
                if let course = submission.courseName {
                    Label(course, systemImage: "mappin")
                        .font(.caption2).foregroundStyle(.secondary)
                }
                Label("\(submission.holeCount) holes", systemImage: "flag")
                    .font(.caption2).foregroundStyle(.secondary)
            }
        }
        .padding(.vertical, 2)
    }
}

struct PendingSubmissionDetailView: View {
    let submission: PendingSubmission
    let onApprove: () async -> Bool
    @State private var isApproving = false
    @State private var approveError: String?
    @State private var approved = false
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        List {
            Section("Submission") {
                LabeledContent("Week", value: "Week \(submission.weekNumber)")
                if let date = submission.scheduledDate {
                    LabeledContent("Scheduled", value: date)
                }
                if let t1 = submission.team1Name, let t2 = submission.team2Name {
                    LabeledContent("Matchup", value: "\(t1) vs \(t2)")
                }
                LabeledContent("Submitted by", value: submission.submittedByName ?? "Unknown")
                LabeledContent("Submitted at", value: String(submission.submittedAt.prefix(19)))
            }

            Section("Course") {
                if let course = submission.courseName {
                    LabeledContent("Course", value: course)
                }
                if let tee = submission.teeName {
                    LabeledContent("Tee", value: tee)
                }
                if let nine = submission.nine {
                    LabeledContent("Nine", value: nine)
                }
                LabeledContent("Holes submitted", value: "\(submission.holeCount)")
            }

            if let err = approveError {
                Section {
                    Label(err, systemImage: "exclamationmark.triangle")
                        .foregroundStyle(.red)
                        .font(.footnote)
                }
            }

            Section {
                if isApproving {
                    HStack { Spacer(); ProgressView("Approving…"); Spacer() }
                } else if approved {
                    Label("Approved!", systemImage: "checkmark.circle.fill")
                        .foregroundStyle(.green)
                } else {
                    Button("Approve & Record Scores") {
                        isApproving = true
                        Task {
                            let success = await onApprove()
                            isApproving = false
                            if success { approved = true; DispatchQueue.main.asyncAfter(deadline: .now() + 1) { dismiss() } }
                            else { approveError = "Approval failed. Scores may already be recorded." }
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .center)
                    .font(.headline)
                    .foregroundStyle(.white)
                    .listRowBackground(Color.green)
                }
            }
        }
        .navigationTitle("Submission #\(submission.id)")
        .navigationBarTitleDisplayMode(.inline)
    }
}
