#!/bin/bash
# Build Mesa (freedreno for the Moto's Adreno 506 + softpipe, through OSMesa)
# for the iOS userland, on macOS with Xcode's iPhoneOS SDK. The recipe and the
# Darwin patches are HakiOS's (tools/mk-mesa.sh, tools/mesa/*.patch and the
# libdrm stand-in tools/mesa/hakios-drm, MIT; pinned commit below), with the
# kernel service renamed to OceanGPU (iokit/Kernel/arm/OceanGPU.cpp).
#
# Out, in $OUT: libOSMesa.8.dylib, ocean_gltest (both ad-hoc signed).
set -euo pipefail
VERSION=25.0.7
SHA256=592272df3cf01e85e7db300c449df5061092574d099da275d19e97ef0510f8a6
HAKIOS=88513176b1e96ecf0b764cd62c6f4e6ac71345e3
HERE=$(cd "$(dirname "$0")" && pwd)
B=${B:-$PWD/mesa-build}
OUT=${OUT:-$PWD/mesa-out}
SDK=$(xcrun --sdk iphoneos --show-sdk-path)
CC=$(xcrun --sdk iphoneos -f clang)
mkdir -p "$B" "$OUT"
cd "$B"
# The iPhoneOS SDK has IOKit to link against but not its headers (HakiOS's SDK
# does): take them from the macOS SDK; the functions are the same.
rm -rf iokit-inc && mkdir -p iokit-inc/IOKit
cp -R "$(xcrun --sdk macosx --show-sdk-path)/System/Library/Frameworks/IOKit.framework/Headers/" iokit-inc/IOKit/
INC="-I$B/iokit-inc"

curl -sL --fail -o mesa-$VERSION.tar.xz https://archive.mesa3d.org/mesa-$VERSION.tar.xz
echo "$SHA256  mesa-$VERSION.tar.xz" | shasum -a 256 -c -
rm -rf mesa-$VERSION hakios
tar xJf mesa-$VERSION.tar.xz

git init -q hakios
git -C hakios remote add origin https://github.com/oosexgang/hackios-xnu-kernel.git
git -C hakios sparse-checkout set tools/mesa
git -C hakios fetch -q --depth 1 origin $HAKIOS
git -C hakios checkout -q FETCH_HEAD
# the Darwin build of freedreno and OSMesa's ES profile; not the AIR (Metal shader) frontend yet
for p in freedreno-darwin osmesa-es-profile ir3-round-default; do
	patch -s --no-backup-if-mismatch -d mesa-$VERSION -p1 < hakios/tools/mesa/$p.patch
done
cp -r hakios/tools/mesa/hakios-drm mesa-$VERSION/src/hakios-drm
sed -i '' 's/"HakiosGPU"/"OceanGPU"/' mesa-$VERSION/src/hakios-drm/hakios.drm.c
grep -q '"OceanGPU"' mesa-$VERSION/src/hakios-drm/hakios.drm.c

python3 -m venv venv
venv/bin/pip -q install mako pyyaml packaging meson ninja
export PATH=$B/venv/bin:/opt/homebrew/opt/bison/bin:/opt/homebrew/opt/flex/bin:$PATH

cat > cross.ini <<INI
[binaries]
c = ['$CC', '-arch', 'arm64', '-isysroot', '$SDK', '-miphoneos-version-min=16.0', '$INC']
cpp = ['$CC++', '-arch', 'arm64', '-isysroot', '$SDK', '-miphoneos-version-min=16.0', '$INC']
objc = ['$CC', '-arch', 'arm64', '-isysroot', '$SDK', '-miphoneos-version-min=16.0', '$INC']
ar = 'ar'
strip = 'strip'
pkg-config = 'false'

[host_machine]
system = 'darwin'
subsystem = 'ios'
cpu_family = 'aarch64'
cpu = 'arm64'
endian = 'little'

[properties]
needs_exe_wrapper = true
INI
meson setup build mesa-$VERSION --cross-file cross.ini --wrap-mode=nofallback \
	--prefix=/usr --libdir=lib --buildtype=release -Db_ndebug=true \
	-Dplatforms= -Dgallium-drivers=softpipe,freedreno -Dfreedreno-kmds=msm -Dvulkan-drivers= -Dglx=disabled \
	-Degl=disabled -Dgbm=disabled -Dosmesa=true -Dllvm=disabled -Dshared-glapi=enabled -Dgles1=disabled \
	-Dgles2=enabled -Dopengl=true -Dzstd=disabled -Dxmlconfig=disabled -Dexpat=disabled -Dshader-cache=disabled \
	-Dvalgrind=disabled -Dlibunwind=disabled -Dglvnd=disabled -Dvideo-codecs= -Dtools= -Dgallium-vdpau=disabled \
	-Dgallium-va=disabled -Dgallium-xa=disabled -Dlmsensors=disabled -Dbuild-tests=false
ninja -C build

cp build/src/gallium/targets/osmesa/libOSMesa.8.dylib "$OUT/"
install_name_tool -id /usr/lib/libOSMesa.8.dylib "$OUT/libOSMesa.8.dylib"
"$CC" -arch arm64 -isysroot "$SDK" -miphoneos-version-min=16.0 -O2 -I mesa-$VERSION/include $INC \
	-o "$OUT/ocean_gltest" "$HERE/ocean_gltest.c" "$OUT/libOSMesa.8.dylib" -framework IOKit -framework CoreFoundation
codesign -s - --force "$OUT/libOSMesa.8.dylib" "$OUT/ocean_gltest"
otool -L "$OUT/ocean_gltest"
ls -l "$OUT"
