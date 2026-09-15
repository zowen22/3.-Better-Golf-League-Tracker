import Foundation
import Observation

@Observable
final class ContestsViewModel {
    enum Tab: String, CaseIterable, Identifiable {
        case detail   = "Detail"
        case summary  = "Summary"
        case lowScore = "Low Score"
        case skins    = "Skins"

        var id: String { rawValue }

        var apiType: String {
            switch self {
            case .detail:   return "detail"
            case .summary:  return "summary"
            case .lowScore: return "low_score"
            case .skins:    return "skins"
            }
        }
    }

    var selectedTab: Tab = .detail
    var detailWinners: [ContestWinner] = []
    var summaryWinners: [ContestSummaryEntry] = []
    var lowScoreWeeks: [ContestLowScoreWeek] = []
    var skinsWinners: [ContestSkinsWinner] = []
    var isLoading = false
    var errorMessage: String?

    func load(seasonId: Int? = nil) async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            switch selectedTab {
            case .detail:
                let r: ContestDetailResponse = try await APIClient.shared.request(
                    .contestsWinners(type: Tab.detail.apiType, seasonId: seasonId)
                )
                detailWinners = r.winners
            case .summary:
                let r: ContestSummaryResponse = try await APIClient.shared.request(
                    .contestsWinners(type: Tab.summary.apiType, seasonId: seasonId)
                )
                summaryWinners = r.winners
            case .lowScore:
                let r: ContestLowScoreResponse = try await APIClient.shared.request(
                    .contestsWinners(type: Tab.lowScore.apiType, seasonId: seasonId)
                )
                lowScoreWeeks = r.weeks
            case .skins:
                let r: ContestSkinsResponse = try await APIClient.shared.request(
                    .contestsWinners(type: Tab.skins.apiType, seasonId: seasonId)
                )
                skinsWinners = r.winners
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
