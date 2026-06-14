import Foundation

actor APIClient {
    static let shared = APIClient()

    private let baseURL: URL
    private let session: URLSession
    private var onUnauthorized: (() -> Void)?

    private init() {
        #if DEBUG
        baseURL = URL(string: "http://localhost:5000")!
        #else
        baseURL = URL(string: "https://bettergolfleaguetracker-oceb.onrender.com")!
        #endif
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 30
        session = URLSession(configuration: config)
    }

    func setUnauthorizedHandler(_ handler: @escaping () -> Void) {
        onUnauthorized = handler
    }

    // MARK: - Core request

    func request<T: Decodable>(_ endpoint: Endpoint) async throws -> T {
        let urlRequest = try buildRequest(endpoint)
        let (data, response) = try await fetch(urlRequest)
        return try decode(T.self, from: data, response: response)
    }

    // Convenience for endpoints that return no meaningful body (e.g. DELETE)
    func requestVoid(_ endpoint: Endpoint) async throws {
        let urlRequest = try buildRequest(endpoint)
        let (_, response) = try await fetch(urlRequest)
        guard let http = response as? HTTPURLResponse else { return }
        try throwIfError(statusCode: http.statusCode, data: nil)
    }

    // MARK: - Build URLRequest

    private func buildRequest(_ endpoint: Endpoint) throws -> URLRequest {
        guard let url = URL(string: endpoint.path, relativeTo: baseURL) else {
            throw APIError.unknown(0)
        }
        var req = URLRequest(url: url)
        req.httpMethod = endpoint.method.rawValue
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")

        if let token = KeychainStore.loadToken() {
            req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }

        if let body = endpoint.body {
            req.httpBody = try JSONEncoder().encode(AnyEncodable(body))
        }
        return req
    }

    // MARK: - Fetch + error mapping

    private func fetch(_ request: URLRequest) async throws -> (Data, URLResponse) {
        do {
            return try await session.data(for: request)
        } catch let urlError as URLError where urlError.code == .notConnectedToInternet
                                             || urlError.code == .networkConnectionLost {
            throw APIError.noNetwork
        }
    }

    private func decode<T: Decodable>(_ type: T.Type, from data: Data, response: URLResponse) throws -> T {
        guard let http = response as? HTTPURLResponse else { throw APIError.unknown(0) }
        try throwIfError(statusCode: http.statusCode, data: data)
        do {
            return try JSONDecoder().decode(T.self, from: data)
        } catch {
            throw APIError.decodingError(error)
        }
    }

    private func throwIfError(statusCode: Int, data: Data?) throws {
        switch statusCode {
        case 200...299: return
        case 401:
            Task { @MainActor in onUnauthorized?() }
            throw APIError.unauthorized
        case 403: throw APIError.forbidden
        case 404: throw APIError.notFound
        case 409: throw APIError.conflict
        case 500...599: throw APIError.serverError(statusCode)
        default: throw APIError.unknown(statusCode)
        }
    }
}

// MARK: - Type-erased Encodable wrapper

private struct AnyEncodable: Encodable {
    private let _encode: (Encoder) throws -> Void
    init(_ wrapped: Encodable) { _encode = wrapped.encode }
    func encode(to encoder: Encoder) throws { try _encode(encoder) }
}
