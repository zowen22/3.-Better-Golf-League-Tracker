import SwiftUI

struct MainTabView: View {
    @Environment(AuthViewModel.self) private var authVM

    var body: some View {
        TabView {
            ScheduleView()
                .tabItem { Label("Schedule", systemImage: "calendar") }

            StandingsView()
                .tabItem { Label("Standings", systemImage: "chart.bar") }

            ScoreEntryPlaceholderView()
                .tabItem { Label("Score Entry", systemImage: "flag.fill") }

            if authVM.currentUser?.role == "admin" {
                AdminView()
                    .tabItem { Label("Admin", systemImage: "gearshape") }
            }
        }
    }
}
