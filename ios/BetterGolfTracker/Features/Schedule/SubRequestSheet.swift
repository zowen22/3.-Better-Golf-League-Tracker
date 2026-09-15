import SwiftUI

@Observable
final class SubRequestSheetViewModel {
    var notes = ""
    var isSubmitting = false
    var errorMessage: String?
    var didSucceed = false

    func submit(matchupId: Int) async {
        isSubmitting = true
        errorMessage = nil
        defer { isSubmitting = false }
        do {
            let _: SubRequestCreateResponse = try await APIClient.shared.request(
                .subRequest(matchupId: matchupId, notes: notes)
            )
            didSucceed = true
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

struct SubRequestSheet: View {
    let matchupId: Int
    @Environment(\.dismiss) private var dismiss
    @State private var vm = SubRequestSheetViewModel()

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextEditor(text: $vm.notes)
                        .frame(minHeight: 100)
                } header: {
                    Text("Need a Sub?")
                } footer: {
                    Text("Optional notes for the admin (e.g. reason, timing).")
                        .font(.caption)
                }

                if let err = vm.errorMessage {
                    Text(err).font(.caption).foregroundStyle(.red)
                }
            }
            .navigationTitle("Request a Sub")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .topBarTrailing) {
                    if vm.isSubmitting {
                        ProgressView()
                    } else {
                        Button("Submit") {
                            Task {
                                await vm.submit(matchupId: matchupId)
                                if vm.didSucceed { dismiss() }
                            }
                        }
                        .bold()
                    }
                }
            }
        }
        .presentationDetents([.medium])
    }
}
