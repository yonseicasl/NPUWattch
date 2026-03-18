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
  name = "nsfet3nm"
  date = "Oct 14 2020"
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

Tile		"i3d_nsfet3nm" {
		width				= 0.044 
		height				= 0.12  
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
                pitch                           = 0.024
                defaultWidth   		        = 0.012
                minWidth                        = 0.012
                maxWidth                        = 5 
                minSpacing                      = 0.012
                minArea                         = 0.000144 
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
		defaultWidth			= 0.01
		minWidth			= 0.01 
		minSpacing			= 0.01
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
		pitch				= 0.044 
		minWidth			= 0.016 
		defaultWidth			= 0.016 
		maxWidth			= 5
		minSpacing			= 0.028
		minArea 			= 0.000256
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
		defaultWidth			= 0.016
		minWidth			= 0.016 
		minSpacing			= 0.016
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
		pitch				= 0.032
		defaultWidth			= 0.016 
		minWidth			= 0.016 
		maxWidth			= 5
		minSpacing			= 0.016
		minArea 			= 0.000256
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
                defaultWidth                    = 0.016 
                minWidth                        = 0.016 
                minSpacing                      = 0.016
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
                pitch                           = 0.032
                defaultWidth                    = 0.016 
                minWidth                        = 0.016 
                maxWidth                        = 5
                minSpacing                      = 0.016
                minArea                         = 0.000256
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
                defaultWidth                    = 0.016 
                minWidth                        = 0.016 
                minSpacing                      = 0.016 
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
                pitch                           = 0.064
                defaultWidth                    = 0.032 
                minWidth                        = 0.032 
                maxWidth                        = 5
                minSpacing                      = 0.032
                minArea                         = 0.001024
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
                defaultWidth                    = 0.032 
                minWidth                        = 0.032 
                minSpacing                      = 0.032 
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
                pitch                           = 0.064 
                defaultWidth                    = 0.032 
                minWidth                        = 0.032 
                maxWidth                        = 5
                minSpacing                      = 0.032
                minArea                         = 0.001024
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
                defaultWidth                    = 0.032 
                minWidth                        = 0.032 
                minSpacing                      = 0.032 
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
                pitch                           = 0.064 
                defaultWidth                    = 0.032 
                minWidth                        = 0.032 
                maxWidth                        = 5
                minSpacing                      = 0.032
                minArea                         = 0.001024
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
                defaultWidth                    = 0.032 
                minWidth                        = 0.032 
                minSpacing                      = 0.032 
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
                pitch                           = 0.08  
                defaultWidth                    = 0.04  
                minWidth                        = 0.04  
                maxWidth                        = 5
                minSpacing                      = 0.04 
                minArea                         = 0.0016
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
                defaultWidth                    = 0.04 
                minWidth                        = 0.04
                minSpacing                      = 0.04 
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
                pitch                           = 0.08
                defaultWidth                    = 0.04 
                minWidth                        = 0.04 
                maxWidth                        = 5
                minSpacing                      = 0.04 
                minArea                         = 0.0016
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
                defaultWidth                    = 0.04 
                minWidth                        = 0.04 
                minSpacing                      = 0.04 
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
                pitch                           = 0.12
                defaultWidth                    = 0.06 
                minWidth                        = 0.06 
                maxWidth                        = 5
                minSpacing                      = 0.06 
                minArea                         = 0.0036
}

Layer           "via9" {
                layerNumber                     = 98
                maskName                        = "via9"
                isDefaultLayer                  = 1
                visible                         = 1
                selectable                      = 1
                blink                           = 0
                color                           = "23"
                lineStyle                       = "solid"
                pattern                         = "rectangleX"
                defaultWidth                    = 0.06 
                minWidth                        = 0.06 
                minSpacing                      = 0.06 
}

Layer           "metal10" {
                layerNumber                     = 99
                maskName                        = "metal10"
                isDefaultLayer                  = 1
                visible                         = 1
                selectable                      = 1
                blink                           = 0
                color                           = "32"
                lineStyle                       = "solid"
                pattern                         = "solid"
                nonPreferredRouteMode           = 1
                pitch                           = 0.12
                defaultWidth                    = 0.06 
                minWidth                        = 0.06 
                maxWidth                        = 5
                minSpacing                      = 0.06 
                minArea                         = 0.0036
}

Layer           "via10" {
                layerNumber                     = 100
                maskName                        = "via10"
                isDefaultLayer                  = 1
                visible                         = 1
                selectable                      = 1
                blink                           = 0
                color                           = "54"
                lineStyle                       = "solid"
                pattern                         = "rectangleX"
                defaultWidth                    = 0.06
                minWidth                        = 0.06 
                minSpacing                      = 0.06 
}

Layer           "metal11" {
                layerNumber                     = 101
                maskName                        = "metal11"
                isDefaultLayer                  = 1
                visible                         = 1
                selectable                      = 1
                blink                           = 0
                color                           = "38"
                lineStyle                       = "solid"
                pattern                         = "solid"
                nonPreferredRouteMode           = 1
                pitch                           = 0.6
                defaultWidth                    = 0.3 
                minWidth                        = 0.3 
                maxWidth                        = 5
                minSpacing                      = 0.3 
                minArea                         = 0.09
}

Layer           "via11" {
                layerNumber                     = 102
                maskName                        = "via11"
                isDefaultLayer                  = 1
                visible                         = 1
                selectable                      = 1
                blink                           = 0
                color                           = "36"
                lineStyle                       = "solid"
                pattern                         = "rectangleX"
                defaultWidth                    = 0.3 
                minWidth                        = 0.3
                minSpacing                      = 0.3 
}

Layer           "metal12" {
                layerNumber                     = 103
                maskName                        = "metal12"
                isDefaultLayer                  = 1
                visible                         = 1
                selectable                      = 1
                blink                           = 0
                color                           = "47"
                lineStyle                       = "solid"
                pattern                         = "solid"
                nonPreferredRouteMode           = 1
                pitch                           = 0.6
                defaultWidth                    = 0.3 
                minWidth                        = 0.3 
                maxWidth                        = 5
                minSpacing                      = 0.3 
                minArea                         = 0.09
}

ContactCode     "via01" {
                contactCodeNumber               = 69
                cutLayer                        = "via0"
                lowerLayer                      = "metal0"
                upperLayer                      = "metal1"
                isDefaultContact                = 1
                cutWidth                        = 0.01
                cutHeight                       = 0.01
                minCutSpacing                   = 0.01
                upperLayerEncWidth              = 0.00
                upperLayerEncHeight             = 0.00
                lowerLayerEncWidth              = 0.00
                lowerLayerEncHeight             = 0.00
}

ContactCode	"via12" {
		contactCodeNumber		= 5
		cutLayer			= "via1"
		lowerLayer			= "metal1"
		upperLayer			= "metal2"
		isDefaultContact		= 1
		cutWidth			= 0.016 
		cutHeight			= 0.016 
		minCutSpacing			= 0.016 
		upperLayerEncWidth		= 0.00
		upperLayerEncHeight		= 0.00 
		lowerLayerEncWidth		= 0.00
		lowerLayerEncHeight		= 0.00 
}

ContactCode     "via23" {
                contactCodeNumber               = 13
                cutLayer                        = "via2"
                lowerLayer                      = "metal2"
                upperLayer                      = "metal3"
                isDefaultContact                = 1
                cutWidth                        = 0.016 
                cutHeight                       = 0.016 
                minCutSpacing                   = 0.016 
                upperLayerEncWidth              = 0.00
                upperLayerEncHeight             = 0.00
                lowerLayerEncWidth              = 0.00
                lowerLayerEncHeight             = 0.00
}

ContactCode     "via34" {
                contactCodeNumber               = 21
                cutLayer                        = "via3"
                lowerLayer                      = "metal3"
                upperLayer                      = "metal4"
                isDefaultContact                = 1
                cutWidth                        = 0.016 
                cutHeight                       = 0.016
                minCutSpacing                   = 0.016 
                upperLayerEncWidth              = 0.00
                upperLayerEncHeight             = 0.00
                lowerLayerEncWidth              = 0.00
                lowerLayerEncHeight             = 0.00
}

ContactCode     "via45" {
                contactCodeNumber               = 29
                cutLayer                        = "via4"
                lowerLayer                      = "metal4"
                upperLayer                      = "metal5"
                isDefaultContact                = 1
                cutWidth                        = 0.032 
                cutHeight                       = 0.032 
                minCutSpacing                   = 0.032 
                upperLayerEncWidth              = 0.00
                upperLayerEncHeight             = 0.00
                lowerLayerEncWidth              = 0.00
                lowerLayerEncHeight             = 0.00
}

ContactCode     "via56" {
                contactCodeNumber               = 37
                cutLayer                        = "via5"
                lowerLayer                      = "metal5"
                upperLayer                      = "metal6"
                isDefaultContact                = 1
                cutWidth                        = 0.032 
                cutHeight                       = 0.032 
                minCutSpacing                   = 0.032 
                upperLayerEncWidth              = 0.00
                upperLayerEncHeight             = 0.00
                lowerLayerEncWidth              = 0.00
                lowerLayerEncHeight             = 0.00
}

ContactCode     "via67" {
                contactCodeNumber               = 45
                cutLayer                        = "via6"
                lowerLayer                      = "metal6"
                upperLayer                      = "metal7"
                isDefaultContact                = 1
                cutWidth                        = 0.032 
                cutHeight                       = 0.032 
                minCutSpacing                   = 0.032 
                upperLayerEncWidth              = 0.00
                upperLayerEncHeight             = 0.00
                lowerLayerEncWidth              = 0.00
                lowerLayerEncHeight             = 0.00
}

ContactCode     "via78" {
                contactCodeNumber               = 53
                cutLayer                        = "via7"
                lowerLayer                      = "metal7"
                upperLayer                      = "metal8"
                isDefaultContact                = 1
                cutWidth                        = 0.04  
                cutHeight                       = 0.04  
                minCutSpacing                   = 0.04  
                upperLayerEncWidth              = 0.00
                upperLayerEncHeight             = 0.00
                lowerLayerEncWidth              = 0.00
                lowerLayerEncHeight             = 0.00
}

ContactCode     "via89" {
                contactCodeNumber               = 61
                cutLayer                        = "via8"
                lowerLayer                      = "metal8"
                upperLayer                      = "metal9"
                isDefaultContact                = 1
                cutWidth                        = 0.04  
                cutHeight                       = 0.04 
                minCutSpacing                   = 0.04  
                upperLayerEncWidth              = 0.00
                upperLayerEncHeight             = 0.00
                lowerLayerEncWidth              = 0.00
                lowerLayerEncHeight             = 0.00
}

ContactCode     "via910" {
                contactCodeNumber               = 77
                cutLayer                        = "via9"
                lowerLayer                      = "metal9"
                upperLayer                      = "metal10"
                isDefaultContact                = 1
                cutWidth                        = 0.06  
                cutHeight                       = 0.06 
                minCutSpacing                   = 0.06  
                upperLayerEncWidth              = 0.00
                upperLayerEncHeight             = 0.00
                lowerLayerEncWidth              = 0.00
                lowerLayerEncHeight             = 0.00
}

ContactCode     "via1011" {
                contactCodeNumber               = 85
                cutLayer                        = "via10"
                lowerLayer                      = "metal10"
                upperLayer                      = "metal11"
                isDefaultContact                = 1
                cutWidth                        = 0.06  
                cutHeight                       = 0.06 
                minCutSpacing                   = 0.06  
                upperLayerEncWidth              = 0.00
                upperLayerEncHeight             = 0.00
                lowerLayerEncWidth              = 0.00
                lowerLayerEncHeight             = 0.00
}

ContactCode     "via1112" {
                contactCodeNumber               = 93
                cutLayer                        = "via11"
                lowerLayer                      = "metal11"
                upperLayer                      = "metal12"
                isDefaultContact                = 1
                cutWidth                        = 0.3  
                cutHeight                       = 0.3 
                minCutSpacing                   = 0.3  
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

