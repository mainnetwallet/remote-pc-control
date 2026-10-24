#!/usr/bin/env bash
# Publishes one build to the GitHub Releases page so that EVERY release holds both downloads:
#   RemotePCControl-Setup.exe     (Windows installer)
#   RemotePCControl-Android.apk   (Android app)
# One release per commit (tag build-<sha7>). The file that was just built goes in; the other file is copied from the newest
# earlier release that has one, unless this commit builds it too (the two workflows run side by side: whichever finishes
# last puts its fresh file in, replacing a carried-over copy).
# Usage: publish-release.sh pc|apk <built file>      env: GH_TOKEN, GITHUB_SHA, GITHUB_RUN_NUMBER (set by GitHub Actions)
set -euo pipefail
kind="${1:?pc or apk}"; built="${2:?built file}"
sha="${GITHUB_SHA:?}"; tag="build-${sha:0:7}"
work="$(mktemp -d)"
if [ "$kind" = pc ]; then
  mine="RemotePCControl-Setup.exe"; other="RemotePCControl-Android.apk"; other_re='\.apk$'
else
  mine="RemotePCControl-Android.apk"; other="RemotePCControl-Setup.exe"; other_re='^RemotePCControl-Setup.*\.exe$'
fi
cp "$built" "$work/$mine"

notes="Built from commit ${sha}.

Downloads in this release:
- **RemotePCControl-Setup.exe**: Windows installer (PC app)
- **RemotePCControl-Android.apk**: Android app

Each file is from the newest build of its kind up to this commit: if only the PC app (or only the phone app) changed in this commit, the other file is carried over from the last build."

if ! gh release view "$tag" >/dev/null 2>&1; then
  # the other workflow may create the same release at the same moment: then just use it
  gh release create "$tag" --target "$sha" --title "Build ${tag#build-}" --notes "$notes" --latest || gh release view "$tag" >/dev/null
fi
gh release upload "$tag" "$work/$mine" --clobber
gh release edit "$tag" --notes "$notes" >/dev/null || true

have_other="$(gh release view "$tag" --json assets --jq '.assets[].name' | grep -cx "$other" || true)"
if [ "$have_other" = 0 ]; then
  for t in $(gh release list --limit 40 --json tagName --jq '.[].tagName'); do
    [ "$t" = "$tag" ] && continue
    name="$(gh release view "$t" --json assets --jq '.assets[].name' | grep -E "$other_re" | head -n1 || true)"
    [ -z "$name" ] && continue
    mkdir -p "$work/prev"
    gh release download "$t" -p "$name" -D "$work/prev"
    mv "$work/prev/$name" "$work/$other"
    gh release upload "$tag" "$work/$other" || true   # no --clobber: a fresh file uploaded meanwhile by the other workflow wins
    echo "Carried over $name from $t"
    break
  done
fi
echo "Release $tag now has:"; gh release view "$tag" --json assets --jq '.assets[].name'
