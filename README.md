# TWRP device tree for Samsung Galaxy A13 (SM-A135F)

TWRP 3.7.1 (`twrp-12.1`) device tree for the Galaxy A13 4G, built with
[langsdorffkernel-a13](https://github.com/clangsdorff/langsdorffkernel-a13).

| | |
|---|---|
| Device | Samsung Galaxy A13 (`a13`, SM-A135F) |
| SoC | Exynos 850 (s5e3830), 8x Cortex-A55 |
| Kernel | langsdorffkernel-a13 5.10 (`p` variant: permissive) |
| Firmware base | A135F / A14 port vendor support |
| Partitions | Non-A/B, dynamic partitions (super), erofs |
| Recovery | Dedicated `recovery` partition, boot header v2 |

## Status

- [ ] Boots
- [ ] Touch, display, brightness
- [ ] ADB / MTP
- [ ] Backup / restore
- [ ] Decryption: active when booted with an A14 vendor, disabled on stock A13 vendor

## How it works

The A13 uses boot header v2 with no `vendor_boot` partition. The recovery
image carries everything itself:

- **Kernel & DTB:** extracted from the langsdorffkernel-a13 release `boot.img`
- **recovery_dtbo:** taken from the release `dtbo.img`
- **Kernel modules & touch firmware:** extracted from the release `boot.img`
  ramdisk into the recovery ramdisk. Modules are loaded by first stage init
  through `modules.load.recovery`.

`scripts/prepare_kernel.py` performs the extraction. The workflow runs it before
every build, so the kernel binaries are not committed to git.

The SELinux mode is hardcoded in each kernel variant. Recovery uses the
permissive `p` build.

## Decryption

The recovery carries the Android 15/KeyMint TEE stack in `/system/tee`.

- **A14 vendor:** when an A14 port vendor is installed, the AIDL KeyMint and
  Gatekeeper stack is brought up, and `langsdorff_decrypt` unlocks metadata, DE
  and CE keys.
- **Stock A13 vendor:** stock A13 TEEGRIS lacks `EVP_PKEY_get_raw_private_key`
  and uses legacy HIDL HALs. The recovery detects this at boot and keeps
  encryption disabled (plain fstab, decrypt stack skipped) so the recovery boots
  and functions normally without hanging.

## Building

Builds run on GitHub Actions (`.github/workflows/build.yml`):

- **Trigger:** a push to `main`, or **Actions → Build TWRP → Run workflow**.
  A manual run lets you pick the kernel release tag and variant.
- **Output:** uploaded as an artifact and to [Gofile](https://gofile.io).

### Local build

```bash
repo init --depth=1 -u https://github.com/minimal-manifest-twrp/platform_manifest_twrp_aosp.git -b twrp-12.1
repo sync -c --no-clone-bundle --no-tags --optimized-fetch --prune --force-sync
git clone https://github.com/clangsdorff/twrp_device_samsung_a13 device/samsung/a13

# boot.img and dtbo.img from langsdorff@a13-<ver>p.tar
python3 device/samsung/a13/scripts/prepare_kernel.py \
    --boot boot.img --dtbo dtbo.img --device-dir device/samsung/a13

export ALLOW_MISSING_DEPENDENCIES=true
source build/envsetup.sh
lunch twrp_a13-eng
mka recoveryimage
```

## Flashing

You need an unlocked bootloader and disabled vbmeta verification.

1. Boot into Download mode.
2. In Odin, put the `.tar.md5` file in the **AP** slot and turn off
   **Auto Reboot**.
3. Flash, then boot straight into recovery with **Volume Up + Power** while
   the USB cable is connected.

## Tree layout

```
BoardConfig.mk                      board and TWRP configuration
device.mk / twrp_a13.mk             product definition
recovery.fstab                      partitions (AOSP v2 format)
recovery/root/system/etc/twrp.flags TWRP display names, backup and storage flags
recovery/root/init.recovery.s5e3830.rc  USB controller, watchdogd
scripts/prepare_kernel.py           kernel release to prebuilts
recovery/root/system/bin/decrypt*.sh firmware security stack and unlock flow
decrypt/                            langsdorff_decrypt and gk_verify
patches/                            bootable/recovery patches applied by CI
```

## Credits

- [TeamWin](https://github.com/TeamWin) for TWRP
- [minimal-manifest-twrp](https://github.com/minimal-manifest-twrp) for the manifest
