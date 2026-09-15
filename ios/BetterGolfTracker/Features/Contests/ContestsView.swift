import SwiftUI

struct ContestsView: View {
    @State private var vm = ContestsViewModel()

    var body: some View {
        VStack(spacing: 0) {
            Picker("View", selection: $vm.selectedTab) {
                ForEach(ContestsViewModel.Tab.allCases) { tab in
                    Text(tab.rawValue).tag(tab)
                }
            }
            .pickerStyle(.segmented)
            .padding()

            Group {
                if vm.isLoading {
                    ProgressView()
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else if let err = vm.errorMessage {
                    ContentUnavailableView(err, systemImage: "exclamationmark.triangle")
                } else {
                    switch vm.selectedTab {
                    case .detail:   detailList
                    case .summary:  summaryList
                    case .lowScore: lowScoreList
                    case .skins:    skinsList
                    }
                }
            }
        }
        .navigationTitle("Contests")
        .navigationBarTitleDisplayMode(.inline)
        .task { await vm.load() }
        .refreshable { await vm.load() }
        .onChange(of: vm.selectedTab) { _, _ in
            Task { await vm.load() }
        }
    }

    // MARK: Detail

    @ViewBuilder
    private var detailList: some View {
        if vm.detailWinners.isEmpty {
            ContentUnavailableView("No contest results yet", systemImage: "trophy")
        } else {
            List(vm.detailWinners) { w in
                VStack(alignment: .leading, spacing: 4) {
                    HStack {
                        Text(w.contestName).font(.subheadline.bold())
                        Spacer()
                        if let amount = w.amountWon {
                            Text(String(format: "$%.2f", amount))
                                .font(.subheadline.bold())
                                .foregroundStyle(.green)
                        }
                    }
                    HStack(spacing: 6) {
                        Text(w.contestTypeLabel)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        if let week = w.weekNum {
                            Text("• Week \(week)")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }
                    if let name = w.playerName ?? w.teamName {
                        Text(name).font(.caption).foregroundStyle(.secondary)
                    }
                    if let value = w.valueText, !value.isEmpty {
                        Text(value).font(.caption2).foregroundStyle(.secondary)
                    }
                }
                .padding(.vertical, 2)
            }
            .listStyle(.plain)
        }
    }

    // MARK: Summary

    @ViewBuilder
    private var summaryList: some View {
        if vm.summaryWinners.isEmpty {
            ContentUnavailableView("No contest winnings yet", systemImage: "trophy")
        } else {
            List(vm.summaryWinners) { w in
                HStack {
                    Text(w.name).font(.subheadline)
                    Spacer()
                    Text(String(format: "$%.2f", w.totalWon))
                        .font(.subheadline.bold())
                        .foregroundStyle(.green)
                }
            }
            .listStyle(.plain)
        }
    }

    // MARK: Low Score

    @ViewBuilder
    private var lowScoreList: some View {
        if vm.lowScoreWeeks.isEmpty {
            ContentUnavailableView("No completed weeks yet", systemImage: "trophy")
        } else {
            List(vm.lowScoreWeeks) { week in
                Section {
                    if !week.lowGross.isEmpty {
                        Text("Low Gross").font(.caption.bold()).foregroundStyle(.secondary)
                        ForEach(Array(week.lowGross.enumerated()), id: \.offset) { _, entry in
                            HStack {
                                Text(entry.name).font(.caption)
                                Spacer()
                                Text("\(entry.gross ?? 0)").font(.caption.bold())
                            }
                        }
                    }
                    if !week.lowNet.isEmpty {
                        Text("Low Net").font(.caption.bold()).foregroundStyle(.secondary)
                        ForEach(Array(week.lowNet.enumerated()), id: \.offset) { _, entry in
                            HStack {
                                Text(entry.name).font(.caption)
                                Spacer()
                                Text("\(entry.net ?? 0)").font(.caption.bold())
                            }
                        }
                    }
                } header: {
                    Text("Week \(week.weekNumber) — \(week.seasonName)")
                }
            }
            .listStyle(.insetGrouped)
        }
    }

    // MARK: Skins

    @ViewBuilder
    private var skinsList: some View {
        if vm.skinsWinners.isEmpty {
            ContentUnavailableView("No skins winners yet", systemImage: "dollarsign.circle")
        } else {
            List(vm.skinsWinners) { w in
                HStack {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(w.name).font(.subheadline.bold())
                        Text("\(w.skinsWon) skins").font(.caption).foregroundStyle(.secondary)
                    }
                    Spacer()
                    Text(String(format: "$%.2f", w.totalWon))
                        .font(.subheadline.bold())
                        .foregroundStyle(.green)
                }
            }
            .listStyle(.plain)
        }
    }
}
