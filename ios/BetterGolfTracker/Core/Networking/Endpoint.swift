import Foundation

enum HTTPMethod: String {
    case GET, POST, DELETE
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
}
