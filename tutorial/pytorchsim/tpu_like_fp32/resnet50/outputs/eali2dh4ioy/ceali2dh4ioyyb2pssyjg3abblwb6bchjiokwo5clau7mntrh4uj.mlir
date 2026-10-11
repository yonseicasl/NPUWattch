
// Single Batch Conv2D kernel
// BATCH = 1
// I_C = 64
// I_H = 56
// I_W = 56
// O_C = 64
// K_H = 3
// K_W = 3
// O_H = 56
// O_W = 56
// TILE_M = 56
// TILE_N = 64
// TILE_K = 64
// TILE_I_H=30,
// TILE_I_W=56,
// TILE_O_H=28,
// TILE_O_W=56,
// TILE_K_H=3,
// TILE_K_W=1,
// SUB_TILE_M=56,
// SUB_TILE_N=64,
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
#offset_w_map = affine_map<(d0, d1) -> (d0 * 64 + d1 * 64)>
#offset_x_map = affine_map<(d0, d1) -> (d0 * 56 + d1)>
#offset_y_map = affine_map<(d0, d1) -> (d0 * 56 + d1 * 56)>
memref.global @X_spad : memref<1x30x56x64xf32, 1>
memref.global @W_spad : memref<3x1x64x64xf32, 1>
memref.global @Y_spad : memref<1x64x28x56xf32, 1>
#t_map0 = affine_map<(d0, d1, d2, d3) -> (3136*d1 + 56*d2 + d3)>
#t_map1 = affine_map<(d0, d1, d2, d3) -> (215296*d0 + 3712*d1 + 64*d2 + d3)>
#t_map2 = affine_map<(d0, d1, d2, d3) -> (12288*d0 + 4096*d1 + 64*d2 + d3)>

func.func @kernel(%X: memref<215296xf32>, %W: memref<36864xf32>, %Y: memref<200704xf32>) {
  %input_buffer = memref.get_global @X_spad : memref<1x30x56x64xf32, 1>
  %weight_buffer = memref.get_global @W_spad : memref<3x1x64x64xf32, 1>
  %output_buffer = memref.get_global @Y_spad : memref<1x64x28x56xf32, 1>
  %v0 = arith.constant dense<0.0> : vector<1568xf32>
  %c0 = arith.constant 0 : index%t_const0 = arith.constant 0 : index
  %t_const1 = arith.constant 1 : index
  %t_const2 = arith.constant 3 : index
  %t_const3 = arith.constant 2 : index
  %t_alloc0 = memref.alloc() : memref<1xi32> // 0
  %t_alloc1 = memref.alloc() : memref<1xi32> // 1
  %t_alloc2 = memref.alloc() : memref<1xi32> // 2
  affine.for %tile_n = 0 to 64 step 64 {
    affine.for %o_h = 0 to 56 step 28 {
      affine.for %tile_m = 0 to 56 step 56 {
        // Initialize output
        affine.vector_store %v0, %output_buffer[%c0, %c0, %c0, %c0] : memref<1x64x28x56xf32, 1>, vector<1568xf32>
        affine.for %k_h = 0 to 3 step 3 {
          affine.for %k_w = 0 to 3 step 1 {
            affine.for %tile_k = 0 to 64 step 64 {
              %index_i_h = affine.apply #map_I_H(%o_h, %k_h)
              %index_i_w = affine.apply #map_I_W(%tile_m, %k_w)
              // Load input & weight matrix
              %apply0 = affine.apply #t_map1(%c0, %index_i_h, %index_i_w, %tile_k)
              memref.dma_start %X[%apply0], %input_buffer[%t_const0, %t_const0, %t_const0, %t_const0], %t_const3, %t_alloc1[%t_const0], %t_const2, %t_const1 : memref<215296xf32>, memref<1x30x56x64xf32, 1>, memref<1xi32> {dram_stride = [215296, 3712, 64, 1], sram_stride = [107520, 3584, 1, 56], padding = 0, subtile_size = [1, 1, 56, 64], async = 1 : i64}
              %apply1 = affine.apply #t_map2(%k_h, %k_w, %tile_k, %tile_n)
              memref.dma_start %W[%apply1], %weight_buffer[%t_const0, %t_const0, %t_const0, %t_const0], %t_const3, %t_alloc2[%t_const0], %t_const2, %t_const1 : memref<36864xf32>, memref<3x1x64x64xf32, 1>, memref<1xi32> {dram_stride = [12288, 4096, 64, 1], sram_stride = [4096, 4096, 1, 64], padding = 0, subtile_size = [1, 1, 64, 64], async = 1 : i64}
              // Compute body part
              affine.for %tile_k_h = 0 to 3 { // loop order should be fixed for timing simulation. Do not change this order.
                affine.for %tile_k_w = 0 to 1 {
                  %offset_w = affine.apply #offset_w_map(%tile_k_h, %tile_k_w)
                  %W_buffer = memref.reinterpret_cast %weight_buffer to offset: [%offset_w], sizes: [64, 64], strides: [64, 1] : memref<3x1x64x64xf32, 1> to memref<64x64xf32, strided<[64, 1], offset: ?>, 1>
                  affine.for %tile_o_h = 0 to 28 {
                    affine.for %tile_o_w = 0 to 1 { // TILE_O_W
                      %tile_i_h = affine.apply #map_I_H(%tile_o_h, %tile_k_h)
                      %offset_x = affine.apply #offset_x_map(%tile_i_h, %tile_k_w)
                      %offset_y = affine.apply #offset_y_map(%tile_o_h, %tile_o_w)
                      %X_buffer = memref.reinterpret_cast %input_buffer to offset: [%offset_x], sizes: [56, 64], strides: [64, 1] : memref<1x30x56x64xf32, 1> to memref<56x64xf32, strided<[64, 1], offset: ?>, 1>
                      %Y_buffer = memref.reinterpret_cast %output_buffer to offset: [%offset_y], sizes: [56, 64], strides: [64, 1] : memref<1x64x28x56xf32, 1> to memref<56x64xf32, strided<[64, 1], offset: ?>, 1>
                      linalg.matmul ins(%X_buffer, %W_buffer : memref<56x64xf32, strided<[64, 1], offset: ?>, 1>, memref<64x64xf32, strided<[64, 1], offset: ?>, 1>)
                            outs(%Y_buffer : memref<56x64xf32, strided<[64, 1], offset: ?>, 1>)
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
        memref.dma_start %output_buffer[%t_const0, %t_const0, %t_const0, %t_const0], %Y[%epilogue_apply0], %t_const2, %t_alloc0[%t_const0], %t_const1, %t_const1 : memref<1x64x28x56xf32, 1>, memref<200704xf32>, memref<1xi32> {dram_stride = [0, 3136, 56, 1], sram_stride = [100352, 56, 3584, 1], padding = 0}
      } { outer_loop=true, subtile_loop="m" }
    } { outer_loop=true }
  } { outer_loop=true, subtile_loop="n" }
  return
}
