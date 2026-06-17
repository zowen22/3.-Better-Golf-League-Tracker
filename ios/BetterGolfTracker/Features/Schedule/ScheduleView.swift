import SwiftUI

struct ScheduleView: View {
    @State private var viewModel = ScheduleViewModel()
    @State private var selectedWeek: Int? = nil

    private static let dateFmt: DateFormatter = {
        let f = DateFormatter(); f.dateFormat = "yyyy-MM-dd"; return f
    }()

    // Sorted unique week numbers
    var weekOptions: [Int] {
        Array(Set(viewModel.matchups.map(\.weekNumber))).sorted()
    }

    // Upcoming week = lowest week number whose scheduled_date >= today
    var upcomingWeek: Int? {
        let today = Calendar.current.startOfDay(for: Date())
        return viewModel.matchups
            .filter { m in
                guard let ds = m.scheduledDate,
                      let d = Self.dateFmt.date(from: ds)
                else { return false }
                return d >= today
            }
            .map(\.weekNumber)
            .min()
        ?? weekOptions.last  // fall back to most recent completed week
    }

    var displayedMatchups: [Matchup] {
        guard let week = selectedWeek else { return viewModel.matchups }
        return viewModel.matchups.filter { $0.weekNumber == week }
    }

    var filterLabel: String {
        guard let week = selectedWeek else { return "All Season" }
        return "Week \(week)"
    }

    var body: some View {
        NavigationStack {
            List {
                ForEach(displayedMatchups) { matchup in
                    NavigationLink(destination: MatchupDetailView(matchupId: matchup.id)) {
                        MatchupRow(matchup: matchup)
                    }
                    .listRowInsets(EdgeInsets(top: 8, leading: 16, bottom: 8, trailing: 16))
                }
            }
            .listStyle(.insetGrouped)
            .navigationTitle("Schedule")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Menu {
                        Button {
                            selectedWeek = nil
                        } label: {
                            Label("All Season", systemImage: selectedWeek == nil ? "checkmark" : "calendar")
                        }
                        Divider()
                        ForEach(weekOptions, id: \.self) { week in
                            Button {
                                selectedWeek = week
                            } label: {
                                Label("Week \(week)", systemImage: selectedWeek == week ? "checkmark" : "")
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
            .refreshable { await viewModel.load() }
            .task {
                await viewModel.load()
                if selectedWeek == nil {
                    selectedWeek = upcomingWeek
                }
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

    var body: some View {
        VStack(spacing: 10) {
            // Teams
            HStack(alignment: .center) {
                teamLabel(matchup.team1)
                Spacer()
                VStack(spacing: 2) {
                    Text("vs")
                        .font(.caption.bold())
                        .foregroundStyle(.secondary)
                    StatusBadge(status: matchup.status)
                }
                Spacer()
                teamLabel(matchup.team2)
            }

            // Meta row
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
    private func teamLabel(_ team: MatchupTeam) -> some View {
        VStack(spacing: 2) {
            ForEach(team.players) { player in
                Text(player.displayName.split(separator: " ").last.map(String.init) ?? player.displayName)
                    .font(.subheadline.bold())
            }
        }
        .frame(maxWidth: .infinity, alignment: team.teamId == team.teamId ? .leading : .trailing)
    }

    private func formattedDate(_ raw: String) -> String {
        let f = DateFormatter(); f.dateFormat = "yyyy-MM-dd"
        guard let d = f.date(from: raw) else { return raw }
        let out = DateFormatter(); out.dateFormat = "MMM d"
        return out.string(from: d)
    }
}
