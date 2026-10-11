
// BMM kernel
// BATCH = 6
// M = 1
// N = 2048
// K = 1408
// TILE_M = 8
// TILE_N = 2048
// TILE_K = 128
// SUB_TILE_M = 8
// SUB_TILE_N = 2048
memref.global @X_spad : memref<1x8x128xf32, 1>
memref.global @W_spad : memref<1x128x2048xf32, 1>
memref.global @Y_spad : memref<1x8x2048xf32, 1>
#t_map0 = affine_map<(d0, d1, d2) -> (2048*d0 + 2048*d1 + d2)>
#t_map1 = affine_map<(d0, d1, d2) -> (1408*d0 + 1408*d1 + d2)>
#t_map2 = affine_map<(d0, d1, d2) -> (2883584*d0 + 2048*d1 + d2)>

func.func @kernel(%X: memref<8448xf32>, %W: memref<17301504xf32>, %Y: memref<12288xf32>) {
  %X_buffer = memref.get_global @X_spad : memref<1x8x128xf32, 1>
  %W_buffer = memref.get_global @W_spad : memref<1x128x2048xf32, 1>
  %Y_buffer = memref.get_global @Y_spad : memref<1x8x2048xf32, 1>

  %v0 = arith.constant dense<0.0> : vector<128xf32>

  %c0 = arith.constant 0 : index
  %t_const0 = arith.constant 0 : index
  %t_const1 = arith.constant 2 : index
  %t_const2 = arith.constant 1 : index
  %t_const3 = arith.constant 3 : index
  %t_alloc0 = memref.alloc() : memref<1xi32> // 0
  %t_alloc1 = memref.alloc() : memref<1xi32> // 1
  %t_alloc2 = memref.alloc() : memref<1xi32> // 2
  affine.for %index0 = 0 to 6 {
    affine.for %index1 = 0 to 1 step 8 {
      affine.for %index2 = 0 to 2048 step 2048 {
        %X_buffer2D = memref.reinterpret_cast %X_buffer to offset: [0], sizes: [8, 128], strides: [128, 1] : memref<1x8x128xf32, 1> to memref<8x128xf32, 1>
        %W_buffer2D = memref.reinterpret_cast %W_buffer to offset: [0], sizes: [128, 2048], strides: [2048, 1] : memref<1x128x2048xf32, 1> to memref<128x2048xf32, 1>
        %Y_buffer2D = memref.reinterpret_cast %Y_buffer to offset: [0], sizes: [8, 2048], strides: [2048, 1] : memref<1x8x2048xf32, 1> to memref<8x2048xf32, 1>
        affine.vector_store %v0, %Y_buffer[0, 0, 0] : memref<1x8x2048xf32, 1>, vector<128xf32>


        affine.for %index3 = 0 to 1408 step 128 {
          %apply0 = affine.apply #t_map1(%index0, %index1, %index3)
          memref.dma_start %X[%apply0], %X_buffer[%t_const0, %t_const0, %t_const0], %t_const1, %t_alloc1[%t_const0], %t_const1, %t_const2 : memref<8448xf32>, memref<1x8x128xf32, 1>, memref<1xi32> {dram_stride = [1408, 1408, 1], sram_stride = [0, 1, 8], padding = 0, subtile_size = [1, 8, 128], async = 1 : i64}
          %apply1 = affine.apply #t_map2(%index0, %index3, %index2)
          memref.dma_start %W[%apply1], %W_buffer[%t_const0, %t_const0, %t_const0], %t_const1, %t_alloc2[%t_const0], %t_const1, %t_const2 : memref<17301504xf32>, memref<1x128x2048xf32, 1>, memref<1xi32> {dram_stride = [2883584, 2048, 1], sram_stride = [0, 1, 128], padding = 0, subtile_size = [1, 128, 2048], async = 1 : i64}
          linalg.matmul ins(%X_buffer2D, %W_buffer2D : memref<8x128xf32, 1>, memref<128x2048xf32, 1>)
                  outs(%Y_buffer2D : memref<8x2048xf32, 1>)
        } { accumulation_loop=true, subtile_loop="k" }
        affine.for %compute_idx = 0 to 1 step 1
        {
        } {inner_loop=false}
        %epilogue_apply0 = affine.apply #t_map0(%index0, %index1, %index2)
        memref.dma_start %Y_buffer[%t_const0, %t_const0, %t_const0], %Y[%epilogue_apply0], %t_const3, %t_alloc0[%t_const0], %t_const1, %t_const2 : memref<1x8x2048xf32, 1>, memref<12288xf32>, memref<1xi32> {dram_stride = [2048, 2048, 1], sram_stride = [0, 1, 8], padding = 0}
      } { outer_loop=true, subtile_loop="n" }
    } { outer_loop=true, subtile_loop="m" }
  } { outer_loop=true }
  return
}
