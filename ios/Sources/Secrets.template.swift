// Auto-generated. Personal dev build only. Do not commit.
//
// Secrets.swift is deliberately NOT vendored in this repository — upstream it
// holds a personal API token and is gitignored. Copy this template to
// Secrets.swift to build, and never commit the result.
//
//     cp Sources/Secrets.template.swift Sources/Secrets.swift
//
// The token is optional: the app runs without it, and the local Mac voice
// (LocalVoiceClient) does not use it at all.

enum Secrets {
    /// Seeded into Keychain on first launch if no token is set.
    /// Leave empty unless you have a personal token for the hosted service.
    static let seedToken = ""
}
