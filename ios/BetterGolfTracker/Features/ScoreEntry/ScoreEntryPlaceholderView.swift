import SwiftUI

struct ScoreEntryPlaceholderView: View {
    var body: some View {
        NavigationStack {
            ContentUnavailableView("Score Entry", systemImage: "flag.fill", description: Text("Coming soon"))
                .navigationTitle("Score Entry")
        }
    }
}
