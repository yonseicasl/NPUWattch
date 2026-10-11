
// Single Batch Conv2D kernel
// BATCH = 1
// I_C = 128
// I_H = 28
// I_W = 28
// O_C = 128
// K_H = 3
// K_W = 3
// O_H = 28
// O_W = 28
// TILE_M = 32
// TILE_N = 128
// TILE_K = 128
// TILE_I_H=30,
// TILE_I_W=32,
// TILE_O_H=28,
// TILE_O_W=32,
// TILE_K_H=3,
// TILE_K_W=1,
// SUB_TILE_M=32,
// SUB_TILE_N=128,
// SUB_TILE_I_W=1,
// SUB_TILE_K_H=1,
// SUB_TILE_K_W=1,
// PADDING_H = 1
// PADDING_W = 1
// STRIDE_H = 1
// STRIDE_W = 1
// DATA_STYPE = f32

#map_I_H = affine_map<(d0, d1) -> (d0 * 1 + d1)>
#map_I_W = affine_map<(d0, d1) -> (d0 * 1 + d1)>
#offset_w_map = affine_map<(d0, d1) -> (d0 * 128 + d1 * 128)>
#offset_x_map = affine_map<(d0, d1) -> (d0 * 32 + d1)>
#offset_y_map = affine_map<(d0, d1) -> (d0 * 32 + d1 * 32)>
memref.global @X_spad : memref<1x30x32x128xf32, 1>
memref.global @W_spad : memref<3x1x128x128xf32, 1>
memref.global @Y_spad : memref<1x128x28x32xf32, 1>
#t_map0 = affine_map<(d0, d1, d2, d3) -> (784*d1 + 28*d2 + d3)>
#t_map1 = affine_map<(d0, d1, d2, d3) -> (115200*d0 + 3840*d1 + 128*d2 + d3)>
#t_map2 = affine_map<(d0, d1, d2, d3) -> (49152*d0 + 16384*d1 + 128*d2 + d3)>

func.func @kernel(%X: memref<115200xf32>, %W: memref<147456xf32>, %Y: memref<100352xf32>) {
  %input_buffer = memref.get_global @X_spad : memref<1x30x32x128xf32, 1>
  %weight_buffer = memref.get_global @W_spad : memref<3x1x128x128xf32, 1>
  %output_buffer = memref.get_global @Y_spad : memref<1x128x28x32xf32, 1>
  %v0 = arith.constant dense<0.0> : vector<896xf32>
  %c0 = arith.constant 0 : index%t_const0 = arith.constant 0 : index
  %t_const1 = arith.constant 1 : index
  %t_const2 = arith.constant 3 : index
  %t_const3 = arith.constant 2 : index
  %t_alloc0 = memref.alloc() : memref<1xi32> // 0
  %t_alloc1 = memref.alloc() : memref<1xi32> // 1
  %t_alloc2 = memref.alloc() : memref<1xi32> // 2
  affine.for %tile_n = 0 to 128 step 128 {
    affine.for %o_h = 0 to 28 step 28 {
      affine.for %tile_m = 0 to 28 step 32 {
        // Initialize output
        affine.vector_store %v0, %output_buffer[%c0, %c0, %c0, %c0] : memref<1x128x28x32xf32, 1>, vector<896xf32>
        affine.for %k_h = 0 to 3 step 3 {
          affine.for %k_w = 0 to 3 step 1 {
            affine.for %tile_k = 0 to 128 step 128 {
              %index_i_h = affine.apply #map_I_H(%o_h, %k_h)
              %index_i_w = affine.apply #map_I_W(%tile_m, %k_w)
              // Load input & weight matrix
              %apply0 = affine.apply #t_map1(%c0, %index_i_h, %index_i_w, %tile_k)
              memref.dma_start %X[%apply0], %input_buffer[%t_const0, %t_const0, %t_const0, %t_const0], %t_const3, %t_alloc1[%t_const0], %t_const2, %t_const1 : memref<115200xf32>, memref<1x30x32x128xf32, 1>, memref<1xi32> {dram_stride = [115200, 3840, 128, 1], sram_stride = [122880, 4096, 1, 32], padding = 0, subtile_size = [1, 1, 32, 128], async = 1 : i64}
              %apply1 = affine.apply #t_map2(%k_h, %k_w, %tile_k, %tile_n)
              memref.dma_start %W[%apply1], %weight_buffer[%t_const0, %t_const0, %t_const0, %t_const0], %t_const3, %t_alloc2[%t_const0], %t_const2, %t_const1 : memref<147456xf32>, memref<3x1x128x128xf32, 1>, memref<1xi32> {dram_stride = [49152, 16384, 128, 1], sram_stride = [16384, 16384, 1, 128], padding = 0, subtile_size = [1, 1, 128, 128], async = 1 : i64}
              // Compute body part
              affine.for %tile_k_h = 0 to 3 { // loop order should be fixed for timing simulation. Do not change this order.
                affine.for %tile_k_w = 0 to 1 {
                  %offset_w = affine.apply #offset_w_map(%tile_k_h, %tile_k_w)
                  %W_buffer = memref.reinterpret_cast %weight_buffer to offset: [%offset_w], sizes: [128, 128], strides: [128, 1] : memref<3x1x128x128xf32, 1> to memref<128x128xf32, strided<[128, 1], offset: ?>, 1>
                  affine.for %tile_o_h = 0 to 28 {
                    affine.for %tile_o_w = 0 to 1 { // TILE_O_W
                      %tile_i_h = affine.apply #map_I_H(%tile_o_h, %tile_k_h)
                      %offset_x = affine.apply #offset_x_map(%tile_i_h, %tile_k_w)
                      %offset_y = affine.apply #offset_y_map(%tile_o_h, %tile_o_w)
                      %X_buffer = memref.reinterpret_cast %input_buffer to offset: [%offset_x], sizes: [32, 128], strides: [128, 1] : memref<1x30x32x128xf32, 1> to memref<32x128xf32, strided<[128, 1], offset: ?>, 1>
                      %Y_buffer = memref.reinterpret_cast %output_buffer to offset: [%offset_y], sizes: [32, 128], strides: [128, 1] : memref<1x128x28x32xf32, 1> to memref<32x128xf32, strided<[128, 1], offset: ?>, 1>
                      linalg.matmul ins(%X_buffer, %W_buffer : memref<32x128xf32, strided<[128, 1], offset: ?>, 1>, memref<128x128xf32, strided<[128, 1], offset: ?>, 1>)
                            outs(%Y_buffer : memref<32x128xf32, strided<[128, 1], offset: ?>, 1>)
                    } { inner_loop=true }
                  } { inner_loop=true }
                } { inner_loop=true }
              } { inner_loop=true }
            } { accumulation_loop=true, subtile_loop="k" }
          } { accumulation_loop=true }
        } { accumulation_loop=true }
        // Store output matrix
        affine.for %compute_idx = 0 to 1 step 1
        {
        } {inner_loop=false}
        %epilogue_apply0 = affine.apply #t_map0(%t_const0, %tile_n, %o_h, %tile_m)
        memref.dma_start %output_buffer[%t_const0, %t_const0, %t_const0, %t_const0], %Y[%epilogue_apply0], %t_const2, %t_alloc0[%t_const0], %t_const1, %t_const1 : memref<1x128x28x32xf32, 1>, memref<100352xf32>, memref<1xi32> {dram_stride = [0, 784, 28, 1], sram_stride = [114688, 32, 4096, 1], padding = 0}
      } { outer_loop=true, subtile_loop="m" }
    } { outer_loop=true }
  } { outer_loop=true, subtile_loop="n" }
  return
}
