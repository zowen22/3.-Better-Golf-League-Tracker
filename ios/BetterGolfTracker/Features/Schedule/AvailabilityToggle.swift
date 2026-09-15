import SwiftUI

@Observable
final class AvailabilityViewModel {
    var byWeek: [Int: AvailabilityEntry] = [:]
    var isLoading = false

    func load(seasonId: Int) async {
        isLoading = true
        defer { isLoading = false }
        do {
            let r: AvailabilityListResponse = try await APIClient.shared.request(.availability(seasonId: seasonId))
            byWeek = Dictionary(uniqueKeysWithValues: r.availability.map { ($0.weekNumber, $0) })
        } catch {
            // Non-fatal — toggle just starts unset
        }
    }

    func setAvailable(seasonId: Int, weekNumber: Int, available: Bool) async {
        let existingNote = byWeek[weekNumber]?.note ?? ""
        // Optimistic update
        byWeek[weekNumber] = AvailabilityEntry(weekNumber: weekNumber, available: available, note: existingNote)
        do {
            let r: AvailabilityUpsertResponse = try await APIClient.shared.request(
                .availabilityUpsert(seasonId: seasonId, weekNumber: weekNumber, available: available, note: existingNote)
            )
            byWeek[weekNumber] = AvailabilityEntry(weekNumber: r.weekNumber, available: r.available, note: r.note)
        } catch {
            // Non-fatal — leave optimistic value; next load() will reconcile
        }
    }
}

/// Small inline Yes/No RSVP control for a schedule week header. The API only
/// models a boolean `available` flag (no tri-state "maybe"), so this is a
/// two-segment toggle rather than three options.
struct AvailabilityToggle: View {
    let entry: AvailabilityEntry?
    let onSet: (Bool) -> Void

    var body: some View {
        HStack(spacing: 4) {
            toggleButton(label: "Yes", isSelected: entry?.available == true, color: .green) {
                onSet(true)
            }
            toggleButton(label: "No", isSelected: entry?.available == false, color: .red) {
                onSet(false)
            }
        }
    }

    @ViewBuilder
    private func toggleButton(label: String, isSelected: Bool, color: Color, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(label)
                .font(.system(size: 10, weight: .semibold))
                .padding(.horizontal, 6).padding(.vertical, 2)
                .background(isSelected ? color.opacity(0.2) : Color.secondary.opacity(0.08))
                .foregroundStyle(isSelected ? color : .secondary)
                .clipShape(Capsule())
        }
        .buttonStyle(.plain)
    }
}
