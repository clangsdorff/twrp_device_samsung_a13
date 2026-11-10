#!/system/bin/sh
ROM=/rom

rom_mounted() {
    [ -e "${ROM}/system/bin/servicemanager" ] && [ -e "${ROM}/system/bin/bootstrap/linker64" ]
}

rom_mount() {
    rom_mounted && return 0
    mkdir -p "${ROM}" 2>/dev/null
    for dev in /dev/block/mapper/system /dev/block/mapper/system_a /dev/block/mapper/system_b; do
        [ -e "${dev}" ] || continue
        for fs in erofs ext4; do
            mount -t "${fs}" -o ro "${dev}" "${ROM}" 2>/dev/null || continue
            rom_mounted && return 0
            umount "${ROM}" 2>/dev/null
        done
    done
    return 1
}

vendor_mounted() {
    [ -e /vendor/bin/tzdaemon ]
}

vendor_mount() {
    vendor_mounted && return 0
    for dev in /dev/block/mapper/vendor /dev/block/mapper/vendor_a /dev/block/mapper/vendor_b; do
        [ -e "${dev}" ] || continue
        for fs in erofs ext4; do
            mount -t "${fs}" -o ro "${dev}" /vendor 2>/dev/null || continue
            vendor_mounted && return 0
            umount /vendor 2>/dev/null
        done
    done
    return 1
}

vendor_is_a14() {
    vendor_mount || return 1
    # A14 vendor carries AIDL fingerprint and Samsung NFC HALs (stock A13 uses HIDL @3.0 and NXP NFC)
    [ -e /vendor/bin/hw/vendor.samsung.hardware.biometrics.fingerprint-service ] && return 0
    [ -e /vendor/bin/hw/sec.android.hardware.nfc-service ] && return 0
    # ro.vendor.build.version.sdk >= 34 or release >= 14
    sdk=$(grep -m1 '^ro.vendor.build.version.sdk=' /vendor/build.prop 2>/dev/null | cut -d= -f2)
    [ -n "${sdk}" ] && [ "${sdk}" -ge 34 ] 2>/dev/null && return 0
    release=$(grep -m1 '^ro.vendor.build.version.release=' /vendor/build.prop 2>/dev/null | cut -d= -f2)
    [ -n "${release}" ] && [ "${release}" -ge 14 ] 2>/dev/null && return 0
    return 1
}
