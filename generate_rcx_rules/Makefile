top_dir1=$(shell pwd)
top_dir=$(top_dir1)
#top_dir=/home/dimitris-ic/z/72424/RegressionTest/
data_dir=$(top_dir)/data

.SILENT :

.PHONY : 1v2_parse ou_parse du_parse M1uM2_parse 1v2 2v2 2v1 1v1 3v2 3v1 5v1 5v2 sept24_1 sept24_2 sept24_3 sept24_fasterCap gen924  6v2

patterns_v1 :  1v1 2v1 3v1 5v1 
patterns_v2 :  1v2 2v2 3v2 5v2 
patterns :  patterns_v1 patterns_v2 6v1 6v2
all : 1v2_parse ou_parse du_parse M1uM2_parse 1v2 2v2 2v1 1v1 3v2 3v1 5v1 5v2 sept24_1 sept24_2 sept24_3 sept24_fasterCap gen924  6v2

# -------------------------------------------------------------------------------------
#                        rcx generates patterns
# -------------------------------------------------------------------------------------
# or_exec=/home/dimitris-ic/z/rcx_v2_or/OpenROAD-OpenRCX-v2-fotakis/build/src/openroad
# or_exec=/home/dimitris-ic/z/rcx_v2_or/OpenROAD-OpenRCX-v2-fotakis/build/src/openroad
# or_exec=/home/dimitris-ic/z/72424/OpenROAD/build/src/openroad
gen_pattern_bash=$(top_dir)/scripts/run_patterns.bash
new_gen_pattern_bash=$(top_dir)/scripts/gen_patterns.bash
script_dir=$(top_dir)/scripts

# Dependency: full path link to operand at dir bin
or_exec=$(shell which openroad)


# IMPORTANT DEPENDENCY: below goals assume data resides at directory one level up from running
data_dr1=../data

1v1: 
	$(new_gen_pattern_bash) $@ $(or_exec) $(data_dr1)/process "TYP" 1 1 $@.GOLD
	
1v2: 
	$(new_gen_pattern_bash) $@ $(or_exec) $(data_dr1)/process "TYP" 1 2 $@.GOLD 
	
2v1: 
	$(new_gen_pattern_bash) $@ $(or_exec) $(data_dr1)/process "TYP" 2 1 $@.GOLD 
	
2v2: 
	$(new_gen_pattern_bash) $@ $(or_exec) $(data_dr1)/process "TYP" 2 2 $@.GOLD 
	
3v1: 
	$(new_gen_pattern_bash) $@ $(or_exec) $(data_dr1)/process "TYP" 3 1 $@.GOLD 
	
3v2: 
	$(new_gen_pattern_bash) $@ $(or_exec) $(data_dr1)/process "TYP" 3 2 $@.GOLD 

5v1: 
	$(new_gen_pattern_bash) $@ $(or_exec) $(data_dr1)/process "TYP" 5 1 $@.GOLD 
	
5v2: 
	$(new_gen_pattern_bash) $@ $(or_exec) $(data_dr1)/process "TYP" 5 2 $@.GOLD 

6v1: 
	$(new_gen_pattern_bash) $@ $(or_exec) $(data_dr1)/process "TYP" 6 1 $@.GOLD 

6v2: 
	$(new_gen_pattern_bash) $@ $(or_exec) $(data_dr1)/process "TYP" 6 2 $@.GOLD 

# -------------------------------------------------------------------------------------
#                        Run fasterCap
# -------------------------------------------------------------------------------------
run_fasterCap=$(top_dir)/scripts/run_fasterCap.bash
UniversalFormat2FasterCap_python_script=$(top_dir)/scripts/UniversalFormat2FasterCap_923.py
fasterCap_exec=$(shell which FasterCap)

#UniversalFormat2FasterCap_python_script=~/z/72424/scripts/UniversalFormat2FasterCap_923.py
#fasterCap_exec=/home/dimitris-ic/fasterCap/920/FasterCAP_v2/FasterCap_v2/build_fasterCap_920/FasterCap

1v2_fc:
	$(run_fasterCap) 1v2 $@ normalized 20 20 20 ALL $(UniversalFormat2FasterCap_python_script) $(fasterCap_exec)

2v2_fc:
	$(run_fasterCap) 2v2 $@ normalized 20 20 20 ALL $(UniversalFormat2FasterCap_python_script) $(fasterCap_exec)

3v1_fc:
	$(run_fasterCap) 3v1 $@ normalized 20 20 20 ALL $(UniversalFormat2FasterCap_python_script) $(fasterCap_exec)

3v2_fc:
	$(run_fasterCap) 3v2 $@ normalized 20 20 20 ALL $(UniversalFormat2FasterCap_python_script) $(fasterCap_exec)

# We keep these examples whenever we need to do the actual extraction...
3v2_fc_M3oM2uM6:
	$(run_fasterCap) 3v2 $@ normalized 20 20 20 M3oM2uM6 $(UniversalFormat2FasterCap_python_script) $(fasterCap_exec)

3v1_fc_M1uM3:
	$(run_fasterCap) 3v1 $@ normalized 20 20 20 M1uM3 $(UniversalFormat2FasterCap_python_script) $(fasterCap_exec)

# -------------------------------------------------------------------------------------
#                        fasterCapParse parse of fasterCap Output
# -------------------------------------------------------------------------------------
parse_fasterCap_bash=$(top_dir)/scripts/parse_fasterCap.bash
fasterCapParse=$(top_dir)/scripts/fasterCapParse.py
fasterCapParsePython=$(top_dir)/scripts/fasterCapParse.py

parse: 1v2_parse 3v1_parse

1v2_parse:
	$(parse_fasterCap_bash) $@  $(top_dir) 1v2_fc.normalized.20.20.20.ALL  $(fasterCapParsePython) 1 $@.GOLD

2v2_parse:
	$(parse_fasterCap_bash) $@  $(top_dir) 2v2_fc.normalized.20.20.20.ALL  $(fasterCapParsePython) 1 $@.GOLD

3v1_parse:
	$(parse_fasterCap_bash) $@  $(top_dir) 3v1_fc.normalized.20.20.20.ALL  $(fasterCapParsePython) 1 $@.GOLD

3v2_parse:
	$(parse_fasterCap_bash) $@  $(top_dir) 3v2_fc.normalized.20.20.20.ALL  $(fasterCapParsePython) 1 $@.GOLD

# -------------------------------------------------------------------------------------
#                        rcx generates model file
# -------------------------------------------------------------------------------------
readCaps_tcl=readCaps.rcx.tcl

gen: 
	echo "-----------------------------------------------------------------" ; \
	echo "             dependency: make 1v2_parse 3v1_parse                " ; \
	echo "-----------------------------------------------------------------" ; \
	echo $@ ; \
        rm -rf $@ ; \
        mkdir $@ ; \
        cd $@ ; \
	echo "init_rcx_model -corner_names \"TYP\" -met_cnt 7" > $(readCaps_tcl) ; \
	echo "read_rcx_tables -corner TYP -file  $(top_dir)/3v1_parse/3v1_fc.normalized.20.20.20.ALL.caps" >>  $(readCaps_tcl) ; \
	echo "read_rcx_tables -corner TYP -file  $(top_dir)/1v2_parse/1v2_fc.normalized.20.20.20.ALL.caps" >>  $(readCaps_tcl) ; \
	echo "read_rcx_tables -corner TYP -file  $(top_dir)/1v1/resistance.TYP " >>  $(readCaps_tcl) ; \
	echo "write_rcx_model -file sept24.rcx.model " >> $(readCaps_tcl) ; \
	$(or_exec) < $(readCaps_tcl) > OUT

.PHONY: clean
clean:
	rm -rfv 1v1 1v2* 3v1* Wires Dielectrics gen
