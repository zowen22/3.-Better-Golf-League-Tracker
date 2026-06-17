import Foundation

/// Matches OCR-detected player name strings to known league players.
/// Result is used to assign parsed score rows to the correct player slots.
enum NicknameMatchService {

    enum MatchResult {
        case confident(MatchupPlayer)
        case suggested(ocrName: String, player: MatchupPlayer, score: Double)
        case unmatched(ocrName: String)
    }

    /// Match a single OCR name against a list of candidates + stored nicknames.
    static func match(
        ocrName: String,
        candidates: [MatchupPlayer],
        nicknames: [PlayerWithNicknames]
    ) -> MatchResult {
        let normalised = normalise(ocrName)
        guard !normalised.isEmpty else { return .unmatched(ocrName: ocrName) }

        // 1. Exact display name match (case-insensitive)
        if let exact = candidates.first(where: { normalise($0.displayName) == normalised }) {
            return .confident(exact)
        }

        // 2. Last-name-only match
        if let byLast = candidates.first(where: {
            let last = $0.displayName.split(separator: " ").last.map(String.init) ?? ""
            return normalise(last) == normalised
        }) {
            return .confident(byLast)
        }

        // 3. Stored nickname match
        for entry in nicknames {
            guard let player = candidates.first(where: { $0.id == entry.id }) else { continue }
            if entry.nicknames.map({ normalise($0) }).contains(normalised) {
                return .confident(player)
            }
        }

        // 4. Jaro-Winkler similarity ≥ 0.82 → suggested
        var best: (player: MatchupPlayer, score: Double)?
        for candidate in candidates {
            let sim = jaroWinkler(normalised, normalise(candidate.displayName))
            if sim > (best?.score ?? 0) { best = (candidate, sim) }

            // Also try last name only
            if let last = candidate.displayName.split(separator: " ").last.map(String.init) {
                let simLast = jaroWinkler(normalised, normalise(last))
                if simLast > (best?.score ?? 0) { best = (candidate, simLast) }
            }
        }

        if let b = best, b.score >= 0.82 {
            return .suggested(ocrName: ocrName, player: b.player, score: b.score)
        }

        return .unmatched(ocrName: ocrName)
    }

    /// Match a set of OCR names (one per row) to an ordered player list.
    /// Returns player-ordered mapping: index = player position, value = matched player (or nil).
    static func matchRows(
        ocrNames: [String],
        players: [MatchupPlayer],
        nicknames: [PlayerWithNicknames]
    ) -> [Int: MatchupPlayer] {
        var mapping = [Int: MatchupPlayer]()
        var usedPlayerIds = Set<Int>()

        for (i, name) in ocrNames.enumerated() {
            let remaining = players.filter { !usedPlayerIds.contains($0.id) }
            let result = match(ocrName: name, candidates: remaining, nicknames: nicknames)
            switch result {
            case .confident(let p):
                mapping[i] = p
                usedPlayerIds.insert(p.id)
            case .suggested(_, let p, _):
                mapping[i] = p
                usedPlayerIds.insert(p.id)
            case .unmatched:
                break
            }
        }
        return mapping
    }

    // MARK: - Helpers

    private static func normalise(_ s: String) -> String {
        s.lowercased()
         .trimmingCharacters(in: .whitespacesAndNewlines)
         .folding(options: .diacriticInsensitive, locale: .current)
    }

    /// Jaro-Winkler similarity (0.0–1.0).
    private static func jaroWinkler(_ s1: String, _ s2: String) -> Double {
        let jaro = jaroSimilarity(s1, s2)
        guard jaro > 0 else { return 0 }
        let prefix = zip(s1, s2).prefix(4).prefix(while: { $0.0 == $0.1 }).count
        return jaro + Double(prefix) * 0.1 * (1 - jaro)
    }

    private static func jaroSimilarity(_ s1: String, _ s2: String) -> Double {
        let a = Array(s1), b = Array(s2)
        guard !a.isEmpty, !b.isEmpty else { return a.isEmpty && b.isEmpty ? 1 : 0 }
        let matchDist = max(a.count, b.count) / 2 - 1
        var s1Matches = Array(repeating: false, count: a.count)
        var s2Matches = Array(repeating: false, count: b.count)
        var matches = 0
        var transpositions = 0

        for i in 0..<a.count {
            let lo = max(0, i - matchDist)
            let hi = min(i + matchDist + 1, b.count)
            for j in lo..<hi {
                guard !s2Matches[j], a[i] == b[j] else { continue }
                s1Matches[i] = true; s2Matches[j] = true; matches += 1; break
            }
        }
        guard matches > 0 else { return 0 }

        var k = 0
        for i in 0..<a.count where s1Matches[i] {
            while !s2Matches[k] { k += 1 }
            if a[i] != b[k] { transpositions += 1 }
            k += 1
        }
        let m = Double(matches)
        return (m / Double(a.count) + m / Double(b.count) + (m - Double(transpositions) / 2) / m) / 3
    }
}
