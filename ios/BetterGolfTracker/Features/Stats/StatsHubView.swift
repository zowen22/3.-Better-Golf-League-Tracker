import SwiftUI

struct StatsHubView: View {
    var body: some View {
        NavigationStack {
            List {
                NavigationLink(destination: StatsLeadersView()) {
                    Label("Season Leaders", systemImage: "medal")
                }
                NavigationLink(destination: StatsAllPlayView()) {
                    Label("All-Play Standings", systemImage: "person.3")
                }
                NavigationLink(destination: StatsTrendView()) {
                    Label("Points Trend", systemImage: "chart.line.uptrend.xyaxis")
                }
                NavigationLink(destination: StatsWeeklyView()) {
                    Label("Weekly Scores", systemImage: "calendar.badge.clock")
                }
                NavigationLink(destination: StatsRecordsView()) {
                    Label("Season Records", systemImage: "star")
                }
            }
            .navigationTitle("Stats")
        }
    }
}
