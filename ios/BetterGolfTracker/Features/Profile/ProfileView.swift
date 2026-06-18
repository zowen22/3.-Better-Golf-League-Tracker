import SwiftUI
import Charts

struct ProfileView: View {
    @Environment(AuthViewModel.self) private var authVM
    @AppStorage("selectedSeasonId") private var selectedSeasonId: Int = 0
    @State private var seasons: [SeasonInfo] = []
    @State private var showLogoutConfirm = false

    private var user: CurrentUser? { authVM.currentUser }

    var body: some View {
        NavigationStack {
            List {
                // ── Handicap card (players only) ──────────────────────
                if let playerId = user?.playerId {
                    handicapSection(playerId: playerId)
                }

                // ── Identity ──────────────────────────────────────────
                Section("Account") {
                    if let name = user?.displayName, !name.isEmpty {
                        LabeledContent("Name", value: name)
                    }
                    if let email = user?.email, !email.isEmpty {
                        LabeledContent("Email", value: email)
                    }
                    LabeledContent("Role", value: roleLabel)
                }

                // ── League ────────────────────────────────────────────
                Section("League") {
                    if let leagueName = user?.leagueName, !leagueName.isEmpty {
                        LabeledContent("League", value: leagueName)
                    }
                    if let seasonName = user?.seasonName {
                        LabeledContent("Current Season", value: seasonName)
                    }
                }

                // ── Season selector ───────────────────────────────────
                if seasons.count > 1 {
                    Section {
                        Picker("Browse Season", selection: $selectedSeasonId) {
                            ForEach(seasons) { s in
                                Text(s.seasonName).tag(s.seasonId)
                            }
                        }
                    } header: {
                        Text("Season")
                    } footer: {
                        Text("Affects Standings and Stats history views.")
                            .font(.caption)
                    }
                }

                // ── Sign out ──────────────────────────────────────────
                Section {
                    Button(role: .destructive) {
                        showLogoutConfirm = true
                    } label: {
                        Label("Sign Out", systemImage: "rectangle.portrait.and.arrow.right")
                    }
                }
            }
            .listStyle(.insetGrouped)
            .navigationTitle("Profile")
            .task {
                await authVM.loadProfile()
                await loadSeasons()
            }
            .refreshable {
                await authVM.loadProfile()
                await loadSeasons()
            }
            .confirmationDialog(
                "Sign out of BetterGolfTracker?",
                isPresented: $showLogoutConfirm,
                titleVisibility: .visible
            ) {
                Button("Sign Out", role: .destructive) { authVM.logout() }
                Button("Cancel", role: .cancel) {}
            }
        }
    }

    // MARK: Handicap section

    @ViewBuilder
    private func handicapSection(playerId: Int) -> some View {
        Section {
            VStack(alignment: .leading, spacing: 12) {
                // Index + label
                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    if let hcp = user?.handicapIndex {
                        Text(String(format: "%.1f", hcp))
                            .font(.system(size: 42, weight: .black))
                            .foregroundStyle(.primary)
                        Text("HCP Index")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                            .padding(.bottom, 4)
                    } else {
                        Text("N/A")
                            .font(.system(size: 42, weight: .black))
                            .foregroundStyle(.secondary)
                        Text("No index yet")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                            .padding(.bottom, 4)
                    }
                    Spacer()
                }

                // Trend sparkline
                if let history = user?.hcpHistory, history.count > 1 {
                    Chart {
                        ForEach(Array(history.enumerated()), id: \.offset) { i, entry in
                            LineMark(
                                x: .value("Calc", i),
                                y: .value("HCP", entry.index)
                            )
                            .foregroundStyle(Color.green)
                            if i == history.count - 1 {
                                PointMark(
                                    x: .value("Calc", i),
                                    y: .value("HCP", entry.index)
                                )
                                .foregroundStyle(Color.green)
                                .symbolSize(40)
                            }
                        }
                    }
                    .frame(height: 60)
                    .chartXAxis(.hidden)
                    .chartYAxis(.hidden)
                    .chartPlotStyle { plot in
                        plot.background(Color.green.opacity(0.05))
                            .cornerRadius(8)
                    }

                    // Direction hint
                    if history.count >= 2 {
                        let delta = history.last!.index - history[history.count - 2].index
                        HStack(spacing: 4) {
                            Image(systemName: delta < 0 ? "arrow.down.right" : delta > 0 ? "arrow.up.right" : "arrow.right")
                                .font(.caption2)
                                .foregroundStyle(delta < 0 ? .green : delta > 0 ? .red : .secondary)
                            Text(delta == 0 ? "No change" : String(format: "%+.1f last recalc", delta))
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }
                } else if let history = user?.hcpHistory, history.count == 1 {
                    Text("First calculation recorded")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            .padding(.vertical, 4)

            // Link to full breakdown
            NavigationLink {
                // Build a LeaguePlayer stub so HandicapDetailView can load
                if let pid = user?.playerId, let name = user?.displayName {
                    HandicapDetailView(player: LeaguePlayer(
                        playerId: pid,
                        displayName: name,
                        firstName: name.components(separatedBy: " ").first ?? name,
                        lastName: name.components(separatedBy: " ").last ?? "",
                        handicapIndex: user?.handicapIndex
                    ))
                }
            } label: {
                Label("View Full Breakdown", systemImage: "function")
                    .font(.subheadline)
            }
        } header: {
            Text("My Handicap")
        }
    }

    // MARK: Helpers

    private var roleLabel: String {
        switch user?.role {
        case "admin", "league_admin": return "Admin"
        case "player": return "Player"
        default: return user?.role.capitalized ?? "—"
        }
    }

    private func loadSeasons() async {
        do {
            let r: SeasonsListResponse = try await APIClient.shared.request(.seasonsList)
            seasons = r.seasons
            // Default to current if not yet set
            if selectedSeasonId == 0, let current = r.currentSeasonId {
                selectedSeasonId = current
            }
        } catch {
            // Non-fatal
        }
    }
}
