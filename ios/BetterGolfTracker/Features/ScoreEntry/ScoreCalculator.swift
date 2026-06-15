import Foundation

/// Pure score calculation logic — mirrors Flask scores.py helpers exactly.
enum ScoreCalculator {

    enum ScoringMode: String {
        case matchPlay  = "match_play"
        case stableford = "stableford"
    }

    // MARK: Handicap

    static func playingHandicap(index: Double, percent: Double, max: Double) -> Double {
        min((index * (percent / 100)).rounded(), max)
    }

    static func strokesOnHole(playingHandicap: Double, holeHcpIndex: Int?, totalHoles: Int = 9) -> Int {
        guard let hci = holeHcpIndex else { return 0 }
        var strokes = 0
        if playingHandicap >= Double(hci)             { strokes += 1 }
        if playingHandicap >= Double(totalHoles + hci) { strokes += 1 }
        return strokes
    }

    // MARK: Match play

    static func matchPlayPoints(net1: Int, net2: Int) -> (Double, Double) {
        if net1 < net2 { return (2.0, 0.0) }
        if net2 < net1 { return (0.0, 2.0) }
        return (1.0, 1.0)
    }

    // MARK: Stableford

    static func stablefordPoints(netVsPar: Int) -> Double {
        switch netVsPar {
        case ..<(-1): return 4
        case -1:      return 3
        case 0:       return 2
        case 1:       return 1
        default:      return 0
        }
    }

    // MARK: Round result

    struct HoleData {
        let par: Int
        let hcpIndex: Int?
    }

    struct PlayerRoundResult {
        let playerId: Int
        let holePoints: Double
        let overallPoint: Double
        var totalPoints: Double { holePoints + overallPoint }
    }

    /// Calculate match results for an A-vs-A or B-vs-B pairing.
    static func pairingResult(
        netScores1: [Int], netScores2: [Int],
        pars: [Int], mode: ScoringMode
    ) -> (p1HolePts: Double, p2HolePts: Double, p1Overall: Double, p2Overall: Double) {
        guard netScores1.count == netScores2.count else { return (0, 0, 0, 0) }

        switch mode {
        case .matchPlay:
            var hp1 = 0.0, hp2 = 0.0
            for i in 0..<netScores1.count {
                let (p1, p2) = matchPlayPoints(net1: netScores1[i], net2: netScores2[i])
                hp1 += p1; hp2 += p2
            }
            let (ov1, ov2) = matchPlayPoints(net1: netScores1.reduce(0, +),
                                             net2: netScores2.reduce(0, +))
            return (hp1, hp2, ov1, ov2)

        case .stableford:
            var sb1 = 0.0, sb2 = 0.0
            for i in 0..<netScores1.count {
                sb1 += stablefordPoints(netVsPar: netScores1[i] - pars[i])
                sb2 += stablefordPoints(netVsPar: netScores2[i] - pars[i])
            }
            // Higher Stableford wins; negate to reuse matchPlayPoints (lower = better)
            let (ov1, ov2) = matchPlayPoints(net1: Int(-sb1), net2: Int(-sb2))
            return (sb1, sb2, ov1, ov2)
        }
    }
}
