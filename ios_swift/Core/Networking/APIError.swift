import Foundation

enum APIError: LocalizedError {
    case unauthorized           // 401 — trigger re-login
    case forbidden              // 403
    case notFound               // 404
    case conflict               // 409 — e.g. duplicate score submit
    case serverError(Int)       // 5xx
    case decodingError(Error)
    case noNetwork
    case unknown(Int)

    var errorDescription: String? {
        switch self {
        case .unauthorized:         return "Session expired. Please log in again."
        case .forbidden:            return "You don't have permission to do that."
        case .notFound:             return "The requested resource was not found."
        case .conflict:             return "This action conflicts with existing data."
        case .serverError(let c):   return "Server error (\(c)). Try again later."
        case .decodingError:        return "Unexpected response from server."
        case .noNetwork:            return "No network connection."
        case .unknown(let c):       return "Unexpected error (HTTP \(c))."
        }
    }
}
