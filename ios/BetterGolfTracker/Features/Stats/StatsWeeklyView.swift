import SwiftUI

@Observable
final class StatsWeeklyViewModel {
    var response: StatsWeeklyResponse?
    var isLoading = false
    var errorMessage: String?

    func load() async {
        isLoading = true; errorMessage = nil
        defer { isLoading = false }
        do {
            response = try await APIClient.shared.request(.statsWeekly)
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

struct StatsWeeklyView: View {
    @State private var vm = StatsWeeklyViewModel()

    var body: some View {
        List {
            if let r = vm.response {
                if r.weeks.isEmpty {
                    Text("No completed rounds yet").foregroundStyle(.secondary)
                } else {
                    ForEach(r.weeks) { week in
                        Section("Week \(week.id)\(week.scheduledDate.map { " — \($0)" } ?? "")") {
                            ForEach(week.matchups) { matchup in
                                NavigationLink(destination: WeeklyMatchupDetailView(matchup: matchup)) {
                                    VStack(alignment: .leading, spacing: 4) {
                                        Text("\(matchup.team1Name) vs \(matchup.team2Name)")
                                            .font(.subheadline.bold())
                                        if let course = matchup.courseName {
                                            Text(course).font(.caption).foregroundStyle(.secondary)
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        .navigationTitle("Weekly Scores")
        .task { await vm.load() }
        .refreshable { await vm.load() }
        .overlay {
            if vm.isLoading { ProgressView() }
            else if vm.response == nil, let err = vm.errorMessage {
                ContentUnavailableView(err, systemImage: "exclamationmark.triangle")
            }
        }
    }
}

struct WeeklyMatchupDetailView: View {
    let matchup: WeeklyMatchup

    var body: some View {
        List {
            Section("Match") {
                LabeledContent("Teams", value: "\(matchup.team1Name) vs \(matchup.team2Name)")
                if let course = matchup.courseName { LabeledContent("Course", value: course) }
                if let tee = matchup.teeName { LabeledContent("Tee", value: tee) }
                if let date = matchup.roundDate { LabeledContent("Date", value: date) }
            }
            Section("Results") {
                ForEach(matchup.results, id: \.playerName) { result in
                    HStack {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(result.playerName).font(.subheadline.bold())
                            if let gross = result.grossScore {
                                Text("Gross: \(gross)").font(.caption).foregroundStyle(.secondary)
                            }
                        }
                        Spacer()
                        VStack(alignment: .trailing, spacing: 2) {
                            Text(String(format: "%.1f pts", result.totalPoints))
                                .font(.subheadline.bold())
                            Text(String(format: "H:%.1f  O:%.1f", result.holePoints, result.overallPoint))
                                .font(.caption).foregroundStyle(.secondary)
                        }
                    }
                }
            }
        }
        .navigationTitle("Week \(matchup.team1Name.prefix(8))…")
    }
}
