
// GEMM   kernel
// M = 1024
// N = 1024
// K = 1024
// TILE_M = 1024
// TILE_N = 1024
// TILE_K = 256
// SUB_TILE_M = 128
// SUB_TILE_N = 1024
memref.global @X_spad : memref<1024x256xf32, 1>
memref.global @W_spad : memref<256x1024xf32, 1>
memref.global @Y_spad : memref<1024x1024xf32, 1>
#t_map0 = affine_map<(d0, d1) -> (1024*d0 + d1)>

func.func @kernel(%X: memref<1048576xf32>, %W: memref<1048576xf32>, %Y: memref<1048576xf32>) {
  %X_buffer = memref.get_global @X_spad : memref<1024x256xf32, 1>
  %W_buffer = memref.get_global @W_spad : memref<256x1024xf32, 1>
  %Y_buffer = memref.get_global @Y_spad : memref<1024x1024xf32, 1>

  %v0 = arith.constant dense<0.0> : vector<8192xf32>
  %t_const0 = arith.constant 0 : index
  %t_const1 = arith.constant 1 : index
  %t_const2 = arith.constant 3 : index
  %t_const3 = arith.constant 2 : index
  %t_alloc0 = memref.alloc() : memref<1xi32> // 0
  %t_alloc1 = memref.alloc() : memref<1xi32> // 1
  %t_alloc2 = memref.alloc() : memref<1xi32> // 2
  affine.for %index0 = 0 to 1024 step 1024 {
    affine.for %index1 = 0 to 1024 step 1024 {
      affine.vector_store %v0, %Y_buffer[0, 0] : memref<1024x1024xf32, 1>, vector<8192xf32>
      affine.for %index2 = 0 to 1024 step 256 {
        %apply0 = affine.apply #t_map0(%index0, %index2)
        memref.dma_start %X[%apply0], %X_buffer[%t_const0, %t_const0], %t_const3, %t_alloc1[%t_const0], %t_const1, %t_const1 : memref<1048576xf32>, memref<1024x256xf32, 1>, memref<1xi32> {dram_stride = [1024, 1], sram_stride = [1, 1024], padding = 0, subtile_size = [128, 256], async = 1 : i64}
        %apply1 = affine.apply #t_map0(%index2, %index1)
        memref.dma_start %W[%apply1], %W_buffer[%t_const0, %t_const0], %t_const3, %t_alloc2[%t_const0], %t_const1, %t_const1 : memref<1048576xf32>, memref<256x1024xf32, 1>, memref<1xi32> {dram_stride = [1024, 1], sram_stride = [1, 256], padding = 0, subtile_size = [256, 1024], async = 1 : i64}
        linalg.matmul ins(%X_buffer, %W_buffer : memref<1024x256xf32, 1>, memref<256x1024xf32, 1>)
                outs(%Y_buffer : memref<1024x1024xf32, 1>)
      } { accumulation_loop=true, subtile_loop="k" }
      affine.for %compute_idx = 0 to 1 step 1
      {
      } {inner_loop=false}
      %epilogue_apply0 = affine.apply #t_map0(%index0, %index1)
      memref.dma_start %Y_buffer[%t_const0, %t_const0], %Y[%epilogue_apply0], %t_const2, %t_alloc0[%t_const0], %t_const1, %t_const1 : memref<1024x1024xf32, 1>, memref<1048576xf32>, memref<1xi32> {dram_stride = [1024, 1], sram_stride = [1, 1024], padding = 0}
    } { outer_loop=true, subtile_loop="n"  }
  } { outer_loop=true, subtile_loop="m" }
  return
}
