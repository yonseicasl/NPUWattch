#########################################################################################
# Nangate 45nm milkyway technology file							#
# created by Taigon Song								#
# drawing grid:   0.001 microns								#
#											#
# Revision History:									#
# Rev.		date		what							#
# -------------------------------------------------------------------------------------	#	
# 1.0		26/July/2019	(First draft)						#
# 1.1           10/Sept./2019   changed M1 metal2 spacing, layer numbers                    #
#########################################################################################

Technology {
  name = "finfet10nm"
  date = "Oct 13 2020"
  unitTimeName = "ns"
  timePrecision = 1000
  unitLengthName = "micron"
  lengthPrecision = 1000
  unitVoltageName = "V"
  voltagePrecision = 10000000
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

Tile		"finfet10nm" {
		width				= 0.08 
		height				= 0.384 
}

Layer           "M0" {
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
                pitch                           = 0.048
                defaultWidth   		        = 0.024
                minWidth                        = 0.024
                maxWidth                        = 5 
                minSpacing                      = 0.024
                minArea                         = 0.000576
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
		defaultWidth			= 0.022
		minWidth			= 0.022
		minSpacing			= 0.022
}

Layer		"M1" {
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
		pitch				= 0.080
		minWidth			= 0.040 
		defaultWidth			= 0.040 
		maxWidth			= 5
		minSpacing			= 0.008
		minArea 			= 0.0016
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
		defaultWidth			= 0.036
		minWidth			= 0.036 
		minSpacing			= 0.036
}

Layer		"M2" {
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
		pitch				= 0.080
		minWidth			= 0.040 
		defaultWidth			= 0.040 
		maxWidth			= 5
		minSpacing			= 0.040
		minArea 			= 0.0016
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
                defaultWidth                    = 0.036 
                minWidth                        = 0.036 
                minSpacing                      = 0.036
}

Layer           "M3" {
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
                pitch				= 0.080
		minWidth			= 0.040 
		defaultWidth			= 0.040 
		maxWidth			= 5
		minSpacing			= 0.040
		minArea 			= 0.0016
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
                defaultWidth                    = 0.036 
                minWidth                        = 0.036 
                minSpacing                      = 0.036 
}

Layer           "M4" {
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
                pitch                           = 0.160
                defaultWidth                    = 0.080 
                minWidth                        = 0.080 
                maxWidth                        = 5
                minSpacing                      = 0.080
                minArea                         = 0.0064
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
                defaultWidth                    = 0.076 
                minWidth                        = 0.076 
                minSpacing                      = 0.076 
}

Layer           "M5" {
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
                pitch                           = 0.160
                defaultWidth                    = 0.080 
                minWidth                        = 0.080 
                maxWidth                        = 5
                minSpacing                      = 0.080
                minArea                         = 0.0064
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
                defaultWidth                    = 0.076 
                minWidth                        = 0.076 
                minSpacing                      = 0.076 
}

Layer           "M6" {
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
                pitch                           = 0.160
                defaultWidth                    = 0.080 
                minWidth                        = 0.080 
                maxWidth                        = 5
                minSpacing                      = 0.080
                minArea                         = 0.0064
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
                defaultWidth                    = 0.076 
                minWidth                        = 0.076 
                minSpacing                      = 0.076 
}

Layer           "M7" {
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
                pitch                           = 0.192  
                defaultWidth                    = 0.096  
                minWidth                        = 0.096  
                maxWidth                        = 5
                minSpacing                      = 0.096 
                minArea                         = 0.009216
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
                defaultWidth                    = 0.092 
                minWidth                        = 0.092
                minSpacing                      = 0.092 
}

Layer           "M8" {
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
                pitch                           = 0.192  
                defaultWidth                    = 0.096  
                minWidth                        = 0.096  
                maxWidth                        = 5
                minSpacing                      = 0.096 
                minArea                         = 0.009216
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
                defaultWidth                    = 0.092 
                minWidth                        = 0.092
                minSpacing                      = 0.092  
}

Layer           "M9" {
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
                pitch                           = 0.32
                defaultWidth                    = 0.16 
                minWidth                        = 0.16 
                maxWidth                        = 5
                minSpacing                      = 0.16 
                minArea                         = 0.0256
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
                defaultWidth                    = 0.092 
                minWidth                        = 0.092
                minSpacing                      = 0.092
}

Layer           "M10" {
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
                pitch                           = 0.32
                defaultWidth                    = 0.16 
                minWidth                        = 0.16 
                maxWidth                        = 5
                minSpacing                      = 0.16 
                minArea                         = 0.0256
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
                defaultWidth                    = 0.092 
                minWidth                        = 0.092
                minSpacing                      = 0.092 
}

Layer           "M11" {
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
                pitch                           = 1.440
                defaultWidth                    = 0.72 
                minWidth                        = 0.72 
                maxWidth                        = 5
                minSpacing                      = 0.72 
                minArea                         = 0.5184
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
                defaultWidth                    = 0.716 
                minWidth                        = 0.716
                minSpacing                      = 0.716 
}

Layer           "M12" {
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
                pitch                           = 1.440
                defaultWidth                    = 0.72 
                minWidth                        = 0.72 
                maxWidth                        = 5
                minSpacing                      = 0.72 
                minArea                         = 0.5184
}

ContactCode     "VIA0" {
                contactCodeNumber               = 69
                cutLayer                        = "via0"
                lowerLayer                      = "M0"
                upperLayer                      = "M1"
                isDefaultContact                = 1
                cutWidth                        = 0.022
                cutHeight                       = 0.022
                minCutSpacing                   = 0.022
                upperLayerEncWidth              = 0.0011
                upperLayerEncHeight             = 0.0011
                lowerLayerEncWidth              = 0.0011
                lowerLayerEncHeight             = 0.0011
}

ContactCode	"VIA1" {
		contactCodeNumber		= 5
		cutLayer			= "via1"
		lowerLayer			= "M1"
		upperLayer			= "M2"
		isDefaultContact		= 1
		cutWidth			= 0.036 
		cutHeight			= 0.036 
		minCutSpacing			= 0.036 
		upperLayerEncWidth		= 0.0011
		upperLayerEncHeight		= 0.0011
		lowerLayerEncWidth		= 0.0011
		lowerLayerEncHeight		= 0.0011 
}

ContactCode     "VIA2" {
                contactCodeNumber               = 13
                cutLayer                        = "via2"
                lowerLayer                      = "M2"
                upperLayer                      = "M3"
                isDefaultContact                = 1
                cutWidth			= 0.036 
		cutHeight			= 0.036 
		minCutSpacing			= 0.036 
                upperLayerEncWidth              = 0.001
                upperLayerEncHeight             = 0.001
                lowerLayerEncWidth              = 0.001
                lowerLayerEncHeight             = 0.001
}

ContactCode     "VIA3" {
                contactCodeNumber               = 21
                cutLayer                        = "via3"
                lowerLayer                      = "M3"
                upperLayer                      = "M4"
                isDefaultContact                = 1
                cutWidth			= 0.036 
		cutHeight			= 0.036 
		minCutSpacing			= 0.036 
                upperLayerEncWidth              = 0.001
                upperLayerEncHeight             = 0.001
                lowerLayerEncWidth              = 0.001
                lowerLayerEncHeight             = 0.001
}

ContactCode     "VIA4" {
                contactCodeNumber               = 29
                cutLayer                        = "via4"
                lowerLayer                      = "M4"
                upperLayer                      = "M5"
                isDefaultContact                = 1
                cutWidth                        = 0.076 
                cutHeight                       = 0.076 
                minCutSpacing                   = 0.076 
                upperLayerEncWidth              = 0.001
                upperLayerEncHeight             = 0.001
                lowerLayerEncWidth              = 0.001
                lowerLayerEncHeight             = 0.001
}

ContactCode     "VIA5" {
                contactCodeNumber               = 37
                cutLayer                        = "via5"
                lowerLayer                      = "M5"
                upperLayer                      = "M6"
                isDefaultContact                = 1
                cutWidth                        = 0.076 
                cutHeight                       = 0.076 
                minCutSpacing                   = 0.076
                upperLayerEncWidth              = 0.001
                upperLayerEncHeight             = 0.001
                lowerLayerEncWidth              = 0.001
                lowerLayerEncHeight             = 0.001
}

ContactCode     "VIA6" {
                contactCodeNumber               = 45
                cutLayer                        = "via6"
                lowerLayer                      = "M6"
                upperLayer                      = "M7"
                isDefaultContact                = 1
                cutWidth                        = 0.076 
                cutHeight                       = 0.076 
                minCutSpacing                   = 0.076
                upperLayerEncWidth              = 0.001
                upperLayerEncHeight             = 0.001
                lowerLayerEncWidth              = 0.001
                lowerLayerEncHeight             = 0.001
}

ContactCode     "VIA7" {
                contactCodeNumber               = 53
                cutLayer                        = "via7"
                lowerLayer                      = "M7"
                upperLayer                      = "M8"
                isDefaultContact                = 1
                cutWidth                        = 0.092  
                cutHeight                       = 0.092  
                minCutSpacing                   = 0.092  
                upperLayerEncWidth              = 0.001
                upperLayerEncHeight             = 0.001
                lowerLayerEncWidth              = 0.001
                lowerLayerEncHeight             = 0.001
}

ContactCode     "VIA8" {
                contactCodeNumber               = 61
                cutLayer                        = "via8"
                lowerLayer                      = "M8"
                upperLayer                      = "M9"
                isDefaultContact                = 1
                cutWidth                        = 0.092  
                cutHeight                       = 0.092  
                minCutSpacing                   = 0.092  
                upperLayerEncWidth              = 0.001
                upperLayerEncHeight             = 0.001
                lowerLayerEncWidth              = 0.001
                lowerLayerEncHeight             = 0.001
}

ContactCode     "VIA9" {
                contactCodeNumber               = 77
                cutLayer                        = "via9"
                lowerLayer                      = "M9"
                upperLayer                      = "M10"
                isDefaultContact                = 1
                cutWidth                        = 0.156  
                cutHeight                       = 0.156
                minCutSpacing                   = 0.156  
                upperLayerEncWidth              = 0.001
                upperLayerEncHeight             = 0.001
                lowerLayerEncWidth              = 0.001
                lowerLayerEncHeight             = 0.001
}

ContactCode     "VIA10" {
                contactCodeNumber               = 85
                cutLayer                        = "via10"
                lowerLayer                      = "M10"
                upperLayer                      = "M11"
                isDefaultContact                = 1
                cutWidth                        = 0.156  
                cutHeight                       = 0.156
                minCutSpacing                   = 0.156  
                upperLayerEncWidth              = 0.001
                upperLayerEncHeight             = 0.001
                lowerLayerEncWidth              = 0.001
                lowerLayerEncHeight             = 0.001
}

ContactCode     "VIA11" {
                contactCodeNumber               = 93
                cutLayer                        = "via11"
                lowerLayer                      = "M11"
                upperLayer                      = "M12"
                isDefaultContact                = 1
                cutWidth                        = 0.716 
                cutHeight                       = 0.716
                minCutSpacing                   = 0.716  
                upperLayerEncWidth              = 0.001
                upperLayerEncHeight             = 0.001
                lowerLayerEncWidth              = 0.001
                lowerLayerEncHeight             = 0.001
}

