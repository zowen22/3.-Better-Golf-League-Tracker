import SwiftUI

struct MainTabView: View {
    @Environment(AuthViewModel.self) private var authVM

    var isAdmin: Bool {
        authVM.currentUser?.isAdmin ?? false
    }

    var body: some View {
        TabView {
            ScheduleView()
                .tabItem { Label("Schedule", systemImage: "calendar") }

            StandingsView()
                .tabItem { Label("Standings", systemImage: "chart.bar") }

            if isAdmin {
                ScoreEntryView()
                    .tabItem { Label("Score Entry", systemImage: "flag.fill") }
            }

            StatsHubView()
                .tabItem { Label("Stats", systemImage: "trophy") }

            if isAdmin {
                AdminView()
                    .tabItem { Label("Admin", systemImage: "gearshape") }
            }
        }
    }
}
