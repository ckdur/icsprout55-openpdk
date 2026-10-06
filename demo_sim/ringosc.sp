* 11-stage ring oscillator, fanout-of-1, tt corner, 1.2V
.include 'models.inc'
.include 'inv.inc'

.param vsup=1.2
Vdd vdd 0 vsup

X1  n1  n2  vdd 0 inv
X2  n2  n3  vdd 0 inv
X3  n3  n4  vdd 0 inv
X4  n4  n5  vdd 0 inv
X5  n5  n6  vdd 0 inv
X6  n6  n7  vdd 0 inv
X7  n7  n8  vdd 0 inv
X8  n8  n9  vdd 0 inv
X9  n9  n10 vdd 0 inv
X10 n10 n11 vdd 0 inv
X11 n11 n1  vdd 0 inv

* Kick the ring out of its metastable point
.ic v(n1)=0 v(n2)=1.2

.control
tran 1p 3n uic
wrdata out/ringosc.csv v(n1) v(n6)
meas tran t1 when v(n1)=0.6 rise=3
meas tran t2 when v(n1)=0.6 rise=4
let period = t2 - t1
let freq_ghz = 1e-9/period
let tpd_ps = period/(2*11)*1e12
echo "Period: $&period s  Freq: $&freq_ghz GHz  Stage delay: $&tpd_ps ps"
meas tran iavg avg i(Vdd) from=t1 to=t2
.endc
.end
