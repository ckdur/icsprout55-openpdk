* 11-stage ring oscillator from INVX1H7H standard cells (ics55_LLSC_H7CH)
.include 'models.inc'
.lib '../icsprout55/libs.tech/ngspice/ICsprout_55LLULP1225_V1p1_hsp.lib' tt_dio
.include '../icsprout55/libs.ref/ics55_LLSC_H7CH/spice/ics55_LLSC_H7CH.spice'

Vdd vdd 0 1.2

X1  n1  vdd 0 n2  INVX1H7H
X2  n2  vdd 0 n3  INVX1H7H
X3  n3  vdd 0 n4  INVX1H7H
X4  n4  vdd 0 n5  INVX1H7H
X5  n5  vdd 0 n6  INVX1H7H
X6  n6  vdd 0 n7  INVX1H7H
X7  n7  vdd 0 n8  INVX1H7H
X8  n8  vdd 0 n9  INVX1H7H
X9  n9  vdd 0 n10 INVX1H7H
X10 n10 vdd 0 n11 INVX1H7H
X11 n11 vdd 0 n1  INVX1H7H

.ic v(n1)=0 v(n2)=1.2

.control
tran 1p 3n uic
wrdata out/stdcell_ringosc.csv v(n1) v(n6)
meas tran t1 when v(n1)=0.6 rise=3
meas tran t2 when v(n1)=0.6 rise=4
let period = t2 - t1
let freq_ghz = 1e-9/period
let tpd_ps = period/(2*11)*1e12
echo "Period: $&period s  Freq: $&freq_ghz GHz  Stage delay: $&tpd_ps ps"
meas tran iavg avg i(Vdd) from=t1 to=t2
.endc
.end
