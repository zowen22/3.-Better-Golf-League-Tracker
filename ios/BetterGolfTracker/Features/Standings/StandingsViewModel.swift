import Foundation
import Observation

@Observable
final class StandingsViewModel {
    var standings: [Standing] = []
    var seasonName: String?
    var seasons: [SeasonInfo] = []
    var selectedSeasonId: Int?
    var isLoading = false
    var errorMessage: String?
    var isShowingCached = false

    private let cacheKey = "/api/v1/standings"

    func loadSeasons() async {
        do {
            let r: SeasonsListResponse = try await APIClient.shared.request(.seasonsList)
            seasons = r.seasons
            if selectedSeasonId == nil {
                selectedSeasonId = r.currentSeasonId
            }
        } catch {
            // Non-fatal — fall back to current season only
        }
    }

    func load() async {
        isLoading = true
        errorMessage = nil
        isShowingCached = false
        defer { isLoading = false }

        // If a non-current season is selected, use the season-specific endpoint
        if let sid = selectedSeasonId, seasons.first?.seasonId != sid || seasons.isEmpty == false {
            // Check if it's not the first (current) season
            if let first = seasons.first, first.seasonId != sid {
                await loadSeason(sid)
                return
            }
        }

        do {
            let response: StandingsResponse = try await APIClient.shared.request(.standings)
            standings = response.standings
            seasonName = response.seasonName
            if selectedSeasonId == nil { selectedSeasonId = response.seasonId }
            ResponseCache.save(response, for: cacheKey)
        } catch APIError.noNetwork {
            if let cached = ResponseCache.loadStale(StandingsResponse.self, for: cacheKey) {
                standings = cached.standings
                seasonName = cached.seasonName
                isShowingCached = true
            } else {
                errorMessage = "No network connection."
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func loadSeason(_ seasonId: Int) async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            let response: StandingsResponse = try await APIClient.shared.request(.seasonStandings(seasonId: seasonId))
            standings = response.standings
            seasonName = response.seasonName
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
