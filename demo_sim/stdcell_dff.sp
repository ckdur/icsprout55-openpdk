* DFFQX1H7H standard cell: capture check and clock-to-Q delay
.include 'models.inc'
.include '../icsprout55/libs.ref/ics55_LLSC_H7CH/spice/ics55_LLSC_H7CH.spice'

Vdd vdd 0 1.2
* 1 GHz clock, D toggles every 2 clock cycles, launched mid-period
Vck ck 0 pulse(0 1.2 0.5n 20p 20p 480p 1n)
Vd  d  0 pulse(0 1.2 0.2n 20p 20p 1.98n 4n)

Xff ck d q vdd 0 DFFQX1H7H
* Load the output with a fanout-of-4 inverter
Xld q vdd 0 qb INVX4H7H

.control
tran 1p 8n
wrdata out/stdcell_dff.csv v(ck) v(d) v(q)
meas tran tck1 when v(ck)=0.6 rise=1
meas tran tq1  when v(q)=0.6 rise=1
meas tran tck3 when v(ck)=0.6 rise=3
meas tran tq2  when v(q)=0.6 fall=1
let clk2q_rise_ps = (tq1 - tck1)*1e12
let clk2q_fall_ps = (tq2 - tck3)*1e12
echo "Clock-to-Q rise: $&clk2q_rise_ps ps  fall: $&clk2q_fall_ps ps"
.endc
.end
