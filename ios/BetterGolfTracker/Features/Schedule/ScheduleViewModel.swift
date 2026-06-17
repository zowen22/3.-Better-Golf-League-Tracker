import Foundation
import Observation

@Observable
final class ScheduleViewModel {
    var matchups: [Matchup] = []
    var isLoading = false
    var errorMessage: String?
    var isShowingCached = false

    private let cacheKey = "/api/v1/schedule"

    var byWeek: [(weekNumber: Int, matchups: [Matchup])] {
        let groups = Dictionary(grouping: matchups, by: \.weekNumber)
        return groups.keys.sorted().map { week in
            (weekNumber: week, matchups: groups[week]!.sorted { $0.id < $1.id })
        }
    }

    func load() async {
        isLoading = true
        errorMessage = nil
        isShowingCached = false
        defer { isLoading = false }
        do {
            let response: ScheduleResponse = try await APIClient.shared.request(.schedule)
            matchups = response.matchups
            ResponseCache.save(response, for: cacheKey)
        } catch APIError.noNetwork {
            if let cached = ResponseCache.loadStale(ScheduleResponse.self, for: cacheKey) {
                matchups = cached.matchups
                isShowingCached = true
            } else {
                errorMessage = "No network connection."
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func matchup(id: Int) -> Matchup? {
        matchups.first { $0.id == id }
    }
}
