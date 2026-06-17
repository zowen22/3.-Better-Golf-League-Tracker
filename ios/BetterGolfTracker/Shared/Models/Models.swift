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

    enum CodingKeys: String, CodingKey {
        case weekNumber    = "week_number"
        case scheduledDate = "scheduled_date"
        case weekType      = "week_type"
        case courseName    = "course_name"
        case teeName       = "tee_name"
        case matchups
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
