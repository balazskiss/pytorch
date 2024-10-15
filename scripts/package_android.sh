#!/bin/bash

set -eu

ANDROID_ABI_LIST=(armeabi-v7a arm64-v8a x86 x86_64)

rm -rf build_android

for ANDROID_ABI in ${ANDROID_ABI_LIST[@]}; do
    BUILD_PYTORCH_MOBILE=1 BUILD_LITE_INTERPRETER=0 ANDROID_STL_SHARED=1 ANDROID_ABI=arm64-v8a scripts/build_android.sh
    mv build_android build_android_${ANDROID_ABI}
done

