import SwiftUI

// MARK: - Name Confirmation View

/// Step 1 of the OCR score entry flow.
/// Shows the names OCR detected on the scorecard and lets the admin confirm or
/// correct which roster player each name maps to. Uses NicknameMatchService for
/// auto-matching (exact → last-name → nickname → fuzzy), with positional
/// elimination: if all but one player slot is resolved, the last is auto-assigned.
///
/// On confirm, calls onConfirm([playerId: [Int]]) with scores pre-filled from
/// the matching OCR row. Empty score arrays are omitted so ScoreInputView knows
/// to keep those players as zero-filled (user enters manually).
struct NameConfirmationView: View {
    let scannedCard: ScannedCard
    let players: [MatchupPlayer]            // all 4 players in the matchup
    let nicknames: [PlayerWithNicknames]
    let onConfirm: ([Int: [Int]]) -> Void   // playerId → hole scores
    let onDismiss: () -> Void

    // slot index (0..<players.count) → assigned player
    @State private var assignments: [Int: MatchupPlayer] = [:]
    @State private var editingSlot: Int? = nil

    private var unassignedPlayers: [MatchupPlayer] {
        let taken = Set(assignments.values.map(\.id))
        return players.filter { !taken.contains($0.id) }
    }
    private var allAssigned: Bool { assignments.count == players.count }
    private var eliminationCandidate: (slot: Int, player: MatchupPlayer)? {
        let emptySlots = (0..<players.count).filter { assignments[$0] == nil }
        guard emptySlots.count == 1, let only = unassignedPlayers.first else { return nil }
        return (emptySlots[0], only)
    }

    var body: some View {
        NavigationStack {
            List {
                infoSection
                if let elim = eliminationCandidate { eliminationBanner(elim) }
                playerSlots
            }
            .listStyle(.insetGrouped)
            .navigationTitle("Confirm Players")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("Cancel", action: onDismiss)
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Confirm") { buildAndConfirm() }
                        .fontWeight(.semibold)
                        .disabled(!allAssigned)
                }
            }
            .onAppear { runInitialMatch() }
            .sheet(item: Binding(
                get: { editingSlot.map { SlotID($0) } },
                set: { editingSlot = $0?.id }
            )) { sid in
                PlayerPickerSheet(
                    slot: sid.id,
                    players: players,
                    current: assignments[sid.id],
                    onSelect: { player in
                        assignments[sid.id] = player
                        editingSlot = nil
                    },
                    onDismiss: { editingSlot = nil }
                )
            }
        }
    }

    // MARK: - Sections

    private var infoSection: some View {
        Section {
            let found = scannedCard.names.count
            let scores = scannedCard.rows.count
            Label(
                found > 0
                    ? "OCR found \(found) name\(found == 1 ? "" : "s") and \(scores) score row\(scores == 1 ? "" : "s"). Verify each player below."
                    : "OCR couldn't detect names. Assign players manually.",
                systemImage: found > 0 ? "person.text.rectangle" : "exclamationmark.triangle"
            )
            .font(.footnote)
            .foregroundStyle(found > 0 ? Color.secondary : Color.orange)
        }
    }

    @ViewBuilder
    private func eliminationBanner(_ elim: (slot: Int, player: MatchupPlayer)) -> some View {
        Section {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Only one player unassigned")
                        .font(.footnote.bold())
                    Text("\(elim.player.displayName) is the only remaining option for slot \(elim.slot + 1).")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Button("Auto-assign") {
                    assignments[elim.slot] = elim.player
                }
                .font(.caption.bold())
                .buttonStyle(.borderedProminent)
                .controlSize(.small)
            }
        }
    }

    private var playerSlots: some View {
        Section("Player Slots") {
            ForEach(0..<players.count, id: \.self) { slot in
                SlotRow(
                    slot: slot,
                    ocrName: slot < scannedCard.names.count ? scannedCard.names[slot] : nil,
                    assigned: assignments[slot],
                    hasScores: slot < scannedCard.rows.count,
                    onTap: { editingSlot = slot }
                )
            }
        }
    }

    // MARK: - Logic

    private func runInitialMatch() {
        let matched = NicknameMatchService.matchRows(
            ocrNames: scannedCard.names,
            players: players,
            nicknames: nicknames
        )
        for (slot, player) in matched {
            assignments[slot] = player
        }
        // Apply elimination immediately if matching left one gap
        if let elim = eliminationCandidate {
            assignments[elim.slot] = elim.player
        }
    }

    private func buildAndConfirm() {
        var result = [Int: [Int]]()
        for (slot, player) in assignments {
            if slot < scannedCard.rows.count {
                result[player.id] = scannedCard.rows[slot]
            }
            // Players with no OCR row are omitted; ScoreInputView keeps their existing scores.
        }
        onConfirm(result)
    }
}

// MARK: - Slot Row

private struct SlotRow: View {
    let slot: Int
    let ocrName: String?
    let assigned: MatchupPlayer?
    let hasScores: Bool
    let onTap: () -> Void

    var body: some View {
        Button(action: onTap) {
            HStack(spacing: 12) {
                // Slot number
                Text("\(slot + 1)")
                    .font(.caption2.bold())
                    .foregroundStyle(.white)
                    .frame(width: 20, height: 20)
                    .background(assigned != nil ? Color.accentColor : Color.secondary)
                    .clipShape(Circle())

                // OCR detected name
                VStack(alignment: .leading, spacing: 1) {
                    Text("Card")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                    Text(ocrName ?? "—")
                        .font(.subheadline)
                        .foregroundStyle(ocrName != nil ? .primary : .tertiary)
                        .italic(ocrName == nil)
                }
                .frame(width: 72, alignment: .leading)

                Image(systemName: "arrow.right")
                    .font(.caption2)
                    .foregroundStyle(.secondary)

                // Assigned player
                VStack(alignment: .leading, spacing: 1) {
                    Text("Player")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                    if let p = assigned {
                        Text(p.displayName)
                            .font(.subheadline.bold())
                    } else {
                        Text("Tap to assign")
                            .font(.subheadline)
                            .foregroundStyle(.orange)
                    }
                }

                Spacer()

                // Status chips
                HStack(spacing: 4) {
                    if hasScores {
                        Image(systemName: "list.number")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                    confidenceChip
                }

                Image(systemName: "chevron.right")
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }

    @ViewBuilder
    private var confidenceChip: some View {
        if assigned != nil {
            if ocrName != nil {
                // Green check if OCR detected a name for this slot
                Image(systemName: "checkmark.circle.fill")
                    .font(.caption)
                    .foregroundStyle(.green)
            } else {
                // Orange if manually assigned (no OCR name to validate against)
                Image(systemName: "hand.point.up.fill")
                    .font(.caption)
                    .foregroundStyle(.orange)
            }
        } else {
            Image(systemName: "exclamationmark.circle.fill")
                .font(.caption)
                .foregroundStyle(.red)
        }
    }
}

// MARK: - Player Picker Sheet

private struct PlayerPickerSheet: View {
    let slot: Int
    let players: [MatchupPlayer]
    let current: MatchupPlayer?
    let onSelect: (MatchupPlayer) -> Void
    let onDismiss: () -> Void

    var body: some View {
        NavigationStack {
            List(players) { player in
                Button {
                    onSelect(player)
                } label: {
                    HStack {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(player.displayName)
                                .font(.body)
                                .foregroundStyle(.primary)
                            if let hcp = player.handicap {
                                Text("HCP \(hcp, format: .number.precision(.fractionLength(0...1)))")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        }
                        Spacer()
                        if current?.id == player.id {
                            Image(systemName: "checkmark")
                                .foregroundStyle(.accentColor)
                        }
                    }
                }
            }
            .navigationTitle("Assign Slot \(slot + 1)")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Cancel", action: onDismiss)
                }
            }
        }
        .presentationDetents([.medium])
    }
}

// MARK: - Helpers

private struct SlotID: Identifiable { let id: Int }
