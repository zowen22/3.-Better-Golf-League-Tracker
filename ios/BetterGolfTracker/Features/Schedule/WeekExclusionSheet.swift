import SwiftUI

// Lets `.sheet(item:)` present a specific week's exclusion editor.
extension ScheduleWeek: Identifiable {
    public var id: Int { weekNumber }
}

@Observable
final class WeekExclusionViewModel {
    var isSaving = false
    var errorMessage: String?

    @discardableResult
    func save(seasonId: Int, weekNum: Int, excludeStats: Bool, excludeHandicap: Bool,
              excludePoints: Bool, reason: String?) async -> Bool {
        isSaving = true
        errorMessage = nil
        defer { isSaving = false }
        do {
            let _: OkResponse = try await APIClient.shared.request(
                .saveWeekExclusion(seasonId: seasonId, weekNum: weekNum, excludeStats: excludeStats,
                                    excludeHandicap: excludeHandicap, excludePoints: excludePoints, reason: reason)
            )
            return true
        } catch {
            errorMessage = error.localizedDescription
            return false
        }
    }
}

/// Admin week-exclusion editor, reached from `ScheduleView`'s week-header
/// "⋯" menu — 3 checkboxes + a reason, mirroring `week_exclusions.save()`.
struct WeekExclusionSheet: View {
    let seasonId: Int
    let week: ScheduleWeek
    var viewModel: WeekExclusionViewModel
    let onSaved: () async -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var excludeStats: Bool
    @State private var excludeHandicap: Bool
    @State private var excludePoints: Bool
    @State private var reason: String

    init(seasonId: Int, week: ScheduleWeek, viewModel: WeekExclusionViewModel, onSaved: @escaping () async -> Void) {
        self.seasonId = seasonId
        self.week = week
        self.viewModel = viewModel
        self.onSaved = onSaved
        _excludeStats    = State(initialValue: week.weekExclusion?.excludeStats ?? false)
        _excludeHandicap = State(initialValue: week.weekExclusion?.excludeHandicap ?? false)
        _excludePoints   = State(initialValue: week.weekExclusion?.excludePoints ?? false)
        _reason          = State(initialValue: week.weekExclusion?.reason ?? "")
    }

    var body: some View {
        NavigationStack {
            Form {
                Section("Week \(week.weekNumber) Exclusions") {
                    Toggle("Exclude from Stats", isOn: $excludeStats)
                    Toggle("Exclude from Handicap", isOn: $excludeHandicap)
                    Toggle("Exclude from Points/Standings", isOn: $excludePoints)
                }
                Section("Reason") {
                    TextField("e.g. Rain out, makeup week", text: $reason, axis: .vertical)
                        .lineLimit(2...4)
                }
                if let err = viewModel.errorMessage {
                    Section { Text(err).font(.caption).foregroundStyle(.red) }
                }
                Section {
                    if viewModel.isSaving {
                        HStack { Spacer(); ProgressView(); Spacer() }
                    } else {
                        Button("Save") { Task { await save() } }
                            .frame(maxWidth: .infinity, alignment: .center)
                            .font(.headline)
                    }
                }
            }
            .navigationTitle("Week Exclusions")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
            }
        }
    }

    private func save() async {
        let success = await viewModel.save(
            seasonId: seasonId, weekNum: week.weekNumber,
            excludeStats: excludeStats, excludeHandicap: excludeHandicap, excludePoints: excludePoints,
            reason: reason.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? nil : reason
        )
        if success {
            await onSaved()
            dismiss()
        }
    }
}
