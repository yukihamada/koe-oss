cask "koe-oss" do
  version "0.1.0"
  sha256 "0bc4e35c8cc00817f2044c105373402bbea259c6205394d61c1e12427c410dc9"

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
