import SwiftUI

struct MainTabView: View {
    @Environment(AuthViewModel.self) private var authVM
    @State private var selectedTab: Int = 0

    // Tab index constants (must stay in sync with TabView order)
    private enum Tab {
        static let schedule = 0
        static let standings = 1
        static let scoreEntry = 2
        static let stats = 3
        static let admin = 4
        static let profile = 5
    }

    var isAdmin: Bool {
        authVM.currentUser?.isAdmin ?? false
    }

    var body: some View {
        TabView(selection: $selectedTab) {
            ScheduleView()
                .tabItem { Label("Schedule", systemImage: "calendar") }
                .tag(Tab.schedule)

            StandingsView()
                .tabItem { Label("Standings", systemImage: "chart.bar") }
                .tag(Tab.standings)

            if isAdmin {
                ScoreEntryView()
                    .tabItem { Label("Score Entry", systemImage: "flag.fill") }
                    .tag(Tab.scoreEntry)
            }

            StatsHubView()
                .tabItem { Label("Stats", systemImage: "trophy") }
                .tag(Tab.stats)

            if isAdmin {
                AdminView()
                    .tabItem { Label("Admin", systemImage: "gearshape") }
                    .tag(Tab.admin)
            }

            ProfileView()
                .tabItem { Label("Profile", systemImage: "person.circle") }
                .tag(Tab.profile)
        }
        .onReceive(NotificationCenter.default.publisher(for: .deepLinkAdmin)) { _ in
            selectedTab = Tab.admin
        }
        .onReceive(NotificationCenter.default.publisher(for: .deepLinkSchedule)) { _ in
            selectedTab = Tab.schedule
        }
    }
}
