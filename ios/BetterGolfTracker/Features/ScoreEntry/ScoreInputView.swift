import SwiftUI

@Observable
final class ScoreInputViewModel {
    var courses: [CourseInfo] = []
    var leaguePlayers: [MatchupPlayer] = []
    var isLoadingCourses = false
    var isSubmitting = false
    var errorMessage: String?
    var submitSuccess = false
    var resultRoundId: Int?

    var scores: [Int: [Int]] = [:]

    func loadCourses() async {
        isLoadingCourses = true
        defer { isLoadingCourses = false }
        do {
            async let coursesReq: CoursesResponse = APIClient.shared.request(.courses)
            async let nicknamesReq: PlayerNicknamesResponse = APIClient.shared.request(.playerNicknames)
            let (c, n) = try await (coursesReq, nicknamesReq)
            courses = c.courses
            leaguePlayers = n.players.map {
                MatchupPlayer(id: $0.id, displayName: $0.displayName, handicap: nil)
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func teeMatching(teeId: Int) -> TeeInfo? {
        for course in courses {
            if let tee = course.tees.first(where: { $0.id == teeId }) { return tee }
        }
        return nil
    }

    func submit(matchupId: Int, teeId: Int, activePlayers: [MatchupPlayer],
                absences: [AbsenceInput], roundDate: String, isSelfReport: Bool) async {
        isSubmitting = true; errorMessage = nil
        defer { isSubmitting = false }

        let absentIds = Set(absences.map(\.playerId))
        let scoringPlayers = activePlayers.filter { !absentIds.contains($0.id) }

        let playerScores: [PlayerScoreInput] = scoringPlayers.compactMap { p in
            guard let holes = scores[p.id], holes.count == 9 else { return nil }
            return PlayerScoreInput(playerId: p.id, holeScores: holes)
        }
        guard playerScores.count == scoringPlayers.count else {
            errorMessage = "Enter scores for all present players before submitting."
            return
        }

        let req = ScoreSubmitRequest(
            matchupId: matchupId, teeId: teeId, courseId: nil,
            roundDate: roundDate, scores: playerScores,
            playerTees: nil, absences: absences.isEmpty ? nil : absences
        )
        do {
            if isSelfReport {
                let _: SelfReportResponse = try await APIClient.shared.request(.submitSelfReport(req))
                resultRoundId = nil
            } else {
                let r: ScoreSubmitResponse = try await APIClient.shared.request(.submitScores(req))
                resultRoundId = r.roundId
            }
            submitSuccess = true
        } catch APIError.conflict {
            errorMessage = "Scores for this matchup have already been recorded."
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

struct ScoreInputView: View {
    let matchup: Matchup
    var openCameraOnAppear: Bool = false
    var isSelfReport: Bool = false

    @State private var vm = ScoreInputViewModel()
    @State private var selectedTee: TeeInfo?
    @State private var roundDate: Date = Date()
    @State private var showingCamera = false
    @State private var showingLibrary = false
    @State private var isOCRProcessing = false
    @State private var scannedCard: ScannedCard? = nil
    @State private var showingNameConfirmation = false
    @State private var showingAbsences = false
    @State private var absences: [AbsenceInput] = []
    @Environment(\.dismiss) private var dismiss

    var allPlayers: [MatchupPlayer] { matchup.team1.players + matchup.team2.players }
    var absentIds: Set<Int> { Set(absences.map(\.playerId)) }

    var navTitle: String {
        isSelfReport ? "Self-Report — Wk \(matchup.weekNumber)" : "Enter Scores — Wk \(matchup.weekNumber)"
    }

    var body: some View {
        Form {
            // OCR scan option (shown once a tee is selected)
            if let tee = selectedTee, !tee.holes.isEmpty, !isSelfReport {
                Section {
                    if isOCRProcessing {
                        HStack { Spacer(); ProgressView("Reading scorecard…"); Spacer() }
                    } else {
                        Menu {
                            Button { showingCamera = true } label: {
                                Label("Take Photo", systemImage: "camera")
                            }
                            Button { showingLibrary = true } label: {
                                Label("Choose from Library", systemImage: "photo.on.rectangle")
                            }
                        } label: {
                            Label("Scan Scorecard (OCR)", systemImage: "doc.viewfinder")
                                .frame(maxWidth: .infinity, alignment: .center)
                                .font(.subheadline.bold())
                        }
                    }
                } footer: {
                    Text("OCR auto-fills scores from a photo. Review and correct before submitting.")
                        .font(.caption2)
                }
            }

            // Tee picker
            Section("Course & Tee") {
                if vm.isLoadingCourses {
                    ProgressView("Loading courses…")
                } else if vm.courses.isEmpty {
                    Text("No course data available.").foregroundStyle(.secondary)
                } else {
                    Picker("Tee", selection: $selectedTee) {
                        Text("Select a tee").tag(Optional<TeeInfo>.none)
                        ForEach(vm.courses) { course in
                            ForEach(course.tees) { tee in
                                Text("\(course.courseName) — \(tee.label)")
                                    .tag(Optional(tee))
                            }
                        }
                    }
                    .pickerStyle(.navigationLink)
                }
                DatePicker("Round Date", selection: $roundDate, displayedComponents: .date)
            }

            // Player score sections
            if let tee = selectedTee {
                playerScoreSections(tee: tee)
                submitSection(tee: tee)
            } else {
                Section {
                    Text("Select a tee to begin entering scores.")
                        .foregroundStyle(.secondary)
                        .font(.footnote)
                }
            }

            if let err = vm.errorMessage {
                Section {
                    Label(err, systemImage: "exclamationmark.triangle")
                        .foregroundStyle(.red)
                        .font(.footnote)
                }
            }
        }
        .navigationTitle(navTitle)
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button {
                    showingAbsences = true
                } label: {
                    Label(absences.isEmpty ? "Absences" : "Absences (\(absences.count))",
                          systemImage: "person.fill.xmark")
                        .foregroundStyle(absences.isEmpty ? AnyShapeStyle(.primary) : AnyShapeStyle(Color.orange))
                }
            }
        }
        .sheet(isPresented: $showingAbsences) {
            AbsenceSheet(
                players: allPlayers,
                leaguePlayers: vm.leaguePlayers,
                absences: $absences
            )
        }
        .task {
            await vm.loadCourses()
            // Auto-select tee from matchup default
            if selectedTee == nil, let teeId = matchup.teeId {
                selectedTee = vm.teeMatching(teeId: teeId)
            }
            if openCameraOnAppear { showingCamera = true }
        }
        .alert(isSelfReport ? "Scores Submitted for Review" : "Scores Submitted!",
               isPresented: $vm.submitSuccess) {
            Button("Done") { dismiss() }
        } message: {
            if isSelfReport {
                Text("Your submission is pending admin approval.")
            } else if let rid = vm.resultRoundId {
                Text("Round #\(rid) has been recorded.")
            } else {
                Text("Scores saved successfully.")
            }
        }
        .sheet(isPresented: $showingCamera) {
            ImagePicker(source: .camera, onPick: handlePickedImage)
        }
        .sheet(isPresented: $showingLibrary) {
            ImagePicker(source: .photoLibrary, onPick: handlePickedImage)
        }
        .sheet(isPresented: $showingNameConfirmation) {
            if let card = scannedCard {
                NameConfirmationView(
                    scannedCard: card,
                    players: allPlayers,
                    nicknames: vm.leaguePlayers.map { p in
                        // Map from MatchupPlayer back to PlayerWithNicknames using league data.
                        // NicknameMatchService needs the nicknames list; leaguePlayers already
                        // has display names loaded from /players/nicknames endpoint.
                        PlayerWithNicknames(
                            id: p.id,
                            displayName: p.displayName,
                            firstName: p.displayName.components(separatedBy: " ").first ?? p.displayName,
                            lastName: p.displayName.components(separatedBy: " ").dropFirst().joined(separator: " "),
                            nicknames: []
                        )
                    },
                    onConfirm: { playerScores in
                        // Merge OCR scores into vm.scores; undetected players keep existing scores.
                        for (playerId, holes) in playerScores where holes.count == 9 {
                            vm.scores[playerId] = holes
                        }
                        showingNameConfirmation = false
                    },
                    onDismiss: { showingNameConfirmation = false }
                )
            }
        }
        .onAppear {
            for player in allPlayers where vm.scores[player.id] == nil {
                vm.scores[player.id] = Array(repeating: 4, count: 9)
            }
        }
    }

    @ViewBuilder
    private func playerScoreSections(tee: TeeInfo) -> some View {
        let pars = tee.holes.map(\.par)
        ForEach(allPlayers) { player in
            let isAbsent = absentIds.contains(player.id)
            Section {
                if isAbsent {
                    Label("Marked absent — no scores needed", systemImage: "person.fill.xmark")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                } else {
                    HoleScoreInputRow(
                        pars: pars,
                        scores: Binding(
                            get: { vm.scores[player.id] ?? Array(repeating: 0, count: 9) },
                            set: { vm.scores[player.id] = $0 }
                        )
                    )
                }
            } header: {
                HStack {
                    Text(player.displayName)
                        .foregroundStyle(isAbsent ? .secondary : .primary)
                    if isAbsent {
                        Text("ABSENT").font(.caption2.bold()).foregroundStyle(.orange)
                    } else if let hcp = player.handicap {
                        Text("(HCP \(hcp, format: .number))").foregroundStyle(.secondary)
                    }
                }
            }
        }
    }

    @ViewBuilder
    private func submitSection(tee: TeeInfo) -> some View {
        Section {
            if vm.isSubmitting {
                HStack { Spacer(); ProgressView(); Spacer() }
            } else {
                Button(isSelfReport ? "Submit for Review" : "Submit Scores") {
                    Task {
                        let fmt = DateFormatter()
                        fmt.dateFormat = "yyyy-MM-dd"
                        await vm.submit(
                            matchupId: matchup.id,
                            teeId: tee.id,
                            activePlayers: allPlayers,
                            absences: absences,
                            roundDate: fmt.string(from: roundDate),
                            isSelfReport: isSelfReport
                        )
                    }
                }
                .frame(maxWidth: .infinity, alignment: .center)
                .font(.headline)
                .foregroundStyle(.white)
                .listRowBackground(isSelfReport ? Color.orange : Color.accentColor)
            }
        } footer: {
            if isSelfReport {
                Text("Your scores will be reviewed and confirmed by the league admin before being recorded.")
                    .font(.caption2)
            }
        }
    }

    private func handlePickedImage(_ image: UIImage) {
        isOCRProcessing = true
        Task {
            let card = await ScorecardOCR.scan(from: image)
            scannedCard = card
            isOCRProcessing = false
            showingNameConfirmation = true
        }
    }
}

struct HoleScoreInputRow: View {
    let pars: [Int]
    @Binding var scores: [Int]

    @FocusState private var focusedHole: Int?
    @State private var texts: [String] = []
    @State private var advanceTask: Task<Void, Never>?

    private var holeCount: Int { min(9, pars.count) }

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            VStack(spacing: 6) {
                // Header row
                HStack(spacing: 0) {
                    Text("Hole").font(.caption2).foregroundStyle(.secondary).frame(width: 44)
                    ForEach(0..<holeCount, id: \.self) { i in
                        Text("\(i + 1)").font(.caption2.bold()).foregroundStyle(.secondary).frame(width: 40)
                    }
                }
                // Par row
                HStack(spacing: 0) {
                    Text("Par").font(.caption2).foregroundStyle(.secondary).frame(width: 44)
                    ForEach(0..<holeCount, id: \.self) { i in
                        Text("\(i < pars.count ? pars[i] : 0)")
                            .font(.caption2).foregroundStyle(.secondary).frame(width: 40)
                    }
                }
                Divider()
                // Score input row
                HStack(spacing: 0) {
                    Text("Score").font(.caption2).foregroundStyle(.secondary).frame(width: 44)
                    ForEach(0..<holeCount, id: \.self) { i in
                        scoreCell(hole: i)
                    }
                }
            }
            .padding(.vertical, 8)
        }
        .onAppear { populateTexts() }
        .onChange(of: scores) { _, _ in
            // Re-sync when OCR fills scores externally (not while user is editing)
            if focusedHole == nil { populateTexts() }
        }
    }

    @ViewBuilder
    private func scoreCell(hole: Int) -> some View {
        let par  = hole < pars.count   ? pars[hole]   : 4
        let val  = hole < scores.count ? scores[hole] : 0
        let isFocused = focusedHole == hole

        TextField("—", text: cellBinding(hole: hole))
            .keyboardType(.numberPad)
            .multilineTextAlignment(.center)
            .frame(width: 40, height: 36)
            .font(.body.bold())
            .foregroundStyle(val > 0 ? scoreColor(val, par: par) : .secondary)
            .background(
                RoundedRectangle(cornerRadius: 5)
                    .fill(isFocused ? Color.accentColor.opacity(0.12) : Color.secondary.opacity(0.08))
            )
            .focused($focusedHole, equals: hole)
    }

    private func cellBinding(hole: Int) -> Binding<String> {
        Binding(
            get: { hole < texts.count ? texts[hole] : "" },
            set: { raw in
                guard hole < texts.count else { return }
                // Keep only digits, cap at 2 chars
                let digits = String(raw.filter(\.isNumber).prefix(2))
                texts[hole] = digits
                if let v = Int(digits), v > 0, hole < scores.count {
                    scores[hole] = v
                }
                // Single-digit auto-advance with 0.3 s window for a second digit
                advanceTask?.cancel()
                if digits.count == 1 {
                    advanceTask = Task {
                        try? await Task.sleep(nanoseconds: 300_000_000)
                        guard !Task.isCancelled else { return }
                        await MainActor.run {
                            focusedHole = hole + 1 < holeCount ? hole + 1 : nil
                        }
                    }
                }
            }
        )
    }

    private func populateTexts() {
        texts = (0..<holeCount).map { i in
            let v = i < scores.count ? scores[i] : 0
            return v > 0 ? "\(v)" : ""
        }
    }

    private func scoreColor(_ score: Int, par: Int) -> Color {
        let diff = score - par
        if diff <= -2 { return .yellow }
        if diff == -1 { return .green }
        if diff == 0  { return .primary }
        if diff == 1  { return .orange }
        return .red
    }
}
