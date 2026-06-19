import SwiftUI

struct WeeklyManualEntryView: View {
    let weekNumber: Int
    let matchups: [Matchup]          // all non-bye matchups for the week, sorted by id
    var cameraMode: Bool = false     // if true, ScoreInputView opens camera on appear

    private static let isoFmt: DateFormatter = {
        let f = DateFormatter(); f.dateFormat = "yyyy-MM-dd"; return f
    }()
    private static let shortFmt: DateFormatter = {
        let f = DateFormatter(); f.dateFormat = "MMM d"; return f
    }()

    // Whether any matchup in this week has a tee time
    private var weekHasTeeTimes: Bool {
        matchups.contains { t in !(t.teeTime ?? "").isEmpty }
    }

    // Strip AM/PM from a tee time string
    private func stripAMPM(_ raw: String) -> String {
        raw
            .replacingOccurrences(of: " AM", with: "", options: .caseInsensitive)
            .replacingOccurrences(of: " PM", with: "", options: .caseInsensitive)
            .trimmingCharacters(in: .whitespaces)
    }

    private func tagLabel(for matchup: Matchup, index: Int) -> String {
        if !weekHasTeeTimes { return "G\(index)" }
        if let tt = matchup.teeTime, !tt.isEmpty { return stripAMPM(tt) }
        return "-:--"
    }

    private func tagColor(for status: MatchupStatus) -> Color {
        switch status {
        case .scheduled:  return .blue
        case .inProgress: return Color(red: 0.93, green: 0.53, blue: 0.06)
        case .completed:  return .green
        default:          return .secondary
        }
    }

    private var weekDateLabel: String {
        matchups
            .compactMap { $0.scheduledDate }
            .first
            .flatMap { Self.isoFmt.date(from: $0) }
            .map { Self.shortFmt.string(from: $0) } ?? ""
    }

    var body: some View {
        List {
            let pending   = matchups.filter { $0.status != .completed }
            let completed = matchups.filter { $0.status == .completed }

            if !pending.isEmpty {
                Section("Pending") {
                    ForEach(Array(pending.enumerated()), id: \.element.id) { idx, m in
                        let groupIndex = matchups.firstIndex(where: { $0.id == m.id }).map { $0 + 1 } ?? idx + 1
                        NavigationLink(destination: ScoreInputView(matchup: m, openCameraOnAppear: cameraMode)) {
                            groupRow(m, label: tagLabel(for: m, index: groupIndex), color: tagColor(for: m.status))
                        }
                    }
                }
            }

            if !completed.isEmpty {
                Section("Completed") {
                    ForEach(Array(completed.enumerated()), id: \.element.id) { idx, m in
                        let groupIndex = matchups.firstIndex(where: { $0.id == m.id }).map { $0 + 1 } ?? idx + 1
                        NavigationLink(destination: MatchupDetailView(matchupId: m.id)) {
                            groupRow(m, label: tagLabel(for: m, index: groupIndex), color: tagColor(for: m.status))
                        }
                    }
                }
            }

            if matchups.isEmpty {
                ContentUnavailableView("No groups this week", systemImage: "flag.fill")
            }
        }
        .listStyle(.insetGrouped)
        .navigationTitle(weekDateLabel.isEmpty ? "Week \(weekNumber)" : "Week \(weekNumber) — \(weekDateLabel)")
        .navigationBarTitleDisplayMode(.inline)
    }

    @ViewBuilder
    private func groupRow(_ m: Matchup, label: String, color: Color) -> some View {
        HStack(spacing: 12) {
            Text(label)
                .font(.caption.bold())
                .foregroundStyle(.white)
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
                .background(color)
                .clipShape(Capsule())

            VStack(alignment: .leading, spacing: 3) {
                Text("\(m.team1.shortName)  vs  \(m.team2.shortName)")
                    .font(.subheadline.bold())
                StatusBadge(status: m.status)
                    .font(.caption)
            }
        }
        .padding(.vertical, 2)
    }
}
