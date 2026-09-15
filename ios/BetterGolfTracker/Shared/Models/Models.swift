import Foundation

// MARK: - Auth

struct AuthResponse: Codable {
    let token: String
    let userId: Int
    let leagueId: Int
    let role: String
    let displayName: String
    let playerId: Int?

    enum CodingKeys: String, CodingKey {
        case token
        case userId        = "user_id"
        case leagueId      = "league_id"
        case role
        case displayName   = "display_name"
        case playerId      = "player_id"
    }
}

struct CurrentUser: Codable {
    let userId: Int
    let leagueId: Int
    let role: String
    let playerId: Int?
    var displayName: String?
    var email: String?
    var leagueName: String?
    var handicapIndex: Double?
    var hcpHistory: [HandicapHistoryEntry]?
    var seasonId: Int?
    var seasonName: String?

    enum CodingKeys: String, CodingKey {
        case userId        = "user_id"
        case leagueId      = "league_id"
        case role
        case playerId      = "player_id"
        case displayName   = "display_name"
        case email
        case leagueName    = "league_name"
        case handicapIndex = "handicap_index"
        case hcpHistory    = "hcp_history"
        case seasonId      = "season_id"
        case seasonName    = "season_name"
    }

    var isAdmin: Bool { role == "admin" || role == "league_admin" }
}

// MARK: - Schedule

struct ScheduleResponse: Codable {
    let seasonId: Int?
    let seasonName: String?
    let weeks: [ScheduleWeek]

    var matchups: [Matchup] {
        weeks.flatMap { week in
            week.matchups.map { m in
                var m = m
                m.weekNumber    = week.weekNumber
                m.scheduledDate = week.scheduledDate
                m.weekType      = week.weekType
                m.courseName    = week.courseName
                m.teeName       = week.teeName
                return m
            }
        }
    }

    enum CodingKeys: String, CodingKey {
        case seasonId   = "season_id"
        case seasonName = "season_name"
        case weeks
    }
}

struct ScheduleWeek: Codable {
    let weekNumber: Int
    let scheduledDate: String?
    let weekType: String?
    let courseName: String?
    let teeName: String?
    let matchups: [Matchup]
    // Tier 2: per-week Stats/Handicap/Points exclusion flags, member-visible.
    let weekExclusion: WeekExclusion?

    enum CodingKeys: String, CodingKey {
        case weekNumber    = "week_number"
        case scheduledDate = "scheduled_date"
        case weekType      = "week_type"
        case courseName    = "course_name"
        case teeName       = "tee_name"
        case matchups
        case weekExclusion = "week_exclusion"
    }
}

struct Matchup: Codable, Identifiable {
    let id: Int
    let teeTime: String?
    let startingHole: Int?
    let isBye: Bool
    let status: MatchupStatus
    let courseId: Int?
    let teeId: Int?
    let team1: MatchupTeam
    let team2: MatchupTeam

    // Populated after decode from the parent ScheduleWeek
    var weekNumber: Int = 0
    var scheduledDate: String?
    var weekType: String?
    var courseName: String?
    var teeName: String?

    enum CodingKeys: String, CodingKey {
        case id            = "matchup_id"
        case teeTime       = "tee_time"
        case startingHole  = "starting_hole"
        case isBye         = "is_bye"
        case status
        case courseId      = "course_id"
        case teeId         = "tee_id"
        case team1
        case team2
    }
}

enum MatchupStatus: String, Codable {
    case scheduled, completed, inProgress = "in_progress", bye, unknown

    init(from decoder: Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        self = MatchupStatus(rawValue: raw) ?? .unknown
    }
}

struct MatchupTeam: Codable {
    let teamId: Int
    let name: String
    let players: [MatchupPlayer]

    var shortName: String {
        players.compactMap { $0.displayName.split(separator: " ").last.map(String.init) }
                .joined(separator: " / ")
    }

    enum CodingKeys: String, CodingKey {
        case teamId = "team_id"
        case name
        case players
    }
}

struct MatchupPlayer: Codable, Identifiable {
    let id: Int
    let displayName: String
    let handicap: Double?

    enum CodingKeys: String, CodingKey {
        case id          = "player_id"
        case displayName = "display_name"
        case handicap
    }
}

// MARK: - Standings

struct StandingsResponse: Codable {
    let standings: [Standing]
    let seasonId: Int?
    let seasonName: String?

    enum CodingKeys: String, CodingKey {
        case standings
        case seasonId   = "season_id"
        case seasonName = "season_name"
    }
}

struct Standing: Codable, Identifiable {
    let id: Int
    let teamName: String
    let points: Double
    let wins: Int
    let losses: Int
    let ties: Int
    let rank: Int
    let roundsPlayed: Int

    var shortName: String {
        // "Zach Owen / Collin Michalec" → "Owen / Michalec"
        teamName.split(separator: "/").map { part in
            part.trimmingCharacters(in: .whitespaces)
                .split(separator: " ").last.map(String.init) ?? String(part)
        }.joined(separator: " / ")
    }

    enum CodingKeys: String, CodingKey {
        case id           = "team_id"
        case teamName     = "team_name"
        case points       = "total_points"
        case wins, losses, ties, rank
        case roundsPlayed = "rounds_played"
    }
}

// MARK: - Scorecard

struct ScorecardResponse: Codable {
    let roundId: Int
    let matchupId: Int
    let weekNumber: Int
    let roundDate: String
    let players: [PlayerScorecard]

    enum CodingKeys: String, CodingKey {
        case roundId    = "round_id"
        case matchupId  = "matchup_id"
        case weekNumber = "week_number"
        case roundDate  = "round_date"
        case players
    }
}

struct PlayerScorecard: Codable, Identifiable {
    let id: Int
    let playerName: String
    let teamId: Int
    let teamName: String
    let isSub: Bool
    let handicapAtTimeOfPlay: Double?
    let role: String?
    let holePoints: Double?
    let overallPoint: Double?
    let totalPoints: Double?
    let holes: [HoleScore]

    enum CodingKeys: String, CodingKey {
        case id                   = "player_id"
        case playerName           = "player_name"
        case teamId               = "team_id"
        case teamName             = "team_name"
        case isSub                = "is_sub"
        case handicapAtTimeOfPlay = "handicap_at_time_of_play"
        case role
        case holePoints           = "hole_points_won"
        case overallPoint         = "overall_point_won"
        case totalPoints          = "total_points"
        case holes
    }
}

struct HoleScore: Codable {
    let holeNumber: Int
    let par: Int?
    let grossScore: Int
    let netScore: Int
    let scoreDifferential: Int
    let strokesReceived: Int

    enum CodingKeys: String, CodingKey {
        case holeNumber        = "hole_number"
        case par
        case grossScore        = "gross_score"
        case netScore          = "net_score"
        case scoreDifferential = "score_differential"
        case strokesReceived   = "strokes_received"
    }
}

// MARK: - Skins

struct SkinsResult: Codable, Identifiable {
    let id = UUID()
    let hole: Int
    let pot: Double
    let carryIn: Double
    let isCarryover: Bool
    let winnerId: Int?
    let winnerName: String?
    let roundId: Int

    enum CodingKeys: String, CodingKey {
        case hole, pot
        case carryIn     = "carry_in"
        case isCarryover = "is_carryover"
        case winnerId    = "winner_id"
        case winnerName  = "winner_name"
        case roundId     = "round_id"
    }
}

struct SkinsWeek: Codable, Identifiable {
    let id = UUID()
    let week: Int
    let roundDate: String?
    let skins: [SkinsResult]

    enum CodingKeys: String, CodingKey {
        case week
        case roundDate = "round_date"
        case skins
    }
}

struct SkinsResponse: Codable {
    let seasonName: String
    let weeks: [SkinsWeek]

    enum CodingKeys: String, CodingKey {
        case seasonName = "season_name"
        case weeks
    }
}

// MARK: - League Board

struct BoardReaction: Codable {
    let emoji: String
    let count: Int
    let iReacted: Bool

    enum CodingKeys: String, CodingKey {
        case emoji, count
        case iReacted = "i_reacted"
    }
}

struct BoardPost: Codable, Identifiable {
    let id: Int
    let body: String
    let createdAt: String
    let isPinned: Bool
    let authorName: String
    var reactions: [BoardReaction]

    enum CodingKeys: String, CodingKey {
        case id, body
        case createdAt  = "created_at"
        case isPinned   = "is_pinned"
        case authorName = "author_name"
        case reactions
    }
}

struct BoardListResponse: Codable {
    let posts: [BoardPost]
}

// MARK: - Players / Nicknames

struct PlayerNicknamesResponse: Codable {
    let players: [PlayerWithNicknames]
}

struct PlayerWithNicknames: Codable, Identifiable {
    let id: Int
    let displayName: String
    let firstName: String
    let lastName: String
    let nicknames: [String]

    enum CodingKeys: String, CodingKey {
        case id          = "player_id"
        case displayName = "display_name"
        case firstName   = "first_name"
        case lastName    = "last_name"
        case nicknames
    }
}

struct MatchupDetailResponse: Codable {
    let roundId: Int?
    let isLocked: Bool
    let matchupId: Int
    let weekNumber: Int
    let scheduledDate: String?
    let teeTime: String?
    let startingHole: Int?
    let isBye: Bool?
    let status: MatchupStatus
    let courseId: Int?
    let courseName: String?
    let teeName: String?
    let teeId: Int?
    let team1: MatchupTeam
    let team2: MatchupTeam

    var asMatchup: Matchup {
        var m = Matchup(
            id: matchupId, teeTime: teeTime, startingHole: startingHole,
            isBye: isBye ?? false, status: status,
            courseId: courseId, teeId: teeId,
            team1: team1, team2: team2
        )
        m.weekNumber    = weekNumber
        m.scheduledDate = scheduledDate
        m.courseName    = courseName
        m.teeName       = teeName
        return m
    }

    enum CodingKeys: String, CodingKey {
        case roundId       = "round_id"
        case isLocked      = "is_locked"
        case matchupId     = "matchup_id"
        case weekNumber    = "week_number"
        case scheduledDate = "scheduled_date"
        case teeTime       = "tee_time"
        case startingHole  = "starting_hole"
        case isBye         = "is_bye"
        case status
        case courseId      = "course_id"
        case courseName    = "course_name"
        case teeName       = "tee_name"
        case teeId         = "tee_id"
        case team1, team2
    }
}

// MARK: - Stats

struct StatsLeadersResponse: Codable {
    let seasonId: Int?
    let seasonName: String?
    let lowGross: [LeaderEntry]
    let highPoints: [LeaderEntry]
    let mostWins: [LeaderEntry]

    enum CodingKeys: String, CodingKey {
        case seasonId   = "season_id"
        case seasonName = "season_name"
        case lowGross   = "low_gross"
        case highPoints = "high_points"
        case mostWins   = "most_wins"
    }
}

struct LeaderEntry: Codable, Identifiable {
    var id: String { "\(playerName)-\(weekNumber ?? 0)-\(totalGross ?? 0)" }
    let playerName: String
    let teamName: String
    let weekNumber: Int?
    let roundDate: String?
    let totalGross: Int?
    let totalPoints: Double?
    let wins: Int?

    enum CodingKeys: String, CodingKey {
        case playerName  = "player_name"
        case teamName    = "team_name"
        case weekNumber  = "week_number"
        case roundDate   = "round_date"
        case totalGross  = "total_gross"
        case totalPoints = "total_points"
        case wins
    }
}

struct StatsAllPlayResponse: Codable {
    let seasonId: Int?
    let seasonName: String?
    let rows: [AllPlayRow]
    let completedWeeks: [CompletedWeek]

    enum CodingKeys: String, CodingKey {
        case seasonId       = "season_id"
        case seasonName     = "season_name"
        case rows
        case completedWeeks = "completed_weeks"
    }
}

struct AllPlayRow: Codable, Identifiable {
    let id: Int
    let teamName: String
    let p1Name: String
    let p2Name: String
    let w: Int
    let l: Int
    let t: Int
    let pct: Double
    let seasonPts: Double
    let rank: Int

    enum CodingKeys: String, CodingKey {
        case id        = "team_id"
        case teamName  = "team_name"
        case p1Name    = "p1_name"
        case p2Name    = "p2_name"
        case w, l, t, pct, rank
        case seasonPts = "season_pts"
    }
}

struct CompletedWeek: Codable {
    let weekNumber: Int
    let scheduledDate: String?

    enum CodingKeys: String, CodingKey {
        case weekNumber    = "week_number"
        case scheduledDate = "scheduled_date"
    }
}

struct StatsTrendResponse: Codable {
    let seasonId: Int?
    let seasonName: String?
    let weeks: [CompletedWeek]
    let teams: [TrendTeam]

    enum CodingKeys: String, CodingKey {
        case seasonId   = "season_id"
        case seasonName = "season_name"
        case weeks, teams
    }
}

struct TrendTeam: Codable, Identifiable {
    let id: Int
    let teamName: String
    let points: [Double]
    let finalPts: Double

    enum CodingKeys: String, CodingKey {
        case id       = "team_id"
        case teamName = "team_name"
        case points
        case finalPts = "final_pts"
    }
}

struct StatsRecordsResponse: Codable {
    let seasonId: Int?
    let seasonName: String?
    let lowGross: [LeaderEntry]
    let highGross: [LeaderEntry]
    let highIndivPts: [LeaderEntry]
    let lowIndivPts: [LeaderEntry]

    enum CodingKeys: String, CodingKey {
        case seasonId    = "season_id"
        case seasonName  = "season_name"
        case lowGross    = "low_gross"
        case highGross   = "high_gross"
        case highIndivPts = "high_indiv_pts"
        case lowIndivPts  = "low_indiv_pts"
    }
}

struct StatsWeeklyResponse: Codable {
    let seasonId: Int?
    let seasonName: String?
    let weeks: [WeeklyWeek]

    enum CodingKeys: String, CodingKey {
        case seasonId   = "season_id"
        case seasonName = "season_name"
        case weeks
    }
}

struct WeeklyWeek: Codable, Identifiable {
    let id: Int
    let scheduledDate: String?
    let matchups: [WeeklyMatchup]

    enum CodingKeys: String, CodingKey {
        case id            = "week_number"
        case scheduledDate = "scheduled_date"
        case matchups
    }
}

struct WeeklyMatchup: Codable, Identifiable {
    let id: Int
    let team1Name: String
    let team2Name: String
    let courseName: String?
    let teeName: String?
    let roundDate: String?
    let results: [WeeklyResult]

    enum CodingKeys: String, CodingKey {
        case id        = "matchup_id"
        case team1Name = "team1_name"
        case team2Name = "team2_name"
        case courseName = "course_name"
        case teeName   = "tee_name"
        case roundDate = "round_date"
        case results
    }
}

struct WeeklyResult: Codable {
    let playerName: String
    let teamId: Int
    let grossScore: Int?
    let totalPoints: Double
    let holePoints: Double
    let overallPoint: Double

    enum CodingKeys: String, CodingKey {
        case playerName  = "player_name"
        case teamId      = "team_id"
        case grossScore  = "gross_score"
        case totalPoints = "total_points"
        case holePoints  = "hole_points"
        case overallPoint = "overall_point"
    }
}

// MARK: - Courses / Tees

struct CoursesResponse: Codable {
    let courses: [CourseInfo]
}

struct CourseInfo: Codable, Identifiable, Hashable {
    let id: Int
    let courseName: String
    let tees: [TeeInfo]

    enum CodingKeys: String, CodingKey {
        case id         = "course_id"
        case courseName = "course_name"
        case tees
    }
}

struct TeeInfo: Codable, Identifiable, Hashable {
    let id: Int
    let teeName: String
    let nine: String?
    let holes: [HoleInfo]

    var label: String { nine.map { "\(teeName) (\($0))" } ?? teeName }

    enum CodingKeys: String, CodingKey {
        case id       = "tee_id"
        case teeName  = "tee_name"
        case nine
        case holes
    }
}

struct HoleInfo: Codable, Hashable {
    let holeNumber: Int
    let par: Int
    let hcpIndex: Int?

    enum CodingKeys: String, CodingKey {
        case holeNumber = "hole_number"
        case par
        case hcpIndex   = "hcp_index"
    }
}

// MARK: - Score Submission

struct ScoreSubmitRequest: Codable {
    let matchupId: Int
    let teeId: Int
    let courseId: Int?
    let roundDate: String?
    let scores: [PlayerScoreInput]
    let playerTees: [PlayerTeeOverride]?
    let absences: [AbsenceInput]?

    enum CodingKeys: String, CodingKey {
        case matchupId  = "matchup_id"
        case teeId      = "tee_id"
        case courseId   = "course_id"
        case roundDate  = "round_date"
        case scores
        case playerTees = "player_tees"
        case absences
    }
}

struct PlayerScoreInput: Codable {
    let playerId: Int
    let holeScores: [Int]

    enum CodingKeys: String, CodingKey {
        case playerId   = "player_id"
        case holeScores = "hole_scores"
    }
}

struct PlayerTeeOverride: Codable {
    let playerId: Int
    let teeId: Int

    enum CodingKeys: String, CodingKey {
        case playerId = "player_id"
        case teeId    = "tee_id"
    }
}

struct AbsenceInput: Codable {
    let playerId: Int
    let subPlayerId: Int?

    enum CodingKeys: String, CodingKey {
        case playerId    = "player_id"
        case subPlayerId = "sub_player_id"
    }
}

struct ScoreSubmitResponse: Codable {
    let roundId: Int
    let matchResults: [MatchResult]

    enum CodingKeys: String, CodingKey {
        case roundId      = "round_id"
        case matchResults = "match_results"
    }
}

struct MatchResult: Codable {
    let playerId: Int
    let role: String
    let teamId: Int
    let holePoints: Double
    let overallPoint: Double
    let totalPoints: Double

    enum CodingKeys: String, CodingKey {
        case playerId    = "player_id"
        case role
        case teamId      = "team_id"
        case holePoints  = "hole_points"
        case overallPoint = "overall_point"
        case totalPoints = "total_points"
    }
}

struct LockResponse: Codable {
    let roundId: Int
    let locked: Bool

    enum CodingKeys: String, CodingKey {
        case roundId = "round_id"
        case locked
    }
}

struct SelfReportResponse: Codable {
    let submissionId: Int
    let status: String

    enum CodingKeys: String, CodingKey {
        case submissionId = "submission_id"
        case status
    }
}

// MARK: - Admin

struct PendingSubmissionsResponse: Codable {
    let pending: [PendingSubmission]
    let count: Int
}

struct PendingSubmission: Codable, Identifiable {
    let id: Int
    let matchupId: Int
    let weekNumber: Int
    let scheduledDate: String?
    let submittedByName: String?
    let submittedAt: String
    let courseName: String?
    let teeName: String?
    let nine: String?
    let team1Name: String?
    let team2Name: String?
    let holeCount: Int

    enum CodingKeys: String, CodingKey {
        case id             = "submission_id"
        case matchupId      = "matchup_id"
        case weekNumber     = "week_number"
        case scheduledDate  = "scheduled_date"
        case submittedByName = "submitted_by_name"
        case submittedAt    = "submitted_at"
        case courseName     = "course_name"
        case teeName        = "tee_name"
        case nine
        case team1Name      = "team1_name"
        case team2Name      = "team2_name"
        case holeCount      = "hole_count"
    }
}

struct ApproveResponse: Codable {
    let roundId: Int
    let submissionId: Int
    let status: String

    enum CodingKeys: String, CodingKey {
        case roundId       = "round_id"
        case submissionId  = "submission_id"
        case status
    }
}

// MARK: - Seasons

struct SeasonInfo: Codable, Identifiable, Hashable {
    let seasonId: Int
    let seasonName: String
    let startDate: String?
    let endDate: String?

    var id: Int { seasonId }

    enum CodingKeys: String, CodingKey {
        case seasonId   = "season_id"
        case seasonName = "season_name"
        case startDate  = "start_date"
        case endDate    = "end_date"
    }
}

struct SeasonsListResponse: Codable {
    let currentSeasonId: Int?
    let seasons: [SeasonInfo]

    enum CodingKeys: String, CodingKey {
        case currentSeasonId = "current_season_id"
        case seasons
    }
}

// MARK: - Handicap Detail

struct LeaguePlayer: Codable, Identifiable, Hashable {
    let playerId: Int
    let displayName: String
    let firstName: String
    let lastName: String
    let handicapIndex: Double?

    var id: Int { playerId }

    enum CodingKeys: String, CodingKey {
        case playerId      = "player_id"
        case displayName   = "display_name"
        case firstName     = "first_name"
        case lastName      = "last_name"
        case handicapIndex = "handicap_index"
    }
}

struct LeaguePlayersResponse: Codable {
    let players: [LeaguePlayer]
}

struct HandicapRound: Codable, Identifiable {
    let roundId: Int?
    let roundDate: String?
    let seasonName: String?
    let weekNumber: Int?
    let courseName: String
    let teeName: String
    let gross: Int
    let par: Int
    let diff: Double
    let inWindow: Bool
    let status: String  // "counting" | "dropped_high" | "dropped_low" | "outside" | "padding"

    var id: String { "\(roundId ?? 0)-\(roundDate ?? "")" }

    enum CodingKeys: String, CodingKey {
        case roundId     = "round_id"
        case roundDate   = "round_date"
        case seasonName  = "season_name"
        case weekNumber  = "week_number"
        case courseName  = "course_name"
        case teeName     = "tee_name"
        case gross, par, diff
        case inWindow    = "in_window"
        case status
    }
}

struct HandicapSettings: Codable {
    let minRounds: Int
    let roundsToAvg: Int
    let highDrop: Int
    let lowDrop: Int
    let padding: Int
    let hcpPct: Double
    let maxHcp: Double
    let window: Int

    enum CodingKeys: String, CodingKey {
        case minRounds   = "min_rounds"
        case roundsToAvg = "rounds_to_avg"
        case highDrop    = "high_drop"
        case lowDrop     = "low_drop"
        case padding, window
        case hcpPct      = "hcp_pct"
        case maxHcp      = "max_hcp"
    }
}

struct HandicapHistoryEntry: Codable {
    let index: Double
    let date: String
}

struct HandicapDetailResponse: Codable {
    let playerId: Int
    let displayName: String
    let currentHandicap: Double?
    let lastCalcDate: String?
    let computedIndex: Double?
    let committeeAdjustment: Double
    let adjReason: String?
    let realCount: Int
    let hasEnough: Bool
    let settings: HandicapSettings
    let rounds: [HandicapRound]
    let combinedWindow: [HandicapRound]
    let hcpHistory: [HandicapHistoryEntry]

    enum CodingKeys: String, CodingKey {
        case playerId            = "player_id"
        case displayName         = "display_name"
        case currentHandicap     = "current_handicap"
        case lastCalcDate        = "last_calc_date"
        case computedIndex       = "computed_index"
        case committeeAdjustment = "committee_adjustment"
        case adjReason           = "adj_reason"
        case realCount           = "real_count"
        case hasEnough           = "has_enough"
        case settings, rounds
        case combinedWindow      = "combined_window"
        case hcpHistory          = "hcp_history"
    }
}

// MARK: - Podium

struct PodiumEntry: Codable, Identifiable {
    var id: Int { position }
    let position: Int
    let teamLabel: String
    let totalPoints: Double
    let wins: Int
    let losses: Int
    let ties: Int

    enum CodingKeys: String, CodingKey {
        case position
        case teamLabel    = "team_label"
        case totalPoints  = "total_points"
        case wins, losses, ties
    }

    var record: String {
        ties > 0 ? "\(wins)–\(losses)–\(ties)" : "\(wins)–\(losses)"
    }
}

struct PodiumResponse: Codable {
    let seasonId: Int?
    let seasonName: String?
    let leagueName: String?
    let podium: [PodiumEntry]

    enum CodingKeys: String, CodingKey {
        case seasonId   = "season_id"
        case seasonName = "season_name"
        case leagueName = "league_name"
        case podium
    }
}

// MARK: - Contests

struct ContestWinner: Codable, Identifiable {
    var id: String { "\(contestName)-\(weekNum ?? 0)-\(playerName ?? teamName ?? UUID().uuidString)" }
    let contestName: String
    let contestType: String
    let contestTypeLabel: String
    let seasonId: Int?
    let seasonName: String?
    let weekNum: Int?
    let holeNumber: Int?
    let distance: Double?
    let amountWon: Double?
    let notes: String?
    let valueText: String?
    let playerName: String?
    let teamName: String?
    let roundDate: String?
    let courseName: String?

    enum CodingKeys: String, CodingKey {
        case contestName      = "contest_name"
        case contestType      = "contest_type"
        case contestTypeLabel = "contest_type_label"
        case seasonId         = "season_id"
        case seasonName       = "season_name"
        case weekNum          = "week_num"
        case holeNumber       = "hole_number"
        case distance
        case amountWon        = "amount_won"
        case notes
        case valueText        = "value_text"
        case playerName       = "player_name"
        case teamName         = "team_name"
        case roundDate        = "round_date"
        case courseName       = "course_name"
    }
}

struct ContestDetailResponse: Codable {
    let winners: [ContestWinner]
}

struct ContestSummaryEntry: Codable, Identifiable {
    let playerId: Int
    let name: String
    let totalWon: Double

    var id: Int { playerId }

    enum CodingKeys: String, CodingKey {
        case playerId = "player_id"
        case name
        case totalWon = "total_won"
    }
}

struct ContestSummaryResponse: Codable {
    let winners: [ContestSummaryEntry]
}

struct ContestScoreEntry: Codable {
    let name: String
    let gross: Int?
    let hcp: Int?
    let net: Int?
}

struct ContestLowScoreWeek: Codable, Identifiable {
    let seasonName: String
    let weekNumber: Int
    let lowGross: [ContestScoreEntry]
    let lowNet: [ContestScoreEntry]

    var id: String { "\(seasonName)-\(weekNumber)" }

    enum CodingKeys: String, CodingKey {
        case seasonName = "season_name"
        case weekNumber = "week_number"
        case lowGross   = "low_gross"
        case lowNet     = "low_net"
    }
}

struct ContestLowScoreResponse: Codable {
    let weeks: [ContestLowScoreWeek]
}

struct ContestSkinsWinner: Codable, Identifiable {
    let winnerPlayerId: Int
    let name: String
    let skinsWon: Int
    let totalWon: Double

    var id: Int { winnerPlayerId }

    enum CodingKeys: String, CodingKey {
        case winnerPlayerId = "winner_player_id"
        case name
        case skinsWon       = "skins_won"
        case totalWon       = "total_won"
    }
}

struct ContestSkinsResponse: Codable {
    let winners: [ContestSkinsWinner]
    let usingDefault: Bool

    enum CodingKeys: String, CodingKey {
        case winners
        case usingDefault = "using_default"
    }
}

// MARK: - Dues

struct DuesPayment: Codable, Identifiable {
    let paymentId: Int
    let amount: Double
    let paidDate: String?
    let method: String?
    let notes: String?

    var id: Int { paymentId }

    enum CodingKeys: String, CodingKey {
        case paymentId = "payment_id"
        case amount
        case paidDate  = "paid_date"
        case method, notes
    }
}

struct DuesResponse: Codable {
    let seasonId: Int
    let duesAmount: Double?
    let duesDueDate: String?
    let myPaid: Bool
    let myPayments: [DuesPayment]
    let paidCount: Int
    let totalCount: Int

    enum CodingKeys: String, CodingKey {
        case seasonId     = "season_id"
        case duesAmount   = "dues_amount"
        case duesDueDate  = "dues_due_date"
        case myPaid       = "my_paid"
        case myPayments   = "my_payments"
        case paidCount    = "paid_count"
        case totalCount   = "total_count"
    }
}

// MARK: - Announcements

struct Announcement: Codable, Identifiable {
    let notificationId: Int
    let type: String?
    let message: String
    let createdDate: String?
    let displayUntil: String?

    var id: Int { notificationId }

    enum CodingKeys: String, CodingKey {
        case notificationId = "notification_id"
        case type, message
        case createdDate    = "created_date"
        case displayUntil   = "display_until"
    }
}

struct AnnouncementsResponse: Codable {
    let active: [Announcement]
    let expired: [Announcement]
}

// MARK: - Subs

struct SubRequest: Codable, Identifiable {
    let requestId: Int
    let matchupId: Int
    let seasonId: Int?
    let weekNumber: Int?
    let notes: String?
    let status: String
    let subPlayerName: String?
    let adminNotes: String?
    let createdAt: String?

    var id: Int { requestId }

    enum CodingKeys: String, CodingKey {
        case requestId     = "request_id"
        case matchupId     = "matchup_id"
        case seasonId      = "season_id"
        case weekNumber    = "week_number"
        case notes, status
        case subPlayerName = "sub_player_name"
        case adminNotes    = "admin_notes"
        case createdAt     = "created_at"
    }
}

struct SubRequestCreateResponse: Codable {
    let request: SubRequest
}

struct SubsMineResponse: Codable {
    let requests: [SubRequest]
}

struct SubCancelResponse: Codable {
    let status: String
}

// MARK: - Availability / RSVP

struct AvailabilityEntry: Codable, Identifiable {
    let weekNumber: Int
    let available: Bool
    let note: String

    var id: Int { weekNumber }

    enum CodingKeys: String, CodingKey {
        case weekNumber = "week_number"
        case available, note
    }
}

struct AvailabilityListResponse: Codable {
    let availability: [AvailabilityEntry]
}

struct AvailabilityUpsertResponse: Codable {
    let status: String
    let weekNumber: Int
    let available: Bool
    let note: String

    enum CodingKeys: String, CodingKey {
        case status
        case weekNumber = "week_number"
        case available, note
    }
}

// MARK: - Shared

/// Generic `{"ok": true}` response body shared by several admin write
/// endpoints (clear point override, save week exclusion, edit contest,
/// delete announcement, ...).
struct OkResponse: Codable {
    let ok: Bool
}

// MARK: - Playoffs (Tier 2 admin/read-only bracket)

struct PlayoffTeamRef: Codable, Hashable {
    let teamId: Int
    let label: String

    enum CodingKeys: String, CodingKey {
        case teamId = "team_id"
        case label
    }
}

struct PlayoffMatchup: Codable, Identifiable {
    let id: Int
    let team1: PlayoffTeamRef?
    let team2: PlayoffTeamRef?
    let team1Points: Double?
    let team2Points: Double?
    let winnerTeamId: Int?
    let isFinals: Bool
    let weekNumber: Int

    enum CodingKeys: String, CodingKey {
        case id           = "matchup_id"
        case team1, team2
        case team1Points  = "team1_points"
        case team2Points  = "team2_points"
        case winnerTeamId = "winner_team_id"
        case isFinals     = "is_finals"
        case weekNumber   = "week_number"
    }
}

struct PlayoffRound: Codable, Identifiable {
    let roundNumber: Int
    let label: String
    let matchups: [PlayoffMatchup]

    var id: Int { roundNumber }

    enum CodingKeys: String, CodingKey {
        case roundNumber = "round_number"
        case label, matchups
    }
}

struct PlayoffBracketResponse: Codable {
    let rounds: [PlayoffRound]
    let champion: PlayoffTeamRef?
}

struct PlayoffResultResponse: Codable {
    let matchupId: Int
    let team1Points: Double
    let team2Points: Double
    let winnerTeamId: Int?

    enum CodingKeys: String, CodingKey {
        case matchupId     = "matchup_id"
        case team1Points   = "team1_points"
        case team2Points   = "team2_points"
        case winnerTeamId  = "winner_team_id"
    }
}

// MARK: - Points Override (Tier 2 admin)

struct PointOverride: Codable, Identifiable {
    let playerId: Int
    let overrideValue: Double
    let originalValue: Double?
    let reason: String?
    let active: Bool

    var id: Int { playerId }

    enum CodingKeys: String, CodingKey {
        case playerId      = "player_id"
        case overrideValue = "override_value"
        case originalValue = "original_value"
        case reason, active
    }
}

struct MatchupOverridesResponse: Codable {
    let overrides: [PointOverride]
}

struct OverridePointsResponse: Codable {
    let changed: Int
    let players: [Int]
}

// MARK: - Week Exclusions (Tier 2 admin; read side embedded in ScheduleWeek)

struct WeekExclusion: Codable {
    let excludeStats: Bool
    let excludeHandicap: Bool
    let excludePoints: Bool
    let reason: String?

    enum CodingKeys: String, CodingKey {
        case excludeStats    = "exclude_stats"
        case excludeHandicap = "exclude_handicap"
        case excludePoints   = "exclude_points"
        case reason
    }
}

// MARK: - Handicap Admin (Tier 2)

struct HandicapMatrixRoundColumn: Codable, Identifiable {
    let roundDate: String
    let weekNumber: Int?

    var id: String { roundDate }

    enum CodingKeys: String, CodingKey {
        case roundDate  = "round_date"
        case weekNumber = "week_number"
    }
}

struct HandicapMatrixCell: Codable {
    let hcp: Double?
    let overridden: Bool
    let scorecardId: Int?
    let matchupId: Int?

    enum CodingKeys: String, CodingKey {
        case hcp, overridden
        case scorecardId = "scorecard_id"
        case matchupId   = "matchup_id"
    }
}

struct HandicapCellOverrideResponse: Codable {
    let ok: Bool
    let updated: Int
    let recalcErrors: [String]

    enum CodingKeys: String, CodingKey {
        case ok, updated
        case recalcErrors = "recalc_errors"
    }
}

struct HandicapMatrixRow: Codable, Identifiable {
    let playerId: Int
    let name: String
    let currentHcp: Double?
    let roundCells: [HandicapMatrixCell?]
    let avg: Double?

    var id: Int { playerId }

    enum CodingKeys: String, CodingKey {
        case playerId   = "player_id"
        case name
        case currentHcp = "current_hcp"
        case roundCells = "round_cells"
        case avg
    }
}

struct HandicapMatrixResponse: Codable {
    let rounds: [HandicapMatrixRoundColumn]
    let matrix: [HandicapMatrixRow]
}

struct HandicapRebuildSummary: Codable {
    let playersProcessed: Int
    let roundsProcessed: Int
    let roundsChanged: Int

    enum CodingKeys: String, CodingKey {
        case playersProcessed = "players_processed"
        case roundsProcessed  = "rounds_processed"
        case roundsChanged    = "rounds_changed"
    }
}

struct HandicapRebuildResponse: Codable {
    let summary: HandicapRebuildSummary
}

struct HandicapOverrideResponse: Codable {
    let handicapId: Int
    let handicapIndex: Double

    enum CodingKeys: String, CodingKey {
        case handicapId    = "handicap_id"
        case handicapIndex = "handicap_index"
    }
}

struct HandicapClearOverrideResponse: Codable {
    let ok: Bool
    let playerId: Int

    enum CodingKeys: String, CodingKey {
        case ok
        case playerId = "player_id"
    }
}

// MARK: - Admin: Contests CRUD

struct AdminContest: Codable, Identifiable {
    let contestId: Int
    let seasonId: Int
    let leagueId: Int
    let name: String
    let description: String?
    let weekNum: Int?
    let contestType: String
    let isRecurringRaw: Int
    let createdDate: String?
    let resultCount: Int?

    var id: Int { contestId }
    var isRecurring: Bool { isRecurringRaw != 0 }

    enum CodingKeys: String, CodingKey {
        case contestId      = "contest_id"
        case seasonId       = "season_id"
        case leagueId       = "league_id"
        case name, description
        case weekNum        = "week_num"
        case contestType    = "contest_type"
        case isRecurringRaw = "is_recurring"
        case createdDate    = "created_date"
        case resultCount    = "result_count"
    }
}

struct AdminContestsListResponse: Codable {
    let contests: [AdminContest]
}

struct AdminContestCreateResponse: Codable {
    let contestId: Int
    let name: String

    enum CodingKeys: String, CodingKey {
        case contestId = "contest_id"
        case name
    }
}

struct AdminContestResult: Codable, Identifiable {
    let resultId: Int
    let contestId: Int
    let playerId: Int?
    let teamId: Int?
    let valueText: String?
    let valueNum: Double?
    let holeNumber: Int?
    let weekNum: Int?
    let distance: String?
    let amountWon: Double?
    let notes: String?
    let rank: Int?
    let firstName: String?
    let lastName: String?
    let teamName: String?

    var id: Int { resultId }

    var displayName: String {
        if let t = teamName, !t.isEmpty { return t }
        return [firstName, lastName].compactMap { $0 }.joined(separator: " ")
    }

    enum CodingKeys: String, CodingKey {
        case resultId   = "result_id"
        case contestId  = "contest_id"
        case playerId   = "player_id"
        case teamId     = "team_id"
        case valueText  = "value_text"
        case valueNum   = "value_num"
        case holeNumber = "hole_number"
        case weekNum    = "week_num"
        case distance
        case amountWon  = "amount_won"
        case notes, rank
        case firstName  = "first_name"
        case lastName   = "last_name"
        case teamName   = "team_name"
    }
}

struct AdminContestDetailResponse: Codable {
    let contest: AdminContest
    let results: [AdminContestResult]
}

struct ContestDeleteResponse: Codable {
    let ok: Bool
    let scope: String
    let weekNum: Int?

    enum CodingKeys: String, CodingKey {
        case ok, scope
        case weekNum = "week_num"
    }
}

struct ContestCalculateResponse: Codable {
    let weekNum: Int
    let results: Int

    enum CodingKeys: String, CodingKey {
        case weekNum = "week_num"
        case results
    }
}

struct ContestCalculateAllResponse: Codable {
    let weeksCalculated: Int
    let weeksSkipped: Int
    let totalResults: Int

    enum CodingKeys: String, CodingKey {
        case weeksCalculated = "weeks_calculated"
        case weeksSkipped    = "weeks_skipped"
        case totalResults    = "total_results"
    }
}

// MARK: - Admin: Announcements CRUD
// (Distinct from the member-facing `Announcement`/`AnnouncementsResponse`
// Tier 1 added above — this admin list is the raw `notifications` table row,
// which carries `active` as a 0/1 int rather than the filtered active/expired
// split the member endpoint returns.)

struct AdminAnnouncement: Codable, Identifiable {
    let notificationId: Int
    let type: String?
    let message: String
    let createdDate: String?
    let displayUntil: String?
    let activeRaw: Int

    var id: Int { notificationId }
    var isActive: Bool { activeRaw != 0 }

    enum CodingKeys: String, CodingKey {
        case notificationId = "notification_id"
        case type, message
        case createdDate    = "created_date"
        case displayUntil   = "display_until"
        case activeRaw      = "active"
    }
}

struct AdminAnnouncementsListResponse: Codable {
    let announcements: [AdminAnnouncement]
}

struct AnnouncementCreateResponse: Codable {
    let notificationId: Int

    enum CodingKeys: String, CodingKey {
        case notificationId = "notification_id"
    }
}

struct AnnouncementToggleResponse: Codable {
    let ok: Bool
    let active: Bool
}

// MARK: - Admin: Subs Queue

struct AdminSubRequest: Codable, Identifiable {
    let requestId: Int
    let seasonId: Int?
    let matchupId: Int?
    let playerId: Int?
    let notes: String?
    let status: String
    let subPlayerId: Int?
    let adminNotes: String?
    let createdAt: String?
    let playerFirst: String?
    let playerLast: String?
    let seasonName: String?
    let weekNum: Int?
    let weekDate: String?
    let team1Name: String?
    let team2Name: String?
    let t1p1First: String?
    let t1p1Last: String?
    let t1p2First: String?
    let t1p2Last: String?
    let t2p1First: String?
    let t2p1Last: String?
    let t2p2First: String?
    let t2p2Last: String?

    var id: Int { requestId }

    var playerName: String {
        [playerFirst, playerLast].compactMap { $0 }.joined(separator: " ")
    }

    var team1Label: String {
        if let n = team1Name, !n.isEmpty { return n }
        let names = [t1p1Last, t1p2Last].compactMap { $0 }
        return names.isEmpty ? "Team 1" : names.joined(separator: " / ")
    }

    var team2Label: String {
        if let n = team2Name, !n.isEmpty { return n }
        let names = [t2p1Last, t2p2Last].compactMap { $0 }
        return names.isEmpty ? "Team 2" : names.joined(separator: " / ")
    }

    enum CodingKeys: String, CodingKey {
        case requestId    = "request_id"
        case seasonId     = "season_id"
        case matchupId    = "matchup_id"
        case playerId     = "player_id"
        case notes, status
        case subPlayerId  = "sub_player_id"
        case adminNotes   = "admin_notes"
        case createdAt    = "created_at"
        case playerFirst  = "player_first"
        case playerLast   = "player_last"
        case seasonName   = "season_name"
        case weekNum      = "week_num"
        case weekDate     = "week_date"
        case team1Name    = "team1_name"
        case team2Name    = "team2_name"
        case t1p1First    = "t1p1_first"
        case t1p1Last     = "t1p1_last"
        case t1p2First    = "t1p2_first"
        case t1p2Last     = "t1p2_last"
        case t2p1First    = "t2p1_first"
        case t2p1Last     = "t2p1_last"
        case t2p2First    = "t2p2_first"
        case t2p2Last     = "t2p2_last"
    }
}

struct AdminSubsPendingResponse: Codable {
    let requests: [AdminSubRequest]
}

struct AdminSubActionResponse: Codable {
    let ok: Bool
    let requestId: Int
    let status: String

    enum CodingKeys: String, CodingKey {
        case ok
        case requestId = "request_id"
        case status
    }
}
