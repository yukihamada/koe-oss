import SwiftUI

/// Lightweight design system: one warm "Koe" accent (焚き火 = fire) + reusable
/// card / field / button styles so every screen looks consistent and modern.
enum Theme {
    /// Primary brand gradient (warm ember → coral).
    static let accent = LinearGradient(
        colors: [Color(red: 1.00, green: 0.45, blue: 0.20),
                 Color(red: 0.98, green: 0.30, blue: 0.42)],
        startPoint: .topLeading, endPoint: .bottomTrailing
    )

    static let accentColor = Color(red: 0.99, green: 0.38, blue: 0.31)

    /// Subtle background fill for grouped cards (adapts to light/dark).
    static let card = Color(.secondarySystemBackground)
    static let field = Color(.tertiarySystemBackground)
}

/// Rounded, soft "card" container used to group related controls.
struct Card<Content: View>: View {
    @ViewBuilder var content: Content
    var body: some View {
        VStack(alignment: .leading, spacing: 14) { content }
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Theme.card, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
    }
}

/// A small caption shown above a control group.
/// Takes LocalizedStringKey so literal call sites localize automatically.
struct FieldLabel: View {
    let text: LocalizedStringKey
    let systemImage: String
    var body: some View {
        Label(text, systemImage: systemImage)
            .font(.subheadline.weight(.semibold))
            .foregroundStyle(.secondary)
    }
}

/// Big primary action button with the brand gradient.
struct PrimaryButton: ButtonStyle {
    var loading: Bool = false
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.headline)
            .foregroundStyle(.white)
            .frame(maxWidth: .infinity, minHeight: 54)
            .background(Theme.accent, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
            .opacity(configuration.isPressed ? 0.85 : 1)
            .scaleEffect(configuration.isPressed ? 0.98 : 1)
            .animation(.easeOut(duration: 0.12), value: configuration.isPressed)
    }
}

extension View {
    /// Rounded text-field background for plain TextField/TextEditor.
    func koeField() -> some View {
        padding(12)
            .background(Theme.field, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
    }
}
