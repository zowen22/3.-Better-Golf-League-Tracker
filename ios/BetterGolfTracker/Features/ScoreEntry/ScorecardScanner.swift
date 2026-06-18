import SwiftUI
import Vision
import PhotosUI

// MARK: - OCR Engine

enum ScorecardOCR {

    /// Attempt to extract 9-hole gross scores for up to 4 players from image text.
    /// Returns arrays of 9 ints. Fewer than 4 arrays if OCR can't find enough rows.
    static func extractScores(from image: UIImage) async -> [[Int]] {
        guard let cgImage = image.cgImage else { return [] }
        return await withCheckedContinuation { continuation in
            let request = VNRecognizeTextRequest { req, _ in
                let strings = (req.results as? [VNRecognizedTextObservation] ?? [])
                    .compactMap { $0.topCandidates(1).first?.string }
                continuation.resume(returning: parseScoreRows(strings))
            }
            request.recognitionLevel = .accurate
            request.usesLanguageCorrection = false
            try? VNImageRequestHandler(cgImage: cgImage).perform([request])
        }
    }

    /// Parse recognized text lines into rows of 9 golf scores (1-12).
    private static func parseScoreRows(_ lines: [String]) -> [[Int]] {
        var rows: [[Int]] = []
        for line in lines {
            let tokens = line.components(separatedBy: .whitespaces)
                .compactMap { Int($0) }
                .filter { $0 >= 1 && $0 <= 12 }
            if tokens.count == 9 {
                rows.append(tokens)
            }
        }
        // If we got rows but not exactly in groups of 9, try a sliding window
        if rows.isEmpty {
            let allNums = lines.joined(separator: " ")
                .components(separatedBy: .whitespaces)
                .compactMap { Int($0) }
                .filter { $0 >= 1 && $0 <= 12 }
            if allNums.count >= 9 {
                stride(from: 0, to: min(allNums.count, 36), by: 9).forEach { start in
                    if start + 9 <= allNums.count {
                        rows.append(Array(allNums[start..<start+9]))
                    }
                }
            }
        }
        return rows
    }
}

// MARK: - Image Picker wrapper

struct ImagePicker: UIViewControllerRepresentable {
    enum SourceType { case camera, photoLibrary }

    let source: SourceType
    let onPick: (UIImage) -> Void

    func makeUIViewController(context: Context) -> UIViewController {
        if source == .camera, UIImagePickerController.isSourceTypeAvailable(.camera) {
            let picker = UIImagePickerController()
            picker.sourceType = .camera
            picker.delegate = context.coordinator
            return picker
        } else {
            var config = PHPickerConfiguration()
            config.filter = .images
            config.selectionLimit = 1
            let picker = PHPickerViewController(configuration: config)
            picker.delegate = context.coordinator
            return picker
        }
    }

    func updateUIViewController(_ uiViewController: UIViewControllerType, context: Context) {}

    func makeCoordinator() -> Coordinator { Coordinator(onPick: onPick) }

    final class Coordinator: NSObject, UIImagePickerControllerDelegate,
                              UINavigationControllerDelegate, PHPickerViewControllerDelegate {
        let onPick: (UIImage) -> Void
        init(onPick: @escaping (UIImage) -> Void) { self.onPick = onPick }

        func imagePickerController(_ picker: UIImagePickerController,
                                   didFinishPickingMediaWithInfo info: [UIImagePickerController.InfoKey: Any]) {
            picker.dismiss(animated: true)
            if let img = info[.originalImage] as? UIImage { onPick(img) }
        }

        func picker(_ picker: PHPickerViewController, didFinishPicking results: [PHPickerResult]) {
            picker.dismiss(animated: true)
            guard let provider = results.first?.itemProvider,
                  provider.canLoadObject(ofClass: UIImage.self) else { return }
            provider.loadObject(ofClass: UIImage.self) { obj, _ in
                if let img = obj as? UIImage { self.onPick(img) }
            }
        }
    }
}

// MARK: - Scan Result Review View

/// Shown after OCR runs: lets admin review parsed scores and confirm or discard.
struct ScanResultView: View {
    let players: [MatchupPlayer]
    let pars: [Int]
    var parsedRows: [[Int]]       // up to 4 rows from OCR
    let onConfirm: ([Int: [Int]]) -> Void   // playerId → 9 scores
    let onDismiss: () -> Void

    @State private var editableScores: [[Int]] = []

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Label(
                        parsedRows.count >= players.count
                            ? "OCR found \(parsedRows.count) score rows. Verify and confirm."
                            : "OCR found \(parsedRows.count) of \(players.count) rows. Fill in missing scores.",
                        systemImage: parsedRows.count >= players.count ? "checkmark.circle" : "exclamationmark.triangle"
                    )
                    .foregroundStyle(parsedRows.count >= players.count ? .green : .orange)
                    .font(.footnote)
                }

                ForEach(Array(players.enumerated()), id: \.element.id) { i, player in
                    Section {
                        HoleScoreInputRow(
                            pars: pars,
                            scores: Binding(
                                get: { editableScores.count > i ? editableScores[i] : Array(repeating: 4, count: 9) },
                                set: { if editableScores.count > i { editableScores[i] = $0 } }
                            )
                        )
                    } header: {
                        Text(player.displayName)
                    }
                }

                Section {
                    Button("Use These Scores") {
                        var result = [Int: [Int]]()
                        for (i, player) in players.enumerated() where editableScores.count > i {
                            result[player.id] = editableScores[i]
                        }
                        onConfirm(result)
                    }
                    .frame(maxWidth: .infinity, alignment: .center)
                    .font(.headline)
                    .foregroundStyle(.white)
                    .listRowBackground(Color.accentColor)
                }
            }
            .navigationTitle("Review OCR Scores")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("Discard", action: onDismiss)
                }
            }
            .onAppear {
                // Seed editableScores: use OCR rows where available, par fallback otherwise
                editableScores = (0..<players.count).map { i in
                    i < parsedRows.count ? parsedRows[i] : pars
                }
            }
        }
    }
}
