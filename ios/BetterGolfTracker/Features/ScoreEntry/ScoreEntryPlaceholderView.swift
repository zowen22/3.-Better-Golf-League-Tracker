import SwiftUI

struct ScoreEntryView: View {
    @State private var viewModel = ScheduleViewModel()
    @State private var selectedWeek: Int? = nil
    @State private var navigateToManual = false
    @State private var navigateToCamera = false

    private static let isoFmt: DateFormatter = {
        let f = DateFormatter(); f.dateFormat = "yyyy-MM-dd"; return f
    }()
    private static let shortFmt: DateFormatter = {
        let f = DateFormatter(); f.dateFormat = "MMM d"; return f
    }()

    // ── Derived data ─────────────────────────────────────────────────────

    var pendingWeeks: [Int] {
        let weeks = viewModel.matchups
            .filter { $0.status == .scheduled || $0.status == .inProgress }
            .map(\.weekNumber)
        return Array(Set(weeks)).sorted()
    }

    var allWeeks: [Int] {
        Array(Set(viewModel.matchups.map(\.weekNumber))).sorted()
    }

    var defaultWeek: Int? {
        let today = Calendar.current.startOfDay(for: Date())
        if let w = viewModel.matchups
            .filter({ $0.status == .inProgress })
            .map(\.weekNumber).min() { return w }
        if let w = viewModel.matchups
            .filter({ m in
                guard m.status == .scheduled,
                      let ds = m.scheduledDate,
                      let d = Self.isoFmt.date(from: ds)
                else { return false }
                return d >= today
            })
            .map(\.weekNumber).min() { return w }
        return allWeeks.last
    }

    var displayedMatchups: [Matchup] {
        guard let week = selectedWeek else { return [] }
        return viewModel.matchups
            .filter { $0.weekNumber == week && $0.status != .bye }
            .sorted { $0.id < $1.id }
    }

    // Whether any matchup in the displayed week has a tee time
    var weekHasTeeTimes: Bool {
        displayedMatchups.contains { !(($0.teeTime) ?? "").isEmpty }
    }

    // Strip AM/PM
    private func stripAMPM(_ raw: String) -> String {
        raw
            .replacingOccurrences(of: " AM", with: "", options: .caseInsensitive)
            .replacingOccurrences(of: " PM", with: "", options: .caseInsensitive)
            .trimmingCharacters(in: .whitespaces)
    }

    func tagLabel(for matchup: Matchup, index: Int) -> String {
        if !weekHasTeeTimes { return "G\(index)" }
        if let tt = matchup.teeTime, !tt.isEmpty { return stripAMPM(tt) }
        return "-:--"
    }

    func tagColor(for status: MatchupStatus) -> Color {
        switch status {
        case .scheduled:  return .blue
        case .inProgress: return Color(red: 0.93, green: 0.53, blue: 0.06)
        case .completed:  return .green
        default:          return .secondary
        }
    }

    func weekLabel(_ week: Int) -> String {
        let date = viewModel.matchups
            .first(where: { $0.weekNumber == week && $0.scheduledDate != nil })
            .flatMap { Self.isoFmt.date(from: $0.scheduledDate ?? "") }
            .map { Self.shortFmt.string(from: $0) }
        if let date { return "Week \(week) — \(date)" }
        return "Week \(week)"
    }

    var filterLabel: String {
        guard let week = selectedWeek else { return "Pick Week" }
        return weekLabel(week)
    }

    // ── Body ─────────────────────────────────────────────────────────────

    var body: some View {
        NavigationStack {
            Group {
                if viewModel.isLoading {
                    ProgressView()
                } else if selectedWeek == nil || displayedMatchups.isEmpty {
                    ContentUnavailableView(
                        selectedWeek == nil ? "Select a week above" : "No matchups this week",
                        systemImage: "flag.fill",
                        description: Text(selectedWeek == nil
                            ? "Use the week picker in the top right."
                            : "All groups for this week are complete.")
                    )
                } else {
                    matchupList
                }
            }
            .navigationTitle("Score Entry")
            .toolbar {
                entryModeButtons
                weekPickerMenu
            }
            .refreshable { await viewModel.load() }
            .task {
                await viewModel.load()
                if selectedWeek == nil { selectedWeek = defaultWeek }
            }
            // Manual entry
            .navigationDestination(isPresented: $navigateToManual) {
                if let week = selectedWeek {
                    WeeklyManualEntryView(
                        weekNumber: week,
                        matchups: displayedMatchups,
                        cameraMode: false
                    )
                }
            }
            // Camera entry
            .navigationDestination(isPresented: $navigateToCamera) {
                if let week = selectedWeek {
                    WeeklyManualEntryView(
                        weekNumber: week,
                        matchups: displayedMatchups,
                        cameraMode: true
                    )
                }
            }
        }
    }

    // ── Matchup list ─────────────────────────────────────────────────────

    @ViewBuilder
    private var matchupList: some View {
        List {
            let pending   = displayedMatchups.filter { $0.status != .completed }
            let completed = displayedMatchups.filter { $0.status == .completed }

            if !pending.isEmpty {
                Section("Pending") {
                    ForEach(Array(pending.enumerated()), id: \.element.id) { idx, matchup in
                        let groupIndex = displayedMatchups.firstIndex(where: { $0.id == matchup.id }).map { $0 + 1 } ?? idx + 1
                        NavigationLink(destination: ScoreInputView(matchup: matchup)) {
                            groupRow(matchup, groupIndex: groupIndex)
                        }
                    }
                }
            }

            if !completed.isEmpty {
                Section("Completed") {
                    ForEach(Array(completed.enumerated()), id: \.element.id) { idx, matchup in
                        let groupIndex = displayedMatchups.firstIndex(where: { $0.id == matchup.id }).map { $0 + 1 } ?? idx + 1
                        NavigationLink(destination: MatchupDetailView(matchupId: matchup.id)) {
                            groupRow(matchup, groupIndex: groupIndex)
                        }
                    }
                }
            }
        }
        .listStyle(.insetGrouped)
    }

    // ── Group row ────────────────────────────────────────────────────────

    @ViewBuilder
    private func groupRow(_ m: Matchup, groupIndex: Int) -> some View {
        HStack(spacing: 12) {
            Text(tagLabel(for: m, index: groupIndex))
                .font(.caption.bold())
                .foregroundStyle(.white)
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
                .background(tagColor(for: m.status))
                .clipShape(Capsule())

            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text("\(m.team1.shortName)  vs  \(m.team2.shortName)")
                        .font(.subheadline.bold())
                    Spacer()
                    StatusBadge(status: m.status)
                }
                if let date = m.scheduledDate,
                   let d = Self.isoFmt.date(from: date) {
                    Label(Self.shortFmt.string(from: d), systemImage: "calendar")
                        .font(.caption2).foregroundStyle(.secondary)
                }
            }
        }
        .padding(.vertical, 2)
    }

    // ── Toolbar ───────────────────────────────────────────────────────────

    @ToolbarContentBuilder
    private var entryModeButtons: some ToolbarContent {
        ToolbarItem(placement: .topBarLeading) {
            HStack(spacing: 6) {
                Button {
                    guard selectedWeek != nil else { return }
                    navigateToManual = true
                } label: {
                    Label("Manual", systemImage: "keyboard")
                        .font(.caption.bold())
                        .padding(.horizontal, 8)
                        .padding(.vertical, 5)
                        .background(Color(.secondarySystemBackground))
                        .clipShape(Capsule())
                }
                .disabled(selectedWeek == nil || displayedMatchups.isEmpty)

                Button {
                    guard selectedWeek != nil else { return }
                    navigateToCamera = true
                } label: {
                    Label("Camera", systemImage: "camera.viewfinder")
                        .font(.caption.bold())
                        .padding(.horizontal, 8)
                        .padding(.vertical, 5)
                        .background(Color(.secondarySystemBackground))
                        .clipShape(Capsule())
                }
                .disabled(selectedWeek == nil || displayedMatchups.isEmpty)
            }
        }
    }

    @ToolbarContentBuilder
    private var weekPickerMenu: some ToolbarContent {
        ToolbarItem(placement: .topBarTrailing) {
            Menu {
                ForEach(allWeeks, id: \.self) { week in
                    let hasPending = pendingWeeks.contains(week)
                    Button { selectedWeek = week } label: {
                        HStack {
                            Text(weekLabel(week))
                            if selectedWeek == week {
                                Image(systemName: "checkmark")
                            } else if hasPending {
                                Image(systemName: "circle.fill").foregroundStyle(.orange)
                            }
                        }
                    }
                }
            } label: {
                HStack(spacing: 4) {
                    Text(filterLabel).font(.subheadline.bold())
                    Image(systemName: "chevron.down").font(.caption.bold())
                }
                .foregroundStyle(.primary)
            }
        }
    }
}
