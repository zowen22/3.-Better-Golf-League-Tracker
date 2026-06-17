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

    // MARK: APNs
    static func registerAPNs(deviceToken: String) -> Endpoint {
        Endpoint(path: "/api/v1/apns/register", method: .POST, body: ["device_token": deviceToken])
    }
}
