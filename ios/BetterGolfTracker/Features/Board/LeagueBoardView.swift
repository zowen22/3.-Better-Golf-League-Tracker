import SwiftUI

@Observable
final class LeagueBoardViewModel {
    var posts: [BoardPost] = []
    var isLoading = false
    var isPosting = false
    var errorMessage: String?

    func load() async {
        isLoading = true; errorMessage = nil
        defer { isLoading = false }
        do {
            let r: BoardListResponse = try await APIClient.shared.request(.boardList)
            posts = r.posts
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func post(body: String) async {
        isPosting = true
        defer { isPosting = false }
        do {
            let _: EmptyResponse = try await APIClient.shared.request(.boardPost(body: body))
            await load()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func toggleReaction(postId: Int, emoji: String) async {
        // Optimistic update
        if let idx = posts.firstIndex(where: { $0.id == postId }) {
            var post = posts[idx]
            if let ri = post.reactions.firstIndex(where: { $0.emoji == emoji }) {
                let r = post.reactions[ri]
                if r.iReacted {
                    let newCount = r.count - 1
                    if newCount <= 0 {
                        post.reactions.remove(at: ri)
                    } else {
                        post.reactions[ri] = BoardReaction(emoji: emoji, count: newCount, iReacted: false)
                    }
                } else {
                    post.reactions[ri] = BoardReaction(emoji: emoji, count: r.count + 1, iReacted: true)
                }
            } else {
                post.reactions.append(BoardReaction(emoji: emoji, count: 1, iReacted: true))
            }
            posts[idx] = post
        }
        do {
            let _: EmptyResponse = try await APIClient.shared.request(.boardReact(postId: postId, emoji: emoji))
        } catch {
            // Revert by reloading
            await load()
        }
    }
}

struct LeagueBoardView: View {
    @Environment(AuthViewModel.self) private var authVM
    @State private var vm = LeagueBoardViewModel()
    @State private var showingCompose = false
    @State private var composeText = ""

    var isAdmin: Bool { authVM.currentUser?.isAdmin == true }

    private let reactionEmojis = ["👍", "🔥", "⛳️", "🏌️", "💪", "😂"]

    var body: some View {
        NavigationStack {
            List {
                if vm.posts.isEmpty && !vm.isLoading {
                    ContentUnavailableView(
                        "No posts yet",
                        systemImage: "megaphone",
                        description: Text(isAdmin ? "Tap + to post an update for your league." : "Your commissioner hasn't posted yet.")
                    )
                } else {
                    ForEach(vm.posts) { post in
                        postCell(post)
                            .listRowInsets(EdgeInsets(top: 10, leading: 16, bottom: 10, trailing: 16))
                    }
                }
            }
            .listStyle(.plain)
            .navigationTitle("League Board")
            .toolbar {
                if isAdmin {
                    ToolbarItem(placement: .topBarTrailing) {
                        Button { showingCompose = true } label: {
                            Image(systemName: "plus")
                        }
                    }
                }
            }
            .overlay { if vm.isLoading { ProgressView() } }
            .refreshable { await vm.load() }
            .task { await vm.load() }
            .sheet(isPresented: $showingCompose) {
                composeSheet
            }
        }
    }

    // MARK: Post cell

    @ViewBuilder
    private func postCell(_ post: BoardPost) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 6) {
                if post.isPinned {
                    Image(systemName: "pin.fill")
                        .font(.caption2)
                        .foregroundStyle(.orange)
                }
                Text(post.authorName)
                    .font(.caption.bold())
                    .foregroundStyle(.secondary)
                Spacer()
                Text(relativeDate(post.createdAt))
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }

            Text(post.body)
                .font(.body)

            // Reactions bar
            reactionBar(post)
        }
    }

    @ViewBuilder
    private func reactionBar(_ post: BoardPost) -> some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 6) {
                // Existing reactions
                ForEach(post.reactions, id: \.emoji) { reaction in
                    Button {
                        Task { await vm.toggleReaction(postId: post.id, emoji: reaction.emoji) }
                    } label: {
                        HStack(spacing: 3) {
                            Text(reaction.emoji).font(.body)
                            Text("\(reaction.count)")
                                .font(.caption.bold())
                                .foregroundStyle(reaction.iReacted ? .white : .primary)
                        }
                        .padding(.horizontal, 8).padding(.vertical, 4)
                        .background(reaction.iReacted ? Color.accentColor : Color.secondary.opacity(0.12))
                        .clipShape(Capsule())
                    }
                    .buttonStyle(.plain)
                }

                // Quick-add emoji picker
                Menu {
                    ForEach(reactionEmojis.filter { emoji in
                        !post.reactions.contains(where: { $0.emoji == emoji && $0.iReacted })
                    }, id: \.self) { emoji in
                        Button(emoji) {
                            Task { await vm.toggleReaction(postId: post.id, emoji: emoji) }
                        }
                    }
                } label: {
                    Image(systemName: "face.smiling")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .padding(.horizontal, 8).padding(.vertical, 4)
                        .background(Color.secondary.opacity(0.08))
                        .clipShape(Capsule())
                }
            }
        }
    }

    // MARK: Compose sheet

    @ViewBuilder
    private var composeSheet: some View {
        NavigationStack {
            Form {
                Section("Post to League Board") {
                    TextEditor(text: $composeText)
                        .frame(minHeight: 120)
                }
            }
            .navigationTitle("New Post")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("Cancel") {
                        composeText = ""
                        showingCompose = false
                    }
                }
                ToolbarItem(placement: .topBarTrailing) {
                    if vm.isPosting {
                        ProgressView()
                    } else {
                        Button("Post") {
                            let text = composeText
                            composeText = ""
                            showingCompose = false
                            Task { await vm.post(body: text) }
                        }
                        .disabled(composeText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                        .bold()
                    }
                }
            }
        }
        .presentationDetents([.medium, .large])
    }

    // MARK: Helpers

    private func relativeDate(_ raw: String) -> String {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        var d = f.date(from: raw)
        if d == nil {
            let f2 = DateFormatter(); f2.dateFormat = "yyyy-MM-dd HH:mm:ss"
            d = f2.date(from: raw)
        }
        guard let date = d else { return raw }
        let formatter = RelativeDateTimeFormatter()
        formatter.unitsStyle = .abbreviated
        return formatter.localizedString(for: date, relativeTo: Date())
    }
}
