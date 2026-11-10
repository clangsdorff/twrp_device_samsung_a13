#!/system/bin/sh
export TMPDIR=/tmp
KEYDIR=/metadata/vold/metadata_encryption
FSTAB=/system/etc/recovery.fstab
LOG=/tmp/fstab_crypto.log
. /system/bin/rom_mount.sh

mkdir -p /metadata 2>/dev/null
mounted_meta=0
if ! mountpoint -q /metadata 2>/dev/null; then
    mount -t ext4 -o ro /dev/block/by-name/metadata /metadata 2>/dev/null && mounted_meta=1
fi

has_key=0
[ -e "${KEYDIR}/key/encrypted_key" ] && has_key=1

is_a14=0
if [ "${has_key}" = 1 ]; then
    vendor_is_a14 && is_a14=1
    # keep vendor unmounted if fstab_crypto mounted it
    umount /vendor 2>/dev/null
fi

if [ "${has_key}" = 1 ] && [ "${is_a14}" = 1 ]; then
    opts="inlinecrypt"
    flags="fileencryption=aes-256-xts:aes-256-cts:v2+inlinecrypt_optimized,keydirectory=${KEYDIR}"
    awk -v o="${opts}" -v f="${flags}" '
        $2 == "/data" && $0 !~ /^#/ { print $1 "\t" $2 "\t" $3 "\t" $4 "," o "\t" $5 "," f; next }
        { print }
    ' "${FSTAB}" > /tmp/recovery.fstab.crypto
    cp /tmp/recovery.fstab.crypto "${FSTAB}"
    echo "metadata encryption present and vendor is A14, /data flagged" > "${LOG}"
elif [ "${has_key}" = 1 ]; then
    echo "metadata key present but vendor is not A14, encryption disabled (fstab left plain)" > "${LOG}"
else
    echo "no metadata key, fstab left plain" > "${LOG}"
fi
grep -E "[[:space:]]/data[[:space:]]" "${FSTAB}" >> "${LOG}"

[ "${mounted_meta}" = 1 ] && umount /metadata 2>/dev/null
exit 0
