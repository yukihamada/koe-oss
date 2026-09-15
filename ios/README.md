# Koe iOS — 声が、そのまま届く 📱

ミッション「**すべての声に、居場所とはたらく場所を**」の手のひら側。
文字にすると落ちる温度を、声のまま送り・残し・働かせる iPhone アプリ。bundle `tokyo.hamada.koe`。

4タブ: **ライブ**(koe.live ラジオトップ・既定の主役) / **トーク**(koe.live/app 声メッセージ受信箱) /
**友だち**(koe.live/friends つながり・在席) / **設定**(トークン・声登録。中に「声を録ってシェア」「一斉送信(β)」)。
プッシュ通知は koe-edge (`/api/push/register` + APNs) と対。通知タップは該当タブへdeep link。多言語 = ja / en(`Sources/*.lproj`)。

## Build & Run

```bash
xcodegen generate                # project.yml → Koe.xcodeproj (要 xcodegen)

# 実機ビルド+インストール(Apple IDアカウント無しでもASC APIキーで署名できる)
ISSUER=$(python3 -c "import json;print(json.load(open('$HOME/.appstoreconnect/api_key.json'))['issuer_id'])")
xcodebuild -project Koe.xcodeproj -scheme Koe \
  -destination 'id=<xcodebuild側デバイスID>' \
  -allowProvisioningUpdates \
  -authenticationKeyPath ~/private_keys/AuthKey_5KT46G9Y29.p8 \
  -authenticationKeyID 5KT46G9Y29 -authenticationKeyIssuerID "$ISSUER" \
  ENABLE_DEBUG_DYLIB=NO build
xcrun devicectl device install app --device <devicectl側ID> <DerivedDataのKoe.app>
```

- デバイスIDは2種類ある: `xcrun devicectl list devices` のIDと `xcodebuild -showdestinations` のID(00008140-…)は別物。
- `Secrets.swift` は個人ビルド用シードトークン(コミットしない運用)。

## Test

```bash
xcodebuild -project Koe.xcodeproj -scheme Koe \
  -destination 'platform=iOS Simulator,name=demo-iphone' test
```

## TestFlight

**Apple要件: iOS 26 SDK(Xcode 26)でのビルドが必須**。ローカルXcodeが古い場合の勝ちパターン:

1. m5 Mac(Xcode 26)で署名なしアーカイブ: `xcodebuild archive CODE_SIGNING_ALLOWED=NO …`
2. rsyncで持ち帰り → ローカルで `xcodebuild -exportArchive`(ASC APIキー署名)
3. `xcrun altool --upload-app -f Koe.ipa -t ios --apiKey 5KT46G9Y29 --apiIssuer $ISSUER`

(m5でSSH越しに署名すると keychain ロックで `errSecInternalComponent` になる。)
外部配布リンク: https://testflight.apple.com/join/kNM2RZ5E

## 関連

- サーバ: `~/workspace/koe-edge`(koe.live Worker・受信箱+APNs送信)
- 声エンジン: voice.koe.live(m5/RunPod)。API契約は `Sources/APIClient.swift`
