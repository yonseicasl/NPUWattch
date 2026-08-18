# text_layer_map.sed -- ICC2 stream-out text layers -> i3d LVS text layers.
# Copy of the proven NN_sram_datagen/KNU_20nm/03-pl/edit_layer.sh table
# (identical file at 20/16/10/7nm; the 5nm i3d library streams out already
# in the target numbering, so this remap is SKIPPED at 5nm).
# Only t{ (text) records are touched: ICC2 emits port text on the drawing
# layer number; the LVS runset expects it on the text layer number.
s/t{84/t{88/g
s/t{11/t{31/g
s/t{13/t{32/g
s/t{15/t{33/g
s/t{17/t{34/g
s/t{19/t{35/g
s/t{21/t{36/g
s/t{23/t{37/g
s/t{25/t{38/g
s/t{27/t{39/g
s/t{92/t{97/g
s/t{94/t{98/g
s/t{96/t{99/g
