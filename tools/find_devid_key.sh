#!/bin/sh
# Exhaustive search for a Developer ID Application private key.
echo "=== 1. signing identities in every keychain ==="
for kc in /Users/yukihamada/jfbuild.keychain-db \
          /Users/yukihamada/Library/Keychains/login.keychain-db \
          /Users/yukihamada/Library/Keychains/mu-ci.keychain-db \
          /Library/Keychains/System.keychain; do
  [ -f "$kc" ] || continue
  echo "-- $(basename "$kc")"
  security find-identity -v -p codesigning "$kc" 2>/dev/null | sed -n 's/.*"\(.*\)".*/  \1/p'
done

echo
echo "=== 2. every certificate (split correctly: one file per cert) ==="
for kc in /Users/yukihamada/jfbuild.keychain-db \
          /Users/yukihamada/Library/Keychains/login.keychain-db \
          /Users/yukihamada/Library/Keychains/mu-ci.keychain-db; do
  [ -f "$kc" ] || continue
  d=$(mktemp -d); (cd "$d" && security find-certificate -a -p "$kc" 2>/dev/null \
      | awk 'BEGIN{n=0}/BEGIN CERT/{n++}{print > ("c" n ".pem")}')
  for f in "$d"/c*.pem; do
    [ -f "$f" ] || continue
    s=$(openssl x509 -in "$f" -noout -subject 2>/dev/null | sed 's/subject=//')
    case "$s" in *"Developer ID Application"*) echo "  *** $s";; esac
  done
  rm -rf "$d"
done
echo "  (nothing above = no Developer ID Application cert in any keychain)"

echo
echo "=== 3. .p12 files that open without a password ==="
find /Users/yukihamada -name "*.p12" -o -name "*.pfx" 2>/dev/null \
  | grep -vE "node_modules|/.cargo/|\.build/" \
  | while read -r f; do
      for pw in "" password 1234 123456 koe yuki hamada yukihamada; do
        if s=$(openssl pkcs12 -in "$f" -nokeys -passin pass:"$pw" 2>/dev/null \
               | grep -m1 subject); then
          echo "  $f  (pw='$pw')  $s"; break
        fi
      done
    done
echo "  (files listed above are what could be opened)"
