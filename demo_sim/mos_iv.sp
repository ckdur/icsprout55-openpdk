* 1.2V LVT NMOS/PMOS Id-Vds curves, W=1u L=lmin
.include 'models.inc'

XN dn gn 0 0 nm1p2_lvt_lp w=1u l=lmin
XP dp gp 0 0 pm1p2_lvt_lp w=1u l=lmin
Vdn dn 0 0
Vgn gn 0 0
Vdp dp 0 0
Vgp gp 0 0

.control
* NMOS: Vds 0..1.2V, Vgs 0.2..1.2V
dc Vdn 0 1.2 0.02 Vgn 0.2 1.2 0.2
let id_ua = -i(Vdn)*1e6
wrdata out/nmos_id_vds.csv id_ua

* PMOS: Vds 0..-1.2V, Vgs -0.2..-1.2V
dc Vdp 0 -1.2 -0.02 Vgp -0.2 -1.2 -0.2
let id_ua = i(Vdp)*1e6
wrdata out/pmos_id_vds.csv id_ua

* Saturation current at |Vgs| = |Vds| = 1.2V
alter Vdn dc=1.2
alter Vgn dc=1.2
alter Vdp dc=-1.2
alter Vgp dc=-1.2
op
let idsat_n = -i(Vdn)*1e6
let idsat_p = i(Vdp)*1e6
echo "Idsat NMOS (uA/um): $&idsat_n"
echo "Idsat PMOS (uA/um): $&idsat_p"
.endc
.end
