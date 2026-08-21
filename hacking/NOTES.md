# libircx_ics55.so

PDK people are trying to hide the RCX values behind their software.
This library contains all the parameters.
In the end, is just plain json, but they are encrypted using XOR.

To see the actual program that does this "the corner provider", 
open ghidra at address: 0x11d650 named "ircx::ICS55CornerProvider::corner"
also here: 0x11d570 named "ircx::ICS55CornerProvider::mappingContent"


Each decrypt actually starts with the first byte in the "start", then
writes from index 1 (not zero) until the end.


(assuming .so at 0x100000)
Key:
::kkey          -> 0x2389d0, size: 0x10

Ciphertexts:
::kItfTyp        -> 0x2376e0, size: 0x11cf starts: 0x54
::kCaptabTyp     -> 0x230540, size: 0x7190 starts: 0x41
::kItfRcbest     -> 0x22f2e0, size: 0x1261 starts: 0x54
::kCaptabRcbest  -> 0x228140, size: 0x7190 starts: 0x41
::kItfRcworst    -> 0x226ec0, size: 0x1266 starts: 0x54
::kCaptabRcworst -> 0x21fd20, size: 0x7190 starts: 0x41
::kItfRcbest     -> 0x21eac0, size: 0x1257 starts: 0x54
::kCaptabCbest   -> 0x217920, size: 0x7190 starts: 0x41
::kItfCworst     -> 0x2166c0, size: 0x124d starts: 0x54
::kCaptabCworst  -> 0x20f520, size: 0x7190 starts: 0x41
::kMapping       -> 0x2388c0, size: 0x108  starts: 99

# Extractor

To get these raw json, I created a python script (with the aid of AI)
Feel free to dig in. Will leave the text files open anyway. They have "json"
extension, but they are just a custom format (or not aware for me)

```bash
# You can find (still) the libircx_ics55.so inside:
# https://github.com/openecos-projects/ecc-tools/blob/main/src/operation/iRCX/interface/ics55/lib/libircx_ics55.so
python3 extractor.py /path/to/libircx_ics55.so
```

## Debugging crashes on OpenROAD

```bash
# Dont forget to compile OpenROAD with debug
export PATH=${HOME}/Documents/SymbioticEDA/OpenROAD/build/bin:$PATH
gdb openroad --ex run
```

Inside of openroad:

```tcl
read_lef -tech /Users/ckdur/Documents/SymbioticEDA/icsprout55-openpdk/icsprout55/libs.tech/librelane/N551P6M_ecos.lef
read_lef -library /Users/ckdur/Documents/SymbioticEDA/icsprout55-openpdk/icsprout55/libs.tech/librelane/N551P6M_ecos.lef
read_lef -library /Users/ckdur/Documents/SymbioticEDA/icsprout55-openpdk/icsprout55/libs.ref/ics55_LLSC_H7CR/lef/ics55_LLSC_H7CR_ecos.lef
read_lef -library /Users/ckdur/Documents/SymbioticEDA/icsprout55-openpdk/demo_counter/runs/debug_ics/final/lef/counter.lef
read_lef -library /Users/ckdur/Documents/SymbioticEDA/icsprout55-openpdk/icsprout55/libs.ref/ICsprout_55LLULP1233_IO_251013/lef/ICSIOA_N55_3P3_1P6M1TM_ecos.lef
read_def /Users/ckdur/Documents/SymbioticEDA/icsprout55-openpdk/demo_chip/runs/debug_ics/52-odb-cellfrequencytables/chip_top.def
define_process_corner -ext_model_index 0 CURRENT_CORNER
extract_parasitics  -ext_model_file /Users/ckdur/Documents/SymbioticEDA/icsprout55-openpdk/icsprout55/libs.tech/librelane/ics55_LLSC_H7CR/rcx.rules -lef_res
```

Also, comment to OpenROAD: Please specify the syntax of OpenRCX! My god!
