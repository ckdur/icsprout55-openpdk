* Inverter voltage transfer curve and switching threshold
.include 'models.inc'
.include 'inv.inc'

Xinv a y vdd 0 inv
Vdd vdd 0 1.2
Va a 0 0

.control
dc Va 0 1.2 0.005
wrdata out/inv_vtc.csv v(y)
meas dc vm when v(y)=v(a)
let gain = deriv(v(y))
meas dc gain_max min gain
.endc
.end
