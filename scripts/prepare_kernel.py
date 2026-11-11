#!/usr/bin/env python3
#
# Copyright (C) 2026 The Android Open Source Project
#
# SPDX-License-Identifier: Apache-2.0
#
"""Turn a langsdorffkernel-a13 release (boot.img + dtbo.img) into the
prebuilts this device tree expects.

Samsung's Galaxy A13 (SM-A135F) uses boot header v2 with no vendor_boot partition.
Everything the kernel needs at runtime (modules and early firmware) lives in the
boot ramdisk:

  boot.img (v2) -> prebuilt/kernel
                -> prebuilt/dtb.img
                -> recovery/root/lib/modules/*
                -> recovery/root/vendor/firmware/*
  dtbo.img      -> prebuilt/dtbo.img
"""

import argparse
import gzip
import os
import shutil
import struct
import subprocess
import sys

BOOT_MAGIC = b"ANDROID!"
LZ4_LEGACY_MAGIC = b"\x02\x21\x4c\x18"
GZIP_MAGIC = b"\x1f\x8b"
ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"
DT_TABLE_MAGIC = b"\xd7\xb7\xab\x1e"

# Modules not needed in recovery that blow past the ~53 MB partition size.
# Camera, GPU 3D, video codecs, Wi-Fi, BT, audio, cellular/GPS, PC gamepads/drawing tablets, debug dumps.
RECOVERY_MODULE_EXCLUDE_PREFIXES = (
    "fimc-is", "is-", "camerapp",
    "mali_kbase",
    "exynos_mfc", "smfc", "gdc", "votf", "scaler",
    "scsc_", "fm_s610",
    "snd-soc-", "sec_audio_",
    "cpif", "dev_ril_bridge", "gnss", "shm_ipc", "cdc-wdm", "cdc_mbim",
    "sensor_core", "nanohub", "shub", "nfc_sec",
    "hid-", "acecad", "aiptek", "hanwang", "kbtab",
    "debug-snapshot-", "sec_debug_", "dropdump", "exynos-bcm_dbg",
    "exynos-flexpmu-dbg", "exynos-pd-dbg", "exynos-coresight", "exynos-debug-test", "xperf",
)


def should_exclude_module(filename):
    for prefix in RECOVERY_MODULE_EXCLUDE_PREFIXES:
        if filename == prefix or filename.startswith(prefix):
            return True
    return False


def align(value, page_size):
    return (value + page_size - 1) // page_size * page_size


def die(msg):
    sys.exit(f"prepare_kernel: error: {msg}")


def decode_os_version(packed):
    version, patch = packed >> 11, packed & 0x7ff
    a, b, c = (version >> 14) & 0x7f, (version >> 7) & 0x7f, version & 0x7f
    year, month = 2000 + (patch >> 4), patch & 0xf
    return f"{a}.{b}.{c}", f"{year:04d}-{month:02d}-01"


def parse_boot_v2(boot):
    if boot[:8] != BOOT_MAGIC:
        die("boot.img: bad magic")
    kernel_size, kernel_addr, ramdisk_size, ramdisk_addr, second_size, second_addr, tags_addr, page_size, header_version, os_version = \
        struct.unpack_from("<10I", boot, 8)
    if header_version not in (1, 2):
        die(f"boot.img: expected header version 1 or 2, got {header_version}")

    recovery_dtbo_size = struct.unpack_from("<I", boot, 1632)[0]
    recovery_dtbo_offset = struct.unpack_from("<Q", boot, 1636)[0]

    dtb_size = 0
    if header_version == 2:
        dtb_size = struct.unpack_from("<I", boot, 1648)[0]

    kernel_off = page_size
    ramdisk_off = kernel_off + align(kernel_size, page_size)
    second_off = ramdisk_off + align(ramdisk_size, page_size)
    dtbo_off = second_off + align(second_size, page_size)
    dtb_off = dtbo_off + align(recovery_dtbo_size, page_size)

    kernel = boot[kernel_off:kernel_off + kernel_size]
    ramdisk = boot[ramdisk_off:ramdisk_off + ramdisk_size] if ramdisk_size else b""
    dtb = boot[dtb_off:dtb_off + dtb_size] if dtb_size else b""
    recovery_dtbo = boot[recovery_dtbo_offset:recovery_dtbo_offset + recovery_dtbo_size] if recovery_dtbo_size else b""

    return kernel, ramdisk, dtb, recovery_dtbo, os_version


def decompress(data):
    if data[:4] == LZ4_LEGACY_MAGIC:
        return subprocess.run(["lz4", "-dc"], input=data, stdout=subprocess.PIPE,
                              check=True).stdout
    if data[:4] == ZSTD_MAGIC:
        return subprocess.run(["zstd", "-dc"], input=data, stdout=subprocess.PIPE,
                              check=True).stdout
    if data[:2] == GZIP_MAGIC:
        return gzip.decompress(data)
    return data


def cpio_entries(data):
    """Yield (name, mode, content) for a newc cpio archive."""
    off = 0
    while off + 110 <= len(data):
        if data[off:off + 6] not in (b"070701", b"070702"):
            die(f"cpio: bad magic at {off}")
        fields = [int(data[off + 6 + i * 8:off + 14 + i * 8], 16) for i in range(13)]
        mode, filesize, namesize = fields[1], fields[6], fields[11]
        name_off = off + 110
        name = data[name_off:name_off + namesize - 1].decode(errors="replace")
        file_off = align(name_off + namesize, 4)
        if name == "TRAILER!!!":
            return
        yield name, mode, data[file_off:file_off + filesize]
        off = align(file_off + filesize, 4)


def write_file(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(content)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--boot", required=True)
    parser.add_argument("--dtbo", default=None)
    parser.add_argument("--device-dir", required=True)
    args = parser.parse_args()

    device_dir = args.device_dir
    root = os.path.join(device_dir, "recovery", "root")
    modules_dir = os.path.join(root, "lib", "modules")
    firmware_dir = os.path.join(root, "vendor", "firmware")
    for path in (modules_dir, firmware_dir):
        shutil.rmtree(path, ignore_errors=True)

    with open(args.boot, "rb") as f:
        kernel, ramdisk, dtb, recovery_dtbo, os_version = parse_boot_v2(f.read())

    write_file(os.path.join(device_dir, "prebuilt", "kernel"), kernel)
    print(f"kernel: {len(kernel)} bytes")

    version, patch = decode_os_version(os_version)
    write_file(os.path.join(device_dir, "prebuilt", "bootimg_version.mk"),
               f"BOARD_MKBOOTIMG_ARGS += --os_version {version} --os_patch_level {patch}\n".encode())
    print(f"boot.img os_version {version}, os_patch_level {patch}")

    if dtb:
        write_file(os.path.join(device_dir, "prebuilt", "dtb.img"), dtb)
        print(f"dtb: {len(dtb)} bytes")

    if args.dtbo and os.path.exists(args.dtbo):
        with open(args.dtbo, "rb") as f:
            dtbo = f.read()
        # release dtbo.img is padded to the 8 MB partition; keep only the DT table
        if dtbo[:4] == DT_TABLE_MAGIC:
            dtbo = dtbo[:struct.unpack_from(">I", dtbo, 4)[0]]
        write_file(os.path.join(device_dir, "prebuilt", "dtbo.img"), dtbo)
        print(f"dtbo: from {args.dtbo} ({len(dtbo)} bytes)")
    elif recovery_dtbo:
        write_file(os.path.join(device_dir, "prebuilt", "dtbo.img"), recovery_dtbo)
        print(f"dtbo: from boot.img recovery_dtbo ({len(recovery_dtbo)} bytes)")

    modules = 0
    firmware = 0
    if ramdisk:
        raw_ramdisk = decompress(ramdisk)
        for path, mode, content in cpio_entries(raw_ramdisk):
            if not (mode & 0o170000) == 0o100000:
                continue
            # A13 ramdisk has lib/modules/* and lib/firmware/*
            if path.startswith("lib/modules/") or path.startswith("first_stage_ramdisk/lib/modules/"):
                rel_path = path if path.startswith("lib/modules/") else path[len("first_stage_ramdisk/"):]
                filename = os.path.basename(rel_path)
                if filename.endswith(".ko") and should_exclude_module(filename):
                    continue
                write_file(os.path.join(root, rel_path), content)
                modules += rel_path.endswith(".ko")
            elif path.startswith("lib/firmware/"):
                # copy firmware to vendor/firmware in recovery ramdisk
                rel = path[len("lib/firmware/"):]
                write_file(os.path.join(firmware_dir, rel), content)
                firmware += 1

    load = os.path.join(modules_dir, "modules.load")
    if modules and os.path.exists(load):
        with open(load, "r") as f:
            lines = [line.strip() for line in f if line.strip()]
        filtered = [l for l in lines if not should_exclude_module(l)]
        with open(os.path.join(modules_dir, "modules.load.recovery"), "w") as f:
            f.write("\n".join(filtered) + "\n")
    print(f"modules: {modules}, firmware files: {firmware}")


if __name__ == "__main__":
    main()
