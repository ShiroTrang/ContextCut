#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 ContextCut contributors
# SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
#
# One-command ContextCut build inside the project's own MSYS2 UCRT64
# (D:\ContextCut\env\msys64). Normally started from Windows by packaging/build.ps1.
#
# Usage: packaging/build.sh [--skip-deps] [--reconfigure] [--configure-only]
#   --skip-deps       do not run pacman
#   --reconfigure     re-run CMake configure even if build/build.ninja exists
#   --configure-only  stop after CMake configure
#
# Environment overrides: BUILD_DIR (default <repo>/build), STAGE_DIR (<repo>/stage),
# CCACHE_DIR (<msys2 root>/../ccache, shared by every clone).
set -euo pipefail

skip_deps=0
reconfigure=0
configure_only=0
for arg in "$@"; do
    case "$arg" in
    --skip-deps) skip_deps=1 ;;
    --reconfigure) reconfigure=1 ;;
    --configure-only) configure_only=1 ;;
    -h | --help)
        sed -n '5,15p' "$0"
        exit 0
        ;;
    *)
        echo "build.sh: unknown option '$arg'" >&2
        exit 2
        ;;
    esac
done

die() {
    echo "build.sh: $*" >&2
    exit 1
}

[[ "${MSYSTEM:-}" == UCRT64 ]] || die "must run in MSYS2 UCRT64 (MSYSTEM='${MSYSTEM:-}'); start it with packaging/build.ps1"
msys_root=$(cygpath -m /)
msys_root=${msys_root%/}
case "${msys_root,,}" in
c:/msys64) die "refusing to build in $msys_root; ContextCut uses its own MSYS2 (default D:/ContextCut/env/msys64)" ;;
esac

# Native tools (cmake, ninja, gcc) only understand Windows paths: /d/x would become D:\d\x.
repo=$(cygpath -m "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)")
build_dir=$(cygpath -m "${BUILD_DIR:-$repo/build}")
stage_dir=$(cygpath -m "${STAGE_DIR:-$repo/stage}")
export CCACHE_DIR
CCACHE_DIR=$(cygpath -m "${CCACHE_DIR:-$(dirname "$msys_root")/ccache}")
# Hash paths relative to the repo so another clone reuses the cache.
export CCACHE_BASEDIR="$repo"

echo "== ContextCut build"
echo "   msys2:  $msys_root"
echo "   source: $repo"
echo "   build:  $build_dir"
echo "   stage:  $stage_dir"
echo "   ccache: $CCACHE_DIR"

if [[ $skip_deps == 0 ]]; then
    pkgs=(
        # "Depends On" of mingw-w64-ucrt-x86_64-kdenlive 26.08.2-1
        breeze-icons frei0r-plugins karchive kbookmarks kcodecs kcolorscheme kcompletion kconfig
        kconfigwidgets kcoreaddons kcrash kddockwidgets kfilemetadata kguiaddons ki18n kiconthemes
        kio kitemviews knewstuff knotifications knotifyconfig ktextwidgets kwidgetsaddons kxmlgui
        mlt opentimelineio purpose shared-mime-info qqc2-desktop-style qt6-base qt6-declarative
        qt6-multimedia qt6-networkauth qt6-svg solid
        # build tools: PKGBUILD makedepends + ccache, python for KI18n translation steps
        gcc extra-cmake-modules icoutils qt6-tools cmake ninja ccache python
        # MLT optional deps Kdenlive needs on Windows (spike 2026-10-21)
        ffmpeg fftw libebur128 libsamplerate rtaudio rnnoise rubberband sox
        # Kdenlive optional deps
        mediainfo
        # AI bridge (P1)
        qt6-websockets
    )
    echo "== Dependencies (pacman --needed)"
    # No -Syu here: a silent full upgrade could swap Qt/KF/MLT under the build.
    pacman -S --needed --noconfirm "${pkgs[@]/#/${MINGW_PACKAGE_PREFIX}-}" ||
        die "pacman failed; if packages are missing from the database, run 'pacman -Syu' in this MSYS2 by hand, then retry"
fi

if [[ $reconfigure == 1 || ! -f "$build_dir/build.ninja" ]]; then
    echo "== Configure"
    # Flags from the MSYS2 kdenlive PKGBUILD. Python is pinned because FindPython
    # otherwise picks a Windows install from the registry.
    cmake -G Ninja -S "$repo" -B "$build_dir" \
        -DCMAKE_BUILD_TYPE=Release \
        -DPython3_EXECUTABLE="$(cygpath -m "$MINGW_PREFIX/bin/python3.exe")" \
        -DCMAKE_INSTALL_PREFIX="$stage_dir" \
        -DCMAKE_C_COMPILER_LAUNCHER=ccache \
        -DCMAKE_CXX_COMPILER_LAUNCHER=ccache \
        -DKDE_INSTALL_USE_QT_SYS_PATHS=OFF \
        -DBUILD_TESTING=OFF \
        -DBUILD_QCH=OFF \
        -DUSE_DBUS=OFF \
        -DFETCH_OTIO=OFF
fi
[[ $configure_only == 1 ]] && exit 0

echo "== Build"
cmake --build "$build_dir"
echo "== Install into $stage_dir"
cmake --install "$build_dir" >/dev/null
ccache --show-stats | sed -n '1,6p'
echo "== Done in ${SECONDS}s. Run: powershell -NoProfile -ExecutionPolicy Bypass -File packaging\\run.ps1"
