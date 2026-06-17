import SwiftUI

@Observable
final class PodiumViewModel {
    var response: PodiumResponse?
    var isLoading = false
    var errorMessage: String?

    func load() async {
        isLoading = true; errorMessage = nil
        defer { isLoading = false }
        do {
            response = try await APIClient.shared.request(.podium)
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

// MARK: - Shareable graphic (standalone view, used by ImageRenderer)

struct PodiumGraphic: View {
    let response: PodiumResponse

    private var top3: [PodiumEntry] { Array(response.podium.prefix(3)) }
    private var rest: [PodiumEntry] { Array(response.podium.dropFirst(3)) }

    // Reorder for podium display: 2nd, 1st, 3rd
    private var displayOrder: [PodiumEntry] {
        guard top3.count >= 3 else { return top3 }
        return [top3[1], top3[0], top3[2]]
    }

    var body: some View {
        VStack(spacing: 0) {
            // Header
            VStack(spacing: 4) {
                if let league = response.leagueName, !league.isEmpty {
                    Text(league.uppercased())
                        .font(.system(size: 11, weight: .semibold))
                        .tracking(2)
                        .foregroundStyle(Color(red: 0.47, green: 0.67, blue: 0.35))
                }
                Text(response.seasonName ?? "Season")
                    .font(.system(size: 26, weight: .black))
                    .foregroundStyle(.white)
                Text("Final Standings")
                    .font(.system(size: 11, weight: .medium))
                    .tracking(1)
                    .foregroundStyle(Color(red: 0.41, green: 0.55, blue: 0.35))
            }
            .padding(.top, 32)
            .padding(.bottom, 24)

            // Podium stage
            HStack(alignment: .bottom, spacing: 10) {
                ForEach(displayOrder) { entry in
                    podiumColumn(entry)
                }
            }
            .padding(.horizontal, 16)

            // Remaining teams
            if !rest.isEmpty {
                VStack(spacing: 6) {
                    ForEach(rest) { entry in
                        HStack(spacing: 8) {
                            Text("\(entry.position).")
                                .font(.system(size: 12, weight: .bold))
                                .foregroundStyle(Color(red: 0.47, green: 0.67, blue: 0.35))
                                .frame(width: 20, alignment: .trailing)
                            Text(entry.teamLabel)
                                .font(.system(size: 13, weight: .semibold))
                                .foregroundStyle(.white)
                            Spacer()
                            Text(String(format: "%.1f pts", entry.totalPoints))
                                .font(.system(size: 12))
                                .foregroundStyle(Color(red: 0.53, green: 0.67, blue: 0.41))
                        }
                        .padding(.horizontal, 24)
                        .padding(.vertical, 5)
                        .background(Color.white.opacity(0.05))
                        .clipShape(Capsule())
                        .padding(.horizontal, 20)
                    }
                }
                .padding(.top, 16)
            }

            // Brand
            Text("BetterGolfTracker")
                .font(.system(size: 10, weight: .medium))
                .tracking(1.5)
                .foregroundStyle(Color(red: 0.24, green: 0.36, blue: 0.24))
                .padding(.top, 20)
                .padding(.bottom, 20)
        }
        .frame(width: 360)
        .background(
            LinearGradient(
                colors: [
                    Color(red: 0.10, green: 0.17, blue: 0.10),
                    Color(red: 0.05, green: 0.12, blue: 0.05),
                    Color(red: 0.04, green: 0.08, blue: 0.04),
                ],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
        )
    }

    @ViewBuilder
    private func podiumColumn(_ entry: PodiumEntry) -> some View {
        let isFirst = entry.position == 1
        let isSecond = entry.position == 2

        VStack(spacing: 0) {
            // Medal + team info
            VStack(spacing: 3) {
                Text(medal(for: entry.position))
                    .font(.system(size: isFirst ? 28 : 22))
                Text(entry.teamLabel)
                    .font(.system(size: isFirst ? 14 : 12, weight: .bold))
                    .foregroundStyle(.white)
                    .multilineTextAlignment(.center)
                    .lineLimit(2)
                Text(String(format: "%.1f", entry.totalPoints))
                    .font(.system(size: isFirst ? 20 : 16, weight: .black))
                    .foregroundStyle(pointsColor(for: entry.position))
                Text("pts")
                    .font(.system(size: 9))
                    .foregroundStyle(Color(red: 0.41, green: 0.55, blue: 0.35))
                Text(entry.record)
                    .font(.system(size: 10))
                    .foregroundStyle(Color(red: 0.53, green: 0.67, blue: 0.41))
            }
            .padding(.bottom, 8)
            .frame(width: isFirst ? 130 : 110)

            // Block
            RoundedRectangle(cornerRadius: 6, style: .continuous)
                .fill(blockGradient(for: entry.position))
                .frame(
                    width: isFirst ? 120 : 100,
                    height: isFirst ? 90 : (isSecond ? 60 : 40)
                )
                .overlay(
                    Text("\(entry.position)")
                        .font(.system(size: 22, weight: .black))
                        .foregroundStyle(.white.opacity(0.25))
                )
        }
    }

    private func medal(for position: Int) -> String {
        switch position {
        case 1: return "🥇"
        case 2: return "🥈"
        case 3: return "🥉"
        default: return ""
        }
    }

    private func pointsColor(for position: Int) -> Color {
        switch position {
        case 1: return Color(red: 1.0, green: 0.84, blue: 0.0)
        case 2: return Color(red: 0.75, green: 0.75, blue: 0.75)
        default: return Color(red: 0.80, green: 0.50, blue: 0.20)
        }
    }

    private func blockGradient(for position: Int) -> LinearGradient {
        let colors: [Color]
        switch position {
        case 1: colors = [Color(red: 0.79, green: 0.64, blue: 0.15), Color(red: 0.54, green: 0.42, blue: 0.06)]
        case 2: colors = [Color(red: 0.62, green: 0.62, blue: 0.62), Color(red: 0.35, green: 0.35, blue: 0.35)]
        default: colors = [Color(red: 0.72, green: 0.45, blue: 0.20), Color(red: 0.48, green: 0.24, blue: 0.08)]
        }
        return LinearGradient(colors: colors, startPoint: .top, endPoint: .bottom)
    }
}

// MARK: - Screen wrapper with share button

struct PodiumView: View {
    @State private var vm = PodiumViewModel()
    @State private var shareImage: UIImage?
    @State private var showingShare = false

    var body: some View {
        Group {
            if vm.isLoading {
                ProgressView()
            } else if let r = vm.response, !r.podium.isEmpty {
                ScrollView {
                    VStack(spacing: 20) {
                        PodiumGraphic(response: r)
                            .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
                            .shadow(color: .black.opacity(0.4), radius: 16, y: 8)
                            .padding(.horizontal, 16)
                            .padding(.top, 16)

                        Button {
                            renderAndShare(response: r)
                        } label: {
                            Label("Share Podium", systemImage: "square.and.arrow.up")
                                .font(.headline)
                                .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.borderedProminent)
                        .tint(Color(red: 0.27, green: 0.55, blue: 0.18))
                        .padding(.horizontal, 16)
                    }
                }
                .sheet(isPresented: $showingShare) {
                    if let img = shareImage {
                        ShareSheet(items: [img])
                    }
                }
            } else if let err = vm.errorMessage {
                ContentUnavailableView(err, systemImage: "exclamationmark.triangle")
            } else if vm.response != nil {
                ContentUnavailableView("No standings yet", systemImage: "trophy")
            }
        }
        .navigationTitle("Podium")
        .task { await vm.load() }
        .refreshable { await vm.load() }
    }

    @MainActor
    private func renderAndShare(response: PodiumResponse) {
        let graphic = PodiumGraphic(response: response)
        let renderer = ImageRenderer(content: graphic)
        renderer.scale = 3.0
        if let img = renderer.uiImage {
            shareImage = img
            showingShare = true
        }
    }
}

// MARK: - UIKit share sheet bridge

struct ShareSheet: UIViewControllerRepresentable {
    let items: [Any]

    func makeUIViewController(context: Context) -> UIActivityViewController {
        UIActivityViewController(activityItems: items, applicationActivities: nil)
    }
    func updateUIViewController(_ vc: UIActivityViewController, context: Context) {}
}
