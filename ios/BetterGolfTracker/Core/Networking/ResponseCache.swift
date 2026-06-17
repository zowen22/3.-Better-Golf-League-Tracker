import Foundation

/// Simple JSON cache backed by UserDefaults.
/// Keyed by endpoint path so each distinct URL caches separately.
enum ResponseCache {

    private static let defaults = UserDefaults.standard
    private static let maxAgeSeconds: TimeInterval = 60 * 60 * 24 // 24 hours

    static func save<T: Encodable>(_ value: T, for key: String) {
        guard let data = try? JSONEncoder().encode(value) else { return }
        defaults.set(data, forKey: cacheKey(key))
        defaults.set(Date().timeIntervalSince1970, forKey: ageKey(key))
    }

    static func load<T: Decodable>(_ type: T.Type, for key: String) -> T? {
        guard let data = defaults.data(forKey: cacheKey(key)),
              let age = defaults.object(forKey: ageKey(key)) as? TimeInterval
        else { return nil }
        // Return nil if cache is too old — callers should re-fetch
        guard Date().timeIntervalSince1970 - age < maxAgeSeconds else { return nil }
        return try? JSONDecoder().decode(T.self, from: data)
    }

    static func loadStale<T: Decodable>(_ type: T.Type, for key: String) -> T? {
        guard let data = defaults.data(forKey: cacheKey(key)) else { return nil }
        return try? JSONDecoder().decode(T.self, from: data)
    }

    private static func cacheKey(_ key: String) -> String { "cache_data_\(key)" }
    private static func ageKey(_ key: String)  -> String { "cache_age_\(key)" }
}
