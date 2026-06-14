import Foundation
import Observation

@Observable
final class AdminViewModel {
    var pendingSubmissions: [PendingSubmission] = []
    var isLoading = false
    var errorMessage: String?
    var lastActionMessage: String?

    func loadPending() async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            let response: PendingSubmissionsResponse = try await APIClient.shared.request(.adminPending)
            pendingSubmissions = response.pending
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func approve(submissionId: Int) async -> Bool {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            let _: ApproveResponse = try await APIClient.shared.request(.approve(submissionId: submissionId))
            pendingSubmissions.removeAll { $0.id == submissionId }
            lastActionMessage = "Submission approved."
            return true
        } catch APIError.conflict {
            errorMessage = "Scores for this matchup have already been entered."
            return false
        } catch {
            errorMessage = error.localizedDescription
            return false
        }
    }
}
