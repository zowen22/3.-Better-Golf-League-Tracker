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

    enum CodingKeys: String, CodingKey {
        case userId    = "user_id"
        case leagueId  = "league_id"
        case role
        case playerId  = "player_id"
    }

    var isAdmin: Bool { role == "admin" || role == "league_admin" }
}

// MARK: - Schedule

struct ScheduleResponse: Codable {
    let matchups: [Matchup]
}

struct Matchup: Codable, Identifiable {
    let id: Int
    let weekNumber: Int
    let scheduledDate: String?
    let teeTime: String?
    let startingHole: Int?
    let status: MatchupStatus
    let courseName: String?
    let teeName: String?
    let teeNine: String?
    let team1: MatchupTeam
    let team2: MatchupTeam

    enum CodingKeys: String, CodingKey {
        case id            = "matchup_id"
        case weekNumber    = "week_number"
        case scheduledDate = "scheduled_date"
        case teeTime       = "tee_time"
        case startingHole  = "starting_hole"
        case status
        case courseName    = "course_name"
        case teeName       = "tee_name"
        case teeNine       = "tee_nine"
        case team1
        case team2
    }
}

enum MatchupStatus: String, Codable {
    case scheduled, completed, inProgress = "in_progress"
}

struct MatchupTeam: Codable {
    let teamId: Int
    let name: String
    let players: [MatchupPlayer]

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

    enum CodingKeys: String, CodingKey {
        case id       = "team_id"
        case teamName = "team_name"
        case points, wins, losses, ties, rank
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

    enum CodingKeys: String, CodingKey {
        case holeNumber       = "hole_number"
        case par
        case grossScore       = "gross_score"
        case netScore         = "net_score"
        case scoreDifferential = "score_differential"
    }
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
