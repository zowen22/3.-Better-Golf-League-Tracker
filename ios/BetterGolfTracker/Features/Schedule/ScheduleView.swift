import SwiftUI

private enum ScheduleNav: Hashable {
    case matchup(Int)
    case playerHandicap(LeaguePlayer)
}

struct ScheduleView: View {
    @State private var viewModel = ScheduleViewModel()
    @State private var selectedWeek: Int? = nil
    @State private var navPath = NavigationPath()

    private static let isoFmt: DateFormatter = {
        let f = DateFormatter(); f.dateFormat = "yyyy-MM-dd"; return f
    }()
    private static let shortFmt: DateFormatter = {
        let f = DateFormatter(); f.dateFormat = "MMM d"; return f
    }()

    // week → "Apr 22" label built from first matchup date for each week
    var weekDates: [Int: String] {
        var map = [Int: String]()
        for m in viewModel.matchups {
            guard map[m.weekNumber] == nil,
                  let ds = m.scheduledDate,
                  let d = Self.isoFmt.date(from: ds) else { continue }
            map[m.weekNumber] = Self.shortFmt.string(from: d)
        }
        return map
    }

    var weekOptions: [Int] {
        Array(Set(viewModel.matchups.map(\.weekNumber))).sorted()
    }

    var upcomingWeek: Int? {
        let today = Calendar.current.startOfDay(for: Date())
        return viewModel.matchups
            .filter { m in
                guard let ds = m.scheduledDate,
                      let d = Self.isoFmt.date(from: ds)
                else { return false }
                return d >= today
            }
            .map(\.weekNumber)
            .min()
        ?? weekOptions.last
    }

    var displayedMatchups: [Matchup] {
        guard let week = selectedWeek else { return viewModel.matchups }
        return viewModel.matchups.filter { $0.weekNumber == week }
    }

    func weekLabel(_ week: Int) -> String {
        if let date = weekDates[week] { return "Week \(week) — \(date)" }
        return "Week \(week)"
    }

    var filterLabel: String {
        guard let week = selectedWeek else { return "All Season" }
        return weekLabel(week)
    }

    var body: some View {
        NavigationStack(path: $navPath) {
            List {
                ForEach(displayedMatchups) { matchup in
                    NavigationLink(value: ScheduleNav.matchup(matchup.id)) {
                        MatchupRow(matchup: matchup) { player in
                            navPath.append(ScheduleNav.playerHandicap(player))
                        }
                    }
                    .listRowInsets(EdgeInsets(top: 8, leading: 16, bottom: 8, trailing: 16))
                }
            }
            .listStyle(.insetGrouped)
            .navigationDestination(for: ScheduleNav.self) { dest in
                switch dest {
                case .matchup(let id):
                    MatchupDetailView(matchupId: id)
                case .playerHandicap(let player):
                    HandicapDetailView(player: player)
                }
            }
            .navigationTitle("Schedule")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Menu {
                        Button { selectedWeek = nil } label: {
                            Label("All Season", systemImage: selectedWeek == nil ? "checkmark" : "calendar")
                        }
                        Divider()
                        ForEach(weekOptions, id: \.self) { week in
                            Button { selectedWeek = week } label: {
                                Label(weekLabel(week), systemImage: selectedWeek == week ? "checkmark" : "")
                            }
                        }
                    } label: {
                        HStack(spacing: 4) {
                            Text(filterLabel)
                                .font(.subheadline.bold())
                            Image(systemName: "chevron.down")
                                .font(.caption.bold())
                        }
                        .foregroundStyle(.primary)
                    }
                }
            }
            .safeAreaInset(edge: .top) {
                if viewModel.isShowingCached {
                    Label("Showing cached data — pull to refresh", systemImage: "wifi.slash")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .padding(.vertical, 6)
                        .frame(maxWidth: .infinity)
                        .background(.bar)
                }
            }
            .refreshable { await viewModel.load() }
            .task {
                await viewModel.load()
                if selectedWeek == nil { selectedWeek = upcomingWeek }
            }
            .overlay {
                if viewModel.isLoading {
                    ProgressView()
                } else if displayedMatchups.isEmpty && !viewModel.matchups.isEmpty {
                    ContentUnavailableView("No matchups this week", systemImage: "calendar")
                } else if viewModel.matchups.isEmpty {
                    ContentUnavailableView(
                        viewModel.errorMessage ?? "No schedule data",
                        systemImage: "calendar"
                    )
                }
            }
        }
    }
}

struct MatchupRow: View {
    let matchup: Matchup
    var onPlayerTap: ((LeaguePlayer) -> Void)? = nil

    var body: some View {
        VStack(spacing: 10) {
            HStack(alignment: .center) {
                teamLabel(matchup.team1, alignment: .leading)
                Spacer()
                VStack(spacing: 2) {
                    Text("vs")
                        .font(.caption.bold())
                        .foregroundStyle(.secondary)
                    StatusBadge(status: matchup.status)
                }
                Spacer()
                teamLabel(matchup.team2, alignment: .trailing)
            }

            HStack(spacing: 12) {
                if let date = matchup.scheduledDate {
                    Label(formattedDate(date), systemImage: "calendar")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                if let teeTime = matchup.teeTime {
                    Label(teeTime, systemImage: "clock")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                if let course = matchup.courseName {
                    Label(course, systemImage: "mappin")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(.vertical, 4)
    }

    @ViewBuilder
    private func teamLabel(_ team: MatchupTeam, alignment: Alignment) -> some View {
        VStack(alignment: alignment == .leading ? .leading : .trailing, spacing: 3) {
            ForEach(team.players) { player in
                Button {
                    let lp = LeaguePlayer(
                        playerId: player.id,
                        displayName: player.displayName,
                        firstName: player.displayName.components(separatedBy: " ").first ?? player.displayName,
                        lastName: player.displayName.components(separatedBy: " ").last ?? "",
                        handicapIndex: player.handicap
                    )
                    onPlayerTap?(lp)
                } label: {
                    HStack(spacing: 4) {
                        if alignment == .trailing, let hcp = player.handicap {
                            hcpBadge(hcp)
                        }
                        Text(player.displayName.split(separator: " ").last.map(String.init) ?? player.displayName)
                            .font(.subheadline.bold())
                            .foregroundStyle(.primary)
                        if alignment == .leading, let hcp = player.handicap {
                            hcpBadge(hcp)
                        }
                    }
                }
                .buttonStyle(.plain)
            }
        }
        .frame(maxWidth: .infinity, alignment: alignment)
    }

    @ViewBuilder
    private func hcpBadge(_ hcp: Double) -> some View {
        Text(hcpLabel(hcp))
            .font(.system(size: 10, weight: .semibold))
            .foregroundStyle(.secondary)
            .padding(.horizontal, 4).padding(.vertical, 1)
            .background(Color.secondary.opacity(0.12))
            .clipShape(Capsule())
    }

    private func hcpLabel(_ hcp: Double) -> String {
        hcp == hcp.rounded() ? "\(Int(hcp))" : String(format: "%.1f", hcp)
    }

    private func formattedDate(_ raw: String) -> String {
        let f = DateFormatter(); f.dateFormat = "yyyy-MM-dd"
        guard let d = f.date(from: raw) else { return raw }
        let out = DateFormatter(); out.dateFormat = "MMM d"
        return out.string(from: d)
    }
}
