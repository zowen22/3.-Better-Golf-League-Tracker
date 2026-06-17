import Foundation
import Observation

@Observable
final class StandingsViewModel {
    var standings: [Standing] = []
    var isLoading = false
    var errorMessage: String?
    var isShowingCached = false

    private let cacheKey = "/api/v1/standings"

    func load() async {
        isLoading = true
        errorMessage = nil
        isShowingCached = false
        defer { isLoading = false }
        do {
            let response: StandingsResponse = try await APIClient.shared.request(.standings)
            standings = response.standings
            ResponseCache.save(response, for: cacheKey)
        } catch APIError.noNetwork {
            if let cached = ResponseCache.loadStale(StandingsResponse.self, for: cacheKey) {
                standings = cached.standings
                isShowingCached = true
            } else {
                errorMessage = "No network connection."
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
