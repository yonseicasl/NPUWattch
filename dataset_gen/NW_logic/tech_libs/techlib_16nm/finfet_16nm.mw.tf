#########################################################################################
# Nangate 45nm milkyway technology file							#
# created by Taigon Song								#
# drawing grid:   0.001 microns								#
#											#
# Revision History:									#
# Rev.		date		what							#
# -------------------------------------------------------------------------------------	#	
# 1.0		26/July/2019	(First draft)						#
# 1.1           10/Sept./2019   changed metal1 metal2 spacing, layer numbers                    #
#########################################################################################

Technology {
  name = "finfet16nm"
  date = "Oct 13 2020"
  unitTimeName = "ns"
  timePrecision = 1000
  unitLengthName = "micron"
  lengthPrecision = 1000
  unitVoltageName = "V"
  voltagePrecision = 1000000
  unitCurrentName = "ma"
  unitPowerName = "mw"
  powerPrecision = 100000
  gridResolution = 1
  currentPrecision = 1000
  unitResistanceName = "kohm"
  resistancePrecision = 10000000
  unitCapacitanceName = "pf"
  capacitancePrecision = 10000000
  unitInductanceName = "nh"
  inductancePrecision = 100
  minEdgeMode = 1
}

Color		6 {
		name				= "6"
		rgbDefined			= 1
		redIntensity			= 0
		greenIntensity			= 80
		blueIntensity			= 190
}

Color		8 {
		name				= "8"
		rgbDefined			= 1
		redIntensity			= 0
		greenIntensity			= 175
		blueIntensity			= 0
}

Color		10 {
		name				= "10"
		rgbDefined			= 1
		redIntensity			= 0
		greenIntensity			= 175
		blueIntensity			= 190
}

Color		11 {
		name				= "11"
		rgbDefined			= 1
		redIntensity			= 0
		greenIntensity			= 175
		blueIntensity			= 255
}

Color		13 {
		name				= "13"
		rgbDefined			= 1
		redIntensity			= 0
		greenIntensity			= 255
		blueIntensity			= 100
}

Color		20 {
		name				= "20"
		rgbDefined			= 1
		redIntensity			= 90
		greenIntensity			= 80
		blueIntensity			= 0
}

Color		23 {
		name				= "23"
		rgbDefined			= 1
		redIntensity			= 90
		greenIntensity			= 80
		blueIntensity			= 255
}

Color		25 {
		name				= "25"
		rgbDefined			= 1
		redIntensity			= 90
		greenIntensity			= 175
		blueIntensity			= 100
}

Color		27 {
		name				= "27"
		rgbDefined			= 1
		redIntensity			= 90
		greenIntensity			= 175
		blueIntensity			= 255
}

Color		28 {
		name				= "28"
		rgbDefined			= 1
		redIntensity			= 90
		greenIntensity			= 255
		blueIntensity			= 0
}

Color		31 {
		name				= "31"
		rgbDefined			= 1
		redIntensity			= 90
		greenIntensity			= 255
		blueIntensity			= 255
}

Color		32 {
		name				= "32"
		rgbDefined			= 1
		redIntensity			= 180
		greenIntensity			= 0
		blueIntensity			= 0
}

Color		34 {
		name				= "34"
		rgbDefined			= 1
		redIntensity			= 180
		greenIntensity			= 0
		blueIntensity			= 190
}

Color		35 {
		name				= "35"
		rgbDefined			= 1
		redIntensity			= 180
		greenIntensity			= 0
		blueIntensity			= 255
}

Color		36 {
		name				= "36"
		rgbDefined			= 1
		redIntensity			= 180
		greenIntensity			= 80
		blueIntensity			= 0
}

Color		38 {
		name				= "38"
		rgbDefined			= 1
		redIntensity			= 180
		greenIntensity			= 80
		blueIntensity			= 190
}

Color		40 {
		name				= "40"
		rgbDefined			= 1
		redIntensity			= 180
		greenIntensity			= 175
		blueIntensity			= 0
}

Color		43 {
		name				= "43"
		rgbDefined			= 1
		redIntensity			= 180
		greenIntensity			= 175
		blueIntensity			= 255
}

Color		44 {
		name				= "44"
		rgbDefined			= 1
		redIntensity			= 180
		greenIntensity			= 255
		blueIntensity			= 0
}

Color		47 {
		name				= "47"
		rgbDefined			= 1
		redIntensity			= 180
		greenIntensity			= 255
		blueIntensity			= 255
}

Color		50 {
		name				= "50"
		rgbDefined			= 1
		redIntensity			= 255
		greenIntensity			= 0
		blueIntensity			= 190
}

Color		51 {
		name				= "ltGreen"
		rgbDefined			= 1
		redIntensity			= 0
		greenIntensity			= 240
		blueIntensity			= 110
}

Color		52 {
		name				= "52"
		rgbDefined			= 1
		redIntensity			= 255
		greenIntensity			= 80
		blueIntensity			= 0
}

Color		54 {
		name				= "54"
		rgbDefined			= 1
		redIntensity			= 255
		greenIntensity			= 80
		blueIntensity			= 190
}

Color		58 {
		name				= "58"
		rgbDefined			= 1
		redIntensity			= 255
		greenIntensity			= 175
		blueIntensity			= 190
}

Color		59 {
		name				= "59"
		rgbDefined			= 1
		redIntensity			= 255
		greenIntensity			= 175
		blueIntensity			= 255
}

Color		62 {
		name				= "62"
		rgbDefined			= 1
		redIntensity			= 255
		greenIntensity			= 255
		blueIntensity			= 190
}

Stipple		"twelldot" {
		width			= 16
		height			= 16
		pattern			= (0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 
					   0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 
					   0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 
					   0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 
					   0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 
					   0, 0, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 
					   0, 0, 0, 0, 0, 0, 1, 0, 1, 0, 0, 0, 0, 0, 0, 0, 
					   0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 
					   0, 0, 0, 0, 0, 0, 1, 0, 1, 0, 0, 0, 0, 0, 0, 0, 
					   0, 0, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 
					   0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 
					   0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 
					   0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 
					   0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 
					   0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 
					   0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0) 
}

Stipple		"welldot" {
		width			= 16
		height			= 16
		pattern			= (0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 
					   0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 
					   0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 
					   0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 
					   0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 
					   0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 
					   0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 
					   0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 
					   0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 
					   0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 
					   0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 
					   0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 
					   0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 
					   0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 
					   0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 
					   0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0) 
}

Stipple		"impdot" {
		width			= 16
		height			= 16
		pattern			= (1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 
					   0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 
					   0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 
					   0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 
					   0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 
					   0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 
					   0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 
					   0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 
					   0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 
					   0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 
					   0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 
					   0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 
					   0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 
					   0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 
					   0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 
					   1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1) 
}

Stipple		"hidot" {
		width			= 16
		height			= 16
		pattern			= (1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 
					   0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 
					   1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 
					   0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 
					   1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 
					   0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 
					   1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 
					   0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 
					   1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 
					   0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 
					   1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 
					   0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 
					   1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 
					   0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 
					   1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 
					   0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1) 
}

Stipple		"rhidot" {
		width			= 16
		height			= 16
		pattern			= (0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 
					   1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 
					   0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 
					   1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 
					   0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 
					   1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 
					   0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 
					   1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 
					   0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 
					   1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 
					   0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 
					   1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 
					   0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 
					   1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 
					   0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 
					   1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0) 
}

Tile		"finfet16nm" {
		width				= 0.108
		height				= 0.576  
}

Layer           "metal0" {
                layerNumber                     = 84
                maskName                        = "metal0"
                isDefaultLayer                  = 1
                visible                         = 1
                selectable                      = 1
                blink                           = 0
                color                           = "silver"
                lineStyle                       = "solid"
                pattern                         = "slash"
                nonPreferredRouteMode           = 1
                pitch                           = 0.064
                defaultWidth   		        = 0.032
                minWidth                        = 0.032
                maxWidth                        = 5 
                minSpacing                      = 0.032
                minArea                         = 0.001024
}


Layer		"via0" {
		layerNumber			= 85
		maskName			= "via0"
		isDefaultLayer			= 1
		visible				= 1
		selectable			= 1
		blink				= 0
		color				= "purple"
		lineStyle			= "solid"
		pattern				= "rectangleX"
		defaultWidth			= 0.030
		minWidth			= 0.030 
		minSpacing			= 0.030
}

Layer		"metal1" {
		layerNumber			= 11
		isDefaultLayer			= 1
		maskName			= "metal1"
		visible				= 1
		selectable			= 1
		blink				= 0
		color				= "blue"
		lineStyle			= "solid"
		pattern				= "impdot"
                nonPreferredRouteMode           = 1
		pitch				= 0.108
		minWidth			= 0.054
		defaultWidth			= 0.054
		maxWidth			= 5
		minSpacing			= 0.01
		minArea 			= 0.002916
}

Layer		"via1" {
		layerNumber			= 12
		maskName			= "via1"
		isDefaultLayer			= 1
		visible				= 1
		selectable			= 1
		blink				= 0
		color				= "cyan"
		lineStyle			= "solid"
		pattern				= "rectangleX"
		defaultWidth			= 0.050
		minWidth			= 0.050
		minSpacing			= 0.050
}

Layer		"metal2" {
		layerNumber			= 13
		maskName			= "metal2"
		isDefaultLayer			= 1
		visible				= 1
		selectable			= 1
		blink				= 0
		color				= "50"
		lineStyle			= "solid"
		pattern				= "twelldot"
                nonPreferredRouteMode           = 1
		pitch				= 0.108
		minWidth			= 0.054
		defaultWidth			= 0.054
		maxWidth			= 5
		minSpacing			= 0.054
		minArea 			= 0.002916
}

Layer           "via2" {
                layerNumber                     = 14
                maskName                        = "via2"
                isDefaultLayer                  = 1
                visible                         = 1
                selectable                      = 1
                blink                           = 0
                color                           = "yellow"
                lineStyle                       = "solid"
                pattern                         = "rectangleX"
		defaultWidth			= 0.050
		minWidth			= 0.050
		minSpacing			= 0.050
}

Layer           "metal3" {
                layerNumber                     = 15
                maskName                        = "metal3"
                isDefaultLayer                  = 1
                visible                         = 1
                selectable                      = 1
                blink                           = 0
                color                           = "38"
                lineStyle                       = "solid"
                pattern                         = "hidot"
                nonPreferredRouteMode           = 1
		pitch				= 0.108
		minWidth			= 0.054
		defaultWidth			= 0.054
		maxWidth			= 5
		minSpacing			= 0.054
		minArea 			= 0.002916
}

Layer           "via3" {
                layerNumber                     = 16
                maskName                        = "via3"
                isDefaultLayer                  = 1
                visible                         = 1
                selectable                      = 1
                blink                           = 0
                color                           = "27"
                lineStyle                       = "solid"
                pattern                         = "rectangleX"
		defaultWidth			= 0.050
		minWidth			= 0.050
		minSpacing			= 0.050 
}

Layer           "metal4" {
                layerNumber                     = 17
                maskName                        = "metal4"
                isDefaultLayer                  = 1
                visible                         = 1
                selectable                      = 1
                blink                           = 0
                color                           = "green"
                lineStyle                       = "solid"
                pattern                         = "rhidot"
                nonPreferredRouteMode           = 1
                pitch                           = 0.212
                defaultWidth                    = 0.106 
                minWidth                        = 0.106 
                maxWidth                        = 5
                minSpacing                      = 0.106
                minArea                         = 0.011236
}

Layer           "via4" {
                layerNumber                     = 18
                maskName                        = "via4"
                isDefaultLayer                  = 1
                visible                         = 1
                selectable                      = 1
                blink                           = 0
                color                           = "orange"
                lineStyle                       = "solid"
                pattern                         = "rectangleX"
                defaultWidth                    = 0.102 
                minWidth                        = 0.102 
                minSpacing                      = 0.102
}

Layer           "metal5" {
                layerNumber                     = 19
                maskName                        = "metal5"
                isDefaultLayer                  = 1
                visible                         = 1
                selectable                      = 1
                blink                           = 0
                color                           = "aqua"
                lineStyle                       = "solid"
                pattern                         = "welldot"
                nonPreferredRouteMode           = 1
                pitch                           = 0.212
                defaultWidth                    = 0.106 
                minWidth                        = 0.106 
                maxWidth                        = 5
                minSpacing                      = 0.106
                minArea                         = 0.011236
}

Layer           "via5" {
                layerNumber                     = 20
                maskName                        = "via5"
                isDefaultLayer                  = 1
                visible                         = 1
                selectable                      = 1
                blink                           = 0
                color                           = "40"
                lineStyle                       = "solid"
                pattern                         = "rectangleX"
                defaultWidth                    = 0.102 
                minWidth                        = 0.102 
                minSpacing                      = 0.102
}

Layer           "metal6" {
                layerNumber                     = 21
                maskName                        = "metal6"
                isDefaultLayer                  = 1
                visible                         = 1
                selectable                      = 1
                blink                           = 0
                color                           = "58"
                lineStyle                       = "solid"
                pattern                         = "impdot"
                nonPreferredRouteMode           = 1
                pitch                           = 0.212
                defaultWidth                    = 0.106 
                minWidth                        = 0.106 
                maxWidth                        = 5
                minSpacing                      = 0.106
                minArea                         = 0.011236
}

Layer           "via6" {
                layerNumber                     = 22
                maskName                        = "via6"
                isDefaultLayer                  = 1
                visible                         = 1
                selectable                      = 1
                blink                           = 0
                color                           = "52"
                lineStyle                       = "solid"
                pattern                         = "rectangleX"
                defaultWidth                    = 0.102 
                minWidth                        = 0.102 
                minSpacing                      = 0.102
}

Layer           "metal7" {
                layerNumber                     = 23
                maskName                        = "metal7"
                isDefaultLayer                  = 1
                visible                         = 1
                selectable                      = 1
                blink                           = 0
                color                           = "cyan"
                lineStyle                       = "solid"
                pattern                         = "solid"
                nonPreferredRouteMode           = 1
                pitch                           = 0.256  
                defaultWidth                    = 0.128  
                minWidth                        = 0.128  
                maxWidth                        = 5
                minSpacing                      = 0.128 
                minArea                         = 0.016384
}

Layer           "via7" {
                layerNumber                     = 24
                maskName                        = "via7"
                isDefaultLayer                  = 1
                visible                         = 1
                selectable                      = 1
                blink                           = 0
                color                           = "blue"
                lineStyle                       = "solid"
                pattern                         = "rectangleX"
                defaultWidth                    = 0.124 
                minWidth                        = 0.124
                minSpacing                      = 0.124 
}

Layer           "metal8" {
                layerNumber                     = 25
                maskName                        = "metal8"
                isDefaultLayer                  = 1
                visible                         = 1
                selectable                      = 1
                blink                           = 0
                color                           = "43"
                lineStyle                       = "solid"
                pattern                         = "solid"
                nonPreferredRouteMode           = 1
                pitch                           = 0.256  
                defaultWidth                    = 0.128  
                minWidth                        = 0.128  
                maxWidth                        = 5
                minSpacing                      = 0.128 
                minArea                         = 0.016384
}

Layer           "via8" {
                layerNumber                     = 26
                maskName                        = "via8"
                isDefaultLayer                  = 1
                visible                         = 1
                selectable                      = 1
                blink                           = 0
                color                           = "drab"
                lineStyle                       = "solid"
                pattern                         = "rectangleX"
                defaultWidth                    = 0.124 
                minWidth                        = 0.124
                minSpacing                      = 0.124 
}

Layer           "metal9" {
                layerNumber                     = 27
                maskName                        = "metal9"
                isDefaultLayer                  = 1
                visible                         = 1
                selectable                      = 1
                blink                           = 0
                color                           = "59"
                lineStyle                       = "solid"
                pattern                         = "solid"
                nonPreferredRouteMode           = 1
                pitch                           = 0.428
                defaultWidth                    = 0.214
                minWidth                        = 0.214
                maxWidth                        = 5
                minSpacing                      = 0.214
                minArea                         = 0.045786
}

Layer           "via9" {
                layerNumber                     = 91
                maskName                        = "via9"
                isDefaultLayer                  = 1
                visible                         = 1
                selectable                      = 1
                blink                           = 0
                color                           = "23"
                lineStyle                       = "solid"
                pattern                         = "rectangleX"
                defaultWidth                    = 0.210
                minWidth                        = 0.210
                minSpacing                      = 0.210
}

Layer           "metal10" {
                layerNumber                     = 92
                maskName                        = "metal10"
                isDefaultLayer                  = 1
                visible                         = 1
                selectable                      = 1
                blink                           = 0
                color                           = "32"
                lineStyle                       = "solid"
                pattern                         = "solid"
                nonPreferredRouteMode           = 1
                pitch                           = 0.428
                defaultWidth                    = 0.214
                minWidth                        = 0.214
                maxWidth                        = 5
                minSpacing                      = 0.214
                minArea                         = 0.045786
}

Layer           "via10" {
                layerNumber                     = 93
                maskName                        = "via10"
                isDefaultLayer                  = 1
                visible                         = 1
                selectable                      = 1
                blink                           = 0
                color                           = "54"
                lineStyle                       = "solid"
                pattern                         = "rectangleX"
                defaultWidth                    = 0.210
                minWidth                        = 0.210
                minSpacing                      = 0.210
}

Layer           "metal11" {
                layerNumber                     = 94
                maskName                        = "metal11"
                isDefaultLayer                  = 1
                visible                         = 1
                selectable                      = 1
                blink                           = 0
                color                           = "38"
                lineStyle                       = "solid"
                pattern                         = "solid"
                nonPreferredRouteMode           = 1
                pitch                           = 1.920
                defaultWidth                    = 0.960
                minWidth                        = 0.960
                maxWidth                        = 5
                minSpacing                      = 0.960
                minArea                         = 0.9216
}

Layer           "via11" {
                layerNumber                     = 95
                maskName                        = "via11"
                isDefaultLayer                  = 1
                visible                         = 1
                selectable                      = 1
                blink                           = 0
                color                           = "36"
                lineStyle                       = "solid"
                pattern                         = "rectangleX"
                defaultWidth                    = 0.956
                minWidth                        = 0.956
                minSpacing                      = 0.956
}

Layer           "metal12" {
                layerNumber                     = 96
                maskName                        = "metal12"
                isDefaultLayer                  = 1
                visible                         = 1
                selectable                      = 1
                blink                           = 0
                color                           = "47"
                lineStyle                       = "solid"
                pattern                         = "solid"
                nonPreferredRouteMode           = 1
                pitch                           = 1.920
                defaultWidth                    = 0.960
                minWidth                        = 0.960
                maxWidth                        = 5
                minSpacing                      = 0.960
                minArea                         = 0.9216
}

ContactCode     "via0" {
                contactCodeNumber               = 69
                cutLayer                        = "via0"
                lowerLayer                      = "metal0"
                upperLayer                      = "metal1"
                isDefaultContact                = 1
                cutWidth                        = 0.030
                cutHeight                       = 0.030
                minCutSpacing                   = 0.030
                upperLayerEncWidth              = 0.00
                upperLayerEncHeight             = 0.00
                lowerLayerEncWidth              = 0.00
                lowerLayerEncHeight             = 0.00
}

ContactCode	"via1" {
		contactCodeNumber		= 5
		cutLayer			= "via1"
		lowerLayer			= "metal1"
		upperLayer			= "metal2"
		isDefaultContact		= 1
		cutWidth			= 0.050 
		cutHeight			= 0.050
		minCutSpacing			= 0.050
		upperLayerEncWidth		= 0.00
		upperLayerEncHeight		= 0.00 
		lowerLayerEncWidth		= 0.00
		lowerLayerEncHeight		= 0.00 
}

ContactCode     "via2" {
                contactCodeNumber               = 13
                cutLayer                        = "via2"
                lowerLayer                      = "metal2"
                upperLayer                      = "metal3"
                isDefaultContact                = 1
		cutWidth			= 0.050 
		cutHeight			= 0.050
		minCutSpacing			= 0.050
                upperLayerEncWidth              = 0.00
                upperLayerEncHeight             = 0.00
                lowerLayerEncWidth              = 0.00
                lowerLayerEncHeight             = 0.00
}

ContactCode     "via3" {
                contactCodeNumber               = 21
                cutLayer                        = "via3"
                lowerLayer                      = "metal3"
                upperLayer                      = "metal4"
                isDefaultContact                = 1
		cutWidth			= 0.050 
		cutHeight			= 0.050
		minCutSpacing			= 0.050
                upperLayerEncWidth              = 0.00
                upperLayerEncHeight             = 0.00
                lowerLayerEncWidth              = 0.00
                lowerLayerEncHeight             = 0.00
}

ContactCode     "via4" {
                contactCodeNumber               = 29
                cutLayer                        = "via4"
                lowerLayer                      = "metal4"
                upperLayer                      = "metal5"
                isDefaultContact                = 1
                cutWidth                        = 0.102 
                cutHeight                       = 0.102 
                minCutSpacing                   = 0.102 
                upperLayerEncWidth              = 0.00
                upperLayerEncHeight             = 0.00
                lowerLayerEncWidth              = 0.00
                lowerLayerEncHeight             = 0.00
}

ContactCode     "via5" {
                contactCodeNumber               = 37
                cutLayer                        = "via5"
                lowerLayer                      = "metal5"
                upperLayer                      = "metal6"
                isDefaultContact                = 1
                cutWidth                        = 0.102 
                cutHeight                       = 0.102 
                minCutSpacing                   = 0.102 
                upperLayerEncWidth              = 0.00
                upperLayerEncHeight             = 0.00
                lowerLayerEncWidth              = 0.00
                lowerLayerEncHeight             = 0.00
}

ContactCode     "via6" {
                contactCodeNumber               = 45
                cutLayer                        = "via6"
                lowerLayer                      = "metal6"
                upperLayer                      = "metal7"
                isDefaultContact                = 1
                cutWidth                        = 0.102 
                cutHeight                       = 0.102 
                minCutSpacing                   = 0.102 
                upperLayerEncWidth              = 0.00
                upperLayerEncHeight             = 0.00
                lowerLayerEncWidth              = 0.00
                lowerLayerEncHeight             = 0.00
}

ContactCode     "via7" {
                contactCodeNumber               = 53
                cutLayer                        = "via7"
                lowerLayer                      = "metal7"
                upperLayer                      = "metal8"
                isDefaultContact                = 1
                cutWidth                        = 0.124 
                cutHeight                       = 0.124  
                minCutSpacing                   = 0.124  
                upperLayerEncWidth              = 0.00
                upperLayerEncHeight             = 0.00
                lowerLayerEncWidth              = 0.00
                lowerLayerEncHeight             = 0.00
}

ContactCode     "via8" {
                contactCodeNumber               = 61
                cutLayer                        = "via8"
                lowerLayer                      = "metal8"
                upperLayer                      = "metal9"
                isDefaultContact                = 1
                cutWidth                        = 0.124 
                cutHeight                       = 0.124  
                minCutSpacing                   = 0.124  
                upperLayerEncWidth              = 0.00
                upperLayerEncHeight             = 0.00
                lowerLayerEncWidth              = 0.00
                lowerLayerEncHeight             = 0.00
}

ContactCode     "via9" {
                contactCodeNumber               = 77
                cutLayer                        = "via9"
                lowerLayer                      = "metal9"
                upperLayer                      = "metal10"
                isDefaultContact                = 1
                cutWidth                        = 0.210  
                cutHeight                       = 0.210
                minCutSpacing                   = 0.210 
                upperLayerEncWidth              = 0.00
                upperLayerEncHeight             = 0.00
                lowerLayerEncWidth              = 0.00
                lowerLayerEncHeight             = 0.00
}

ContactCode     "via10" {
                contactCodeNumber               = 85
                cutLayer                        = "via10"
                lowerLayer                      = "metal10"
                upperLayer                      = "metal11"
                isDefaultContact                = 1
                cutWidth                        = 0.210  
                cutHeight                       = 0.210
                minCutSpacing                   = 0.210 
                upperLayerEncWidth              = 0.00
                upperLayerEncHeight             = 0.00
                lowerLayerEncWidth              = 0.00
                lowerLayerEncHeight             = 0.00
}

ContactCode     "via11" {
                contactCodeNumber               = 93
                cutLayer                        = "via11"
                lowerLayer                      = "metal11"
                upperLayer                      = "metal12"
                isDefaultContact                = 1
                cutWidth                        = 0.956 
                cutHeight                       = 0.956
                minCutSpacing                   = 0.956 
                upperLayerEncWidth              = 0.00
                upperLayerEncHeight             = 0.00
                lowerLayerEncWidth              = 0.00
                lowerLayerEncHeight             = 0.00
}


PRRule		{
		rowSpacingTopTop		= 0.067
		rowSpacingTopBot		= 0.033
		rowSpacingBotBot		= 0.067
		abuttableTopTop			= 1
		abuttableTopBot			= 0
		abuttableBotBot			= 1
}

