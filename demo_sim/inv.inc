* Static CMOS inverter on the 1.2V LVT devices
.subckt inv a y vdd vss wn=210n wp=270n
XN y a vss vss nm1p2_lvt_lp w=wn l=lmin
XP y a vdd vdd pm1p2_lvt_lp w=wp l=lmin
.ends inv
