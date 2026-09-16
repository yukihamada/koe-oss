cask "koe-oss" do
  version "0.1.0"
  sha256 "16818ebc7726eeab6e5c799c0e93672d188b675c8bb9b2480d0794cb3ad011ea"

  url "https://github.com/yukihamada/koe-oss/releases/download/v#{version}/KOE.dmg"
  name "KOE"
  desc "Local-first text-to-speech in your own voice"
  homepage "https://github.com/yukihamada/koe-oss"

  depends_on arch: :arm64
  depends_on macos: :ventura

  app "KOE.app"

  # The build is ad-hoc signed: no Developer ID certificate was available when
  # it was produced. Gatekeeper blocks it via the quarantine attribute, so
  # clear that after install. A properly signed build would not need this.
  # `postflight_steps` is what brew style asks for, but its `run` DSL rejects
  # the args form we need, so this stays on `postflight`. It works and only
  # prints a deprecation notice.
  postflight do
    system_command "/usr/bin/xattr",
                   args: ["-dr", "com.apple.quarantine", "#{appdir}/KOE.app"]
  end

  zap trash: [
    "~/Library/Application Support/live.koe.oss",
    "~/Library/Preferences/live.koe.oss.plist",
  ]
end
