
// Single Batch Conv2D kernel
// BATCH = 1
// I_C = 512
// I_H = 7
// I_W = 7
// O_C = 512
// K_H = 3
// K_W = 3
// O_H = 7
// O_W = 7
// TILE_M = 8
// TILE_N = 512
// TILE_K = 512
// TILE_I_H=7,
// TILE_I_W=8,
// TILE_O_H=7,
// TILE_O_W=8,
// TILE_K_H=1,
// TILE_K_W=1,
// SUB_TILE_M=8,
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
#offset_w_map = affine_map<(d0, d1) -> (d0 * 2048 + d1 * 2048)>
#offset_x_map = affine_map<(d0, d1) -> (d0 * 32 + d1)>
#offset_y_map = affine_map<(d0, d1) -> (d0 * 32 + d1 * 32)>
memref.global @X_spad : memref<1x7x8x512xf32, 1>
memref.global @W_spad : memref<1x1x512x512xf32, 1>
memref.global @Y_spad : memref<1x512x7x8xf32, 1>
#t_map0 = affine_map<(d0, d1, d2, d3) -> (49*d1 + 7*d2 + d3)>
#t_map1 = affine_map<(d0, d1, d2, d3) -> (41472*d0 + 4608*d1 + 512*d2 + d3)>
#t_map2 = affine_map<(d0, d1, d2, d3) -> (786432*d0 + 262144*d1 + 512*d2 + d3)>

func.func @kernel(%X: memref<41472xf32>, %W: memref<2359296xf32>, %Y: memref<25088xf32>) {
  %input_buffer = memref.get_global @X_spad : memref<1x7x8x512xf32, 1>
  %weight_buffer = memref.get_global @W_spad : memref<1x1x512x512xf32, 1>
  %output_buffer = memref.get_global @Y_spad : memref<1x512x7x8xf32, 1>
  %v0 = arith.constant dense<0.0> : vector<224xf32>
  %c0 = arith.constant 0 : index%t_const0 = arith.constant 0 : index
  %t_const1 = arith.constant 1 : index
  %t_const2 = arith.constant 3 : index
  %t_const3 = arith.constant 2 : index
  %t_alloc0 = memref.alloc() : memref<1xi32> // 0
  %t_alloc1 = memref.alloc() : memref<1xi32> // 1
  %t_alloc2 = memref.alloc() : memref<1xi32> // 2
  affine.for %tile_n = 0 to 512 step 512 {
    affine.for %o_h = 0 to 7 step 7 {
      affine.for %tile_m = 0 to 7 step 8 {
        // Initialize output
        affine.vector_store %v0, %output_buffer[%c0, %c0, %c0, %c0] : memref<1x512x7x8xf32, 1>, vector<224xf32>
        affine.for %k_h = 0 to 3 step 1 {
          affine.for %k_w = 0 to 3 step 1 {
            affine.for %tile_k = 0 to 512 step 512 {
              %index_i_h = affine.apply #map_I_H(%o_h, %k_h)
              %index_i_w = affine.apply #map_I_W(%tile_m, %k_w)
              // Load input & weight matrix
              %apply0 = affine.apply #t_map1(%c0, %index_i_h, %index_i_w, %tile_k)
              memref.dma_start %X[%apply0], %input_buffer[%t_const0, %t_const0, %t_const0, %t_const0], %t_const3, %t_alloc1[%t_const0], %t_const2, %t_const1 : memref<41472xf32>, memref<1x7x8x512xf32, 1>, memref<1xi32> {dram_stride = [41472, 4608, 512, 1], sram_stride = [28672, 4096, 1, 8], padding = 0, subtile_size = [1, 1, 8, 512], async = 1 : i64}
              %apply1 = affine.apply #t_map2(%k_h, %k_w, %tile_k, %tile_n)
              memref.dma_start %W[%apply1], %weight_buffer[%t_const0, %t_const0, %t_const0, %t_const0], %t_const3, %t_alloc2[%t_const0], %t_const2, %t_const1 : memref<2359296xf32>, memref<1x1x512x512xf32, 1>, memref<1xi32> {dram_stride = [786432, 262144, 512, 1], sram_stride = [262144, 262144, 1, 512], padding = 0, subtile_size = [1, 1, 512, 128], async = 1 : i64}
              // Compute body part
              affine.for %tile_k_h = 0 to 1 { // loop order should be fixed for timing simulation. Do not change this order.
                affine.for %tile_k_w = 0 to 1 {
                  %offset_w = affine.apply #offset_w_map(%tile_k_h, %tile_k_w)
                  %W_buffer = memref.reinterpret_cast %weight_buffer to offset: [%offset_w], sizes: [512, 512], strides: [512, 1] : memref<1x1x512x512xf32, 1> to memref<512x512xf32, strided<[512, 1], offset: ?>, 1>
                  affine.for %tile_o_h = 0 to 7 {
                    affine.for %tile_o_w = 0 to 1 { // TILE_O_W
                      %tile_i_h = affine.apply #map_I_H(%tile_o_h, %tile_k_h)
                      %offset_x = affine.apply #offset_x_map(%tile_i_h, %tile_k_w)
                      %offset_y = affine.apply #offset_y_map(%tile_o_h, %tile_o_w)
                      %X_buffer = memref.reinterpret_cast %input_buffer to offset: [%offset_x], sizes: [8, 512], strides: [512, 1] : memref<1x7x8x512xf32, 1> to memref<8x512xf32, strided<[512, 1], offset: ?>, 1>
                      %Y_buffer = memref.reinterpret_cast %output_buffer to offset: [%offset_y], sizes: [8, 512], strides: [512, 1] : memref<1x512x7x8xf32, 1> to memref<8x512xf32, strided<[512, 1], offset: ?>, 1>
                      linalg.matmul ins(%X_buffer, %W_buffer : memref<8x512xf32, strided<[512, 1], offset: ?>, 1>, memref<512x512xf32, strided<[512, 1], offset: ?>, 1>)
                            outs(%Y_buffer : memref<8x512xf32, strided<[512, 1], offset: ?>, 1>)
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
        memref.dma_start %output_buffer[%t_const0, %t_const0, %t_const0, %t_const0], %Y[%epilogue_apply0], %t_const2, %t_alloc0[%t_const0], %t_const1, %t_const1 : memref<1x512x7x8xf32, 1>, memref<25088xf32>, memref<1xi32> {dram_stride = [0, 49, 7, 1], sram_stride = [28672, 8, 4096, 1], padding = 0}
      } { outer_loop=true, subtile_loop="m" }
    } { outer_loop=true }
  } { outer_loop=true, subtile_loop="n" }
  return
}
