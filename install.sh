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

# This one contains the terminals in RDL, where they are supposed to
cp hacking/ICSIOA_N55_3P3_1P6M1TM_ecos.lef icsprout55/libs.ref/ICsprout_55LLULP1233_IO_251013/lef/ICSIOA_N55_3P3_1P6M1TM_ecos.lef