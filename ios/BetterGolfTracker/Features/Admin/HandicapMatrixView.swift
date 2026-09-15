import SwiftUI

@Observable
final class HandicapMatrixViewModel {
    var rounds: [HandicapMatrixRoundColumn] = []
    var matrix: [HandicapMatrixRow] = []
    var isLoading = false
    var errorMessage: String?

    var isRebuilding = false
    var rebuildPreview: HandicapRebuildSummary?
    var rebuildError: String?

    var isSavingCell = false
    var cellError: String?

    func load(seasonId: Int? = nil) async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            let r: HandicapMatrixResponse = try await APIClient.shared.request(.handicapMatrix(seasonId: seasonId))
            rounds = r.rounds
            matrix = r.matrix
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func previewRebuild() async {
        isRebuilding = true
        rebuildError = nil
        defer { isRebuilding = false }
        do {
            let r: HandicapRebuildResponse = try await APIClient.shared.request(.handicapRebuild(preview: true))
            rebuildPreview = r.summary
        } catch {
            rebuildError = error.localizedDescription
        }
    }

    @discardableResult
    func confirmRebuild(seasonId: Int?) async -> Bool {
        isRebuilding = true
        rebuildError = nil
        defer { isRebuilding = false }
        do {
            let _: HandicapRebuildResponse = try await APIClient.shared.request(.handicapRebuild(preview: false))
            rebuildPreview = nil
            await load(seasonId: seasonId)
            return true
        } catch {
            rebuildError = error.localizedDescription
            return false
        }
    }

    @discardableResult
    func overrideCell(seasonId: Int?, scorecardId: Int, matchupId: Int, hcp: Double) async -> Bool {
        guard let seasonId else {
            cellError = "No season selected."
            return false
        }
        isSavingCell = true
        cellError = nil
        defer { isSavingCell = false }
        do {
            let r: HandicapCellOverrideResponse = try await APIClient.shared.request(
                .overrideHandicapMatrixCell(seasonId: seasonId, scorecardId: scorecardId, matchupId: matchupId, hcp: hcp)
            )
            if !r.ok {
                cellError = r.recalcErrors.first ?? "Override failed."
                return false
            }
            await load(seasonId: seasonId)
            return true
        } catch {
            cellError = error.localizedDescription
            return false
        }
    }
}

/// Admin horizontally-scrolling handicap grid (player rows x round columns)
/// plus the "Rebuild Handicap Timeline" preview -> confirm flow, reached from
/// `AdminView`.
///
/// Tap-a-cell targets `scorecard_id`/`matchup_id` (now included per cell by
/// `GET /api/v1/admin/handicap/matrix`) via
/// `POST /api/v1/admin/handicap/matrix/<season_id>/cell-override` — mirrors
/// the web matrix's own `matrix_update()` mechanism, which edits
/// `scorecards.handicap_at_time_of_play` directly. This is deliberately NOT
/// the same path as `/admin/handicap/history/<handicap_id>/override` (that
/// one targets a `handicap_history` row from the separate per-player
/// Handicap History timeline, a different feature) — a matrix cell has never
/// carried a `handicap_id` to begin with, on web or mobile.
struct HandicapMatrixView: View {
    @State private var vm = HandicapMatrixViewModel()
    @Environment(AuthViewModel.self) private var authVM
    @State private var showingRebuildSheet = false
    @State private var overrideCell: (row: HandicapMatrixRow, roundIndex: Int)?

    private var seasonId: Int? { authVM.currentUser?.seasonId }

    var body: some View {
        Group {
            if vm.isLoading {
                ProgressView()
            } else if vm.matrix.isEmpty {
                ContentUnavailableView(
                    vm.errorMessage ?? "No handicap data yet",
                    systemImage: "function"
                )
            } else {
                matrixGrid
            }
        }
        .navigationTitle("Handicap Admin")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button {
                    showingRebuildSheet = true
                    Task { await vm.previewRebuild() }
                } label: {
                    Label("Rebuild", systemImage: "arrow.triangle.2.circlepath")
                }
            }
        }
        .task { await vm.load(seasonId: seasonId) }
        .refreshable { await vm.load(seasonId: seasonId) }
        .sheet(isPresented: $showingRebuildSheet) {
            HandicapRebuildSheet(viewModel: vm, seasonId: seasonId)
        }
        .sheet(item: Binding(
            get: { overrideCell.map { CellRef(row: $0.row, roundIndex: $0.roundIndex) } },
            set: { newValue in overrideCell = newValue.map { ($0.row, $0.roundIndex) } }
        )) { ref in
            HandicapCellOverrideSheet(
                row: ref.row, round: vm.rounds[ref.roundIndex], cell: ref.row.roundCells[ref.roundIndex],
                viewModel: vm, seasonId: seasonId
            )
        }
    }

    private struct CellRef: Identifiable {
        let row: HandicapMatrixRow
        let roundIndex: Int
        var id: String { "\(row.playerId)-\(roundIndex)" }
    }

    @ViewBuilder
    private var matrixGrid: some View {
        ScrollView([.horizontal, .vertical]) {
            VStack(alignment: .leading, spacing: 0) {
                headerRow
                Divider()
                ForEach(vm.matrix) { row in
                    matrixRow(row)
                    Divider()
                }
            }
        }
    }

    private var headerRow: some View {
        HStack(spacing: 0) {
            Text("Player")
                .font(.caption.bold())
                .frame(width: 130, alignment: .leading)
                .padding(.horizontal, 6)
            ForEach(vm.rounds) { round in
                Text(shortDate(round.roundDate))
                    .font(.caption2.bold())
                    .foregroundStyle(.secondary)
                    .frame(width: 54)
            }
            Text("Avg")
                .font(.caption.bold())
                .frame(width: 48)
        }
        .padding(.vertical, 6)
    }

    @ViewBuilder
    private func matrixRow(_ row: HandicapMatrixRow) -> some View {
        HStack(spacing: 0) {
            VStack(alignment: .leading, spacing: 1) {
                Text(row.name).font(.caption.bold()).lineLimit(1)
                if let current = row.currentHcp {
                    Text("Current: \(formatted(current))")
                        .font(.caption2).foregroundStyle(.secondary)
                }
            }
            .frame(width: 130, alignment: .leading)
            .padding(.horizontal, 6)

            ForEach(Array(row.roundCells.enumerated()), id: \.offset) { idx, cell in
                Button {
                    overrideCell = (row, idx)
                } label: {
                    cellView(cell)
                }
                .buttonStyle(.plain)
                .frame(width: 54)
            }

            Text(row.avg.map(formatted) ?? "—")
                .font(.caption.bold())
                .frame(width: 48)
        }
        .padding(.vertical, 4)
    }

    @ViewBuilder
    private func cellView(_ cell: HandicapMatrixCell?) -> some View {
        if let cell, let hcp = cell.hcp {
            Text(formatted(hcp))
                .font(.caption2.bold())
                .foregroundStyle(cell.overridden ? .orange : .primary)
                .padding(.horizontal, 4).padding(.vertical, 2)
                .background(cell.overridden ? Color.orange.opacity(0.15) : Color.clear)
                .clipShape(RoundedRectangle(cornerRadius: 4))
        } else {
            Text("—").font(.caption2).foregroundStyle(.secondary.opacity(0.5))
        }
    }

    private func formatted(_ v: Double) -> String {
        v == v.rounded() ? "\(Int(v))" : String(format: "%.1f", v)
    }

    private func shortDate(_ raw: String) -> String {
        let f = DateFormatter(); f.dateFormat = "yyyy-MM-dd"
        guard let d = f.date(from: raw) else { return raw }
        let out = DateFormatter(); out.dateFormat = "M/d"
        return out.string(from: d)
    }
}

private struct HandicapCellOverrideSheet: View {
    let row: HandicapMatrixRow
    let round: HandicapMatrixRoundColumn
    let cell: HandicapMatrixCell?
    var viewModel: HandicapMatrixViewModel
    let seasonId: Int?
    @Environment(\.dismiss) private var dismiss
    @State private var hcpText: String = ""
    @State private var saved = false

    private var canSave: Bool {
        cell?.scorecardId != nil && cell?.matchupId != nil && Double(hcpText) != nil
    }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    LabeledContent("Player", value: row.name)
                    LabeledContent("Round", value: round.roundDate)
                    LabeledContent("Current Value", value: cell?.hcp.map { String($0) } ?? "—")
                }
                if cell?.scorecardId == nil {
                    Section {
                        Text("No round played this week — nothing to override.")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                } else {
                    Section("New Value") {
                        TextField("Playing handicap", text: $hcpText)
                            .keyboardType(.decimalPad)
                    }
                    if let err = viewModel.cellError {
                        Section { Text(err).font(.caption).foregroundStyle(.red) }
                    }
                    Section {
                        if viewModel.isSavingCell {
                            HStack { Spacer(); ProgressView(); Spacer() }
                        } else if saved {
                            Label("Saved.", systemImage: "checkmark.circle.fill").foregroundStyle(.green)
                        } else {
                            Button("Save Override") {
                                guard let scId = cell?.scorecardId, let mId = cell?.matchupId,
                                      let hcp = Double(hcpText) else { return }
                                Task {
                                    let ok = await viewModel.overrideCell(seasonId: seasonId, scorecardId: scId, matchupId: mId, hcp: hcp)
                                    if ok { saved = true; DispatchQueue.main.asyncAfter(deadline: .now() + 0.8) { dismiss() } }
                                }
                            }
                            .disabled(!canSave)
                            .frame(maxWidth: .infinity, alignment: .center)
                            .font(.headline)
                        }
                    }
                }
            }
            .onAppear { hcpText = cell?.hcp.map { formatted($0) } ?? "" }
            .navigationTitle("Cell Override")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Close") { dismiss() }
                }
            }
        }
    }

    private func formatted(_ v: Double) -> String {
        v == v.rounded() ? "\(Int(v))" : String(format: "%.1f", v)
    }
}

private struct HandicapRebuildSheet: View {
    var viewModel: HandicapMatrixViewModel
    let seasonId: Int?
    @Environment(\.dismiss) private var dismiss
    @State private var confirmed = false

    var body: some View {
        NavigationStack {
            Form {
                if viewModel.isRebuilding && viewModel.rebuildPreview == nil {
                    Section { HStack { Spacer(); ProgressView("Computing preview…"); Spacer() } }
                } else if let summary = viewModel.rebuildPreview {
                    Section("Preview") {
                        LabeledContent("Players processed", value: "\(summary.playersProcessed)")
                        LabeledContent("Rounds processed", value: "\(summary.roundsProcessed)")
                        LabeledContent("Rounds changed", value: "\(summary.roundsChanged)")
                    }
                    if let err = viewModel.rebuildError {
                        Section { Text(err).font(.caption).foregroundStyle(.red) }
                    }
                    Section {
                        if viewModel.isRebuilding {
                            HStack { Spacer(); ProgressView(); Spacer() }
                        } else if confirmed {
                            Label("Rebuild committed.", systemImage: "checkmark.circle.fill").foregroundStyle(.green)
                        } else {
                            Button("Confirm & Rebuild") {
                                Task {
                                    let ok = await viewModel.confirmRebuild(seasonId: seasonId)
                                    if ok { confirmed = true; DispatchQueue.main.asyncAfter(deadline: .now() + 1) { dismiss() } }
                                }
                            }
                            .frame(maxWidth: .infinity, alignment: .center)
                            .font(.headline)
                            .foregroundStyle(.white)
                            .listRowBackground(Color.orange)
                        }
                    }
                } else if let err = viewModel.rebuildError {
                    Section { Text(err).font(.caption).foregroundStyle(.red) }
                }
            }
            .navigationTitle("Rebuild Handicap Timeline")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
            }
        }
    }
}
