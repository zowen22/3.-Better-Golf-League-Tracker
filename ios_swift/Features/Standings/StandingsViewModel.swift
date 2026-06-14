import Foundation
import Observation

@Observable
final class StandingsViewModel {
    var standings: [Standing] = []
    var isLoading = false
    var errorMessage: String?

    func load() async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            let response: StandingsResponse = try await APIClient.shared.request(.standings)
            standings = response.standings
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
