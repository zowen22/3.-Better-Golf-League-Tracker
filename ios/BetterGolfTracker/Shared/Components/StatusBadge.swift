import SwiftUI

struct StatusBadge: View {
    let status: MatchupStatus

    var body: some View {
        Text(label)
            .font(.caption.bold())
            .foregroundStyle(color)
    }

    private var label: String {
        switch status {
        case .scheduled:   return "Upcoming"
        case .completed:   return "Completed"
        case .inProgress:  return "Unfinished"
        case .bye:         return "Bye"
        case .unknown:     return "—"
        }
    }

    private var color: Color {
        switch status {
        case .scheduled:   return .blue
        case .completed:   return .green
        case .inProgress:  return Color(red: 0.93, green: 0.53, blue: 0.06)
        case .bye:         return .secondary
        case .unknown:     return .secondary
        }
    }
}
