#!/bin/bash
# Does the regular installation of the PDK

git submodule update --init --recursive
(cd icsprout55-pdk && make start download unzip)

mkdir -p icsprout55/libs.ref
cp -r icsprout55-pdk/IP/IO/ICsprout_55LLULP1233_IO_251013 icsprout55/libs.ref
cp -r icsprout55-pdk/IP/STD_cell/ics55_LLSC_H7C_V1p10C100/ics55_LLSC_H7CH icsprout55/libs.ref
cp -r icsprout55-pdk/IP/STD_cell/ics55_LLSC_H7C_V1p10C100/ics55_LLSC_H7CL icsprout55/libs.ref
cp -r icsprout55-pdk/IP/STD_cell/ics55_LLSC_H7C_V1p10C100/ics55_LLSC_H7CR icsprout55/libs.ref
cp -r icsprout55-pdk/prtech icsprout55/libs.ref

# The installed CDLs are converted from the vendor ones (LVS-ready, see hacking/cdl_convert.py)
# and the ngspice-compatible copies are generated from the vendor CDLs too
STD_SRC=icsprout55-pdk/IP/STD_cell/ics55_LLSC_H7C_V1p10C100
for lib in ics55_LLSC_H7CH ics55_LLSC_H7CL ics55_LLSC_H7CR; do
  python3 hacking/cdl_convert.py $STD_SRC/$lib/cdl/$lib.cdl icsprout55/libs.ref/$lib/cdl/$lib.cdl
  mkdir -p icsprout55/libs.ref/$lib/spice
  python3 hacking/cdl_to_spice.py $STD_SRC/$lib/cdl/$lib.cdl icsprout55/libs.ref/$lib/spice/$lib.spice
done
IO_SRC=icsprout55-pdk/IP/IO/ICsprout_55LLULP1233_IO_251013
# --lef: empty subcircuits for the corner / spacer cells, needed by OpenROAD write_cdl
python3 hacking/cdl_convert.py $IO_SRC/cdl/ICSIOA_N55_3P3.cdl icsprout55/libs.ref/ICsprout_55LLULP1233_IO_251013/cdl/ICSIOA_N55_3P3.cdl \
  --lef hacking/ICSIOA_N55_3P3_1P6M1TM_openpdk.lef

# The vendor _ecos.lef has the pad terminals on the top metal; this one moves them to
# RDL, where they belong. PAD_LEFS (libs.tech/librelane/config.tcl) uses this file.
cp hacking/ICSIOA_N55_3P3_1P6M1TM_openpdk.lef icsprout55/libs.ref/ICsprout_55LLULP1233_IO_251013/lef/ICSIOA_N55_3P3_1P6M1TM_openpdk.lef

# ----------------------------------------------------------------------------
# Private standard cells (ICsprout_55LLULP1225_STD_0818, "ICsprout55 SC9T")
# ----------------------------------------------------------------------------
# Not part of the public release and not in the icsprout55-pdk submodule, so
# they are only installed when the vendor directory is found next to the repo
# (../pdk/ICsprout_55LLULP1225_STD_0818). Override with
#   PRIVATE_STD_ROOT=<dir> bash ./install.sh
REPO_DIR=$(cd "$(dirname "$0")" && pwd)
if [ -z "${PRIVATE_STD_ROOT:-}" ]; then
  for cand in \
      "$REPO_DIR/../pdk/ICsprout_55LLULP1225_STD_0818" \
      "$REPO_DIR/../ICsprout_55LLULP1225_STD_0818"; do
    if [ -d "$cand" ]; then PRIVATE_STD_ROOT=$(cd "$cand" && pwd); break; fi
  done
fi

# Liberty corners to install. The vendor lib/ directory is ~15 GB per library
# (CCS .lib plus .db for all 16 corners), so only the NLDM files of the corners
# in libs.tech/librelane/config.tcl (STA_CORNERS) are copied.
# PRIVATE_STD_LIBERTY=all installs every NLDM corner instead (~1.8 GB per library).
PRIVATE_STD_LIBERTY=${PRIVATE_STD_LIBERTY:-used}
LIBERTY_CORNERS="tt_v1p2_25c ss_v1p08_125c ff_v1p32_-40c"

if [ -n "${PRIVATE_STD_ROOT:-}" ] && [ -d "$PRIVATE_STD_ROOT" ]; then
  echo "Installing the private standard cells from $PRIVATE_STD_ROOT"
  # <vendor directory>:<installed library name> (= the view file basename)
  for entry in \
      ICsprout55_SC9T_BASIC_SVT:ICsprout55_9TSVT_basic \
      ICsprout55_SC9T_BASIC_HVT:ICsprout55_9THVT_basic \
      ICsprout55_SC9T_BASIC_LVT:ICsprout55_9TLVT_basic; do
    src="$PRIVATE_STD_ROOT/${entry%%:*}/0.1"
    lib=${entry##*:}
    # Liberty files are named after the library without the "_basic" suffix
    lib_base=${lib%_basic}
    dst=icsprout55/libs.ref/$lib
    if [ ! -d "$src" ]; then
      echo "  skipping $lib: $src not found"
      continue
    fi
    echo "  $lib"
    rm -rf "$dst"
    mkdir -p "$dst/cdl" "$dst/spice" "$dst/liberty"
    # Only the views the open flow needs; the vendor doc/, mway/, tmax/ and
    # fastscan/ directories are left where they are.
    for view in gds lef verilog cell_list; do
      [ -d "$src/$view" ] && cp -r "$src/$view" "$dst/$view"
    done
    # The vendor calls it "lib"; the other libraries in this PDK use "liberty"
    if [ "$PRIVATE_STD_LIBERTY" = all ]; then
      cp "$src"/lib/*_nldm.lib "$dst/liberty/"
    else
      for corner in $LIBERTY_CORNERS; do
        cp "$src/lib/${lib_base}_${corner}_basic_nldm.lib" "$dst/liberty/"
      done
    fi
    find "$dst" -name .DS_Store -delete
    # Same treatment as the public standard cells (see hacking/cdl_convert.py)
    python3 hacking/cdl_convert.py "$src/cdl/$lib.cdl" "$dst/cdl/$lib.cdl"
    python3 hacking/cdl_to_spice.py "$src/cdl/$lib.cdl" "$dst/spice/$lib.spice"
  done
else
  echo "Private standard cells not found, skipping (set PRIVATE_STD_ROOT to install them)"
fi
