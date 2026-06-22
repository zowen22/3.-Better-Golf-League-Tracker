import SwiftUI
import Vision
import PhotosUI

// MARK: - Scanned Card

/// Output of a single OCR pass on a scorecard photo.
struct ScannedCard {
    /// Up to 4 player names detected from the name column (left side of card).
    /// May be empty or partial if OCR couldn't find them.
    let names: [String]
    /// Up to 4 rows of 9 gross scores. Indices correspond to `names` where available.
    let rows: [[Int]]
}

// MARK: - OCR Engine

enum ScorecardOCR {

    private static let scoreCardStopWords: Set<String> = [
        "hole", "par", "out", "in", "total", "hdcp", "hcp", "gross", "net",
        "scorer", "date", "handicap", "attest", "men", "ladies", "red", "white",
        "blue", "gold", "green", "black", "tee", "front", "back", "rating", "slope"
    ]

    /// Scan a scorecard photo and return detected player names + score rows.
    static func scan(from image: UIImage) async -> ScannedCard {
        guard let cgImage = image.cgImage else { return ScannedCard(names: [], rows: []) }
        return await withCheckedContinuation { continuation in
            var scoreRows: [[Int]] = []
            var nameCandidates: [(text: String, minX: CGFloat, minY: CGFloat)] = []

            let request = VNRecognizeTextRequest { req, _ in
                let observations = req.results as? [VNRecognizedTextObservation] ?? []

                for obs in observations {
                    guard let text = obs.topCandidates(1).first?.string else { continue }
                    let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)

                    // Try to parse as a score row (9 integers 1-12)
                    let nums = trimmed.components(separatedBy: .whitespaces)
                        .compactMap { Int($0) }.filter { $0 >= 1 && $0 <= 12 }
                    if nums.count == 9 {
                        scoreRows.append(nums)
                        continue
                    }

                    // Heuristic name detection: short text, mostly letters, on the left
                    // of the card. Vision bounding box: origin bottom-left, normalized 0-1.
                    // Names are typically in x < 0.35 of the card width.
                    guard trimmed.count >= 2 && trimmed.count <= 30 else { continue }
                    let letterFraction = Double(trimmed.filter { $0.isLetter || $0.isWhitespace }.count) /
                                        Double(trimmed.count)
                    guard letterFraction >= 0.70 else { continue }
                    guard !scoreCardStopWords.contains(trimmed.lowercased()) else { continue }
                    guard obs.boundingBox.minX < 0.35 else { continue }

                    nameCandidates.append((trimmed, obs.boundingBox.minX, obs.boundingBox.minY))
                }

                // Sort names top-to-bottom (Vision minY = distance from bottom, so descending = top first).
                // Fallback: if bounding boxes are ambiguous (rotated card), the UI handles reassignment.
                let sortedNames = nameCandidates
                    .sorted { $0.minY > $1.minY }
                    .map(\.text)

                // Sliding-window fallback when rows came out in pieces
                if scoreRows.isEmpty {
                    let allNums = observations
                        .compactMap { $0.topCandidates(1).first?.string }
                        .joined(separator: " ")
                        .components(separatedBy: .whitespaces)
                        .compactMap { Int($0) }
                        .filter { $0 >= 1 && $0 <= 12 }
                    stride(from: 0, to: min(allNums.count, 36), by: 9).forEach { start in
                        if start + 9 <= allNums.count {
                            scoreRows.append(Array(allNums[start..<start + 9]))
                        }
                    }
                }

                continuation.resume(returning: ScannedCard(
                    names: Array(sortedNames.prefix(4)),
                    rows: Array(scoreRows.prefix(4))
                ))
            }
            request.recognitionLevel = .accurate
            request.usesLanguageCorrection = false
            try? VNImageRequestHandler(cgImage: cgImage).perform([request])
        }
    }
}

// MARK: - Image Picker

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
