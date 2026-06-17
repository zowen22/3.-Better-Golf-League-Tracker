import SwiftUI

@Observable
final class ScoreInputViewModel {
    var courses: [CourseInfo] = []
    var isLoadingCourses = false
    var isSubmitting = false
    var errorMessage: String?
    var submitSuccess = false
    var resultRoundId: Int?

    // [playerId: [holeIndex: grossScore]]
    var scores: [Int: [Int]] = [:]

    func loadCourses() async {
        isLoadingCourses = true
        defer { isLoadingCourses = false }
        do {
            let r: CoursesResponse = try await APIClient.shared.request(.courses)
            courses = r.courses
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func submit(matchupId: Int, teeId: Int, players: [MatchupPlayer], roundDate: String) async {
        isSubmitting = true; errorMessage = nil
        defer { isSubmitting = false }

        let playerScores: [PlayerScoreInput] = players.compactMap { p in
            guard let holes = scores[p.id], holes.count == 9 else { return nil }
            return PlayerScoreInput(playerId: p.id, holeScores: holes)
        }
        guard playerScores.count == players.count else {
            errorMessage = "Enter scores for all players before submitting."
            return
        }

        let req = ScoreSubmitRequest(
            matchupId: matchupId, teeId: teeId, courseId: nil,
            roundDate: roundDate, scores: playerScores,
            playerTees: nil, absences: nil
        )
        do {
            let r: ScoreSubmitResponse = try await APIClient.shared.request(.submitScores(req))
            resultRoundId = r.roundId
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
    @State private var vm = ScoreInputViewModel()
    @State private var selectedTee: TeeInfo?
    @State private var roundDate: Date = Date()
    @State private var showingCamera = false
    @State private var showingLibrary = false
    @State private var isOCRProcessing = false
    @State private var ocrResultRows: [[Int]] = []
    @State private var showingScanResult = false
    @Environment(\.dismiss) private var dismiss

    var allPlayers: [MatchupPlayer] { matchup.team1.players + matchup.team2.players }

    var body: some View {
        Form {
            // OCR scan option (shown once a tee is selected)
            if let tee = selectedTee, !tee.holes.isEmpty {
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
                let pars = tee.holes.map(\.par)
                ForEach(Array(allPlayers.enumerated()), id: \.element.id) { _, player in
                    Section {
                        HoleScoreInputRow(
                            pars: pars,
                            scores: Binding(
                                get: { vm.scores[player.id] ?? Array(repeating: 0, count: 9) },
                                set: { vm.scores[player.id] = $0 }
                            )
                        )
                    } header: {
                        HStack {
                            Text(player.displayName)
                            if let hcp = player.handicap {
                                Text("(HCP \(hcp, format: .number))")
                                    .foregroundStyle(.secondary)
                            }
                        }
                    }
                }

                // Submit
                Section {
                    if vm.isSubmitting {
                        HStack { Spacer(); ProgressView(); Spacer() }
                    } else {
                        Button("Submit Scores") {
                            Task {
                                let fmt = DateFormatter()
                                fmt.dateFormat = "yyyy-MM-dd"
                                await vm.submit(
                                    matchupId: matchup.id,
                                    teeId: tee.id,
                                    players: allPlayers,
                                    roundDate: fmt.string(from: roundDate)
                                )
                            }
                        }
                        .frame(maxWidth: .infinity, alignment: .center)
                        .font(.headline)
                        .foregroundStyle(.white)
                        .listRowBackground(Color.accentColor)
                    }
                }
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
        .navigationTitle("Enter Scores — Wk \(matchup.weekNumber)")
        .navigationBarTitleDisplayMode(.inline)
        .task { await vm.loadCourses() }
        .alert("Scores Submitted!", isPresented: $vm.submitSuccess) {
            Button("Done") { dismiss() }
        } message: {
            if let rid = vm.resultRoundId {
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
        .sheet(isPresented: $showingScanResult) {
            if let tee = selectedTee {
                ScanResultView(
                    players: allPlayers,
                    pars: tee.holes.map(\.par),
                    parsedRows: ocrResultRows,
                    onConfirm: { scores in
                        vm.scores = scores
                        showingScanResult = false
                    },
                    onDismiss: { showingScanResult = false }
                )
            }
        }
        .onAppear {
            for player in allPlayers where vm.scores[player.id] == nil {
                vm.scores[player.id] = Array(repeating: 4, count: 9)
            }
        }
    }

    private func handlePickedImage(_ image: UIImage) {
        isOCRProcessing = true
        Task {
            ocrResultRows = await ScorecardOCR.extractScores(from: image)
            isOCRProcessing = false
            showingScanResult = true
        }
    }
}

struct HoleScoreInputRow: View {
    let pars: [Int]
    @Binding var scores: [Int]

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            VStack(spacing: 6) {
                // Header: hole numbers
                HStack(spacing: 0) {
                    Text("Hole").font(.caption2).foregroundStyle(.secondary).frame(width: 40)
                    ForEach(0..<min(9, pars.count), id: \.self) { i in
                        Text("\(i + 1)").font(.caption2.bold()).foregroundStyle(.secondary)
                            .frame(width: 36)
                    }
                }
                // Par row
                HStack(spacing: 0) {
                    Text("Par").font(.caption2).foregroundStyle(.secondary).frame(width: 40)
                    ForEach(pars.prefix(9), id: \.self) { p in
                        Text("\(p)").font(.caption2).foregroundStyle(.secondary).frame(width: 36)
                    }
                }
                Divider()
                // Score steppers
                HStack(spacing: 0) {
                    Text("Score").font(.caption2).foregroundStyle(.secondary).frame(width: 40)
                    ForEach(0..<min(9, pars.count), id: \.self) { i in
                        VStack(spacing: 2) {
                            Button {
                                if scores.count > i { scores[i] += 1 }
                            } label: {
                                Image(systemName: "plus.circle")
                                    .font(.caption)
                            }
                            .buttonStyle(.borderless)

                            Text("\(scores.count > i ? scores[i] : 0)")
                                .font(.caption.bold())
                                .foregroundStyle(scoreColor(score: scores.count > i ? scores[i] : 0, par: pars[i]))
                                .frame(width: 28)

                            Button {
                                if scores.count > i, scores[i] > 1 { scores[i] -= 1 }
                            } label: {
                                Image(systemName: "minus.circle")
                                    .font(.caption)
                            }
                            .buttonStyle(.borderless)
                        }
                        .frame(width: 36)
                    }
                }
            }
            .padding(.vertical, 4)
        }
    }

    private func scoreColor(score: Int, par: Int) -> Color {
        let diff = score - par
        if diff <= -2 { return .yellow }
        if diff == -1 { return .green }
        if diff == 0  { return .primary }
        if diff == 1  { return .orange }
        return .red
    }
}
