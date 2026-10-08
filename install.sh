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
  --lef hacking/ICSIOA_N55_3P3_1P6M1TM_ecos.lef

# This one contains the terminals in RDL, where they are supposed to
cp hacking/ICSIOA_N55_3P3_1P6M1TM_ecos.lef icsprout55/libs.ref/ICsprout_55LLULP1233_IO_251013/lef/ICSIOA_N55_3P3_1P6M1TM_ecos.lef