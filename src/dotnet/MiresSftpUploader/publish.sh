#!/usr/bin/env bash
# Builds the release publishes of MiresSftpUploader for all four targets, smoke-tests the one matching this
# machine, and packages each as artifacts/packages/MiresSftpUploader-<version>-<rid>.{zip,tar.gz}.
#
# Usage: publish.sh [--version <x.y.z>] [--rid <rid>]...     (default: all four RIDs, version from the csproj)
# Signing is off unless SignWindows / SignMac are set; see docs/signing.md.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(cd "$here/../../.." && pwd)"
project="$here/MiresSftpUploader.csproj"
out="$root/artifacts"
all_rids=(win-x64 linux-x64 linux-arm64 osx-arm64)

version=""
rids=()
while [ $# -gt 0 ]; do
    case "$1" in
        --version) version="${2:?--version needs a value}"; shift 2 ;;
        --rid) rids+=("${2:?--rid needs a value}"); shift 2 ;;
        *) echo "Unknown argument: $1" >&2; exit 64 ;;
    esac
done
[ ${#rids[@]} -gt 0 ] || rids=("${all_rids[@]}")

props=()
if [ -n "$version" ]; then
    props+=("-p:Version=$version")
else
    version="$(dotnet msbuild "$project" -getProperty:Version | tr -d '[:space:]')"
fi

case "$(uname -s)-$(uname -m)" in
    Linux-x86_64) host_rid=linux-x64 ;;
    Linux-aarch64|Linux-arm64) host_rid=linux-arm64 ;;
    Darwin-arm64) host_rid=osx-arm64 ;;
    *) host_rid="" ;;
esac

smoke_test() {
    local dir="$1" actual errors unexpected
    local exe="$dir/MiresSftpUploader"
    echo "Smoke test: $exe"
    actual="$("$exe" --version)" || { echo "--version failed" >&2; return 1; }
    [ "$actual" = "$version" ] || { echo "--version printed '$actual', expected '$version'" >&2; return 1; }

    # --configure needs a terminal; under redirected streams it must refuse with exit 2 and print nothing on stdout.
    local configure_out configure_rc=0
    configure_out="$("$exe" --configure </dev/null 2>/dev/null)" || configure_rc=$?
    [ "$configure_rc" = 2 ] && [ -z "$configure_out" ] || { echo "--configure under redirected streams exited $configure_rc with stdout '$configure_out', expected 2 and no output" >&2; return 1; }

    # The shipped appsettings.json has no host, username, host key or Sources, so --validate-config is expected to
    # report exactly those four required fields and nothing else.
    local rc=0
    errors="$("$exe" --validate-config 2>&1 >/dev/null)" || rc=$?
    case "$rc" in
        0) ;;
        2)
            unexpected="$(printf '%s\n' "$errors" | grep -E '^  ' | grep -vE '^  (Sftp:Host|Sftp:Username|Sftp:HostKeyFingerprint): is required|^  Sources: at least one enabled Source is required' || true)"
            if [ -n "$unexpected" ]; then
                echo "--validate-config reported unexpected errors:" >&2
                echo "$unexpected" >&2
                return 1
            fi ;;
        *) echo "--validate-config exited $rc:" >&2; echo "$errors" >&2; return 1 ;;
    esac
}

mkdir -p "$out/packages"
for rid in "${rids[@]}"; do
    echo "=== $rid"
    rm -rf "$out/publish/$rid"
    dotnet publish "$project" -p:PublishProfile="$rid" ${props[@]+"${props[@]}"}

    exe="MiresSftpUploader"; [ "${rid%%-*}" = "win" ] && exe="MiresSftpUploader.exe"
    for required in "$exe" appsettings.json README.md; do
        [ -f "$out/publish/$rid/$required" ] || { echo "Missing $required in publish output for $rid" >&2; exit 1; }
    done

    if [ "$rid" = "$host_rid" ]; then
        smoke_test "$out/publish/$rid"
    else
        echo "Skipping smoke test for $rid (host is ${host_rid:-unsupported})"
    fi

    name="MiresSftpUploader-$version-$rid"
    rm -f "$out/packages/$name.zip" "$out/packages/$name.tar.gz"
    if [ "${rid%%-*}" = "win" ]; then
        (cd "$out/publish/$rid" && zip -qr "$out/packages/$name.zip" .)
    else
        tar -czf "$out/packages/$name.tar.gz" -C "$out/publish/$rid" .
    fi
    echo "Packaged $name"
done
