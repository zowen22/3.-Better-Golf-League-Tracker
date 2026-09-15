import SwiftUI

// Mirrors CONTEST_TYPES / TEAM_CONTEST_TYPES in app/routes/contests.py.
enum ContestTypeOption: String, CaseIterable, Identifiable {
    case longDrive     = "long_drive"
    case closestToPin  = "closest_to_pin"
    case lowGross      = "low_gross"
    case lowNet        = "low_net"
    case mostBirdies   = "most_birdies"
    case teamLowNet    = "team_low_net"
    case custom        = "custom"

    var id: String { rawValue }

    var label: String {
        switch self {
        case .longDrive:    return "Long Drive"
        case .closestToPin: return "Closest to Pin"
        case .lowGross:     return "Low Gross"
        case .lowNet:       return "Low Net"
        case .mostBirdies:  return "Most Birdies"
        case .teamLowNet:   return "Team Low Net"
        case .custom:       return "Custom"
        }
    }

    var isTeamAutoCalculated: Bool { self == .teamLowNet }
}

@Observable
final class AdminContestsViewModel {
    var contests: [AdminContest] = []
    var isLoading = false
    var errorMessage: String?
    var isSaving = false

    func load(seasonId: Int) async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            let r: AdminContestsListResponse = try await APIClient.shared.request(.adminContests(seasonId: seasonId))
            contests = r.contests
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    @discardableResult
    func create(seasonId: Int, contestType: String, weekNum: Int?, description: String?, isRecurring: Bool) async -> Bool {
        isSaving = true; errorMessage = nil
        defer { isSaving = false }
        do {
            let _: AdminContestCreateResponse = try await APIClient.shared.request(
                .createAdminContest(seasonId: seasonId, contestType: contestType, weekNum: weekNum,
                                     description: description, isRecurring: isRecurring)
            )
            await load(seasonId: seasonId)
            return true
        } catch {
            errorMessage = error.localizedDescription
            return false
        }
    }

    @discardableResult
    func update(contestId: Int, seasonId: Int, contestType: String, weekNum: Int?, description: String?, isRecurring: Bool) async -> Bool {
        isSaving = true; errorMessage = nil
        defer { isSaving = false }
        do {
            let _: OkResponse = try await APIClient.shared.request(
                .updateAdminContest(contestId: contestId, contestType: contestType, weekNum: weekNum,
                                     description: description, isRecurring: isRecurring)
            )
            await load(seasonId: seasonId)
            return true
        } catch {
            errorMessage = error.localizedDescription
            return false
        }
    }

    func delete(contestId: Int, seasonId: Int) async {
        do {
            let _: ContestDeleteResponse = try await APIClient.shared.request(.deleteAdminContest(contestId: contestId))
            await load(seasonId: seasonId)
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    @discardableResult
    func calculate(contestId: Int, weekNum: Int?) async -> String? {
        do {
            let r: ContestCalculateResponse = try await APIClient.shared.request(.calculateAdminContest(contestId: contestId, weekNum: weekNum))
            return "Week \(r.weekNum): \(r.results) result(s) calculated."
        } catch {
            errorMessage = error.localizedDescription
            return nil
        }
    }

    @discardableResult
    func calculateAll(contestId: Int) async -> String? {
        do {
            let r: ContestCalculateAllResponse = try await APIClient.shared.request(.calculateAllAdminContest(contestId: contestId))
            return "\(r.weeksCalculated) week(s) calculated, \(r.weeksSkipped) skipped, \(r.totalResults) total results."
        } catch {
            errorMessage = error.localizedDescription
            return nil
        }
    }
}

/// Admin contests list + add/edit form + calculate actions, reached from
/// `AdminView`.
struct AdminContestsView: View {
    @State private var vm = AdminContestsViewModel()
    @Environment(AuthViewModel.self) private var authVM
    @State private var showingAddForm = false
    @State private var editingContest: AdminContest?
    @State private var actionMessage: String?

    private var seasonId: Int? { authVM.currentUser?.seasonId }

    var body: some View {
        Group {
            if vm.isLoading {
                ProgressView()
            } else if vm.contests.isEmpty {
                ContentUnavailableView(
                    vm.errorMessage ?? "No contests yet",
                    systemImage: "scope"
                )
            } else {
                List {
                    ForEach(vm.contests) { contest in
                        contestRow(contest)
                    }
                }
                .listStyle(.insetGrouped)
            }
        }
        .navigationTitle("Contests")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button { showingAddForm = true } label: {
                    Image(systemName: "plus")
                }
            }
        }
        .task { if let seasonId { await vm.load(seasonId: seasonId) } }
        .refreshable { if let seasonId { await vm.load(seasonId: seasonId) } }
        .sheet(isPresented: $showingAddForm) {
            if let seasonId {
                AdminContestFormView(seasonId: seasonId, contest: nil, viewModel: vm)
            }
        }
        .sheet(item: $editingContest) { contest in
            if let seasonId {
                AdminContestFormView(seasonId: seasonId, contest: contest, viewModel: vm)
            }
        }
        .alert("Result", isPresented: Binding(
            get: { actionMessage != nil },
            set: { if !$0 { actionMessage = nil } }
        )) {
            Button("OK") { actionMessage = nil }
        } message: {
            Text(actionMessage ?? "")
        }
    }

    @ViewBuilder
    private func contestRow(_ contest: AdminContest) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(contest.name).font(.subheadline.bold())
                Spacer()
                if contest.isRecurring {
                    Text("Recurring").font(.caption2.bold()).foregroundStyle(.blue)
                } else if let wn = contest.weekNum {
                    Text("Week \(wn)").font(.caption2.bold()).foregroundStyle(.secondary)
                }
            }
            if let desc = contest.description, !desc.isEmpty {
                Text(desc).font(.caption).foregroundStyle(.secondary)
            }
            HStack(spacing: 12) {
                Text("\(contest.resultCount ?? 0) result(s)").font(.caption2).foregroundStyle(.secondary)
                Spacer()
                Button("Edit") { editingContest = contest }
                    .font(.caption.bold())
                if let type = ContestTypeOption(rawValue: contest.contestType), type.isTeamAutoCalculated {
                    calculateMenu(contest)
                }
                Button(role: .destructive) {
                    if let seasonId { Task { await vm.delete(contestId: contest.id, seasonId: seasonId) } }
                } label: {
                    Text("Delete").font(.caption.bold())
                }
            }
        }
        .padding(.vertical, 4)
    }

    @ViewBuilder
    private func calculateMenu(_ contest: AdminContest) -> some View {
        Menu {
            if contest.isRecurring {
                Button("Calculate All Weeks") {
                    Task { actionMessage = await vm.calculateAll(contestId: contest.id) }
                }
            } else {
                Button("Calculate") {
                    Task { actionMessage = await vm.calculate(contestId: contest.id, weekNum: contest.weekNum) }
                }
            }
        } label: {
            Text("Calc").font(.caption.bold()).foregroundStyle(.green)
        }
    }
}

private struct AdminContestFormView: View {
    let seasonId: Int
    let contest: AdminContest?
    var viewModel: AdminContestsViewModel
    @Environment(\.dismiss) private var dismiss

    @State private var contestType: ContestTypeOption
    @State private var isRecurring: Bool
    @State private var weekNum: String
    @State private var description: String

    init(seasonId: Int, contest: AdminContest?, viewModel: AdminContestsViewModel) {
        self.seasonId = seasonId
        self.contest = contest
        self.viewModel = viewModel
        _contestType = State(initialValue: ContestTypeOption(rawValue: contest?.contestType ?? "custom") ?? .custom)
        _isRecurring = State(initialValue: contest?.isRecurring ?? false)
        _weekNum = State(initialValue: contest?.weekNum.map(String.init) ?? "")
        _description = State(initialValue: contest?.description ?? "")
    }

    var body: some View {
        NavigationStack {
            Form {
                Section("Type") {
                    Picker("Contest Type", selection: $contestType) {
                        ForEach(ContestTypeOption.allCases) { type in
                            Text(type.label).tag(type)
                        }
                    }
                }
                Section("Schedule") {
                    Toggle("Recurring (every completed week)", isOn: $isRecurring)
                    if !isRecurring {
                        TextField("Week Number", text: $weekNum)
                            .keyboardType(.numberPad)
                    }
                }
                Section("Description") {
                    TextField("Optional description", text: $description, axis: .vertical)
                        .lineLimit(2...4)
                }
                if let err = viewModel.errorMessage {
                    Section { Text(err).font(.caption).foregroundStyle(.red) }
                }
                Section {
                    if viewModel.isSaving {
                        HStack { Spacer(); ProgressView(); Spacer() }
                    } else {
                        Button(contest == nil ? "Create Contest" : "Save Changes") {
                            Task { await save() }
                        }
                        .frame(maxWidth: .infinity, alignment: .center)
                        .font(.headline)
                    }
                }
            }
            .navigationTitle(contest == nil ? "New Contest" : "Edit Contest")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
            }
        }
    }

    private func save() async {
        let wn = Int(weekNum)
        let desc = description.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? nil : description
        let success: Bool
        if let contest {
            success = await viewModel.update(contestId: contest.id, seasonId: seasonId, contestType: contestType.rawValue,
                                               weekNum: wn, description: desc, isRecurring: isRecurring)
        } else {
            success = await viewModel.create(seasonId: seasonId, contestType: contestType.rawValue,
                                               weekNum: wn, description: desc, isRecurring: isRecurring)
        }
        if success { dismiss() }
    }
}
