import Foundation

enum HTTPMethod: String {
    case GET, POST, PUT, DELETE
}

struct Endpoint {
    let path: String
    let method: HTTPMethod
    let body: Encodable?

    // MARK: Auth
    static func login(email: String, password: String, leagueCode: String) -> Endpoint {
        Endpoint(path: "/api/v1/auth/login", method: .POST,
                 body: ["email": email, "password": password, "league_code": leagueCode])
    }
    static func refresh(token: String) -> Endpoint {
        Endpoint(path: "/api/v1/auth/refresh", method: .POST, body: ["token": token])
    }
    static var me: Endpoint {
        Endpoint(path: "/api/v1/auth/me", method: .GET, body: nil)
    }

    // MARK: Schedule
    static var schedule: Endpoint {
        Endpoint(path: "/api/v1/schedule", method: .GET, body: nil)
    }
    static func matchupDetail(_ id: Int) -> Endpoint {
        Endpoint(path: "/api/v1/schedule/\(id)", method: .GET, body: nil)
    }

    // MARK: Standings
    static var standings: Endpoint {
        Endpoint(path: "/api/v1/standings", method: .GET, body: nil)
    }

    // MARK: Scorecards
    static func scorecard(roundId: Int) -> Endpoint {
        Endpoint(path: "/api/v1/scorecards/\(roundId)", method: .GET, body: nil)
    }

    // MARK: Players / Nicknames
    static var playerNicknames: Endpoint {
        Endpoint(path: "/api/v1/players/nicknames", method: .GET, body: nil)
    }
    static func addNickname(playerId: Int, nickname: String) -> Endpoint {
        struct Body: Encodable {
            let player_id: Int
            let nickname: String
        }
        return Endpoint(path: "/api/v1/nicknames", method: .POST,
                        body: Body(player_id: playerId, nickname: nickname))
    }
    static func deleteNickname(nicknameId: Int) -> Endpoint {
        Endpoint(path: "/api/v1/nicknames/\(nicknameId)", method: .DELETE, body: nil)
    }

    // MARK: Score Submission
    static func submitScores(_ request: ScoreSubmitRequest) -> Endpoint {
        Endpoint(path: "/api/v1/scores/submit", method: .POST, body: request)
    }

    // MARK: Admin
    static var adminPending: Endpoint {
        Endpoint(path: "/api/v1/admin/pending", method: .GET, body: nil)
    }
    static func approve(submissionId: Int) -> Endpoint {
        Endpoint(path: "/api/v1/admin/approve/\(submissionId)", method: .POST, body: nil)
    }

    // MARK: Stats
    static var statsLeaders: Endpoint {
        Endpoint(path: "/api/v1/stats/leaders", method: .GET, body: nil)
    }
    static var statsAllPlay: Endpoint {
        Endpoint(path: "/api/v1/stats/allplay", method: .GET, body: nil)
    }
    static var statsTrend: Endpoint {
        Endpoint(path: "/api/v1/stats/trend", method: .GET, body: nil)
    }
    static var statsRecords: Endpoint {
        Endpoint(path: "/api/v1/stats/records", method: .GET, body: nil)
    }
    static var statsWeekly: Endpoint {
        Endpoint(path: "/api/v1/stats/weekly", method: .GET, body: nil)
    }

    // MARK: Courses
    static var courses: Endpoint {
        Endpoint(path: "/api/v1/courses", method: .GET, body: nil)
    }

    // MARK: Self-Report
    static func submitSelfReport(_ request: ScoreSubmitRequest) -> Endpoint {
        Endpoint(path: "/api/v1/self-report/submit", method: .POST, body: request)
    }

    // MARK: Lock
    static func toggleLock(matchupId: Int) -> Endpoint {
        Endpoint(path: "/api/v1/admin/lock/\(matchupId)", method: .POST, body: nil)
    }

    // MARK: Seasons
    static var seasonsList: Endpoint {
        Endpoint(path: "/api/v1/seasons/list", method: .GET, body: nil)
    }
    static func seasonStandings(seasonId: Int) -> Endpoint {
        Endpoint(path: "/api/v1/seasons/\(seasonId)/standings/mobile", method: .GET, body: nil)
    }

    // MARK: Players
    static var leaguePlayers: Endpoint {
        Endpoint(path: "/api/v1/players/league", method: .GET, body: nil)
    }
    static func handicapDetail(playerId: Int) -> Endpoint {
        Endpoint(path: "/api/v1/players/\(playerId)/handicap-detail", method: .GET, body: nil)
    }

    // MARK: Podium
    static var podium: Endpoint {
        Endpoint(path: "/api/v1/standings/podium", method: .GET, body: nil)
    }

    // MARK: Skins
    static var skins: Endpoint {
        Endpoint(path: "/api/v1/skins", method: .GET, body: nil)
    }

    // MARK: League Board
    static var boardList: Endpoint {
        Endpoint(path: "/api/v1/board", method: .GET, body: nil)
    }
    static func boardPost(body: String, isPinned: Bool = false) -> Endpoint {
        struct Body: Encodable { let body: String; let is_pinned: Bool }
        return Endpoint(path: "/api/v1/board", method: .POST,
                        body: Body(body: body, is_pinned: isPinned))
    }
    static func boardReact(postId: Int, emoji: String) -> Endpoint {
        struct Body: Encodable { let emoji: String }
        return Endpoint(path: "/api/v1/board/\(postId)/react", method: .POST,
                        body: Body(emoji: emoji))
    }

    // MARK: APNs
    static func registerAPNs(deviceToken: String) -> Endpoint {
        Endpoint(path: "/api/v1/apns/register", method: .POST, body: ["device_token": deviceToken])
    }

    // MARK: Contests
    static func contestsWinners(type: String, seasonId: Int? = nil, weekNum: Int? = nil) -> Endpoint {
        var path = "/api/v1/contests/winners?type=\(type)"
        if let seasonId { path += "&season_id=\(seasonId)" }
        if let weekNum { path += "&week_num=\(weekNum)" }
        return Endpoint(path: path, method: .GET, body: nil)
    }

    // MARK: Dues
    static func dues(seasonId: Int? = nil) -> Endpoint {
        var path = "/api/v1/dues"
        if let seasonId { path += "?season_id=\(seasonId)" }
        return Endpoint(path: path, method: .GET, body: nil)
    }

    // MARK: Announcements
    static var announcements: Endpoint {
        Endpoint(path: "/api/v1/announcements", method: .GET, body: nil)
    }

    // MARK: Subs
    static func subRequest(matchupId: Int, notes: String) -> Endpoint {
        struct Body: Encodable { let matchup_id: Int; let notes: String }
        return Endpoint(path: "/api/v1/subs/request", method: .POST,
                        body: Body(matchup_id: matchupId, notes: notes))
    }
    static func subCancel(requestId: Int) -> Endpoint {
        Endpoint(path: "/api/v1/subs/\(requestId)/cancel", method: .POST, body: nil)
    }
    static var subsMine: Endpoint {
        Endpoint(path: "/api/v1/subs/mine", method: .GET, body: nil)
    }

    // MARK: Availability
    static func availability(seasonId: Int) -> Endpoint {
        Endpoint(path: "/api/v1/availability?season_id=\(seasonId)", method: .GET, body: nil)
    }
    static func availabilityUpsert(seasonId: Int, weekNumber: Int, available: Bool, note: String) -> Endpoint {
        struct Body: Encodable {
            let season_id: Int
            let week_number: Int
            let available: Bool
            let note: String
        }
        return Endpoint(path: "/api/v1/availability", method: .POST,
                        body: Body(season_id: seasonId, week_number: weekNumber, available: available, note: note))
    }

    // MARK: Playoffs
    static func playoffs(seasonId: Int? = nil) -> Endpoint {
        var path = "/api/v1/playoffs"
        if let seasonId { path += "?season_id=\(seasonId)" }
        return Endpoint(path: path, method: .GET, body: nil)
    }
    static func savePlayoffResult(matchupId: Int, team1Points: Double, team2Points: Double, winnerTeamId: Int?) -> Endpoint {
        struct Body: Encodable {
            let team1_points: Double
            let team2_points: Double
            let winner_team_id: Int?
        }
        return Endpoint(path: "/api/v1/admin/playoffs/matchup/\(matchupId)/result", method: .POST,
                        body: Body(team1_points: team1Points, team2_points: team2Points, winner_team_id: winnerTeamId))
    }

    // MARK: Points Override
    static func matchupOverrides(matchupId: Int) -> Endpoint {
        Endpoint(path: "/api/v1/matchups/\(matchupId)/overrides", method: .GET, body: nil)
    }
    static func overridePoints(matchupId: Int, values: [(playerId: Int, totalPoints: Double)], reason: String) -> Endpoint {
        struct ValueBody: Encodable { let player_id: Int; let total_points: Double }
        struct Body: Encodable { let reason: String; let values: [ValueBody] }
        return Endpoint(path: "/api/v1/admin/matchups/\(matchupId)/override-points", method: .POST,
                        body: Body(reason: reason, values: values.map { ValueBody(player_id: $0.playerId, total_points: $0.totalPoints) }))
    }
    static func clearOverridePoints(matchupId: Int, playerId: Int, reason: String? = nil) -> Endpoint {
        struct Body: Encodable { let reason: String? }
        return Endpoint(path: "/api/v1/admin/matchups/\(matchupId)/override-points/\(playerId)/clear", method: .POST,
                        body: Body(reason: reason))
    }

    // MARK: Week Exclusions
    static func saveWeekExclusion(seasonId: Int, weekNum: Int, excludeStats: Bool, excludeHandicap: Bool,
                                   excludePoints: Bool, reason: String?) -> Endpoint {
        struct Body: Encodable {
            let exclude_stats: Bool
            let exclude_handicap: Bool
            let exclude_points: Bool
            let reason: String?
        }
        return Endpoint(path: "/api/v1/admin/week-exclusions/\(seasonId)/\(weekNum)", method: .POST,
                        body: Body(exclude_stats: excludeStats, exclude_handicap: excludeHandicap,
                                   exclude_points: excludePoints, reason: reason))
    }

    // MARK: Handicap Admin
    static func handicapMatrix(seasonId: Int? = nil) -> Endpoint {
        var path = "/api/v1/admin/handicap/matrix"
        if let seasonId { path += "?season_id=\(seasonId)" }
        return Endpoint(path: path, method: .GET, body: nil)
    }
    static func handicapRebuild(preview: Bool) -> Endpoint {
        Endpoint(path: "/api/v1/admin/handicap/rebuild?preview=\(preview)", method: .POST, body: nil)
    }
    /// Overrides one matrix cell's playing handicap. Distinct from the
    /// per-history-row override below -- a matrix cell maps to a
    /// `scorecards` row (`scorecard_id`), not a `handicap_history` row.
    static func overrideHandicapMatrixCell(seasonId: Int, scorecardId: Int, matchupId: Int, hcp: Double) -> Endpoint {
        struct Body: Encodable { let scorecard_id: Int; let hcp: Double; let matchup_id: Int }
        return Endpoint(path: "/api/v1/admin/handicap/matrix/\(seasonId)/cell-override", method: .POST,
                        body: Body(scorecard_id: scorecardId, hcp: hcp, matchup_id: matchupId))
    }
    static func overrideHandicapHistory(handicapId: Int, newIndex: Double, reason: String) -> Endpoint {
        struct Body: Encodable { let new_index: Double; let reason: String }
        return Endpoint(path: "/api/v1/admin/handicap/history/\(handicapId)/override", method: .POST,
                        body: Body(new_index: newIndex, reason: reason))
    }
    static func clearHandicapHistoryOverride(handicapId: Int) -> Endpoint {
        Endpoint(path: "/api/v1/admin/handicap/history/\(handicapId)/clear", method: .POST, body: nil)
    }

    // MARK: Admin Contests CRUD
    static func adminContests(seasonId: Int) -> Endpoint {
        Endpoint(path: "/api/v1/admin/contests?season_id=\(seasonId)", method: .GET, body: nil)
    }
    static func createAdminContest(seasonId: Int, contestType: String, weekNum: Int?, description: String?, isRecurring: Bool) -> Endpoint {
        struct Body: Encodable {
            let season_id: Int
            let contest_type: String
            let week_num: Int?
            let description: String?
            let is_recurring: Bool
        }
        return Endpoint(path: "/api/v1/admin/contests", method: .POST,
                        body: Body(season_id: seasonId, contest_type: contestType, week_num: weekNum,
                                   description: description, is_recurring: isRecurring))
    }
    static func adminContestDetail(contestId: Int) -> Endpoint {
        Endpoint(path: "/api/v1/admin/contests/\(contestId)", method: .GET, body: nil)
    }
    static func updateAdminContest(contestId: Int, contestType: String, weekNum: Int?, description: String?, isRecurring: Bool) -> Endpoint {
        struct Body: Encodable {
            let contest_type: String
            let week_num: Int?
            let description: String?
            let is_recurring: Bool
        }
        return Endpoint(path: "/api/v1/admin/contests/\(contestId)", method: .PUT,
                        body: Body(contest_type: contestType, week_num: weekNum, description: description, is_recurring: isRecurring))
    }
    static func deleteAdminContest(contestId: Int, scope: String = "all", weekNum: Int? = nil) -> Endpoint {
        var path = "/api/v1/admin/contests/\(contestId)?scope=\(scope)"
        if let weekNum { path += "&week_num=\(weekNum)" }
        return Endpoint(path: path, method: .DELETE, body: nil)
    }
    static func calculateAdminContest(contestId: Int, weekNum: Int?) -> Endpoint {
        struct Body: Encodable { let week_num: Int? }
        return Endpoint(path: "/api/v1/admin/contests/\(contestId)/calculate", method: .POST, body: Body(week_num: weekNum))
    }
    static func calculateAllAdminContest(contestId: Int) -> Endpoint {
        Endpoint(path: "/api/v1/admin/contests/\(contestId)/calculate-all", method: .POST, body: nil)
    }

    // MARK: Admin Announcements CRUD
    static var adminAnnouncements: Endpoint {
        Endpoint(path: "/api/v1/admin/announcements", method: .GET, body: nil)
    }
    static func createAdminAnnouncement(type: String, message: String, displayUntil: String?) -> Endpoint {
        struct Body: Encodable { let type: String; let message: String; let display_until: String? }
        return Endpoint(path: "/api/v1/admin/announcements", method: .POST,
                        body: Body(type: type, message: message, display_until: displayUntil))
    }
    static func updateAdminAnnouncement(notifId: Int, type: String, message: String, displayUntil: String?) -> Endpoint {
        struct Body: Encodable { let type: String; let message: String; let display_until: String? }
        return Endpoint(path: "/api/v1/admin/announcements/\(notifId)", method: .PUT,
                        body: Body(type: type, message: message, display_until: displayUntil))
    }
    static func deleteAdminAnnouncement(notifId: Int) -> Endpoint {
        Endpoint(path: "/api/v1/admin/announcements/\(notifId)", method: .DELETE, body: nil)
    }
    static func toggleAdminAnnouncement(notifId: Int) -> Endpoint {
        Endpoint(path: "/api/v1/admin/announcements/\(notifId)/toggle", method: .POST, body: nil)
    }

    // MARK: Admin Subs Queue
    static var adminSubsPending: Endpoint {
        Endpoint(path: "/api/v1/admin/subs/pending", method: .GET, body: nil)
    }
    static func adminSubAssign(requestId: Int, subPlayerId: Int?, adminNotes: String?) -> Endpoint {
        struct Body: Encodable { let sub_player_id: Int?; let admin_notes: String? }
        return Endpoint(path: "/api/v1/admin/subs/\(requestId)/assign", method: .POST,
                        body: Body(sub_player_id: subPlayerId, admin_notes: adminNotes))
    }
    static func adminSubDismiss(requestId: Int, adminNotes: String?) -> Endpoint {
        struct Body: Encodable { let admin_notes: String? }
        return Endpoint(path: "/api/v1/admin/subs/\(requestId)/dismiss", method: .POST, body: Body(admin_notes: adminNotes))
    }
}
